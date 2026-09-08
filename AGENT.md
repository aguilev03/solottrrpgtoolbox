# SOLO TTRPG TOOLS — Agent & Developer Guide

This document serves as the comprehensive architectural reference, implementation history, and development blueprint for AI agents and human developers maintaining and extending **SOLO TTRPG TOOLS**.

---

## 1. System Vision & Design Philosophy

**SOLO TTRPG TOOLS** is a lightweight, self-hosted web application providing system-neutral procedural referee engines for solo tabletop roleplaying games.

### Non-Negotiable Core Rules:
1. **Procedural GM / Referee, NOT a VTT or Combat Simulator:**
   - The software answers: *"What exists?", "What happens next?", "What does this NPC do?"*
   - The software **never** answers: *"Does it hit?", "How much damage does it take?", "Do you pass the DC check?"*
   - No character stats (HP, AC, Ability Scores, Spell Slots), no combat simulators, no turn-order initiative, and no AI text generation/storytelling.
2. **Emergent Delving & Behavior (Zero Pre-Generation):**
   - Dungeons and character actions come into existence only as the solo player takes action.
   - Hidden variables (such as floor count and progress pool) preserve tension and uncertainty.
3. **Extreme Simplicity & Self-Hosted Portability:**
   - Single Python/Flask web server running on port `8080`.
   - Single SQLite database file (`instance/solo_tools.db`).
   - Zero frontend build step: No Node.js, npm, webpack, or external CDNs required.
   - Fast deployment in Debian LXC containers, Raspberry Pis, or homelab servers.
4. **Cross-Device Persistence:**
   - All state is preserved server-side in SQLite.
   - Navigating away, closing the browser, or switching from desktop to tablet/phone immediately resumes the exact delver/character state.

---

