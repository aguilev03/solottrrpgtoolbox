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

## Using custom sparks

The main view shows every saved table as a button in a two-column grid. Press a
button to roll one entry with replacement and append it to the shared Spark log
on the right (below the buttons on narrow screens). Rolls appear oldest first,
with the table name beside each result. The log is saved in SQLite across page
reloads and devices, and has no automatic 30-result cutoff. **Reset log** clears
this shared log without changing tables, sampling pools, or per-table recent
results. Editing or deleting a table also leaves the shared log intact.

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
| `custom_cards` | Deck FK, optional name, face file, unique shuffled rank, unique nullable draw order, reversal, x/y offset |
| `custom_spark_tables` | Name, JSON entry array, remaining entry indices, last sampling mode and batch size |
| `custom_spark_results` | Table FK and result text; increasing ID supplies chronology |
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
| POST | `/decks/<deck_id>/cards/<card_id>/delete` | Delete card and face |
| GET | `/sparks?table=<table_id>` | Table buttons, shared log, library and selected table |
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

Validation result: **107 tests passed**, including all existing regression tests.

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
