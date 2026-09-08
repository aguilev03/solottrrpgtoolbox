# SOLO TTRPG TOOLS

A lightweight, system-neutral, self-hosted web suite for solo tabletop roleplaying games.

The application includes two specialized solo modules:
1. **Dungeon Crawler:** A procedural room-by-room generator acting as a referee. Delves, landmarks, hazards, and floor descents emerge unpredictably using a pure Progress dice pool.
2. **Character Emulator:** Based on Cezar Capacle's *Triple-O: The Player Character Emulator*. Answers "What does this character do?" for party members, companions, hirelings, allies, and recurring NPCs without system-bound math.

---

## 1. Core Philosophy & Design Rules

- **Zero Pre-Generation:** No room count, map, or floor sequence is generated ahead of time. The dungeon literally comes into existence chamber by chamber.
- **Uncertainty Over Knowledge:** The player never sees progress bars, remaining room counts, or hidden floor limits.
- **System-Neutral:** Outputs abstract narrative encounters and hazards rather than RPG-specific math (no Armor Class, HP, DC checks, or 5e stat blocks). Compatible with any fantasy ruleset.
- **Routes as Information:** Routes are displayed as descriptive text (e.g., `• Heavy wooden door (stuck)`), not navigational buttons. The player decides how to map and explore in their own game.
- **Cross-Device Persistence:** All state is saved to a server-side SQLite database. Access and resume games seamlessly across desktop, tablet, and phone without relying on browser `localStorage`.

---

## 2. Dungeon Crawler Mechanics

### The Pure Progress Dice Pool Mechanic
Exploration does not accumulate points toward a static target. Instead, it uses a growing **D6 dice pool**:

1. **Initial State:** `progress_points = 0`. Minimum dice pool is always **1D6**.
2. **Dice Pool Formula:**
   $$\text{number\_of\_dice} = \text{progress\_points} + 1$$
3. **Evaluating Dice:**
   - **5 or 6** = 1 success
   - **1, 2, 3, or 4** = 0 (blank)
4. **Outcomes & Player-Visible Progress:**
   - Displayed to the player as a simple number representing the current pool size:
     $$\text{displayed\_progress} = \text{progress\_points} + 1$$
   - **0 Successes (Failure):** Generates a normal room. `progress_points` remains unchanged. No progress message.
   - **1 Success (Weak Success):** Generates a normal room. `progress_points += 1` (the next explore rolls +1D6).
     - Surfaces and logs: `Progress made! X → Y` (e.g., `Progress made! 1 → 2`).
   - **2+ Successes (Strong Success):** Generates the **Unique Room** for the current floor!
5. **Floor Descent:**
   - When transitioning from a Unique Room to a new floor: `current_level += 1`, `progress_points` resets to `0`, the Entrance room is generated, and visual Progress resets to **1**.

### Route Directions (Compass Heading)
Every visible route is assigned a unique compass direction selected without replacement from the 8 cardinal and intercardinal points:
- `↑ North`
- `↗ Northeast`
- `→ East`
- `↘ Southeast`
- `↓ South`
- `↙ Southwest`
- `← West`
- `↖ Northwest`

**Rules:**
- No duplicate directions within the same room.
- Secret routes discovered through **Search** receive an unused compass direction from the remaining directions.
- Stored as structured data (`direction`, `arrow`, `text`) so the UI renders clear, scannable route lists (e.g. `• ↑ North — Arched entryway`). Routes remain non-clickable info.

### Dungeon Size & Hidden Floors
Dungeon Size strictly governs the **hidden number of floors** and does *not* modify the Progress dice pool:

| Size | Hidden Floors |
| :--- | :---: |
| **Small** | Exactly 1 floor |
| **Medium** | 1–2 floors (randomly rolled) |
| **Large** | 2–3 floors (randomly rolled) |
| **Random** | Rolls size first, then rolls floors |

*The exact floor count is determined at dungeon creation but is never displayed to the player.*

