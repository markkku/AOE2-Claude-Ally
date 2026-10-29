#!/usr/bin/env python3
"""Claude kui AoE II DE tiimikaaslane ("kindral").

Kaivitus: python3 general.py   (vt README.md)

Voog:
  kaardi XS (claude_bridge.xs) -> ClaudeGeneral.xsdat -> siit loetakse seis
  salvestusfail savegame/*.aoe2record -> siit loetakse inimese chat
  claude -p (struktureeritud JSON)    -> otsus
  claude_cmd.xsdat                    -> AI (claude_ai.xs + ClaudeAI.per) taidab, kaardi XS naitab sonumit chatis
"""

import argparse
import json
import queue
import re
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

from bridge_test import Reader, find_games_base, find_profile_dirs, write_atomic

MAGIC = 20261029
VERSION = 1       # seisufaili versioon
CMD_VERSION = 2   # kasufaili versioon
STATE_NAME = "ClaudeGeneral.xsdat"
CMD_NAME = "claude_cmd.xsdat"
PROJECT_DIR = Path(__file__).resolve().parent

UNITS = {"militia": 1, "spear": 2, "archer": 3, "skirm": 4, "knight": 5,
         "cav_archer": 6, "siege": 7, "monk": 8}
UNIT_ET = {"militia": "mõõgamehed", "spear": "odamehed", "archer": "vibukütid", "skirm": "skirmišerid",
           "knight": "rüütlid/skaudid", "cav_archer": "ratsavibukütid", "siege": "piiramismasinad", "monk": "mungad"}
MODES = {"defend": 0, "attack": 1, "help": 2}
# jarjekord PEAB klappima claude_ai.xs aiBuildingId()-ga; vaartus = seisu voti
BUILDINGS = {"barracks": "b_barracks", "archery_range": "b_range", "stable": "b_stable",
             "siege_workshop": "b_workshop", "blacksmith": "b_blacksmith", "market": "b_market",
             "monastery": "b_monastery", "university": "b_university", "castle": "b_castle",
             "town_center": "b_tc", "tower": "b_tower", "dock": "b_dock"}
BUILDING_ET = {"barracks": "kasarmud", "archery_range": "laskeväli", "stable": "tall",
               "siege_workshop": "piiramistöökoda", "blacksmith": "sepikoda", "market": "turg",
               "monastery": "klooster", "university": "ülikool", "castle": "loss",
               "town_center": "linnakeskus", "tower": "torn", "dock": "sadam"}
AGES = ["Pimeaeg", "Feodaalaeg", "Lossiaeg", "Keiserlik aeg"]

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

