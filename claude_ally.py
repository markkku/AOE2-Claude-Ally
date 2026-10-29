#!/usr/bin/env python3
"""Claude Ally - Claude as your teammate ("general") in Age of Empires II: Definitive Edition.

    python claude_ally.py [--lang Estonian] [--model sonnet] [--interval 45]

Data flow:
  map XS (claude_bridge.xs)  -> <map>.xsdat         game state, read here
  replay file *.aoe2record   -> your chat messages, read here
  `claude -p` (JSON schema)  -> a decision
  claude_cmd.xsdat           -> carried out by the AI (claude_ai.xs + ClaudeAI.per);
                                the map XS shows Claude's message in chat
"""

import argparse
import json
import queue
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

from aoe2common import CMD_NAME, MAGIC, Reader, find_profile_dirs, find_user_base, write_atomic

STATE_VERSION = 1   # state file written by claude_bridge.xs
CMD_VERSION = 2     # command file read by claude_bridge.xs and claude_ai.xs
STATE_MAX_AGE = 30  # seconds; older state files (from previous games) are ignored
ROOT = Path(__file__).resolve().parent

# value = number sent to the game; order/numbers MUST match claude_ai.xs and ClaudeAI.per
UNITS = {"militia": 1, "spear": 2, "archer": 3, "skirm": 4, "knight": 5,
         "cav_archer": 6, "siege": 7, "monk": 8}
MODES = {"defend": 0, "attack": 1, "help": 2}
# order MUST match aiBuildingId() in claude_ai.xs; value = key in the state file
BUILDINGS = {"barracks": "b_barracks", "archery_range": "b_range", "stable": "b_stable",
             "siege_workshop": "b_workshop", "blacksmith": "b_blacksmith", "market": "b_market",
             "monastery": "b_monastery", "university": "b_university", "castle": "b_castle",
             "town_center": "b_tc", "tower": "b_tower", "dock": "b_dock"}
AGES = ["Dark Age", "Feudal Age", "Castle Age", "Imperial Age"]
COLORS = {1: "blue", 2: "red", 3: "green", 4: "yellow", 5: "cyan", 6: "purple", 7: "grey", 8: "orange"}
READY_RE = re.compile(r"ClaudeAI ready, player (\d)")