### In-Game Time & Tension Clock
- Every exploration action adds **10 minutes** to elapsed time:
  - `Generate New Room` (+10 min)
  - `Search` (+10 min)
  - Entrance begins at `00:00`.
- **Hourly Tension Clock:**
  - Tracks `tension_dice` (+1 per action).
  - When `tension_dice` reaches **6** (one dungeon hour), the engine triggers an automatic tension/encounter event from `data/tension_events.json` and resets `tension_dice = 0`.

### Searching Chambers
- Each chamber may only be searched **once**.
- Upon clicking **Search**, time advances +10 minutes and a roll is made against `data/search.json`.
- The button locks and changes to `[ ✓ Searched ]`.
- **Secret Route Discovery:** If Search rolls *Secret route*, a hidden passage is dynamically composed and appended to the current room's visible Routes list.

### Trap Reveal System
Traps can be encountered either as room contents (via `contents.json` → `hazards.json` → `traps.json`) or uncovered during chamber search (via `search.json` → `hazards.json` or `search_trouble.json`).

Each trap features two distinct atmospheric descriptions:
1. **Warning:** What your character initially notices. Subtle and ambiguous enough that the nature of the trap remains concealed.
2. **Reveal:** What you learn after deciding your character successfully identifies or investigates the mechanism.

#### Trap States
1. **Hidden / Unidentified:** When a trap is first encountered, its specific type is hidden. The UI displays the ambiguous warning:
   > **Trap**
   > *"<Initial Warning>"* (e.g. *"The floor gives a faint creak beneath your weight."*)
   > `[ Reveal ]`
2. **Revealed:** The player resolves any detection or inspection check using their own tabletop RPG system. Clicking `[ Reveal ]` reveals the specific trap name and its full mechanism description (e.g., **Pitfall** — *"A section of flooring is nothing more than a carefully disguised cover over a deep pit."*).

**System-Neutral Adherence:**
- The application does not mechanically resolve traps, roll damage, assign save DCs, or provide an "Activate" button.
- The player handles tactical resolution in their own journal, character sheet, or VTT.
- The revealed state is saved directly into SQLite (`has_trap`, `trap_revealed`, `trap_data_json`), guaranteeing that closing, navigating away, or resuming a session preserves the revealed state.

#### Traps Roll Table (`data/traps.json` — 1d20)