SYSTEM_PROMPT = """Sa oled Age of Empires II: Definitive Editioni mängus inimese tiimikaaslane ja juhid ühte arvutimängijat ("kindral").
Sinu AI-skript teeb ise majandust (külaelanikud, majad, farmid, laod) ja toodab sõjaväge. Sina teed strateegilised otsused:
- unit1 / unit2: põhiüksus ja toetav üksus. AI toodab mõlemat, unit1 eelisjärjekorras.
  militia=mõõgamehed, spear=odamehed (ratsaväe vastu), archer=vibukütid, skirm=skirmišerid (vibukütide vastu),
  knight=skaut/rüütel (feodaalajal skaut, lossiajast rüütel), cav_archer=ratsavibukütid (lossiaeg),
  siege=müürilõhkujad ja katapuldid (lossiaeg, hoonete vastu), monk=mungad (lossiaeg).
  Vali kontrad vastase nähtavate üksuste järgi ja arvesta ajastut (cav_archer, siege, monk alles lossiajast).
- mode: defend = armee püsib kodus; attack = kogu armee ründab mängijat target_player; help = armee läheb liitlase target_player linnakeskuse juurde appi.
  Ära ründa liiga väikese armeega (alla ~15 sõduri), kui just vastane pole nõrk. Kui liitlase juures on oht ("threat" > 0), kaalu appi minekut.
- age_up: kas koguda ressursse järgmise ajastu jaoks (sõjaväe tootmine on siis pausil, välja arvatud rünnaku või ohu ajal).
- villagers: külaelanike sihtarv (tavaliselt 60–100).
- buildings: iga hoonetüübi SIHTARV kokku (mitte juurde ehitatav arv). AI ehitab juurde, kuni arv on täis; arvu vähendamine hooneid ei lammuta.
  Tüübid: barracks, archery_range, stable, siege_workshop, blacksmith, market, monastery, university, castle, town_center, tower, dock.
  Majad, farmid, veski ning puidu- ja kaevanduslaod ehitab AI ise. Ilma vajaliku hooneta ei saa üksust toota
  (militia/spear → barracks, archer/skirm/cav_archer → archery_range, knight → stable, siege → siege_workshop, monk → monastery).
  Ajastu eeldused: feodaalajaks on vaja kasarmuid (veski ja puiduladu tulevad ise); lossiajaks 2 feodaalaja hoonet
  (blacksmith, market, archery_range, stable); keiserlikuks ajaks loss VÕI 2 lossiaja hoonet (university, monastery, siege_workshop).
  Hoone, mida praeguses ajastus veel ehitada ei saa, ehitatakse automaatselt siis, kui see võimalikuks muutub.
  Hooned maksavad ressursse – ära telli rohkem tootmishooneid, kui majandus jõuab käigus hoida (u 1 tootmishoone 8–10 külaelaniku kohta).
- message: lühike sõnum inimesele mängu chatti (eesti keeles, kuni 120 märki). Kui inimene kirjutas sulle, vasta talle otse.
  Kui midagi olulist pole muutunud ja inimene midagi ei küsinud, jäta message tühjaks "" (ära spämmi chatti).
- reasoning: 1–2 lauset, miks (läheb ainult logisse).
Sa näed vaenlastest ainult seda, mis on praegu nähtav (vis_*). Inimese palvetel (nt "tule appi", "ründa sinist") on kõrge prioriteet.
Mängijate numbrid: 1 = sinine, 2 = punane, 3 = roheline, 4 = kollane, 5 = tsüaan, 6 = lilla, 7 = hall, 8 = oranž."""

COLORS = {1: "sinine", 2: "punane", 3: "roheline", 4: "kollane", 5: "tsüaan", 6: "lilla", 7: "hall", 8: "oranž"}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --- Seis ------------------------------------------------------------------------

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
    if r.int() != MAGIC:
        return None
    version = r.int()
    if version != VERSION:
        return None
    st = {"counter": r.int(), "time": r.int(), "ack_seq": r.int(), "claude": r.int(), "local": r.int(), "players": {}}
    for p in range(1, 9):
        raw = r.string().decode("utf-8", "replace")
        if raw:
            st["players"][p] = parse_player(raw)
    return st


def fmt_time(sec):
    return f"{sec // 60}:{sec % 60:02d}"


