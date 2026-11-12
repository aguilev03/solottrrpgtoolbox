# Custom decks and spark tables

These two system-neutral libraries are separate from the Character Emulator and
its built-in Triple-O tables. Both appear on the home menu and use the existing
login guard. As with existing dungeons and NPCs, libraries are shared among
logged-in users of this installation; they are not private per-user collections.
A saved deck/table ID can be reopened from another device on the same server.

## Using decks

Create a named deck, expand **Deck settings & card library**, and upload one or
more card faces. PNG, JPG, JPEG and still WebP are supported, plus an optional
card back. Images keep their original dimensions and aspect ratios. Names are
optional and editable per card. Replace a face by deleting that card and uploading
the new image. Replacing a back removes the old back file.

Draws consume a shuffled, persisted pool. Each card can appear once per cycle.
The default reversal probability is 50%; set it to 0 to disable reversals or 100
for all reversed cards. Settings affect future draws. Cards stay on the tabletop
in draw order with their recorded orientation. Click a card or press Enter to
open its full-size image; Escape closes it. Dragging saves a bounded offset
(horizontal percentage of card width, vertical pixels) relative to the responsive
grid, so the arrangement adapts across screen sizes. Drag saves report failure
and restore the previous position if the server cannot save.

**Reshuffle** clears all drawn cards, orientation and offsets, restores the entire
pool and randomizes its order. It keeps names, images, settings and deck identity.
Uploading more cards mixes them into the remaining pool without changing existing
draws. Deleting a card removes it from both the library and tabletop.
Press **↻** under a drawn card to turn it 90° clockwise; the turn is saved and is
independent of the draw-time reversal.

## Using dealer's tables

A dealer's table (**Dealer's tables** in the custom-tools menu) is one large,
shared surface for dealing from any number of decks at once. Create as many named
tables as you like.

- **Deal**: the deck shelf shows every deck with its remaining count. Press a deck
  to draw its next card into the middle of the visible part of the table. Tick
  **Deal face down** to deal cards showing the deck's back (or a themed pattern
  when the deck has no back image). Draws share the deck's pool, so a card dealt to
  a table is no longer available on the deck's own page, and vice versa.