| d20 | Trap | Initial Warning | Revealed Description |
| :---: | :--- | :--- | :--- |
| **1** | **Swinging Blade** | You hear a click, as though something has just been activated. | A thin seam in the nearby wall conceals a heavy blade poised to sweep across the room. |
| **2** | **Pitfall** | The floor gives a faint creak beneath your weight. | A section of flooring is nothing more than a carefully disguised cover over a deep pit. |
| **3** | **Dart Launcher** | A soft mechanical tick comes from somewhere nearby. | Tiny holes along the wall conceal a series of spring-loaded dart launchers aimed across the passage. |
| **4** | **Falling Block** | Dust suddenly trickles down from the ceiling. | A massive stone block overhead has been rigged to drop when the mechanism below is disturbed. |
| **5** | **Poison Gas** | You hear a quiet hiss that wasn't there a moment ago. | Narrow vents hidden in the masonry are beginning to release a strange vapor into the chamber. |
| **6** | **Swinging Weight** | Somewhere above you, a chain suddenly pulls taut. | A massive suspended weight is concealed overhead, positioned to swing violently through the room. |
| **7** | **Snare** | Something thin brushes against your boot. | Nearly invisible cords run across the floor into a concealed mechanism designed to snare anyone crossing them. |
| **8** | **Crushing Walls** | Stone grinds against stone somewhere behind the walls. | Hidden mechanisms connect the opposing walls, allowing them to slowly close together and crush anything between them. |
| **9** | **Flame Jet** | You smell something sharp and oily in the air. | Small nozzles concealed among the stonework connect to a reservoir designed to engulf the passage in flame. |
| **10** | **Collapsing Ceiling** | A small pebble strikes the floor beside you. Then another. | Several ceiling supports have been deliberately weakened and connected to a concealed trigger. |
| **11** | **Needle Lock** | The mechanism gives an unusually sharp click as it moves. | A tiny needle is concealed inside the lock or handle, positioned to strike the hand of anyone manipulating it. |
| **12** | **False Door** | The door shifts strangely when touched, almost as though the entire frame moved. | The apparent doorway is part of a larger mechanism designed to drop, tilt, or collapse when opened. |
| **13** | **Flooding Chamber** | You hear the distant rush of moving water. | Hidden channels and sealed sluices surround the chamber, designed to rapidly fill the area with water. |
| **14** | **Rolling Boulder** | A deep *thunk* echoes from somewhere beyond the passage. | A large stone has been secured farther up the passage and connected to a trigger that releases it downhill. |
| **15** | **Net Trap** | Something overhead rustles despite the still air. | A weighted net has been carefully concealed above the area, ready to drop and entangle anyone beneath it. |
| **16** | **Spiked Floor** | One of the floor stones sinks slightly beneath your foot. | Several floor panels conceal rows of spikes connected to pressure mechanisms beneath the stone. |
| **17** | **Magical Ward** | For an instant, faint markings shimmer across a nearby surface and disappear. | An arcane sigil has been worked into the area, its lines forming a dormant magical ward awaiting a trigger. |
| **18** | **Alarm** | You hear a faint metallic chime somewhere in the distance. | A concealed line or pressure mechanism connects this area to an alarm elsewhere in the dungeon. |
| **19** | **Sealing Doors** | Something heavy shifts inside the walls behind you. | Counterweights and hidden tracks are positioned to slam nearby doors shut and seal the chamber. |
| **20** | **Pendulum** | A slow metallic scrape comes from somewhere overhead. | A large pendulum mechanism is concealed above, positioned to sweep repeatedly across the chamber once released. |

### Room Objects & Furnishings
Every generated chamber (Entrance, standard rooms, and Unique Chambers) is automatically furnished with **3 random, distinct objects** rolled without replacement from the 100-entry `data/room_objects.json` table.

- **Atmospheric & Tangible:** Spans furniture (benches, tables, lecterns), storage (iron-bound chests, rot-weakened crates, urns), fixtures (iron braziers, wall sconces, hanging chains), work tools (chisels, mining picks), and atmospheric dungeon detritus (shattered pottery, discarded bone dice, wax figurines).
- **System-Neutral:** Objects are purely narrative and evocative, providing environmental flavor, improvisational prompts for solo roleplay, and targets for investigation without imposing system-bound stats.
- **SQLite Persistence:** The rolled 3-item list is serialized into `objects_json` on the room record in SQLite, ensuring that returning to or reloading a chamber displays the exact same objects.

---

## 3. Character Emulator Mechanics (Triple-O)

Adapted from *Triple-O: The Player Character Emulator* by Cezar Capacle under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

The **Character Emulator** answers *"What does this character do?"* while your chosen tabletop RPG system answers *"Does it work?"*. It gives autonomous personality and decision-making to companions, party members, hirelings, allies, and recurring NPCs without requiring the solo player to direct every action.

### The Behavioral Prompt Formula
When rolling an action for an NPC, the emulator generates **3 independent prompts**, each combining:
$$\text{Weighted Trait} + \text{d66 Action} + \text{1d6 Triple-O Check} = \text{Behavioral Prompt}$$

1. **Trait Selection (Weighted):**
   - **Default (Weight 1):** Foundational traits.
   - **Prevalent (Weight 2):** Dominant personality quirks or backgrounds that appear twice as often.
   - **Temporary (Weight 1):** Fleeting conditions, injuries, or moods.
   - *Zero Traits Rule:* NPCs do not need traits to roll actions. If an NPC has 0 traits, `DEFAULT` is used as a display-only placeholder without storing fake traits.