def describe_state(st, human):
    claude = st["claude"]
    lines = [f"Mänguaeg {fmt_time(st['time'])}. Sina juhid mängijat {claude}; inimene (sinu liitlane) on mängija {human}."]
    team = {p: d for p, d in st["players"].items() if d.get("team")}
    enemies = {p: d for p, d in st["players"].items() if not d.get("team")}
    lines.append("MEESKOND:")
    for p, d in sorted(team.items()):
        who = "SINA" if p == claude else ("inimene" if p == human else "liitlane")
        age = AGES[d.get("age", 0)] if 0 <= d.get("age", 0) < 4 else d.get("age")
        lines.append(
            f"  P{p} {COLORS.get(p, '')} ({who}, {d.get('civ')}, {age}): toit {d.get('food')}, puit {d.get('wood')}, "
            f"kuld {d.get('gold')}, kivi {d.get('stone')}; pop {d.get('pop')}/{d.get('popcap')}, külaelanikke {d.get('vil')}; "
            f"armee: jalavägi {d.get('inf')}, vibukütid {d.get('arch')}, ratsavägi {d.get('cav')}, ratsavibukütid {d.get('cavarch')}, "
            f"piiramine {d.get('siege')}, mungad {d.get('monk')}, laevad {d.get('ship')}; linnakeskusi {d.get('tc')}, losse {d.get('castle')}; "
            f"vaenlase sõdureid linnakeskuse juures (threat): {d.get('threat')}; hooned: "
            + ", ".join(f"{b} {d.get(k, 0)}" for b, k in BUILDINGS.items()) + f", majad {d.get('b_house')}, farmid {d.get('b_farm')}")
    lines.append("VAENLASED (ainult praegu nähtav):")
    for p, d in sorted(enemies.items()):
        age = AGES[d.get("age", 0)] if 0 <= d.get("age", 0) < 4 else d.get("age")
        lines.append(
            f"  P{p} {COLORS.get(p, '')} ({d.get('civ')}, {age}): nähtavad jalavägi {d.get('vis_inf')}, vibukütid {d.get('vis_arch')}, "
            f"ratsavägi {d.get('vis_cav')}, ratsavibukütid {d.get('vis_cavarch')}, piiramine {d.get('vis_siege')}, "
            f"mungad {d.get('vis_monk')}, laevad {d.get('vis_ship')}, külaelanikud {d.get('vis_vil')}, "
            f"linnakeskused {d.get('vis_tc')}, lossid {d.get('vis_castle')}")
    return "\n".join(lines)


def find_state_file(base):
    for prof in find_profile_dirs(base):
        p = prof / "profile" / STATE_NAME
        if p.exists():
            return p
    return None


# --- Chat salvestusfailist -------------------------------------------------------

CHAT_RE = re.compile(rb"\x04\x00\x00\x00\xff\xff\xff\xff(....)(?=\{\"player\")", re.S)


class ChatTail:
    """Loeb jooksva mangu salvestusfailist (.aoe2record) uued chatisonumid."""

    def __init__(self, savegame_dir):
        self.dir = savegame_dir
        self.file = None
        self.offset = 0
        self.seen = set()

    def _newest(self):
        files = list(self.dir.glob("*.aoe2record")) if self.dir.exists() else []
        return max(files, key=lambda p: p.stat().st_mtime) if files else None

    def start_at_end(self):
        self.file = self._newest()
        self.offset = self.file.stat().st_size if self.file else 0

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

