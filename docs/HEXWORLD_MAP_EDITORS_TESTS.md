# Map editor validation — 2026-11-12

All implementation checks ran on the development workstation and isolated local
databases. Production CT 120, its services/data and its allocations were unchanged.

## Automated application checks

`114 passed` in the complete pytest suite, including all 107 preexisting tests.
New coverage checks native project bytes and levels, unknown JSON fields and
embedded assets, rename/duplicate/delete, stale/concurrent writers, bounded revision
history, project/quota rollback, authentication/CSRF/private download headers,
additive migrations, fresh database connections and backup restoration.

JavaScript syntax checks and `git diff --check` passed. The pinned static editor
build passed TypeScript and Vite production packaging. Source archives were
verified against their recorded SHA-256 hashes before extraction.

Dungeon Mapper's full adapted upstream suite: **87 files / 1,169 tests passed**.
The workstation uses Node 26.13.0; its built-in web-storage globals initially
caused 35 jsdom setup failures (`localStorage.clear` on undefined). Running with
`NODE_OPTIONS=--no-experimental-webstorage npm test` resolved the host mismatch.
No upstream assertions were disabled or edited. Node 22.12+ is recommended for
building; the production Python server does not run Node.

## Browser and export evidence

The repeatable browser script is `tests/map_editors.browser.mjs`, using the pinned
upstream Playwright package against loopback Gunicorn at port 5088.

- Chromium and Firefox: both editor prefixes and assets, actual drawing gestures,
  two levels, explicit server save, editable download, refresh/reopen, and rejection
  of a stale page's write. Native imports, loading old revisions into the workspace
  and saving an independent copy also passed for both editors in both engines.
  No page errors or failed document/script/style/image/font loads occurred.
- Tablet viewport: 820 × 1180 layout, usable save/download controls and editor
  workspace. Chromium additionally exercises actual emulated touch input: a long
  touch in Gridmapper and a canvas tap in Dungeon Mapper, followed by server save.
- Gridmapper touch testing exposed an upstream NaN-coordinate drawing-loop hang.
  The wrapper normalizes TouchEvent coordinates before the original pen function;
  geometry-changing long-touch input now completes and saves.
- PNG files from Chromium and Firefox decoded successfully with Pillow.
  Gridmapper output: 640 × 640; Dungeon Mapper output: 2304 × 2304.
- Actual Obsidian 1.15.0, isolated vault: both PNG attachments rendered in Markdown
  preview, with `complete=true` and matching nonzero natural dimensions. This was
  checked in Obsidian's Electron renderer, not only an ordinary image viewer.

Browser logs, native exports and screenshots are local evidence under
`/tmp/hexworld-editor-stage/`; Obsidian's temporary vault is
`/tmp/hexworld-obsidian-vault/`. These test artifacts contain only generated test
maps and are not production backups.

WebKit could not launch: this Arch-based workstation lacks the required
`libicu74`, `libxml2` compatibility and `libflite1` libraries for Playwright's
downloaded build. Safari/WebKit remains unverified. Physical tablet touch/pen
testing is still required; browser emulation does not establish device acceptance.

## Persistence and resources

A full staging Gunicorn stop/start preserved the SHA-256 digest of all 23 saved
native revisions present at that checkpoint; the restarted library returned HTTP
200. Subsequent database reopen/migration tests also preserved project bytes.
The backup test restored projects/revisions and original private card asset bytes
from an independent snapshot and verified every file against its manifest.
Existing Proxmox backup archives were inspected but no full CT restore was attempted.

Compiled editor assets total approximately **1.8 MiB**. Unmodified upstream source
archives total approximately **21 MiB**, mainly Dungeon Mapper documentation media.
The local two-worker staging Gunicorn process group reported about **111 MiB
aggregate RSS** after browser tests (shared pages counted more than once). This
is not a container peak-load measurement and should not be compared directly
with production's cgroup accounting. Test map requests did not show sustained CPU
load. Large simultaneous imports and physical tablet rendering limits were not
load-qualified; payload/quota limits are enforced and tested.

No new server daemon or resource increase is required for the compiled editors.
Keep the current CT allocation initially and monitor actual project/art growth.
The default retained-project quota is 512 MiB; backup/archive growth must also be
monitored independently. Any future LXC resize remains subject to approval.