2. **Specific Action Tables (d66):**
   Seven distinct 36-entry tables covering all adventuring situations:
   - **Combat:** Offensive tactics, maneuvers, repositioning, and morale checks.
   - **Social:** Persuasion, leverage, deception, empathy, and intimidation.
   - **Exploration:** Wilderness navigation, foraging, scouting, and tracking.
   - **Delving:** Underground tactics, searching for mechanisms, testing rooms, and formations.
   - **Interpretation:** How the character perceives ambiguous discoveries, omens, or secrets.
   - **Downtime:** Campfire conversations, personal traditions, coping vices, and bonding.
   - **Planning:** Tactical preparation, divinations, gathering intel, and risk assessment.
3. **Triple-O Check (1d6):**
   Determines how characteristic or unexpected the action is:
   - **1:** `THE ODD` (16.67% — surprising, unorthodox, or out-of-character choice)
   - **2–3:** `THE OPTION` (33.33% — sensible alternative, unexpected variation)
   - **4–6:** `THE OBVIOUS` (50.00% — standard, instinctive, or expected reaction)

### Spark Tables
Six 36-entry inspiration tables (`data/character_sparks.json`) provide immediate answers when behavior or motivation is uncertain:
- **Action:** What they are doing.
- **Focus:** What they are paying attention to or concerned with.
- **Method:** How they approach the situation.
- **Disposition:** Their current mood or attitude.
- **Motivation:** Underlying drive, fear, or desire.
- **Dynamics:** How the character relates to another companion or NPC.
- **Predefined Combinations:** `Action + Focus`, `Action + Method`, `Action + Motivation`.

### Party Member & Current Rules
- **Current:** Marks NPCs physically present in the active scene. Removing Current never deletes the NPC.
- **Party Members:** Always active in the party. If an NPC is marked as a Party Member, `Current` is strictly required (`Party Member = true` forces `Current = true`).
- **Unchecking Party Member:** Keeps `Current = true` (the character leaves the party but remains in the scene).
- **Preventing Invalid State:** Unchecking `Current` while `Party Member` is active is prevented with a clear explanation: *"Party Members are always Current. Uncheck Party Member first."*
- **Persistent Library:** All characters and traits are saved in SQLite. Use **Find NPC** or **Manage NPCs** to activate, edit, or search any saved character.

---

## 4. Directory Structure