def ask_claude(prompt, model, timeout):
    cmd = ["claude", "-p", "--safe-mode", "--tools", "", "--no-session-persistence",
           "--model", model, "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--system-prompt", SYSTEM_PROMPT, prompt]
    t0 = time.monotonic()
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=tempfile.gettempdir())
    dt = time.monotonic() - t0
    if res.returncode != 0:
        raise RuntimeError(f"claude lopetas koodiga {res.returncode}: {res.stderr.strip()[:300]}")
    out = json.loads(res.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude viga: {out.get('result')}")
    decision = out.get("structured_output")
    if not isinstance(decision, dict):
        decision = json.loads(out.get("result", ""))
    return decision, dt


def clean_message(msg, ascii_only):
    msg = msg.replace("%", " protsenti").replace("\n", " ").strip()
    if ascii_only:
        msg = unicodedata.normalize("NFKD", msg).encode("ascii", "ignore").decode()
    return msg[:160]


def encode_cmd(seq, claude, d, ascii_only):
    msg = clean_message(d.get("message", ""), ascii_only).encode("utf-8")
    ints = [MAGIC, CMD_VERSION, seq, claude, UNITS[d["unit1"]], UNITS[d["unit2"]], MODES[d["mode"]],
            d["target_player"], 1 if d["age_up"] else 0, d["villagers"]]
    ints += [int(d["buildings"].get(b, 0)) for b in BUILDINGS]
    return struct.pack(f"<{len(ints)}i", *ints) + struct.pack("<I", len(msg)) + msg


def validate(d, st):
    """Parandab ilmselged vead (nt ryndab liitlast)."""
    players = st["players"]
    t = d.get("target_player", 0)
    if d["mode"] == "attack" and (t not in players or players[t].get("team")):
        enemies = [p for p, x in players.items() if not x.get("team")]
        d["target_player"] = enemies[0] if enemies else 0
        if not enemies:
            d["mode"] = "defend"
    if d["mode"] == "help" and (t not in players or not players[t].get("team") or t == st["claude"]):
        d["mode"], d["target_player"] = "defend", 0
    return d


# --- Peatsykkel ---------------------------------------------------------------------

class General:
    def __init__(self, args):
        self.args = args
        self.base = Path(args.base) if args.base else find_games_base()
        if not self.base:
            sys.exit("Mangu kasutajakausta ei leitud.")
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
        log_dir = PROJECT_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        self.logfile = open(log_dir / time.strftime("game-%Y%m%d-%H%M%S.jsonl"), "a", encoding="utf-8")

    def write_log(self, **kw):
        kw["ts"] = time.time()
        self.logfile.write(json.dumps(kw, ensure_ascii=False) + "\n")
        self.logfile.flush()

    # seis
    def poll_state(self):
        if self.state_path is None:
            self.state_path = find_state_file(self.base)
            if self.state_path is None:
                return
            log(f"Seisufail: {self.state_path}")
            savegame = self.state_path.parent.parent / "savegame"
            self.chat = ChatTail(savegame)
            self.chat.start_at_end()
            log(f"Chati jalgin: {savegame}")
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
        first = self.state is None or st["time"] < self.state["time"]
        self.state = st
        if first:
            log(f"Mang leitud (aeg {fmt_time(st['time'])}), mangijaid {len(st['players'])}.")
            if self.chat:
                self.chat.start_at_end()
            self.trigger.put("algus")
        self.check_threats(st)

    def check_threats(self, st):
        for p, d in st["players"].items():
            if not d.get("team"):
                continue
            threat = d.get("threat", 0) or 0
            before = self.last_threat.get(p, 0)
            self.last_threat[p] = threat
            if threat >= self.args.threat and before < self.args.threat:
                log(f"OHT: mangija {p} linnakeskuse juures {threat} vaenlase sodurit")
                self.trigger.put(f"oht P{p}")

    def poll_chat(self):
        if not self.chat or not self.state:
            return
        human = self.args.human or self.state["local"] or 1
        for m in self.chat.poll():
            if m.get("player") != human:
                continue
            text = (m.get("message") or "").strip()
            if not text:
                continue
            log(f"Sina: {text}")
            self.pending_chat.append(text)
            self.trigger.put("chat")

    def stdin_reader(self):
        for line in sys.stdin:
            text = line.strip()
            if text:
                self.pending_chat.append(text)
                self.trigger.put("terminal")

    # otsus
    def build_prompt(self, reason):
        st = self.state
        human = self.args.human or st["local"] or 1
        parts = [describe_state(st, human)]
        if self.last:
            parts.append("SINU PRAEGUNE KÄSK: " + json.dumps({k: self.last[k] for k in
                         ("unit1", "unit2", "mode", "target_player", "age_up", "villagers", "buildings")}, ensure_ascii=False))
        if self.history:
            parts.append("VIIMASED SÕNUMID CHATIS:\n" + "\n".join(self.history[-8:]))
        if self.pending_chat:
            parts.append("INIMENE KIRJUTAS SULLE NÜÜD:\n" + "\n".join(f'"{t}"' for t in self.pending_chat))
        parts.append(f"Põhjus, miks küsin: {reason}. Otsusta.")
        return "\n\n".join(parts)

    def decide(self, reason):
        if not self.state:
            return
        with self.busy:
            chat_now = list(self.pending_chat)
            prompt = self.build_prompt(reason)
            self.pending_chat.clear()
            self.last_ask = time.monotonic()
            try:
                d, dt = ask_claude(prompt, self.args.model, self.args.timeout)
                d = validate(d, self.state)
            except Exception as e:  # noqa: BLE001 - logime ja jatkame
                log(f"Claude'i viga: {e}")
                self.pending_chat[:0] = chat_now
                self.write_log(kind="error", reason=reason, error=str(e), prompt=prompt)
                return
            self.seq += 1
            write_atomic(self.state_path.parent / CMD_NAME, encode_cmd(self.seq, self.state["claude"], d, self.args.ascii))
            self.last = d
            for t in chat_now:
                self.history.append(f"inimene: {t}")
            if d.get("message"):
                self.history.append(f"sina: {d['message']}")
            tgt = f" -> P{d['target_player']}" if d["mode"] != "defend" else ""
            log(f"Claude ({dt:.1f}s, {reason}): {UNIT_ET[d['unit1']]} + {UNIT_ET[d['unit2']]}, {d['mode']}{tgt}, "
                f"ajastu={'jah' if d['age_up'] else 'ei'}, kyla={d['villagers']}")
            log("  hooned: " + ", ".join(f"{BUILDING_ET[b]} {n}" for b, n in d["buildings"].items() if n))
            if d.get("message"):
                log(f"  chatti: {d['message']}")
            log(f"  pohjus: {d.get('reasoning', '')}")
            self.write_log(kind="decision", reason=reason, latency=dt, seq=self.seq, decision=d,
                           game_time=self.state["time"], prompt=prompt)

    def decision_worker(self):
        while True:
            reasons = [self.trigger.get()]
            time.sleep(self.args.debounce)  # kogu kokku jarjestikused sonumid
            while not self.trigger.empty():
                reasons.append(self.trigger.get())
            talk = [r for r in reasons if r in ("chat", "terminal")]
            self.decide("inimene kirjutas" if talk else ", ".join(dict.fromkeys(reasons)))

    def run(self):
        log(f"Claude kindral kaivitub. Mudel {self.args.model}, intervall {self.args.interval}s. "
            "Kirjuta siia (voi mangu chatti), et Claude'iga raakida. Ctrl+C lopetab.")
        threading.Thread(target=self.decision_worker, daemon=True).start()
        threading.Thread(target=self.stdin_reader, daemon=True).start()
        last_wait_msg = 0.0
        while True:
            self.poll_state()
            self.poll_chat()
            now = time.monotonic()
            if self.state is None and now - last_wait_msg > 15:
                log(f"Ootan mangu (kaart ClaudeGeneral)... {STATE_NAME} pole veel tekkinud.")
                last_wait_msg = now
            if self.state and not self.busy.locked() and now - self.last_ask > self.args.interval:
                self.last_ask = now
                self.trigger.put("regulaarne")
            time.sleep(0.5)


def main():
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description="Claude kui AoE2 tiimikaaslane")
    ap.add_argument("--base", help="'Age of Empires 2 DE' kasutajakausta tee")
    ap.add_argument("--model", default="sonnet", help="claude mudel (sonnet, haiku, opus)")
    ap.add_argument("--interval", type=float, default=45.0, help="regulaarse otsuse intervall sekundites")
    ap.add_argument("--threat", type=int, default=3, help="mitu vaenlase sodurit linnakeskuse juures kaivitab kohese otsuse")
    ap.add_argument("--human", type=int, default=0, help="inimmangija number (vaikimisi automaatne)")
    ap.add_argument("--debounce", type=float, default=1.5, help="ootus enne kysimist, et koguda jarjestikused sonumid")
    ap.add_argument("--timeout", type=float, default=90.0, help="claude -p ajalimiit")
    ap.add_argument("--ascii", action="store_true", help="eemalda sonumitest tapitahed (kui mangu chat naitab neid valesti)")
    args = ap.parse_args()
    try:
        General(args).run()
    except KeyboardInterrupt:
        print("\nLopetatud.")


if __name__ == "__main__":
    main()
