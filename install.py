#!/usr/bin/env python3
"""Install (or uninstall) the Claude Ally files into your Age of Empires II: DE user profile.

    python install.py              # install / update
    python install.py --uninstall  # remove everything this script installed

What gets installed, for every profile folder (…/Games/Age of Empires 2 DE/<steamId>/):
  resources/_common/xs/claude_bridge.xs, claude_ai.xs
  resources/_common/ai/ClaudeAI.ai, ClaudeAI.per
  resources/_common/random-map-scripts/Claude_<Map>.rms  - a copy of every built-in map with
                                                           '#includeXS claude_bridge.xs' added on top
The game's own files are never modified.
"""

import argparse
import shutil
import sys
from pathlib import Path

from aoe2common import find_install_dir, find_profile_dirs, find_user_base

ROOT = Path(__file__).resolve().parent
XS_FILES = ["claude_bridge.xs", "claude_ai.xs"]
AI_NAME = "ClaudeAI"
MAP_PREFIX = "Claude_"
# special-purpose maps that make no sense with an AI ally
SKIP_MAPS = ("Network_Test",)
SKIP_PREFIXES = ("BR_",)
# files created by earlier development versions; removed by --uninstall
LEGACY = ["xs/bridge_test.xs", "random-map-scripts/ClaudeGeneral.rms", "random-map-scripts/ClaudeBridge.rms"]


def profile_targets(args):
    base = find_user_base(args.user_dir)
    if not base or not base.exists():
        sys.exit("Could not find the 'Age of Empires 2 DE' user folder. Start the game once (to the main menu),\n"
                 "or pass --user-dir \"…/Games/Age of Empires 2 DE\".")
    profiles = find_profile_dirs(base)
    if not profiles:
        sys.exit(f"No profile folders in {base}. Start the game once (to the main menu) and try again.")
    return [p / "resources" / "_common" for p in profiles]


def install_maps(game_dir, rms_dir):
    src_dir = game_dir / "resources" / "_common" / "drs" / "gamedata_x2"
    if not src_dir.exists():
        print(f"  ! built-in maps not found in {src_dir}; no Claude_ maps created")
        return
    for old in rms_dir.glob(f"{MAP_PREFIX}*.rms"):
        old.unlink()
    made, skipped = 0, []
    for src in sorted(src_dir.glob("*.rms")):
        data = src.read_bytes()
        if src.stem in SKIP_MAPS or src.stem.startswith(SKIP_PREFIXES) or b"#includexs" in data.lower():
            skipped.append(src.stem)
            continue
        (rms_dir / f"{MAP_PREFIX}{src.stem}.rms").write_bytes(b"#includeXS claude_bridge.xs\r\n" + data)
        made += 1
    print(f"  maps: {made} x {MAP_PREFIX}<map>.rms" + (f" (skipped: {', '.join(skipped)})" if skipped else ""))


def install(args):
    game_dir = find_install_dir(args.game_dir)
    if not game_dir or not game_dir.exists():
        sys.exit("Could not find the game installation (…/steamapps/common/AoE2DE). Pass --game-dir.")
    print(f"Game:     {game_dir}")
    for common in profile_targets(args):
        print(f"Profile:  {common.parent.parent}")
        xs_dir, ai_dir, rms_dir = common / "xs", common / "ai", common / "random-map-scripts"
        for d in (xs_dir, ai_dir, rms_dir):
            d.mkdir(parents=True, exist_ok=True)
        for name in XS_FILES:
            shutil.copy2(ROOT / "xs" / name, xs_dir / name)
        shutil.copy2(ROOT / "ai" / f"{AI_NAME}.per", ai_dir / f"{AI_NAME}.per")
        (ai_dir / f"{AI_NAME}.ai").write_bytes(b"")
        print(f"  xs: {', '.join(XS_FILES)}   ai: {AI_NAME}")
        install_maps(game_dir, rms_dir)
    print("\nDone. In game: Single Player > Skirmish > Map Style 'Custom' > any 'Claude_<map>',\n"
          f"and set your ally's AI to '{AI_NAME}'. Then run: python claude_ally.py")


def uninstall(args):
    for common in profile_targets(args):
        removed = []
        paths = [common / "xs" / n for n in XS_FILES]
        paths += [common / "ai" / f"{AI_NAME}.per", common / "ai" / f"{AI_NAME}.ai"]
        paths += sorted((common / "random-map-scripts").glob(f"{MAP_PREFIX}*.rms"))
        paths += [common / rel for rel in LEGACY]
        for p in paths:
            if p.exists():
                p.unlink()
                removed.append(p.name)
        print(f"{common.parent.parent}: removed {len(removed)} files")


def main():
    ap = argparse.ArgumentParser(description="Install Claude Ally into Age of Empires II: DE")
    ap.add_argument("--uninstall", action="store_true", help="remove all installed files")
    ap.add_argument("--game-dir", help="game installation folder (…/steamapps/common/AoE2DE)")
    ap.add_argument("--user-dir", help="user folder (…/Games/Age of Empires 2 DE)")
    args = ap.parse_args()
    (uninstall if args.uninstall else install)(args)


if __name__ == "__main__":
    main()