```text
solo-ttrpg-tools/
├── app.py                      # Flask web application & API routes (Dungeon + Emulator)
├── config.py                   # Centralized configuration & environment variables
├── database.py                 # SQLite schema (dungeons, rooms, logs, npcs, traits)
├── dice.py                     # Dice parser (1d6, 2d6, d12, d66) & Progress dice pool
├── dungeon_engine.py           # Procedural referee: rooms, tension clock, search
├── emulator_engine.py          # Character Emulator engine: Triple-O, weighted traits, sparks
├── table_loader.py             # TableManager: startup validation & recursive subtable engine
├── solo-ttrpg-tools.service    # Production systemd service unit file
├── requirements.txt            # Python dependencies (Flask, Gunicorn, Pytest)
├── README.md                   # This documentation guide
├── .gitignore                  # Excludes .venv, pycache, and database files
├── data/                       # Modular JSON roll tables
│   ├── dungeon_types.json      # d12 Dungeon types (Cave, Tomb, Fort, Temple, Ruins, Sewers)
│   ├── dungeon_sizes.json      # Dungeon size definitions & hidden floor ranges
│   ├── dungeon_names.json      # Composable type-specific naming vocabulary
│   ├── descriptors.json        # d66 Room Descriptors
│   ├── routes.json             # 2d6 Route counts, physical vocabulary & conditions
│   ├── contents.json           # 2d6 Room Contents with subtable links
│   ├── hazards.json            # d12 Hazards table (linking to Traps)
│   ├── traps.json              # d20 Traps table (dual description: warning & reveal)
│   ├── curios.json             # d12 Interactive Curios with interaction_table fields
│   ├── puzzles.json            # d8 System-neutral puzzle scenarios
│   ├── search.json             # 2d6 Search table with recursive links & secret route action
│   ├── search_trouble.json     # d6 Search Trouble subtable
│   ├── tension_events.json     # d6 Hourly tension event roll table
│   ├── unique_rooms.json       # Unique landmark rooms by dungeon type
│   ├── room_objects.json       # d100 Room Objects (furniture, fixtures, misc junk)
│   ├── character_actions.json  # 7 d66 Action tables (Combat, Social, Exploration, Delving, etc.)
│   ├── character_sparks.json   # 6 d66 Spark tables (Action, Focus, Method, Disposition, etc.)
│   └── rooms/                  # Type-specific room type tables
│       ├── tomb.json           # d12 Tomb room types
│       ├── cave.json           # d12 Cave room types
│       ├── fort.json           # d12 Fort room types
│       ├── temple.json         # d12 Temple room types
│       ├── ruins.json          # d12 Ruins room types
│       └── sewers.json         # d12 Sewers room types
├── instance/
│   └── solo_tools.db           # SQLite database (auto-created on first run)
├── static/
│   ├── css/
│   │   └── style.css           # Dark fantasy / parchment responsive stylesheet
│   └── js/
│       ├── app.js              # Name generator, modal controllers, log export handlers
│       └── emulator.js         # Character Emulator card toggles, action rolls, sparks
├── templates/
│   ├── base.html               # Base layout, typography & modal dialogs
│   ├── index.html              # Main menu (Dungeon Crawler + Character Emulator)
│   ├── dungeon_menu.html       # Saved dungeons list & resume/delete
│   ├── dungeon_new.html        # New dungeon setup form
│   ├── dungeon_play.html       # Primary room exploration interface
│   ├── emulator.html           # Character Emulator roster & modal controllers
│   └── emulator_card.html      # Individual NPC card component
└── tests/
    ├── test_phase1.py              # Mechanics, dice, and engine tests (23 tests)
    ├── test_dungeon_app.py         # End-to-end integration & persistence tests (15 tests)
    └── test_character_emulator.py  # Character Emulator acceptance & API tests (23 tests)
```

---

## 5. Installation Guide (Debian LXC / Linux)

### Step 1: Install System Prerequisites
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git sqlite3
```

### Step 2: Deploy Project Code
Place the project into `/opt/solo-ttrpg-tools`:
```bash
sudo mkdir -p /opt/solo-ttrpg-tools
sudo chown -R $USER:$USER /opt/solo-ttrpg-tools
cp -r . /opt/solo-ttrpg-tools/
cd /opt/solo-ttrpg-tools
```

### Step 3: Create Python Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### Step 4: Run the Automated Test Suite
Verify all 61 unit and integration tests pass:
```bash
PYTHONPATH=. .venv/bin/pytest -v
```

### Step 5: Run the Server

#### Development Mode
```bash
.venv/bin/python3 app.py
```
Access in your browser at `http://<SERVER_IP>:8080`.

#### Production Mode (Gunicorn)
Run with 3 worker processes bound to all interfaces:
```bash
.venv/bin/gunicorn --workers 3 --bind 0.0.0.0:8080 app:app
```

---

## 6. Systemd Service Setup (Auto-Start on Boot)

1. Copy the included service file into systemd:
   ```bash
   sudo cp solo-ttrpg-tools.service /etc/systemd/system/
   ```

2. Edit the service file if your user or directory differs:
   ```bash
   sudo nano /etc/systemd/system/solo-ttrpg-tools.service
   ```
   *(Ensure `User=`, `Group=`, and `WorkingDirectory=` match your deployment).*