SCHEMA = {
    "type": "object",
    "properties": {
        "unit1": {"type": "string", "enum": list(UNITS)},
        "unit2": {"type": "string", "enum": list(UNITS)},
        "mode": {"type": "string", "enum": list(MODES)},
        "target_player": {"type": "integer", "minimum": 0, "maximum": 8},
        "age_up": {"type": "boolean"},
        "villagers": {"type": "integer", "minimum": 15, "maximum": 130},
        "buildings": {
            "type": "object",
            "properties": {b: {"type": "integer", "minimum": 0, "maximum": 10} for b in BUILDINGS},
            "required": list(BUILDINGS),
            "additionalProperties": False,
        },
        "message": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["unit1", "unit2", "mode", "target_player", "age_up", "villagers", "buildings", "message", "reasoning"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are the human player's teammate in Age of Empires II: Definitive Edition, commanding one computer player (the "general").
Your AI script handles the economy by itself (villagers, houses, farms, mill, lumber and mining camps, eco upgrades) and trains the army.
You make the strategic decisions:
- unit1 / unit2: main and supporting unit. The AI trains both, unit1 first.
  militia=swordsmen, spear=spearmen (anti-cavalry), archer=archers, skirm=skirmishers (anti-archer),
  knight=scout cavalry in Feudal / knights from Castle Age, cav_archer=cavalry archers (Castle Age),
  siege=rams and mangonels (Castle Age, against buildings), monk=monks (Castle Age).
  Counter the enemy's visible units and respect the current age.
- mode: defend = army stays home; attack = the whole army attacks player target_player;
  help = the army goes to ally target_player's town center.
  Do not attack with a tiny army (below ~15 soldiers) unless the enemy is weak. If an ally has "threat" > 0, consider helping.
- age_up: whether to save resources for the next age (military production pauses, except while attacking or under attack).
- villagers: target number of villagers (usually 60-100).
- buildings: TOTAL target count per building type (not how many to add). The AI builds until the count is met;
  lowering a number never deletes buildings.
  Types: barracks, archery_range, stable, siege_workshop, blacksmith, market, monastery, university, castle, town_center, tower, dock.
  A unit cannot be trained without its building (militia/spear -> barracks, archer/skirm/cav_archer -> archery_range,
  knight -> stable, siege -> siege_workshop, monk -> monastery).
  Age requirements: Feudal needs barracks (mill and lumber camp come automatically); Castle needs 2 Feudal buildings
  (blacksmith, market, archery_range, stable); Imperial needs a castle OR 2 Castle buildings (university, monastery, siege_workshop).
  Buildings not yet available in the current age are built automatically once they become available.
  Buildings cost resources - do not order more production buildings than the economy can keep busy (about 1 per 8-10 villagers).
- message: a short chat message to the human (max 120 characters). {language}
  If the human wrote to you, answer them directly. If nothing important changed and the human said nothing,
  leave message empty "" (do not spam the chat).
- reasoning: 1-2 sentences on why (goes to the log only).
You only see enemy units that are currently visible (vis_*). Requests from the human ("help me", "attack blue") have high priority.
Player colors: 1 blue, 2 red, 3 green, 4 yellow, 5 cyan, 6 purple, 7 grey, 8 orange."""


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --- Game state ------------------------------------------------------------------

def parse_player(s):
    out = {}
    for part in s.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if v in ("true", "false"):
            out[k] = v == "true"
        else:
            try:
                out[k] = int(v)
            except ValueError:
                out[k] = v
    return out


def parse_state(data):
    r = Reader(data)
    if r.int() != MAGIC or r.int() != STATE_VERSION:
        return None
    st = {"counter": r.int(), "time": r.int(), "ack_seq": r.int(), "claude": r.int(), "local": r.int(), "players": {}}
    for p in range(1, 9):
        raw = r.string().decode("utf-8", "replace")
        if raw:
            st["players"][p] = parse_player(raw)
    return st


def fmt_time(sec):
    return f"{sec // 60}:{sec % 60:02d}"


def age_name(d):
    a = d.get("age", 0)
    return AGES[a] if isinstance(a, int) and 0 <= a < 4 else a


def describe_state(st, claude, human):
    lines = [f"Game time {fmt_time(st['time'])}. You command player {claude}; the human (your ally) is player {human}."]
    lines.append("TEAM:")
    for p, d in sorted(st["players"].items()):
        if not d.get("team"):
            continue
        who = "YOU" if p == claude else ("human" if p == human else "ally")
        lines.append(
            f"  P{p} {COLORS.get(p, '')} ({who}, {d.get('civ')}, {age_name(d)}): food {d.get('food')}, wood {d.get('wood')}, "
            f"gold {d.get('gold')}, stone {d.get('stone')}; pop {d.get('pop')}/{d.get('popcap')}, villagers {d.get('vil')}; "
            f"army: infantry {d.get('inf')}, archers {d.get('arch')}, cavalry {d.get('cav')}, cav archers {d.get('cavarch')}, "
            f"siege {d.get('siege')}, monks {d.get('monk')}, ships {d.get('ship')}; "
            f"enemy soldiers near its town centers (threat): {d.get('threat')}; buildings: "
            + ", ".join(f"{b} {d.get(k, 0)}" for b, k in BUILDINGS.items())
            + f", houses {d.get('b_house')}, farms {d.get('b_farm')}")
    lines.append("ENEMIES (currently visible only):")
    for p, d in sorted(st["players"].items()):
        if d.get("team"):
            continue
        lines.append(
            f"  P{p} {COLORS.get(p, '')} ({d.get('civ')}, {age_name(d)}): visible infantry {d.get('vis_inf')}, "
            f"archers {d.get('vis_arch')}, cavalry {d.get('vis_cav')}, cav archers {d.get('vis_cavarch')}, "
            f"siege {d.get('vis_siege')}, monks {d.get('vis_monk')}, ships {d.get('vis_ship')}, villagers {d.get('vis_vil')}, "
            f"town centers {d.get('vis_tc')}, castles {d.get('vis_castle')}")
    return "\n".join(lines)


def find_state_file(base):
    """The most recently written valid state file. Its name is the map name (e.g. Claude_Arena.xsdat),
    so files are recognised by content."""
    best, best_mtime = None, 0.0
    now = time.time()
    for prof in find_profile_dirs(base):
        for p in (prof / "profile").glob("*.xsdat"):
            if p.name == CMD_NAME:
                continue
            try:
                mtime = p.stat().st_mtime
                if now - mtime > STATE_MAX_AGE or mtime <= best_mtime:
                    continue
                if parse_state(p.read_bytes()):
                    best, best_mtime = p, mtime
            except (OSError, struct.error):
                continue
    return best


# --- Chat from the replay file ------------------------------------------------------
# A chat operation in the recorded game: int32 4, int32 -1, uint32 length, JSON {"player":N,"message":"…",…}

CHAT_RE = re.compile(rb"\x04\x00\x00\x00\xff\xff\xff\xff(....)(?=\{\"player\")", re.S)


class ChatTail:
    """Reads new chat messages from the replay file (.aoe2record) that the game writes while playing."""

    def __init__(self, savegame_dir):
        self.dir = savegame_dir
        self.file = None
        self.offset = 0
        self.seen = set()

    def _newest(self):
        files = list(self.dir.glob("*.aoe2record")) if self.dir.exists() else []
        return max(files, key=lambda p: p.stat().st_mtime) if files else None

    def read_all(self):
        """Read the current replay from the start (marks everything as seen)."""
        self.file, self.offset, self.seen = self._newest(), 0, set()
        return self.poll()

    def poll(self):
        newest = self._newest()
        if newest is None:
            return []
        if newest != self.file:
            self.file, self.offset, self.seen = newest, 0, set()
        size = newest.stat().st_size
        if size < self.offset:
            self.offset, self.seen = 0, set()
        if size == self.offset:
            return []
        start = max(0, self.offset - 4096)
        with open(newest, "rb") as f:
            f.seek(start)
            buf = f.read(size - start)
        out = []
        for m in CHAT_RE.finditer(buf):
            length = struct.unpack("<I", m.group(1))[0]
            body_start = m.end()
            if body_start + length > len(buf) or length > 4096:
                continue
            pos = start + m.start()
            if pos in self.seen:
                continue
            self.seen.add(pos)
            try:
                out.append(json.loads(buf[body_start:body_start + length].decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        self.offset = size
        return out


# --- Claude ---------------------------------------------------------------------------

def find_claude_cli():
    exe = shutil.which("claude")
    if not exe:
        sys.exit("The 'claude' command (Claude Code CLI) was not found on PATH.\n"
                 "Install it from https://claude.com/claude-code and log in once by running 'claude'.")
    return exe


def ask_claude(exe, system_prompt, prompt, model, timeout):
    cmd = [exe, "-p", "--safe-mode", "--tools", "", "--no-session-persistence",
           "--model", model, "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--system-prompt", system_prompt, prompt]
    t0 = time.monotonic()
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         timeout=timeout, cwd=tempfile.gettempdir())
    dt = time.monotonic() - t0
    if res.returncode != 0:
        raise RuntimeError(f"claude exited with code {res.returncode}: {(res.stderr or res.stdout).strip()[:300]}")
    out = json.loads(res.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude error: {out.get('result')}")
    decision = out.get("structured_output")
    if not isinstance(decision, dict):
        decision = json.loads(out.get("result", ""))
    return decision, dt


def clean_message(msg, ascii_only):
    msg = msg.replace("%", " percent").replace("\n", " ").strip()
    if ascii_only:
        msg = unicodedata.normalize("NFKD", msg).encode("ascii", "ignore").decode()
    return msg[:160]


def encode_cmd(seq, claude, d, ascii_only):
    msg = clean_message(d.get("message", ""), ascii_only).encode("utf-8")
    ints = [MAGIC, CMD_VERSION, seq, claude, UNITS[d["unit1"]], UNITS[d["unit2"]], MODES[d["mode"]],
            d["target_player"], 1 if d["age_up"] else 0, d["villagers"]]
    ints += [int(d["buildings"].get(b, 0)) for b in BUILDINGS]
    return struct.pack(f"<{len(ints)}i", *ints) + struct.pack("<I", len(msg)) + msg


def validate(d, st, claude):
    """Fix obvious mistakes (e.g. attacking an ally)."""
    players = st["players"]
    t = d.get("target_player", 0)
    if d["mode"] == "attack" and (t not in players or players[t].get("team")):
        enemies = [p for p, x in players.items() if not x.get("team")]
        d["target_player"] = enemies[0] if enemies else 0
        if not enemies:
            d["mode"] = "defend"
    if d["mode"] == "help" and (t not in players or not players[t].get("team") or t == claude):
        d["mode"], d["target_player"] = "defend", 0
    return d


# --- Main loop ---------------------------------------------------------------------

class Ally:
    def __init__(self, args):
        self.args = args
        self.exe = find_claude_cli()
        self.base = find_user_base(args.user_dir)
        if not self.base or not self.base.exists():
            sys.exit("Could not find the 'Age of Empires 2 DE' user folder. Run install.py first, or pass --user-dir.")
        if args.lang == "auto":
            language = "Write it in the same language the human uses in chat; if unsure, use English."
        else:
            language = f"Write it in {args.lang}."
        self.system_prompt = SYSTEM_PROMPT.replace("{language}", language)
        self.claude = args.claude_player or 0  # 0 = not detected yet
        self.state = None
        self.state_path = None
        self.state_mtime = 0
        self.seq = int(time.time()) % 1_000_000
        self.last = None
        self.history = []
        self.pending_chat = []
        self.trigger = queue.Queue()
        self.busy = threading.Lock()
        self.last_ask = 0.0
        self.last_threat = {}
        self.chat = None
        self.last_scan = 0.0
        log_dir = ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        self.logfile = open(log_dir / time.strftime("game-%Y%m%d-%H%M%S.jsonl"), "a", encoding="utf-8")

    def write_log(self, **kw):
        kw["ts"] = time.time()
        self.logfile.write(json.dumps(kw, ensure_ascii=False) + "\n")
        self.logfile.flush()

    def claude_player(self):
        return self.claude or 2

    def human_player(self):
        return self.args.human or (self.state or {}).get("local") or 1

    def reset_game(self):
        self.state, self.state_mtime = None, 0
        self.last, self.history, self.last_threat = None, [], {}
        if not self.args.claude_player:
            self.claude = 0

    # game state
    def poll_state(self):
        now = time.monotonic()
        if now - self.last_scan > 2:
            self.last_scan = now
            path = find_state_file(self.base)
            if path is not None and path != self.state_path:
                self.state_path = path
                self.reset_game()
                log(f"State file: {path} (map {path.stem})")
                self.chat = ChatTail(path.parent.parent / "savegame")
                self.handle_chat(self.chat.read_all(), old=True)
        if self.state_path is None:
            return
        try:
            mtime = self.state_path.stat().st_mtime_ns
        except FileNotFoundError:
            return
        if mtime == self.state_mtime:
            return
        self.state_mtime = mtime
        try:
            st = parse_state(self.state_path.read_bytes())
        except (struct.error, OSError):
            return
        if not st:
            return
        new_game = self.state is None or st["time"] < self.state["time"]
        if new_game and self.state is not None:
            self.reset_game()
            if self.chat:
                self.handle_chat(self.chat.read_all(), old=True)
        self.state = st
        if new_game:
            log(f"Game found (time {fmt_time(st['time'])}), {len(st['players'])} players. "
                f"Human: player {self.human_player()}, ClaudeAI: player {self.claude_player()}"
                + ("" if self.claude else " (assumed; waiting for 'ClaudeAI ready')"))
            self.trigger.put("game start")
        self.check_threats(st)

    def check_threats(self, st):
        for p, d in st["players"].items():
            if not d.get("team"):
                continue
            threat = d.get("threat", 0) or 0
            before = self.last_threat.get(p, 0)
            self.last_threat[p] = threat
            if threat >= self.args.threat and before < self.args.threat:
                log(f"THREAT: {threat} enemy soldiers near player {p}'s town center")
                self.trigger.put(f"threat at P{p}")

    def handle_chat(self, messages, old=False):
        for m in messages:
            text = (m.get("message") or "").strip()
            ready = READY_RE.search(text)
            if ready and not self.args.claude_player:
                player = int(ready.group(1))
                if player != self.claude:
                    self.claude = player
                    log(f"ClaudeAI detected as player {player}.")
                    if not old:
                        self.trigger.put("ClaudeAI detected")
                continue
            if old or not self.state or not text or m.get("player") != self.human_player():
                continue
            log(f"You: {text}")
            self.pending_chat.append(text)
            self.trigger.put("chat")

    def poll_chat(self):
        if self.chat:
            self.handle_chat(self.chat.poll())

    def stdin_reader(self):
        for line in sys.stdin:
            text = line.strip()
            if text:
                self.pending_chat.append(text)
                self.trigger.put("terminal")

    # decisions
    def build_prompt(self, reason):
        parts = [describe_state(self.state, self.claude_player(), self.human_player())]
        if self.last:
            parts.append("YOUR CURRENT ORDERS: " + json.dumps({k: self.last[k] for k in
                         ("unit1", "unit2", "mode", "target_player", "age_up", "villagers", "buildings")}))
        if self.history:
            parts.append("RECENT CHAT:\n" + "\n".join(self.history[-8:]))
        if self.pending_chat:
            parts.append("THE HUMAN JUST WROTE TO YOU:\n" + "\n".join(f'"{t}"' for t in self.pending_chat))
        parts.append(f"Reason for asking: {reason}. Decide.")
        return "\n\n".join(parts)

    def decide(self, reason):
        if not self.state:
            return
        with self.busy:
            chat_now = list(self.pending_chat)
            prompt = self.build_prompt(reason)
            self.pending_chat.clear()
            self.last_ask = time.monotonic()
            claude = self.claude_player()
            try:
                d, dt = ask_claude(self.exe, self.system_prompt, prompt, self.args.model, self.args.timeout)
                d = validate(d, self.state, claude)
            except Exception as e:  # noqa: BLE001 - log and keep going
                log(f"Claude error: {e}")
                self.pending_chat[:0] = chat_now
                self.write_log(kind="error", reason=reason, error=str(e), prompt=prompt)
                return
            self.seq += 1
            write_atomic(self.state_path.parent / CMD_NAME, encode_cmd(self.seq, claude, d, self.args.ascii))
            self.last = d
            self.history += [f"human: {t}" for t in chat_now]
            if d.get("message"):
                self.history.append(f"you: {d['message']}")
            tgt = f" -> P{d['target_player']}" if d["mode"] != "defend" else ""
            log(f"Claude ({dt:.1f}s, {reason}): {d['unit1']} + {d['unit2']}, {d['mode']}{tgt}, "
                f"age up={'yes' if d['age_up'] else 'no'}, villagers={d['villagers']}")
            log("  buildings: " + ", ".join(f"{b} {n}" for b, n in d["buildings"].items() if n))
            if d.get("message"):
                log(f"  chat: {d['message']}")
            log(f"  why: {d.get('reasoning', '')}")
            self.write_log(kind="decision", reason=reason, latency=dt, seq=self.seq, decision=d,
                           game_time=self.state["time"], prompt=prompt)

    def decision_worker(self):
        while True:
            reasons = [self.trigger.get()]
            time.sleep(self.args.debounce)  # collect messages typed in quick succession
            while not self.trigger.empty():
                reasons.append(self.trigger.get())
            talk = [r for r in reasons if r in ("chat", "terminal")]
            self.decide("the human wrote" if talk else ", ".join(dict.fromkeys(reasons)))

    def run(self):
        log(f"Claude Ally started. Model {self.args.model}, decision every {self.args.interval:.0f}s, "
            f"language: {self.args.lang}. Type here or in the game chat to talk to Claude. Ctrl+C quits.")
        threading.Thread(target=self.decision_worker, daemon=True).start()
        threading.Thread(target=self.stdin_reader, daemon=True).start()
        last_wait_msg = 0.0
        while True:
            self.poll_state()
            self.poll_chat()
            now = time.monotonic()
            if self.state is None and now - last_wait_msg > 15:
                log("Waiting for a game... Skirmish > Map Style 'Custom' > a 'Claude_<map>' map, ally AI = ClaudeAI.")
                last_wait_msg = now
            if self.state and not self.busy.locked() and now - self.last_ask > self.args.interval:
                self.last_ask = now
                self.trigger.put("regular check")
            time.sleep(0.5)


def main():
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description="Claude as your teammate in Age of Empires II: DE")
    ap.add_argument("--lang", default="auto", help="language for Claude's chat messages, e.g. English, Estonian "
                                                   "(default: same as yours)")
    ap.add_argument("--model", default="sonnet", help="Claude model: sonnet, haiku or opus (default sonnet)")
    ap.add_argument("--interval", type=float, default=45.0, help="seconds between regular decisions (default 45)")
    ap.add_argument("--threat", type=int, default=3,
                    help="enemy soldiers near a teammate's town center that trigger an immediate decision (default 3)")
    ap.add_argument("--claude-player", type=int, default=0, help="ClaudeAI's player number (default: auto-detect)")
    ap.add_argument("--human", type=int, default=0, help="your player number (default: auto-detect)")
    ap.add_argument("--debounce", type=float, default=1.5, help="seconds to wait for more chat before asking")
    ap.add_argument("--timeout", type=float, default=90.0, help="timeout for one `claude -p` call")
    ap.add_argument("--ascii", action="store_true", help="strip accents from chat messages (if the game shows them wrong)")
    ap.add_argument("--user-dir", help="user folder (…/Games/Age of Empires 2 DE)")
    args = ap.parse_args()
    try:
        Ally(args).run()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
