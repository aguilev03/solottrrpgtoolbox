# Personal HexWorld map editors

Implemented on `hexworld/map-editors-assessment`. This is an isolated local
implementation; production deployment still requires approval. The resource and
architecture inspection is in [the assessment](HEXWORLD_MAP_EDITORS_PLAN.md).

## Use

Open **Map Library** from Home. Create a campaign, give the map a name and select
Gridmapper or Dungeon Mapper. You can optionally upload an existing native TXT
or JSON project. Open the map, draw using the original editor tools, then press
**Save to HexWorld**. The status changes from unsaved/saving to a saved revision.
Gridmapper's cursor movement alone does not count as an edit.

The separate launchers are `/gridmapper/` and `/dungeon-mapper/`. Choose a project
from `/maps/`; editor links include `?map=<id>`. Library names are independent
of titles inside the native project. Rename campaigns/maps, duplicate maps, and
delete maps with confirmation in the library. Save as copy retains current
in-memory work in a separate project, including after a save conflict.

Maps are editor-specific. Gridmapper TXT command exports retain its levels;
Dungeon Mapper JSON retains its levels, stairs, custom themes and embedded art.
Use each editor's native level controls; Gridmapper's `?` help explains its
keyboard/touch commands. No conversion or flattening takes place.

**Download editable project** exports your current workspace, even before a
server save. Library downloads export the last saved server version. Importing
or loading a retained revision changes the workspace; press Save to make it the
current server revision. Five recent server revisions are retained by default.
Deleting a map deletes those revisions, so download a backup first.

**Export PNG (current level)** creates an image for an Obsidian attachment folder.
Embed it as `![[your-map.png]]`. Dungeon Mapper's wrapper export is a 72 DPI GM
image; its original Export dialog provides additional resolution, print and
player-view options. PNG is an image, not an editable backup.

## Save guarantees and limitations

- Native project bytes and metadata are committed atomically in SQLite. Refresh
  and application restart reopen the server version. Save before switching devices.
- Revision tokens reject stale writes from another tab/device. A failed save
  leaves the previous server version intact. Download working data or Save as copy
  before reloading after a conflict. The application never silently chooses a winner.
- The original Dungeon Mapper status **Saved on this device** refers to IndexedDB,
  not HexWorld. Local databases are separated by HexWorld map ID. Server saves use
  the wrapper's explicit button. Refresh intentionally loads the server snapshot;
  unsaved device-only changes are not automatically merged into it. A dirty-page
  warning helps prevent leaving without saving, but browser prompts are not a
  substitute for explicit saves and native downloads.
- Dungeon Mapper Run sessions/player displays remain upstream device-local
  features. They are outside the shared map library and not part of project JSON
  backups. Reopen the authored map to use HexWorld save controls after changing
  to a separate workspace. No collaborative or cross-editor editing is provided.
- Offline PWA registration is disabled in embedded HexWorld workspaces. The
  authenticated online server and explicit Save are the persistence boundary.
- Import native Gridmapper exports, not scripted demos containing pause commands.
  Quoted label punctuation is preserved. The server validates size/basic JSON
  structure; the upstream decoder provides full Dungeon Mapper field validation.
  Unreadable imports remain downloadable; they do not overwrite other maps.
- This follows the existing shared authenticated library policy. The intended
  installation is personal, accessible only to its owner.

## Build and isolated preview

Production Python requirements are unchanged. The build workstation needs
Python 3.12+ and a supported Node release (recommend Node 22.12+), npm and network
access to the public npm registry. Source archives and upstream revisions are
listed in [vendor/README.md](../vendor/README.md). Pinned npm versions and integrity
hashes come from the upstream lockfile. A few mirror URLs are normalized to the
standard npm registry without changing versions or integrity values.

```bash
python scripts/build_map_editors.py
```

This verifies sources, leaves them untouched, applies checked transformations to
a separate build copy and writes `build/editors/`. Node and `node_modules` are
not needed in production. Keep the source archives and integration scripts with
the release so the exact upstream and adapter code remain available.

For a local preview, use a new database and a separate asset directory:

```bash
SOLO_TOOLS_DB=/tmp/hexworld-preview/tools.db \
CARD_UPLOAD_DIR=/tmp/hexworld-preview/cards \
LOGIN_DISABLED=true .venv/bin/gunicorn --bind 127.0.0.1:5088 --workers 2 app:app
```

Do not set `LOGIN_DISABLED` for production or expose this preview externally.
Review [integrations/README.md](../integrations/README.md) for adapter boundaries.

