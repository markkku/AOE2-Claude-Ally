# AOE2-Claude-Ally

**Play Age of Empires II: Definitive Edition with Claude as your teammate.**

Claude commands an allied computer player. It reads the game state, decides what to build and train,
when to age up, when to attack and when to come to your rescue, and talks to you in the in-game chat.
You can talk back: type in the normal game chat ("help me!", "attack blue", "what should I build?")
and Claude answers within seconds, in your language.

```
  game ──(XS writes state)──► <map>.xsdat ──► claude_ally.py ──► claude -p ──► decision
   ▲                                              │
   │                                  replay file (your chat)
   └──(AI script + XS carry it out)── claude_cmd.xsdat ◄──┘
```

- **Claude decides:** main and support unit, building targets (barracks, ranges, stables, siege workshop,
  blacksmith, market, monastery, university, castle, town centers, towers, docks), aging up, villager count,
  mode (defend / attack player X / help ally X), and what to say in chat.
- **The AI script does the rest:** villagers, houses, farms, mill, lumber and mining camps, eco upgrades,
  training the chosen units and their upgrades, moving the army.
- **Fair play:** Claude only sees your team's data and the enemy units that are currently visible to you.

## Requirements

- Age of Empires II: Definitive Edition on **Steam**, on Windows or on Linux (Proton).
- **Python 3.9+** (standard library only).
- **[Claude Code](https://claude.com/claude-code)** installed and logged in, so that the `claude` command works.
  Each decision is one `claude -p` call on your Claude plan (roughly 50–80 calls in a 40-minute game).
- Single player only (you + Claude vs computer AIs). Multiplayer and ranked are not supported.

## Install

1. Start the game once and go to the main menu (this creates your profile folder), then quit.
2. Download this repository and run:
   ```
   python install.py
   ```
   It finds the game automatically (any Steam library, Windows or Proton) and copies into your user profile:
   two XS scripts, the `ClaudeAI` AI script and a `Claude_<map>` copy of every built-in random map (174 maps).
   The game's own files are never changed. `python install.py --uninstall` removes everything again.

## Play

1. Start the bridge and leave it running:
   ```
   python claude_ally.py
   ```
2. In the game: **Single Player → Skirmish**
   - Map Style **Custom**, pick any **`Claude_<map>`** (e.g. `Claude_Arabia`, `Claude_Black_Forest`).
   - Put a computer player on **your team** and set its AI to **`ClaudeAI`**.
   - Add enemies on the other team (any normal AI).
3. Start. Within a few seconds the chat shows `[Claude] bridge active` and Claude's first message.
4. Talk to Claude in the game chat (or type into the terminal where `claude_ally.py` runs).

### Options

| Option | Default | |
|---|---|---|
| `--lang Estonian` | `auto` | language of Claude's chat messages (`auto` = the language you write in) |
| `--model haiku\|sonnet\|opus` | `sonnet` | Claude model |
| `--interval 45` | `45` | seconds between regular decisions; Claude also decides immediately when you write or a teammate is attacked |
| `--threat 3` | `3` | enemy soldiers near a teammate's town center that trigger an immediate decision |
| `--ascii` | off | strip accents from Claude's messages, if the game chat shows them wrong |
| `--claude-player N`, `--human N` | auto | override player detection |
| `--user-dir`, `--game-dir` (install.py) | auto | override folder detection |

Every decision (prompt, answer, latency) is logged to `logs/game-*.jsonl`.

## How it works

| File | Role |
|---|---|
| `xs/claude_bridge.xs` | Map-side XS, included by every `Claude_<map>`. Every 5 game seconds writes the state (`<map>.xsdat`); shows Claude's messages in chat. |
| `ai/ClaudeAI.per` | The AI player: economy, aging up, production, building Claude's building targets. |
| `xs/claude_ai.xs` | Loaded by the AI. Reads `claude_cmd.xsdat`, turns it into AI goals, moves the army. |
| `claude_ally.py` | Reads the state and your chat (from the replay file the game writes), asks Claude, writes `claude_cmd.xsdat`. |
| `install.py` | Installs / uninstalls the files above. |
| `aoe2common.py` | Folder detection (Windows / Proton, all Steam libraries) and `.xsdat` helpers. |
| `tools/bridge_test.*` | Minimal bridge test (scenario editor). |
| `docs/FINDINGS.md` | How it was figured out: `.xsdat` format, file locations, XS ↔ AI script communication, replay chat. |

## Limitations

- Water maps: the AI does not build a navy or cross water to attack.
- Only random maps from Skirmish (no scenarios or campaigns).
- When attacking, the army walks to the nearest enemy building even if it has not been scouted yet.
- Accented characters in Claude's messages have not been verified on every setup; use `--ascii` if they look wrong.

## Troubleshooting

- **`claude_ally.py` keeps "Waiting for a game"** → the map must be one of the `Claude_<map>` maps.
- **AI script error on game start** → note the file and line number and open an issue.
- **Claude never acts** → check that the ally's AI is `ClaudeAI` and that it is on your team.
- **`'claude' command not found`** → install Claude Code and run `claude` once to log in.
