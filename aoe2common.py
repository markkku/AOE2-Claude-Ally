"""Shared helpers: locating Age of Empires II: DE folders and reading/writing .xsdat files.

Works on Windows (native Steam) and Linux (Steam + Proton).
"""

import os
import re
import struct
import sys
from pathlib import Path

APP_ID = "813780"  # AoE II: Definitive Edition on Steam
GAME_DIR_NAME = "Age of Empires 2 DE"
MAGIC = 20261029   # first int of every file this project writes
CMD_NAME = "claude_cmd.xsdat"


# --- Steam / game folders ---------------------------------------------------------

def steam_roots():
    roots = []
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
        roots += [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    else:
        home = Path.home()
        roots += [home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root",
                  home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    seen, out = set(), []
    for r in roots:
        try:
            key = r.resolve()
        except OSError:
            continue
        if r.exists() and key not in seen:
            seen.add(key)
            out.append(r)
    return out


def steam_libraries():
    """All Steam library folders (from libraryfolders.vdf), including the Steam root itself."""
    libs = []
    for root in steam_roots():
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            text = vdf.read_text(encoding="utf-8", errors="replace")
            for path in re.findall(r'"path"\s+"([^"]+)"', text):
                libs.append(Path(path.replace("\\\\", "\\")))
    seen, out = set(), []
    for lib in libs:
        try:
            key = lib.resolve()
        except OSError:
            continue
        if lib.exists() and key not in seen:
            seen.add(key)
            out.append(lib)
    return out


def find_install_dir(override=None):
    """The game installation folder (…/steamapps/common/AoE2DE)."""
    if override:
        return Path(override)
    for lib in steam_libraries():
        p = lib / "steamapps" / "common" / "AoE2DE"
        if p.exists():
            return p
    return None


def find_user_base(override=None):
    """The '…/Games/Age of Empires 2 DE' folder that holds one sub-folder per profile (<steamId>)."""
    if override:
        return Path(override)
    candidates = []
    if sys.platform == "win32":
        candidates.append(Path(os.environ.get("USERPROFILE", Path.home())) / "Games" / GAME_DIR_NAME)
    for lib in steam_libraries():
        candidates.append(lib / "steamapps" / "compatdata" / APP_ID / "pfx" / "drive_c" / "users"
                          / "steamuser" / "Games" / GAME_DIR_NAME)
    for c in candidates:
        if c.exists():
            return c
    return None


def find_profile_dirs(base):
    """Profile folders (<steamId>, or '0' for offline) inside the user base folder."""
    if not base or not base.exists():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and p.name.isdigit())


# --- .xsdat format -------------------------------------------------------------------
# No header; values are back to back, little-endian:
#   int = int32, float = float32 (IEEE 754), vector = 3 x float32,
#   string = uint32 byte length + bytes.

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
        if self.pos + n > len(self.data):
            raise struct.error("string runs past end of file")
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        return raw


def pack_string(text):
    raw = text.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


def write_atomic(path, data):
    """Write via a temp file + rename so the game never reads a half-written file."""
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