## Storage settings

| Setting | Default |
| --- | --- |
| `EDITOR_BUILD_DIR` | `<checkout>/build/editors` |
| `MAP_MAX_PROJECT_BYTES` | 16 MiB per native project |
| `MAP_LIBRARY_MAX_BYTES` | 512 MiB of retained native payloads |
| `MAP_RETAIN_REVISIONS` | 5 per map, minimum 1 |
| `SOLO_TOOLS_DB` | Existing `instance/solo_tools.db` |
| `CARD_UPLOAD_DIR` | Existing `instance/card_uploads` |

Map assets embedded in native projects are included in SQLite backups. No new
map filesystem store is needed. The quota counts retained payloads; SQLite files
also have indexes, metadata and reusable free pages, so monitor filesystem space
as well. Oversize/quota failures roll back the entire write.

## Back up and restore

Before deployment, take a fresh Proxmox CT 120 backup and verify it completed.
Save the production Git diff, systemd unit and relevant proxy/tunnel configuration
in restricted backup storage. The production diff intentionally disables Hexroll;
carry it forward. Do not commit service environment values or secrets.

For a matching database/card snapshot, pause writes (the simplest way is stopping
the app), run this with the same storage environment as the service, then restart:

```bash
sudo systemctl stop solo-ttrpg-tools
# Run as the application user, with the service's SOLO_TOOLS_DB/CARD_UPLOAD_DIR.
python scripts/backup_data.py /path/outside/checkout/new-backup-directory
sudo systemctl start solo-ttrpg-tools
```

The helper refuses to overwrite a backup or back up a nonexistent database. It
uses SQLite's online backup API, checks integrity and writes SHA-256 checksums for
the copied database and card assets. Its integrity check does not verify temporal
consistency with assets if writes were not paused. Native projects/revisions/art
are in `solo_tools.db`; existing card assets are copied to `card_uploads/`.

Test restoration into separate directories first. Compare the manifest, run
SQLite `PRAGMA integrity_check`, configure the restored database/assets for an
isolated server, then reopen maps and existing tools. Production restoration
requires stopping writes and restoring the database and card directory together.
Preserve the current state first; restoring an older snapshot loses later edits.

## Deployment after separate approval

1. Verify the Cloudflare Access hostname/tunnel route to CT 120. The repository
   Nginx file and LXC 106's old `.net` proxy are not the active `.com` routing
   specification; do not overwrite them based on their names.
2. Back up as above, including the production-only Hexroll disable changes.
3. Prepare a separate release directory with this Python source, templates,
   static files, JSON data tables, `vendor/` and prebuilt `build/editors/`.
   Create a venv using `requirements.txt`. Keep production data outside the
   release; explicitly configure its existing database and card directory.
4. Apply/carry forward the intentional production diff in the release. Preserve
   the current secret key, secure cookies, service user and authentication policy.
5. Restore a backup to staging and verify additive schema migration plus legacy
   tools. New tables are `map_campaigns`, `library_maps`, and `map_revisions`;
   existing tool tables are not rewritten.
6. After deployment approval, stop writes, take a final consistent snapshot,
   switch the service WorkingDirectory/ExecStart to the prepared release and
   restart. Confirm both editor assets, login, saves, PNG downloads and existing
   tools. No new service, public port, or LXC allocation is required.
7. Keep the previous release and data backup. Check that CT 120 backups still
   include the persistent paths, especially if moving assets to external mounts.

Rollback: stop writes, point the service back to the previous code/venv and
restart with the same database/assets. The extra tables may remain. Avoid a
database rollback solely to undo code: that discards later edits. If a data
restore is required, preserve current data and restore a matching snapshot only
after deciding how to recover later work. Never destroy CT 120 for rollback.

## Tests

```bash
SOLO_TOOLS_DB=/tmp/hexworld-tests.db \
CARD_UPLOAD_DIR=/tmp/hexworld-test-cards PYTHONPATH=. .venv/bin/pytest -q

# After starting the isolated loopback preview above:
MAP_TEST_ENGINES=chromium,firefox node tests/map_editors.browser.mjs
```

Browser binaries come from the pinned build's Playwright package. Install them
on the workstation with `npx playwright install chromium firefox webkit` in
`build/dungeon-mapper-work/`. Do not install browser binaries on CT 120.
WebKit requires supported host libraries; a viewport test is not physical tablet
qualification. See [validation results](HEXWORLD_MAP_EDITORS_TESTS.md) for evidence
and remaining device checks.