- **Arrange**: drag cards anywhere; the dragged card comes to the top. Tap or click
  a card for its action bar: rotate left/right 90°, flip face up/down, enlarge, or
  **Return** (shuffle it back into its deck's undrawn pool). With a card focused:
  `R` / `Shift+R` rotate, `F` flips, `Enter` enlarges, arrow keys nudge (Shift for
  larger steps), `Escape` deselects.
- **Pan and zoom**: drag empty table space with a mouse or pen, scroll, or swipe on
  touch screens. Zoom from 25% to 200% with the − / + buttons or Ctrl/⌘ + wheel
  (trackpad pinch).
- **Grow**: tables start at 2400 × 1600. Holding a card near the right or bottom
  edge of the view scrolls, and the table grows automatically as cards approach its
  far edges. **Wider** / **Taller** add space, and **Fit to cards** shrinks the table
  around the current spread. The maximum is 20000 × 20000.
- **Gather all cards** shuffles every card on the table back into its deck. Deleting
  a table does the same. Reshuffling a deck also pulls its cards off every table.

Positions, rotation, face-down state, stacking order and table size are saved in
SQLite on every change, so a table looks the same after a reload or on another
device.

### Saved layouts (suspend and resume)

Use **Saved layouts** to suspend a table and come back to it later, for example
one layout per dungeon room:

- **Save & clear table** stores every card's position, rotation, face-down state and
  stacking order, plus the table size, zoom and view, under a name (default
  `Save N`), then clears the table for the next spread.
- Saved cards stay **out of their decks**, so a suspended room's cards can't be drawn
  elsewhere in the meantime.
- **Resume** restores the layout exactly, including the zoom and where you were
  looking. If the table has cards on it, they are first saved automatically as
  `Auto-saved before resuming <name>`, so switching rooms never loses anything.
  Resuming removes the save from the list (save again when you leave).
- **Rename** a save at any time. **Discard** deletes it and shuffles its cards back
  into their decks. Deleting the table discards its saves too, and reshuffling a deck
  pulls its cards out of every saved layout.

## Using custom sparks

A compact **Fate Oracle** sits above the table buttons. Choose **Odds** and press
**Roll**. The server rolls an unbiased d100 (1–100 inclusive), resolves one of
Exceptional Yes, Yes, No or Exceptional No, and records the result, selected odds
and d100 value in the existing shared Spark log. The existing **Reset log** clears
Oracle and table rolls together. There is no separate Oracle history or database
migration. The selected odds are remembered in the current session, defaulting
to **50/50 or Unknown**.

The nine settings and inclusive ranges follow the **Ask The Game Master** chart
from *One-Page Mythic*, originally in *Mythic Magazine #25*, by Tana Pigeon /
[Word Mill Games](https://www.wordmillgames.com/onepagemythicgme.html).
The chart was verified against the [original magazine document](https://treasure.fractumseraph.net/books/Mythic%20Magazine%20Compilation%205/Mythic%20Magazine%20Volume%2025.pdf).


The main view uses three table columns on desktop, two on tablets and one on
phones. The table area takes approximately 65% of the desktop workspace, with a
sticky Spark log on the right. The log stays below navigation and scrolls its
entries independently; on phones it appears below the tables.

Press a table button to roll one entry with replacement. Rolls appear newest
first, with the table name beside each result. The shared log is saved in SQLite
across page reloads and devices, with no automatic 30-result cutoff. **Reset log**
clears this log without changing tables, sampling pools, or per-table recent
results. Editing or deleting a table also leaves the shared log intact.

Use the separate star button to add or remove a favorite without rolling.
Favorites appear above regular tables without duplication and stay visible while
searching. Search filters only regular table names, ignoring case. Favorites are
stored per authenticated user in SQLite and survive refreshes, logouts, logins
and restarts. When login is disabled, anonymous users can still roll and search;
they must sign in to save favorites. Tables and the log retain their existing
shared visibility. Favorite requests derive user identity from the session and
require the existing CSRF token. Deleting a user or table removes its favorites.

Expand **Manage tables** for the existing create, import, edit, delete, batch
and sampling controls. Batch rolls also append to the shared log. The separate
**Reset available entries** control restores only the selected sampling pool.

Create from pasted text or an uploaded UTF-8 `.txt`/`.json` file. A selected file
wins over pasted text. Each nonempty text line becomes an entry. JSON supports:

```json
["A distant bell", "An unexpected visitor"]
```

```json
{"name": "Omens", "entries": ["A distant bell", "An unexpected visitor"]}
```

```json
{"Omens": ["A distant bell", "An unexpected visitor"]}
```

A supplied name overrides the JSON name. Blank entries, non-string JSON entries,
unsupported structures and malformed JSON are rejected before writes occur.
The editor uses a JSON array to preserve strings containing embedded newlines.
Saving an edit resets that table's pool and recent results. Renaming uses the
same edit form. Invalid edits leave the saved table intact.

Generate 1–20 entries at once. With replacement is the default; each entry index
has equal probability on every roll. Without replacement consumes indices until
reset. Duplicate strings in the source are separate entries and can therefore
appear more than once. If a batch exceeds the remaining pool, the whole batch
is rejected. With-replacement rolls do not consume or reset the optional pool.
The latest batch is prominent; the last 30 results persist per table. There is
no limit on the number of tables, subject to disk space and server capacity.

## Persistence and migration

`Database.init_db()` retains the existing schema and records; initialization then
runs the additive, idempotent `custom_tools.migrate()` migration. New tables:

| Table | Contents |
| --- | --- |
| `custom_decks` | Name, reversal probability and optional back file |
| `custom_cards` | Deck FK, optional name, face file, unique shuffled rank, unique nullable draw order, reversal, x/y offset, `rotation` (0/90/180/270), dealer-table placement (`table_id`, `table_x`, `table_y`, `table_z`, `face_down`) |
| `custom_dealer_tables` | Name, `width`, `height` (pixels, 800/600–20000) |
| `custom_table_saves` | Table FK (cascade), name, table size, `zoom`, view centre (`view_x`, `view_y`), `created_at`; cards point at a save through `custom_cards.save_id` |
| `custom_spark_tables` | Name, JSON entry array, remaining entry indices, last sampling mode and batch size |
| `custom_spark_results` | Table FK and result text; increasing ID supplies chronology |
| `custom_spark_favorites` | User/table pair; foreign keys cascade on user or table deletion |
| `custom_spark_log` | Shared roll log with table-name snapshots and result text, retained until reset |

Foreign keys cascade deck/card and table/result deletes. Existing tables and
`data/character_sparks.json` are unchanged. Draws, reshuffles, pool changes and
uploads use `BEGIN IMMEDIATE` to serialize SQLite writers across threads/processes.
A draw selects and records the next available card inside one transaction;
concurrent requests cannot draw the same card. Reads use a consistent snapshot.
Connections close after each custom operation; writers wait up to 15 seconds.
An exhausted pool returns HTTP 409. Missing records return 404; invalid input or
CSRF tokens return 400; oversized requests return 413.

Original image bytes live in `instance/card_uploads/` by default, never in
`static/`. Client filenames are discarded in favor of random UUID basenames.
Extension, actual decoded format, byte size, pixel count, still-image status and
image integrity are validated using Pillow. Entire batches validate before any
file is written; database errors roll back and remove newly written files.
The application refuses a configured upload directory inside `static/`.

Back up **both the SQLite database and the upload directory**. Keep this directory
on persistent storage and grant write access only to the application account.
For consistent file/database backups, stop writes or stop the app during backup.
Do not expose the upload directory through a static web-server alias. Image routes
check deck membership and login, use safe directory serving and send private
cache and `nosniff` headers. Upload directories outside the repository must also
be excluded from any source archiving process.

## Configuration

All settings accept environment variables of the same name (integer limits):

| Setting | Default | Meaning |
| --- | --- | --- |
| `CARD_UPLOAD_DIR` | `<repository>/instance/card_uploads` | Permanent image directory |
| `MAX_CONTENT_LENGTH` | 33554432 | App-wide request size limit, 32 MiB |
| `CARD_MAX_IMAGE_BYTES` | 8388608 | Per-image size, 8 MiB |
| `CARD_MAX_PIXELS` | 20000000 | Maximum width × height |
| `CARD_MAX_UPLOAD_FILES` | 100 | Faces per upload, plus one optional back |
| `CARD_MAX_DECK_CARDS` | 2000 | Cards in a single deck |
| `SPARK_MAX_IMPORT_BYTES` | 1048576 | UTF-8 import/pasted text size, 1 MiB |
| `SPARK_MAX_ENTRIES` | 10000 | Entries per table; each at most 4000 characters |

Pillow is the only added dependency. Install the updated `requirements.txt`.
Existing `SOLO_TOOLS_DB`, cookie settings, login and reverse-proxy configuration
continue to apply. No localStorage is used. No production deployment is performed
by this feature.

## Routes and request fields

All mutations are POST. Forms include `csrf_token`; JSON requests send
`X-CSRF-Token` from the current session's page meta tag. This token is required
even when login is disabled. JSON request objects or `Accept: application/json`
receive JSON mutation responses; forms redirect to the saved resource. File
uploads use multipart form data. GET requests never mutate library state.

| Method | Path | Action / fields |
| --- | --- | --- |
| GET, POST | `/decks` | List / create (`name`) |
| GET | `/decks/<deck_id>` | Saved tabletop and library |
| POST | `/decks/<deck_id>/edit` | `name`, `reversal_probability` (0–100) |
| POST | `/decks/<deck_id>/upload` | Repeated `cards` file fields, optional `back` file |
| GET | `/decks/<deck_id>/images/<filename>` | Authenticated, membership-checked image |
| POST | `/decks/<deck_id>/draw` | Draw one; JSON includes `id`, `order`, `reversed` |
| POST | `/decks/<deck_id>/reshuffle` | Reset and randomize |
| POST | `/decks/<deck_id>/delete` | Delete deck and files |
| POST | `/decks/<deck_id>/cards/<card_id>/edit` | Optional `name` |
| POST | `/decks/<deck_id>/cards/<card_id>/position` | `x` (−80–80), `y` (−200–200); JSON response |
| POST | `/decks/<deck_id>/cards/<card_id>/rotate` | `rotation` (0, 90, 180 or 270) for a drawn card |
| POST | `/decks/<deck_id>/cards/<card_id>/delete` | Delete card and face |
| GET, POST | `/tables` | List / create dealer's table (`name`, default "Dealer's Table") |
| GET | `/tables/<table_id>` | Table surface, deck shelf and cards |
| POST | `/tables/<table_id>/edit` | Optional `name`, `width`, `height`; cards are kept on the surface when it shrinks |
| POST | `/tables/<table_id>/draw` | `deck_id`, optional `x`, `y`, `face_down`; JSON card plus the deck's `remaining` |
| POST | `/tables/<table_id>/cards/<card_id>` | Any of `x`, `y`, `rotation`, `face_down`, `raise` (bring to top); JSON response |
| POST | `/tables/<table_id>/cards/<card_id>/return` | Shuffle the card back into its deck |
| POST | `/tables/<table_id>/clear` | Shuffle every card on the table back into its deck |
| POST | `/tables/<table_id>/delete` | Return its cards (including saved layouts), then delete the table |
| POST | `/tables/<table_id>/saves` | Save & clear: optional `name`, `zoom`, `view_x`, `view_y`; 400 if the table is empty |
| POST | `/tables/<table_id>/saves/<save_id>/resume` | Restore the layout (auto-saving current cards first); JSON includes `view`, `autosave_id`; forms redirect with the view in the URL |
| POST | `/tables/<table_id>/saves/<save_id>/rename` | `name` |
| POST | `/tables/<table_id>/saves/<save_id>/delete` | Discard the save and shuffle its cards back into their decks |
| GET | `/sparks?table=<table_id>&q=<query>` | Table buttons, current user favorites, name search, shared log and selected table |
| POST | `/sparks/<table_id>/favorite` | Authenticated user only; `favorite` (`1` to add, `0` to remove); JSON includes `favorite`, `table_id` |
| POST | `/sparks/oracle/roll` | `odds` (one of nine labels); JSON includes `odds`, `roll`, `outcome`, `log_entries`; appends to shared log |
| POST | `/sparks/log/reset` | Clear shared log; keep tables and sampling pools |
| POST | `/sparks` | Create: `name`, `entries`, `format` (`text` or `json`), optional `file` |
| POST | `/sparks/<table_id>/edit` | Replace name and entries; same import fields |
| POST | `/sparks/<table_id>/generate` | `count` (1–20), `replacement` (`1` default, `0` without); JSON includes `results` and `log_entries` |
| POST | `/sparks/<table_id>/reset` | Restore optional pool; keep recent results |
| POST | `/sparks/<table_id>/delete` | Delete table and results |

## Validation and limitations

Run `.venv/bin/python -m pytest -q` from the repository root. The suite covers
existing application regressions, uploads and integrity/limit failures, atomic
invalid batches, deck CRUD, orientations, exhaustion, reshuffle, position saving,
concurrent independent-client draws, fresh-process restart persistence, additive
migration preservation, spark imports/edits/deletes, malformed JSON, sampling,
recent history, authentication and CSRF checks.

Current validation: **151 tests passed**, including per-user favorite isolation,
CSRF/auth checks, logout/login persistence, additive migration, deletion cascades,
search rendering, uniform index selection, newest-first rendering and existing
rolling/reset regressions. Oracle tests cover all 900 odds/d100 combinations,
all 72 range endpoints through the HTTP route, invalid odds, auth and CSRF,
native forms, shared log persistence/reset and unchanged spark table state.

Run `node tests/custom_sparks.browser.mjs` for isolated Chromium checks. This uses
the existing Playwright installation under `build/dungeon-mapper-work/node_modules`
and `/usr/bin/chromium`, with a temporary database and server on an ephemeral
localhost port. It checks star/roll separation, favorites after login, live search,
log ordering and reset, no-JavaScript forms, sticky positioning, initial log height,
3/2/1 table columns and horizontal overflow at widths 1440, 1000, 768, 390 and 360.
It also checks the two-control Oracle at all five widths, AJAX and native Oracle
rolls, odds selection persistence and the shared reset. Screenshots are saved in
the temporary directory printed by the test.

Manual headless Chromium checks at 1280×1000, 768×1024 and 390×844 verified both pages,
no horizontal overflow, multiple prominent sparks, card enlargement and pointer
drag saves, without JavaScript exceptions. Screenshots used temporary sample
data, not application or production records.

Each browser tab renders a snapshot; other devices' draws appear on refresh.
There is one shared active tabletop per deck, no live collaboration or undo.
Dragging is a bounded offset in a responsive grid rather than an infinite canvas;
large offsets can overlap adjacent cards. Image bytes and SQLite cannot be one
atomic filesystem transaction: an abrupt process/power failure during file writes
or post-delete cleanup can leave unused image files. These do not enter the draw
pool; ordinary request failures clean up newly written files. No automatic orphan
cleanup or global disk quota is included. Animated images are intentionally
rejected. JavaScript is needed for drag/enlargement and delete confirmations;
core forms and draws are server-rendered.


## Deploying the spark layout and favorites update

This update is validated locally; it has not been deployed. No new runtime
packages or frontend build step are required.

1. Stop application writes and back up the configured `SOLO_TOOLS_DB` database
   and card upload directory using the existing backup procedure.
2. Update the application checkout to the reviewed commit containing this change.
3. Restart the existing application service (for the included unit,
   `sudo systemctl restart solo-ttrpg-tools`). Database initialization creates the
   additive `custom_spark_favorites` table automatically; existing entries,
   sampling pools and spark history are retained.
4. Sign in and verify table rolling, stars after logout/login, search, log reset
   and the responsive layout. Refresh browser assets if an older layout is cached.

Rolling back the application files leaves the additive favorites table harmlessly
in the database; no destructive schema rollback is needed.