## 2. Technical Stack & Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    Web Browser (Client)                     │
│  Dark Fantasy / Parchment Theme (CSS Grid, Variables)       │
│  Vanilla JavaScript (Fast AJAX, Modals, Dynamic Injection)  │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON API
┌──────────────────────────────▼──────────────────────────────┐
│                    Flask Application (app.py)               │
│  Central routing, context processors, JSON REST endpoints   │
├──────────────────────────────┬──────────────────────────────┤
│      Engines & Logic         │      Persistence Layer       │
│  - dungeon_engine.py         │  - database.py (SQLite)      │
│  - emulator_engine.py        │  - Atomic transactions       │
│  - table_loader.py           │  - Dynamic PRAGMA migrations │
│  - dice.py                   │  - instance/solo_tools.db    │
├──────────────────────────────┴──────────────────────────────┤
│                    Modular Data Tables                      │
│  data/*.json (Dungeon tables, Actions, Sparks, Objects)     │
└─────────────────────────────────────────────────────────────┘
```

- **Backend:** Python 3.10+ with Flask and Gunicorn.
- **Database:** SQLite 3 with WAL mode, foreign key enforcement, and non-destructive schema migrations.
- **Frontend:** Semantic HTML5 (`Jinja2`), pure modern CSS3 with CSS variables and responsive `auto-fit` grids, and modular ES6 JavaScript.
- **Testing:** `pytest` suite ensuring 100% test passing and zero regressions.

---

## 3. What Has Been Implemented So Far

### A. Core Platform & Infrastructure
- **Unified Main Menu (`templates/index.html`):**
  Extensible tools grid with dedicated launcher cards for active and upcoming modules.
- **Centralized Layout & Base Template (`templates/base.html`):**
  Global navigation, modal shells, dark fantasy styling, and breadcrumb trails.
- **Styling Architecture (`static/css/style.css`):**
  Dark fantasy parchment aesthetic using custom CSS properties (`--bg-dark`, `--gold-primary`, `--border-accent`, etc.), responsive touch targets, and flexible grid layouts.
- **Service Configuration (`solo-ttrpg-tools.service`):**
  Production-ready systemd unit file for headless background service operation.

---

### B. Module 1: Dungeon Crawler
A procedural, room-by-room subterranean delve referee.

1. **Pure Progress Dice Pool Mechanic (`dice.py`, `dungeon_engine.py`):**
   - Starts at **1D6** (`progress_points = 0`).
   - Evaluates dice: 5 or 6 = 1 success; 1, 2, 3, 4 = blank.
   - **0 Successes (Failure):** Generates normal room; progress pool remains unchanged.
   - **1 Success (Weak Success):** Generates normal room; `progress_points += 1` (+1D6 for next delve), surfaces `Progress made! X → Y`.
   - **2+ Successes (Strong Success):** Generates the Unique Room for the current floor.
   - **Floor Descent:** Descents reset progress to **1D6** for the new level.
2. **Hidden Floors & Dungeon Size:**
   - Governs floor depth without altering the Progress dice pool:
     - Small = 1 floor | Medium = 1–2 floors | Large = 2–3 floors | Random = rolls size first.
3. **Compass Route Directions:**
   - Every route in a chamber receives an arrow and unique compass direction (`↑ North` to `↖ Northwest`) picked without replacement.
   - Routes remain non-clickable descriptions for player journal mapping.
4. **Tension Clock:**
   - Tracks 10 minutes per action (`Generate Room` or `Search`).
   - Every 6 actions (1 hour), the engine triggers an hourly tension/encounter event from `data/tension_events.json`.
5. **Chamber Searching:**
   - Each chamber can be searched once. Locks to `[ ✓ Searched ]`.
   - Secret routes discovered dynamically append to the current room's route list with an unused compass direction.
6. **Dual-State Trap Reveal System:**
   - Traps have two persistent states: **Hidden/Unidentified** and **Revealed**.
   - Displays subtle, ambiguous **Warning** (e.g. *"The floor gives a faint creak beneath your weight"*).
   - Clicking `[ Reveal ]` reveals the specific trap name and mechanism (e.g. *Pitfall*).
   - No mechanical checks or damage rolls; state persists in SQLite across reloads.
7. **Room Objects & Furnishings (`data/room_objects.json`):**
   - 100-entry `d100` roll table covering furniture, storage, fixtures, tools, and atmospheric debris.
   - Rolls exactly 3 distinct items without replacement for every newly generated chamber.
   - Serialized into `objects_json` on the room record in SQLite.
8. **Delve Log & Exports:**
   - Auto-logging of delve events with elapsed timestamps.
   - Plain Text (`.txt`) and Obsidian Markdown (`.md`) export downloads.

---

### C. Module 2: Character Emulator (Triple-O)
Based on *Triple-O: The Player Character Emulator* by Cezar Capacle (adapted under CC BY-SA 4.0).

1. **Solo Role Separation:**
   - The solo player directly controls their **Main Character**.
   - The Character Emulator controls party members, companions, hirelings, allies, and recurring NPCs.
2. **The Behavioral Prompt Loop:**
   - Formula: **Weighted Trait + d66 Action + 1d6 Triple-O Check = Behavioral Prompt**.
   - Generates exactly **3 independent prompts** inside the NPC's card.
3. **Specific Action Tables (`data/character_actions.json`):**
   - 7 distinct 36-entry tables: *Combat, Social, Exploration, Delving, Interpretation, Downtime, Planning*.
4. **Spark Tables (`data/character_sparks.json`):**
   - 6 tables: *Action, Focus, Method, Disposition, Motivation, Dynamics*.
   - Predefined dual combinations: *Action + Focus*, *Action + Method*, *Action + Motivation*.
5. **Triple-O Check (1d6):**
   - 1 = **THE ODD** (16.67%)
   - 2–3 = **THE OPTION** (33.33%)
   - 4–6 = **THE OBVIOUS** (50.00%)
6. **Weighted Trait Selection:**
   - Statuses: `Default` (weight 1), `Prevalent` (weight 2), `Temporary` (weight 1).
   - Prevalent traits appear twice as often in generated prompts.
7. **Zero Traits Rule:**
   - NPCs can be created with only a Name and immediately rolled.
   - When an NPC has 0 traits, `DEFAULT` is used as a display-only placeholder without storing fake records.
8. **Party Member vs Current Rules:**
   - `Party Member = true` strictly requires `Current = true`.
   - Unchecking `Party Member` keeps `Current = true` (NPC leaves party but remains in scene).
   - Unchecking `Current` while `Party Member` is active is rejected: *"Party Members are always Current. Uncheck Party Member first."*
   - Removing `Current` never deletes an NPC; characters remain in the persistent library.
9. **UI & Management:**
   - Auto-reflowing responsive grid: `repeat(auto-fit, minmax(350px, 1fr))`.
   - Section headers for `PARTY MEMBERS` and `CURRENT NPCs` (empty sections are suppressed).
   - Modals for *+ Add NPC*, *+ Trait* (quick-add), *Edit NPC*, *Find NPC*, and *Manage NPCs* with confirmed permanent deletion.

---

## 4. In-Depth Module Architecture & Design (For Future Agents)

### 4.1 Dungeon Crawler Architecture (`dungeon_engine.py`, `table_loader.py`, `dice.py`)

#### Design Goal
The Dungeon Crawler module acts as an impartial, procedural referee for room-by-room exploration. It solves the solo player's dilemma of wanting an unpredictable delve without having to manually consult dozens of physical books or spoil dungeon layouts in advance.

#### Core State Model (`dungeon_engine.py` & `database.py`)
- **`DungeonState`**:
  - `id`: Database primary key.
  - `name`: Generated or user-specified title.
  - `dungeon_type`: Cave, Tomb, Fort, Temple, Ruins, Sewers.
  - `size`: Small, Medium, Large, Random.
  - `current_level`: Active floor level (1-indexed).
  - `hidden_total_levels`: Hidden floor depth determined at creation (Small=1, Medium=1–2, Large=2–3).
  - `current_room_number`: Sequential room number for the delve.
  - `elapsed_minutes`: Total delve time, increments by +10 minutes per exploration or search action.
  - `tension_dice`: Die count (0–5). Reaches 6 to trigger an automatic hourly event, then resets to 0.
  - `progress_points`: Core mechanic pool modifier. The active dice pool size is always `progress_points + 1`.
  - `current_room_id`: Foreign key pointer to the active chamber.
  - `is_complete`: Boolean flag set when descending the final floor.
- **`RoomState`**:
  - `level`, `room_number`: Position in delve hierarchy.
  - `descriptor`: Atmospheric chamber feature rolled on d66 (`descriptors.json`).
  - `room_type`: Type-specific architecture rolled from `rooms/<type>.json`.
  - `is_unique`: Flag indicating the floor landmark/exit chamber.
  - `is_entrance`: Flag for the floor threshold.
  - `contents_type` & `contents_data`: Parsed outcome from `contents.json`, resolving nested subtables (`hazards`, `curios`, `puzzles`).
  - `has_trap`, `trap_revealed`, `trap_data`: Dual-state hazard mechanism.
  - `routes`: Structured list of door/passage dictionaries (`direction`, `arrow`, `text`).
  - `objects`: 3 atmospheric furnishings rolled without replacement from `room_objects.json`.
  - `searched` & `search_result`: One-time inspection status and outcome.

#### Step-by-Step Delve Lifecycle
1. **Creation & Entrance:**
   - On `POST /dungeon/new`, `engine.determine_hidden_floors(size)` rolls hidden depth.
   - `engine.generate_entrance_room(dungeon)` generates Room 1 (Level 1) **without** rolling on the progress pool. It rolls room type (index 1 of type table), descriptor, 1+ routes, and 3 objects.
   - Initial log entry created at `00:00`.
2. **Action: Explore (`engine.explore(dungeon, current_room)`):**
   - **Time & Tension:** `elapsed_minutes += 10`, `tension_dice += 1`. If `tension_dice == 6`, an hourly event is rolled on `tension_events.json`, logged, and `tension_dice` resets to 0.
   - **Progress Pool Evaluation:** The engine rolls `number_of_dice = progress_points + 1` six-sided dice.
     - `successes = count(rolls >= 5)`.
     - *Strong Success (2+ successes):* Triggers Unique Room generation. `is_unique = True`. If `current_level < hidden_total_levels`, `next_level_exists = True`.
     - *Weak Success (1 success):* Generates normal room. `progress_points += 1`. Logs `Progress made! X → Y`.
     - *Failure (0 successes):* Generates normal room. `progress_points` unchanged.
   - **Chamber Resolution:**
     - Rolls architecture from `rooms/<type>.json`.
     - Rolls contents from `contents.json` (2d6). If Hazard/Trap is rolled, initial `has_trap = True` and `trap_revealed = False`.
     - Rolls routes from `routes.json` (2d6 for structure/count, physical door type, and condition). Assigns unique compass directions from the 8 cardinal points without repetition in the room.
     - Rolls 3 distinct objects from `data/room_objects.json` using `random.sample()`.
3. **Action: Search (`engine.search(dungeon, room)`):**
   - Validates `room.searched is False`.
   - Advances time +10 minutes and tension +1.
   - Rolls 2d6 on `search.json`. If result is "Secret route", a new passage is dynamically created and appended to the current room's visible routes with an unused compass direction.
4. **Action: Trap Reveal (`engine.reveal_trap(room)`):**
   - When a trap is present, the player initially sees an ambiguous warning (e.g. *"You hear a quiet hiss that wasn't there a moment ago"*).
   - After resolving any check in their solo RPG system, clicking `[ Reveal ]` reveals the trap name and mechanism (e.g. *Poison Gas*).
   - Saved to SQLite (`trap_revealed = 1`).
5. **Action: Descend Floor:**
   - Available only in Unique Rooms when `next_level_exists = True`.
   - Increments `current_level += 1`, resets `progress_points = 0`, generates the Entrance Room for the new level, and resets visual Progress to 1.

---

### 4.2 Character Emulator Architecture (`emulator_engine.py`, `database.py`)

#### Design Goal
Based on Cezar Capacle's *Triple-O: The Player Character Emulator* (CC BY-SA 4.0), this module answers *"What does this character do?"* for companions, party members, hirelings, allies, and recurring NPCs. The player directly directs their Main Character, while the emulator provides autonomous, emergent behavioral prompts for everyone else.

#### Core State Model (`database.py`)
- **`npcs` Table:**
  - `id`: Auto-increment integer primary key.
  - `name`: Character name (required).
  - `details`: Background notes, role, or concept.
  - `current`: Boolean (0 or 1). Determines if the character is active in the current scene.
  - `party_member`: Boolean (0 or 1). Determines if the character is an active adventuring companion.
- **`npc_traits` Table:**
  - `id`: Primary key.
  - `npc_id`: Foreign key to `npcs.id` with `ON DELETE CASCADE`.
  - `status`: `default` (weight 1), `prevalent` (weight 2), or `temporary` (weight 1).
  - `trait`: Descriptive text (e.g. *"Protective"*, *"Grew up on a farm"*, *"Injured leg"*).
  - `category`: Classification tag (`PR` = Personality, `SK` = Skill, `BG` = Background, `CL` = Class, `CN` = Condition, `MT` = Motivation, or custom tags like `RL`, `GO`).

#### Invariants & State Rules
1. **Party Member Implication:**
   If `party_member == True`, then `current` **must** equal `True`. Party members are always present in the scene.
2. **Invalid State Rejection:**
   Attempting to set `current = False` while `party_member == True` is rejected in `database.py` and via HTTP 400: *"Party Members are always Current. Uncheck Party Member first."*
3. **Leaving Party:**
   Unchecking `party_member` sets `party_member = False` while preserving `current = True`. The character remains in the scene (moving from PARTY MEMBERS to CURRENT NPCs).
4. **Persistent Library:**
   Setting `current = False` removes an NPC from the main emulator screen, but the character remains permanently in SQLite. Characters can be searched and made current again at any time using **Find NPC** or **Manage NPCs**.

#### The Triple-O Randomization Pipeline (`emulator_engine.py`)
Each time **Roll Action** is pressed, the engine generates **3 independent prompts**:
1. **Weighted Trait Draw (`select_weighted_trait(traits)`):**
   - Prevalent traits have twice the selection probability:
     $$\text{Weight}(\text{prevalent}) = 2.0, \quad \text{Weight}(\text{default}) = 1.0, \quad \text{Weight}(\text{temporary}) = 1.0$$
   - Drawn using `random.choices(traits, weights=weights, k=1)[0]`.
   - *Zero Traits Rule:* If an NPC has 0 traits, the engine returns `{"trait": "DEFAULT", "status": "Default", "is_placeholder": True}`. Roll Action is never disabled, and no fake database records are created.
2. **Action d66 Roll (`roll_d66()`):**
   - Rolls two independent six-sided dice: $\text{tens} \times 10 + \text{ones}$.
   - Valid d66 values: 11–16, 21–26, 31–36, 41–46, 51–56, 61–66.
   - Looks up the result in the selected table from `data/character_actions.json` (Combat, Social, Exploration, Delving, Interpretation, Downtime, Planning).
3. **Triple-O Check (`roll_triple_o()`):**
   - Rolls an independent **1d6**:
     - **1:** `THE ODD` (16.67% — unexpected, surprising, or counter-intuitive choice)
     - **2–3:** `THE OPTION` (33.33% — viable alternative, pragmatic variation)
     - **4–6:** `THE OBVIOUS` (50.00% — standard, instinctive, or expected reaction)
   - Every prompt in the 3-prompt set receives its own independent roll.

#### Spark Tables Pipeline (`data/character_sparks.json`)
- Allows quick rolling of inspiration tables: *Action, Focus, Method, Disposition, Motivation, Dynamics*.
- Predefined dual combinations (`Action + Focus`, `Action + Method`, `Action + Motivation`) roll two independent d66s simultaneously.
- Results appear in a compact sub-panel inside the specific NPC card for immediate reference.

---

## 5. Current File Inventory

```text
solo-ttrpg-tools/
├── app.py                         # Web routes, API endpoints, Flask application
├── config.py                      # Application environment settings
├── database.py                    # SQLite persistence, schema, migrations
├── dice.py                        # Dice rollers (1d6, 2d6, d12, d66, Progress pool)
├── dungeon_engine.py              # Delve engine (rooms, tension, search, traps)
├── emulator_engine.py             # Triple-O engine (traits, actions, sparks)
├── table_loader.py                # JSON table manager & recursive resolution
├── solo-ttrpg-tools.service       # Systemd unit file
├── requirements.txt               # Dependencies: Flask, gunicorn, pytest
├── README.md                      # End-user & deployment documentation
├── AGENT.md                       # Developer architecture & roadmap guide
├── .gitignore                     # Git rules for venv, cache, sqlite, logs
├── data/
│   ├── dungeon_types.json         # d12 Dungeon themes
│   ├── dungeon_sizes.json         # Hidden floor depth definitions
│   ├── dungeon_names.json         # Procedural naming vocabulary
│   ├── descriptors.json           # d66 Chamber descriptors
│   ├── routes.json                # 2d6 Route counts, doors, conditions
│   ├── contents.json              # 2d6 Room contents & subtable links
│   ├── hazards.json               # d12 Hazards table
│   ├── traps.json                 # d20 Traps table (warning & reveal)
│   ├── curios.json                # d12 Interactive curios
│   ├── puzzles.json               # d8 Puzzle scenarios
│   ├── search.json                # 2d6 Search roll table
│   ├── search_trouble.json        # d6 Search trouble subtable
│   ├── tension_events.json        # d6 Hourly tension events
│   ├── unique_rooms.json          # Landmark rooms by dungeon type
│   ├── room_objects.json          # d100 Room objects roll table
│   ├── character_actions.json     # 7 d66 Triple-O Action tables
│   ├── character_sparks.json      # 6 d66 Triple-O Spark tables
│   └── rooms/                     # Type-specific room type tables
│       ├── tomb.json, cave.json, fort.json, temple.json, ruins.json, sewers.json
├── instance/
│   └── solo_tools.db              # SQLite runtime database
├── static/
│   ├── css/style.css              # Dark fantasy / parchment stylesheet
│   └── js/
│       ├── app.js                 # Global utilities & delve handlers
│       └── emulator.js            # Character Emulator interactive logic
├── templates/
│   ├── base.html                  # Base layout & modal containers
│   ├── index.html                 # Tools hub launcher
│   ├── dungeon_menu.html          # Delve launcher & saved campaigns
│   ├── dungeon_new.html           # New dungeon configuration form
│   ├── dungeon_play.html          # Dungeon delve play interface
│   ├── emulator.html              # Character Emulator main view & modals
│   └── emulator_card.html         # Modular NPC card component
└── tests/
    ├── test_phase1.py             # Dungeon mechanics & engine tests (23 tests)
    ├── test_dungeon_app.py        # Dungeon app integration tests (15 tests)
    └── test_character_emulator.py # Character Emulator tests (23 tests)
```

---

## 6. Developer Blueprint: How to Add a New Tool

When tasked with adding a new tool (e.g. *Oracle & Sparks*, *Wilderness Delver*, *Faction Matrix*), follow this battle-tested step-by-step procedure:

### Step 1: Define Data Tables in `data/`
- Create modular JSON files under `data/`.
- Use clean, structured formats (e.g., standard dice range tables or key-mapped dictionaries).
- Never hard-code roll table results in Python strings or JavaScript.

### Step 2: Implement the Engine in `<module>_engine.py`
- Write modular, testable logic separated from web and UI concerns.
- Reuse `dice.py` for standard dice rolls (`roll_die`, `roll_d66`, `roll_notation`).
- Structure returns as Python dictionaries or dataclasses.

### Step 3: Extend Database Schema in `database.py`
- Add new tables in `Database.init_db()` using `CREATE TABLE IF NOT EXISTS`.
- If modifying existing tables, use `PRAGMA table_info(...)` checks to add columns safely without breaking existing user saves.
- Add indexes on foreign keys and frequently filtered columns.
- Implement atomic helper methods on `Database` (`create_*`, `get_*`, `list_*`, `update_*`, `delete_*`).

### Step 4: Add Flask Routes & APIs in `app.py`
- Add main page route (e.g. `GET /<module>`).
- Add JSON REST API endpoints for interactive actions so the page does not need full reloads for simple rolls.
- Handle errors gracefully and return JSON `{ "success": false, "error": "..." }` with appropriate HTTP status codes.

### Step 5: Wire Navigation in `templates/index.html`
- Update the `.tools-grid` in `templates/index.html` to convert the placeholder slot into an active `<a href="..." class="tool-card active">`.

### Step 6: Create Templates & Components in `templates/`
- Inherit from `base.html`.
- Use `{% block main_class %}main-content-wide{% endblock %}` if the tool requires multi-column card reflow.
- Provide breadcrumb navigation back to `url_for('index')`.
- Build modular sub-components (using `{% include "..." %}`) for repeatable cards or complex rows.

### Step 7: Style with CSS in `static/css/style.css`
- Reuse existing CSS variables (`--bg-card`, `--gold-primary`, `--border-accent`, etc.).
- Ensure tablet and mobile responsiveness:
  - Use `grid-template-columns: repeat(auto-fit, minmax(..., 1fr))`.
  - Ensure touch targets are at least 44px.
  - Test on viewport widths from 360px up to 1920px.

### Step 8: Client-Side Interactivity in `static/js/<module>.js`
- Write clean, vanilla JavaScript (no npm dependencies).
- Use `fetch()` with `async/await` to call backend endpoints.
- Provide immediate visual feedback on errors or state locks.

### Step 9: Write Automated Tests in `tests/test_<module>.py`
- Test randomization logic, edge cases, weighting, and constraints.
- Test database operations, cascade deletes, and persistence across fresh connections.
- Test Flask HTTP routes and JSON API endpoints using pytest's `client`.
- **Run the full test suite (`PYTHONPATH=. .venv/bin/pytest -v`) to ensure 100% pass rate and zero regressions.**

---

## 7. Future Roadmap / Development Plan

The following modules are planned for future integration into **SOLO TTRPG TOOLS**:

### Priority 1: Oracle & Sparks (GM Emulator)
- **Purpose:** System-neutral probability oracle for solo yes/no questions.
- **Mechanics:**
  - Odds selector: *Likely, 50/50, Unlikely, Certain, Near Impossible*.
  - Dual d6 or d100 roll resolving: *Yes, And...*, *Yes*, *Yes, But...*, *No, But...*, *No*, *No, And...*.
  - Chaos / Tension Factor that tracks campaign instability and triggers unexpected scene interruptions.
  - General Spark generator combining verbs, nouns, and adjectives for open-ended interpretation.

### Priority 2: Wilderness & Overland Travel
- **Purpose:** Procedural travel referee for hex delves, road travel, and uncharted exploration.
- **Mechanics:**
  - Day/Watch tracker (Morning, Afternoon, Evening, Night).
  - Terrain generation (Forest, Mountains, Marsh, Plains, Desert, Tundra).
  - Procedural weather shifts and navigation checks (lost in wilderness).
  - Foraging, camping, and random encounter clocks.

### Priority 3: Settlement & Faction Matrix
- **Purpose:** Living towns and dynamic NPC faction schemes.
- **Mechanics:**
  - Settlement generator: size, government, economic specialty, primary problem.
  - Faction tension clocks: factions pursue hidden agendas independently of the player.
  - Rumor table and district generator.

### Priority 4: Loot, Relic & Treasure Generator
- **Purpose:** System-neutral treasure generator that outputs evocative, atmospheric spoils rather than generic +1 swords.
- **Mechanics:**
  - Pocket change, trade goods, unusual curiosities, and ancient relics with narrative history and minor quirks.

### Priority 5: Unified Campaign Notebook & Obsidian Vault Export
- **Purpose:** Aggregate session logs across all tools into a single chronological timeline.
- **Mechanics:**
  - Export complete campaign history as a multi-file Markdown bundle ready to drag directly into an Obsidian vault.