3. Reload systemd and enable the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now solo-ttrpg-tools
   ```

4. Check status:
   ```bash
   sudo systemctl status solo-ttrpg-tools
   ```

5. View live logs:
   ```bash
   journalctl -u solo-ttrpg-tools -f
   ```

---

## 7. Configuration Options

Set configuration options as environment variables in `/etc/systemd/system/solo-ttrpg-tools.service` or your shell:

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `8080` | Port the web application listens on |
| `HOST` | `0.0.0.0` | Network interface binding |
| `DEBUG_DUNGEON_ROLLS` | `false` | When `true`, displays a debug banner on the play screen with progress pool, raw dice rolls, and successes |
| `SOLO_TOOLS_DB` | `instance/solo_tools.db` | Path to the SQLite database file |
| `SECRET_KEY` | *(dev key)* | Secret key for Flask session security |

---

## 8. Customizing Roll Tables (JSON)

All table content is separated from the engine logic. To modify, add, or replace tables, edit the JSON files in `data/`.

The table engine supports:

### Range Tables (`min` and `max`)
Evaluated against standard dice notation (`2d6`, `d12`, `d66`, `d6`):
```json
{
  "name": "hazards",
  "dice": "d12",
  "entries": [
    { "min": 1, "max": 1, "name": "Trap", "subtable": "traps" },
    { "min": 2, "max": 2, "name": "Unstable ceiling", "description": "Loose masonry falls." }
  ]
}
```

### Recursive Subtables
Any entry can include `"subtable": "<table_id>"`. When that entry is rolled, the engine automatically rolls on the referenced subtable and nests the result.
*Example:* `contents.json` (Hazard) $\rightarrow$ `hazards.json` (Trap) $\rightarrow$ `traps.json`.

### Weighted Lists
Entries rolled based on relative weights:
```json
{
  "entries": [
    { "value": "Heavy wooden door", "weight": 2 },
    { "value": "Iron gate", "weight": 1 }
  ]
}
```

### Compositional Routes (`routes.json`)
Routes are assembled from three distinct data-driven components:
1. **Structure roll:** Roll on 2d6 to determine number of routes and conditions (`normal`, `stuck`, `locked`, `blocked`, `unusual`).
2. **Physical vocabulary:** Roll for the door/passage description (`Stone archway`, `Heavy wooden door`).
3. **Condition modifier:** Applied to the description (e.g. `Heavy wooden door (stuck)`).

---

## 9. Database Backup & Restore

All saved dungeons, room history, and exploration logs are preserved in `instance/solo_tools.db`.

### Create a Live Backup
Use SQLite's safe online backup command:
```bash
sqlite3 instance/solo_tools.db ".backup 'instance/solo_tools_backup_$(date +%Y%m%d_%H%M%S).db'"
```

### Restore from Backup
```bash
sudo systemctl stop solo-ttrpg-tools
cp instance/solo_tools_backup_YYYYMMDD_HHMMSS.db instance/solo_tools.db
sudo systemctl start solo-ttrpg-tools
```

---

## 10. Updating the Application Without Losing Saves

The database file (`instance/solo_tools.db`) is git-ignored and self-contained in `instance/`.

To update the application safely:
```bash
cd /opt/solo-ttrpg-tools

# 1. Back up database first
sqlite3 instance/solo_tools.db ".backup 'instance/solo_tools_pre_update.db'"

# 2. Pull or copy updated code
git pull

# 3. Update virtual environment dependencies if requirements changed
.venv/bin/pip install -r requirements.txt

# 4. Restart the service
sudo systemctl restart solo-ttrpg-tools
```
All active dungeons, floor levels, search histories, and logs will remain untouched.

---

## 11. Dungeon Log & Obsidian Export

During exploration, all events (room entries, discoveries, searches, and tension checks) are automatically logged.

- Click **View Log** on the play screen to view the chronological delve record with elapsed time stamps.
- Click **Export Plain Text** to download a clean `.txt` log.
- Click **Export Markdown** to download a formatted `.md` log ready to drag and drop directly into **Obsidian** or your solo campaign notebook.

