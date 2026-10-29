#!/usr/bin/env python3
"""AoE2 DE <-> Claude silla 1. faasi test.

Alamkasud:
  install  - kopeerib bridge_test.xs kasutaja XS-kausta ja loob ClaudeBridge.rms
             (Arabia koopia, mille alguses on #includeXS) kasutaja RMS-kausta
  run      - jalgib XS-i kirjutatud .xsdat faile, prindib manguaja ja kirjutab
             claude_cmd.xsdat faili kasvava numbri
  dump     - prindib .xsdat faili hex-dumpi ja dekodeeritud valjad

.xsdat formaat (vt LEIUD.md): little-endian int32 / float32 (IEEE 754),
string = uint32 pikkus + baidid.
"""

import argparse
import glob
import os
import shutil
import struct
import sys
import time
from pathlib import Path

MAGIC = 20261029
CMD_NAME = "claude_cmd.xsdat"
PROJECT_DIR = Path(__file__).resolve().parent
GAME_DIR_NAME = "Age of Empires 2 DE"


# --- Asukohtade leidmine -----------------------------------------------------

def steam_roots():
    home = Path.home()
    roots = [
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    ]
    return [r for r in roots if r.exists()]


def find_games_base():
    """Kaust '...\\Games\\Age of Empires 2 DE' (Windows voi Protoni prefiks)."""
    candidates = []
    if os.name == "nt":
        candidates.append(Path(os.environ["USERPROFILE"]) / "Games" / GAME_DIR_NAME)
    for root in steam_roots():
        candidates.append(root / "steamapps/compatdata/813780/pfx/drive_c/users/steamuser/Games" / GAME_DIR_NAME)
    for c in candidates:
        if c.exists():
            return c.resolve()
    return None


def find_install_dir():
    if os.name == "nt":
        p = Path(r"C:\Program Files (x86)\Steam\steamapps\common\AoE2DE")
        return p if p.exists() else None
    for root in steam_roots():
        p = root / "steamapps/common/AoE2DE"
        if p.exists():
            return p.resolve()
    return None


def find_profile_dirs(base):
    """Numbrilised alamkaustad (<steamId>)."""
    return sorted(p for p in base.iterdir() if p.is_dir() and p.name.isdigit())


# --- .xsdat kodeerimine --------------------------------------------------------

class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def int(self):
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def float(self):
        v = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return v

    def string(self):
        n = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        return raw


def encode_cmd(seq, value):
    return struct.pack("<iii", MAGIC, seq, value)


