# Technical findings

Notes from building the bridge between Age of Empires II: Definitive Edition and an external program.
Everything here was verified in game (Linux + Steam/Proton, October 2026) unless marked otherwise.

## 1. XS can talk to an external program through `.xsdat` files

**The game re-reads `.xsdat` files from disk on every `xsOpenFile`.** When an external program rewrites
`claude_cmd.xsdat`, the next `xsOpenFile` → `xsRead*` → `xsCloseFile` cycle sees the new content.
Verified by writing an increasing sequence number from Python and printing it from XS: it went up on every read.

| Question | Answer |
|---|---|
| Is the file re-read during a game? | ✅ Yes. Write atomically (temp file + rename) so the game never sees a half-written file. |
| Where are `.xsdat` files? | `…/Games/Age of Empires 2 DE/<steamId>/profile/`. On Windows `%USERPROFILE%\Games\…`; on Linux inside the Proton prefix `steamapps/compatdata/813780/pfx/drive_c/users/steamuser/Games/…`. |
| Where does `xsOpenFile` read from? | The same `profile/` folder. |
| Can `xsOpenFile` open any file name? | ✅ Yes, e.g. `xsOpenFile("claude_cmd")` (name without extension). |
| Can `xsCreateFile` choose the name? | ❌ No. The file is named after the scenario or map: `default0.xsdat` in the editor test, `<RMS name>.xsdat` in a random map game (e.g. `Claude_Arena.xsdat`). |
| Timing | XS rules (`minInterval`) run on **game time**. Default game speed is 1.7×, so 5 game seconds ≈ 2.9 real seconds. |

There can be several profile folders (`<steamId>/` and `0/` for offline); the installer writes to all of them.

## 2. `.xsdat` binary format (verified with a hex dump)

No header; values are written back to back, little-endian.

```
a5 28 35 01  34 00 00 00  04 01 00 00  00 00 82 43  06 00 00 00  62 72 69 64 67 65
magic        counter=52   time=260     float 260.0  str len=6    "bridge"
```

| Type | Bytes |
|---|---|
| int | 4, signed int32 |
| float | 4, IEEE 754 float32 |
| vector | 12, 3 × float32 (documented, not tested) |
| string | uint32 byte length + bytes (ASCII verified; non-ASCII not yet verified) |

`xsCreateFile(false)` overwrites the file each time.

## 3. Random map scripts can load XS

`#includeXS claude_bridge.xs` as the first line of a user RMS works; the XS file is looked up in the profile's
`resources/_common/xs/` folder. The XS `main()` runs at game start and `rule`s run periodically.
None of the 180 built-in maps use `#includeXS`, so a copy of each map with that line on top is safe.

## 4. An AI script (.per) can run XS and react to it

Mechanism: `(include "file.xs")` + `(xs-script-call "function")` + goals. The game's own AI (Promisory) uses
the same mechanism (`ai/Promisory/scoutcontrol.per` → `xs/ailib/Geometry.xs`).

- `(include "claude_ai.xs")` finds the file in the **profile's** `xs/` folder. It must come after all `load` commands.
- `(xs-script-call "fn")` calls a parameterless XS function **in the AI player's context**.
- In that context `xsGetGoal` / `xsSetGoal` read and write that AI's goals, so XS → .per communication works:
  XS sets a goal, a `.per` rule like `(goal gl-x 1)` or `(up-compare-goal gl-x c:== 1)` reacts.
- `xsOpenFile` works in that context, so the AI can read `claude_cmd.xsdat` directly.
- XS `rule`s do not run per AI player (airef), so AI-side XS uses only functions called by `xs-script-call`.
  Global XS variables are separate for each AI player.
- Verified: a value written by Python reached a `.per` rule and was printed with `up-chat-data-to-all`.
- Gotcha: the AI command is `enable-timer`, not `enable-timers` (error 2005 "invalid identifier").

## 5. Player chat can be read from the replay file

While a game runs, the game writes the recorded game to `<steamId>/savegame/*.aoe2record`.
Chat messages are stored as an operation `int32 4, int32 -1, uint32 length` followed by JSON, e.g.

```json
{"player":2,"channel":0,"message":"…","tauntNumber":0,"messageAGP":"@#22 ClaudeAI: …"}
```

Chat sent by AI scripts (`up-chat-data-to-all`) is recorded too, which is how `claude_ally.py` detects which player
is ClaudeAI (`"ClaudeAI ready, player N"`). Chat printed with XS `xsChatData` is **not** recorded.

## 6. What XS can read from the game

Source: the XS function list in `xs-check`'s `prelude.xs`.

| Data | Function |
|---|---|
| Resources | `xsPlayerAttribute(p, cAttributeFood/Wood/Stone/Gold)` |
| Population | `cAttributePopulation`, `cAttributePopulationCap`, `cAttributeCivilianPopulation`, `cAttributeMilitaryPopulation` |
| Age | `cAttributeCurrentAge` |
| Unit / building counts by type or class | `xsGetObjectCount(p, id)`, `xsGetObjectCountTotal` (includes ones in production / under construction). Class IDs are 900 + class (e.g. `cArcherClass` = 900). |
| Individual units | `xsGetPlayerUnitIds(p, idOrClass, array)` → `xsGetUnitPosition`, `xsGetUnitHitpoints`, … |
| Diplomacy | `xsGetDiplomacy(a, b)` → `cDiplomacyAlly` (0), `Neutral` (1), `Enemy` (3) |
| Visibility | `xsUnsyncIsUnitVisible(unit, allowInFog, -1)`: visible to the **local** (human) player |

⚠️ These functions see the whole map, including units under fog of war. To keep Claude fair, the bridge only
reports enemy units that are currently visible to the human player. (Exception: when attacking, the AI walks to
the nearest enemy building even if it has not been scouted.)

## 7. Asking Claude for a decision

Measured with `claude -p --output-format json` and a realistic game-state prompt:

| Model | Wall time | API time |
|---|---|---|
| haiku | 6.1–7.1 s | 3.2–3.8 s |
| sonnet | 4.4–7.3 s | 3.0–3.3 s |

- `claude -p` uses the user's Claude subscription; no API key needed. CLI startup adds ~1–3 s.
- `--json-schema` returns a validated object in `structured_output`, so free-text variations
  (e.g. "spear" vs "spearman") are avoided.
- `--safe-mode --tools ""` keeps the call minimal (no tools, no project files).
- 5–8 s per decision fits a 30–60 s decision cycle; the game does not pause.

## Sources

- [Divy1211/xs-check](https://github.com/Divy1211/xs-check) – `xsc-core/prelude.xs` (XS functions and constants), and the linter used for all XS files
- [Divy1211/vsc-xs-support](https://github.com/Divy1211/vsc-xs-support)
- [airef: XS Scripting for AI Tournaments](https://airef.github.io/resources/articles/xs-for-tournaments.html) and the [AI command reference](https://airef.github.io/)
- The game's own files: `ai/Promisory/scoutcontrol.per`, `xs/ailib/Geometry.xs`
- [AoE forum: .xsdat in campaigns](https://forums.ageofempires.com/t/xsdat-file-cannot-be-stored-in-correct-file-as-expected-for-campaigns/204962)
