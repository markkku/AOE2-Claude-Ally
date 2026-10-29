#!/usr/bin/env python3
"""Low-level bridge test: proves that XS and an external program can talk through .xsdat files.

Usage (see docs/FINDINGS.md for background):
  python tools/bridge_test.py install   copy bridge_test.xs into your profile's xs folder
  python tools/bridge_test.py run       print the game time XS writes; write an increasing number to claude_cmd
  python tools/bridge_test.py dump F    hex-dump an .xsdat file

In game: Editors > Create Scenario > Map tab > script file 'bridge_test' > Test.
Chat should show "Claude says: 1", "Claude says: 2", ...
"""

import argparse
import shutil
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aoe2common import CMD_NAME, MAGIC, Reader, find_profile_dirs, find_user_base, hexdump, write_atomic  # noqa: E402

HERE = Path(__file__).resolve().parent


def user_base(args):
    base = find_user_base(args.user_dir)
    if not base or not base.exists():
        sys.exit("User folder not found. Start the game once, or pass --user-dir.")
    return base


def parse_state(data):
    """bridge_test.xs state: magic, counter, game time, float game time, string."""
    r = Reader(data)
    if len(data) < 12 or r.int() != MAGIC:
        return None
    out = {"counter": r.int(), "game_time": r.int()}
    try:
        out["game_time_f"] = r.float()
        out["text"] = r.string()
    except struct.error:
        pass
    return out


def cmd_install(args):
    for prof in find_profile_dirs(user_base(args)):
        xs_dir = prof / "resources" / "_common" / "xs"
        xs_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / "bridge_test.xs", xs_dir / "bridge_test.xs")
        print(f"XS -> {xs_dir / 'bridge_test.xs'}")


def cmd_run(args):
    base = user_base(args)
    profile_dirs = [p / "profile" for p in find_profile_dirs(base) if (p / "profile").exists()]
    print(f"Watching .xsdat files under {base}")
    seen, dumped, state_dirs = {}, set(), set()
    seq, value, last_cmd = 0, args.start, 0.0
    while True:
        for d in profile_dirs:
            for path in d.glob("*.xsdat"):
                if path.name == CMD_NAME:
                    continue
                mtime = path.stat().st_mtime_ns
                if seen.get(path) == mtime:
                    continue
                seen[path] = mtime
                data = path.read_bytes()
                st = parse_state(data)
                if st is None or len(data) > 64:  # skip files written by claude_bridge.xs
                    continue
                if path not in dumped:
                    dumped.add(path)
                    print(f"\n=== {path} ({len(data)} bytes)\n{hexdump(data)}\n")
                state_dirs.add(path.parent)
                print(f"[{time.strftime('%H:%M:%S')}] {path.name}: game time {st['game_time']} s, counter {st['counter']}")
        if time.monotonic() - last_cmd >= args.interval:
            last_cmd = time.monotonic()
            seq += 1
            for d in sorted(state_dirs) or profile_dirs:
                write_atomic(d / CMD_NAME, struct.pack("<iii", MAGIC, seq, value))
            print(f"[{time.strftime('%H:%M:%S')}] command seq={seq} value={value}")
            value += 1
        time.sleep(0.5)


def cmd_dump(args):
    data = Path(args.file).read_bytes()
    print(f"{args.file}: {len(data)} bytes\n{hexdump(data)}")


def main():
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-dir", help="user folder (…/Games/Age of Empires 2 DE)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("install")
    r = sub.add_parser("run")
    r.add_argument("--interval", type=float, default=2.0, help="seconds between commands (game runs at 1.7x by default)")
    r.add_argument("--start", type=int, default=1)
    d = sub.add_parser("dump")
    d.add_argument("file")
    args = ap.parse_args()
    try:
        {"install": cmd_install, "run": cmd_run, "dump": cmd_dump}[args.cmd](args)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