def write_atomic(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def hexdump(data):
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hx = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {off:08x}  {hx:<47}  {asc}")
    return "\n".join(lines)


def parse_state(data):
    r = Reader(data)
    magic = r.int()
    if magic != MAGIC:
        return None
    out = {"counter": r.int(), "game_time": r.int()}
    try:
        out["game_time_f"] = r.float()
        out["text"] = r.string()
    except struct.error:
        pass
    return out


# --- Alamkasud -----------------------------------------------------------------

def cmd_install(args):
    base = Path(args.base) if args.base else find_games_base()
    if not base or not base.exists():
        sys.exit("Ei leidnud kausta '%s'. Kaivita mang korra (kuni peamenyyni), siis proovi uuesti." % GAME_DIR_NAME)
    profiles = find_profile_dirs(base)
    if not profiles:
        sys.exit(f"Kaustas {base} pole <steamId> alamkausta. Kaivita mang korra peamenyyni.")
    install = find_install_dir()
    for prof in profiles:
        xs_dir = prof / "resources/_common/xs"
        rms_dir = prof / "resources/_common/random-map-scripts"
        xs_dir.mkdir(parents=True, exist_ok=True)
        rms_dir.mkdir(parents=True, exist_ok=True)
        ai_dir = prof / "resources/_common/ai"
        ai_dir.mkdir(parents=True, exist_ok=True)
        for name in ("bridge_test.xs", "claude_bridge.xs", "claude_ai.xs"):
            shutil.copy2(PROJECT_DIR / name, xs_dir / name)
            print(f"XS  -> {xs_dir / name}")
        shutil.copy2(PROJECT_DIR / "ClaudeAI.per", ai_dir / "ClaudeAI.per")
        (ai_dir / "ClaudeAI.ai").write_bytes(b"")
        print(f"AI  -> {ai_dir / 'ClaudeAI.per'} (+ tyhi ClaudeAI.ai)")
        arabia = install / "resources/_common/drs/gamedata_x2/Arabia.rms" if install else None
        if arabia and arabia.exists():
            src = arabia.read_bytes()
            for rms, xs in (("ClaudeBridge.rms", "bridge_test.xs"), ("ClaudeGeneral.rms", "claude_bridge.xs")):
                (rms_dir / rms).write_bytes(b"#includeXS " + xs.encode() + b"\r\n" + src)
                print(f"RMS -> {rms_dir / rms} (Arabia + #includeXS {xs})")
        else:
            print("Arabia.rms ei leitud, RMS-i ei loodud (stsenaariumi test toimib ikka).")


def candidate_cmd_dirs(base):
    """Kuhu claude_cmd kirjutada, kuni pole teada, kus XS-i failid tekivad."""
    dirs = []
    for prof in find_profile_dirs(base):
        dirs += [prof / "profile", prof / "resources/_common/xs", prof]
    return [d for d in dirs if d.exists()]


def scan_xsdat(roots):
    found = {}
    for root in roots:
        for p in glob.glob(str(root / "**" / "*.xsdat"), recursive=True):
            p = Path(p)
            if p.name == CMD_NAME:
                continue
            try:
                found[p] = p.stat().st_mtime_ns
            except FileNotFoundError:
                pass
    return found


def cmd_run(args):
    base = Path(args.base) if args.base else find_games_base()
    if not base or not base.exists():
        sys.exit("Ei leidnud mangu kasutajakausta. Kaivita mang korra voi anna --base.")
    roots = [base]
    install = find_install_dir()
    if install and args.scan_install:
        roots.append(install / "resources")
    print(f"Jalgin .xsdat faile: {', '.join(map(str, roots))}")

    seen = {}            # path -> mtime
    dumped = set()
    state_dirs = set()   # kaustad, kus XS-i seisufail tekkis
    seq = 0
    value = args.start
    last_cmd = 0.0

    while True:
        now = time.monotonic()

        # 1) loe XS-i seisufaile
        for path, mtime in scan_xsdat(roots).items():
            if seen.get(path) == mtime:
                continue
            seen[path] = mtime
            try:
                data = path.read_bytes()
            except OSError as e:
                print(f"[viga] {path}: {e}")
                continue
            if path not in dumped:
                dumped.add(path)
                print(f"\n=== Uus .xsdat: {path} ({len(data)} baiti)\n{hexdump(data)}\n")
            st = parse_state(data) if len(data) >= 12 else None
            if st is None:
                continue
            if path.parent not in state_dirs:
                state_dirs.add(path.parent)
                print(f"*** XS kirjutab kausta: {path.parent}")
            print(f"[{time.strftime('%H:%M:%S')}] {path.name}: manguaeg={st['game_time']} s  "
                  f"loendur={st['counter']}  float={st.get('game_time_f')}  str={st.get('text')!r}")

        # 2) kirjuta kask
        if now - last_cmd >= args.interval:
            last_cmd = now
            seq += 1
            targets = sorted(state_dirs) or candidate_cmd_dirs(base)
            for d in targets:
                write_atomic(d / CMD_NAME, encode_cmd(seq, value))
            print(f"[{time.strftime('%H:%M:%S')}] kask seq={seq} vaartus={value} -> "
                  + ", ".join(str(d / CMD_NAME) for d in targets))
            value += 1

        time.sleep(0.5)


def cmd_dump(args):
    data = Path(args.file).read_bytes()
    print(f"{args.file}: {len(data)} baiti\n{hexdump(data)}")
    if len(data) == 12:
        print("Dekodeeritud kasufail: magic=%d seq=%d value=%d" % struct.unpack("<iii", data))
    elif len(data) > 12:
        print("Dekodeeritud seisufail:", parse_state(data))


def main():
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help=f"'{GAME_DIR_NAME}' kasutajakausta tee (vaikimisi automaatne)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("install")
    r = sub.add_parser("run")
    r.add_argument("--interval", type=float, default=2.0, help="kasu kirjutamise intervall (paris)sekundites; mang jookseb vaikimisi 1.7x")
    r.add_argument("--start", type=int, default=1, help="esimene kasu vaartus")
    r.add_argument("--scan-install", action="store_true", help="otsi .xsdat faile ka mangu paigalduskaustast")
    d = sub.add_parser("dump")
    d.add_argument("file")
    args = ap.parse_args()
    try:
        {"install": cmd_install, "run": cmd_run, "dump": cmd_dump}[args.cmd](args)
    except KeyboardInterrupt:
        print("\nLopetatud.")


if __name__ == "__main__":
    main()
