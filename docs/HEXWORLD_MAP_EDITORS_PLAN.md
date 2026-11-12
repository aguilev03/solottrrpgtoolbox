# HexWorld map editors: assessment and approval plan

Assessed 2026-11-12. Branch: `hexworld/map-editors-assessment`.
Original assessment status: inspection and planning only. The user subsequently
approved isolated implementation. See `HEXWORLD_MAP_EDITORS.md` and
`HEXWORLD_MAP_EDITORS_TESTS.md` for the implemented result. Production configuration,
services, databases, backup policy and Proxmox allocations remain unchanged.

## Observed installation

Production is Proxmox VE 8.4.21 on `solar` (`server.eaguil.local`), unprivileged
Debian LXC **120**, hostname `hexworld`, IP `192.168.68.120/22`.

| Resource | Allocation / observation |
| --- | --- |
| CPU | 1 core |
| RAM | 1,024 MiB; 173 MiB used, approximately 850 MiB available |
| Swap | 512 MiB; 224 KiB used |
| Root disk | 8 GiB on local-lvm; filesystem 7.8 GiB, 1.6 GiB used, 5.9 GiB free |
| App service | Active; Gunicorn, 3 workers, `0.0.0.0:5000` |
| App cgroup memory | Approximately 283 MiB (`MemoryCurrent`; accounting differs from `free`) |
| Persistent instance directory | 179 MiB, mostly card uploads; database 128 KiB |

These are point-in-time measurements, not peak-load results. The workstation
(`earth`, EndeavourOS, 62 GiB RAM and 12 CPUs) is a separate development machine.
Do not use its capacity to infer container capacity. Proxmox reported roughly
174 GiB available RAM; this does not authorize reallocating it.

Application directory: `/home/hexroll/solottrrpgtoolbox`. Flask/Jinja, vanilla JS,
SQLite, Pillow and Gunicorn. The active systemd unit is
`/etc/systemd/system/solo-ttrpg-tools.service`. Production uses secure cookies.
Do not copy service environment values into documentation or source control.

Production and local checkout have base commit
`e56c1697ec2f95a510f4ef33291e1c91821731a7`. Production has intentional uncommitted
changes: `/hexroll` returns 404 and its launcher card is removed. Preserve these
changes when deploying. Hexroll/Xpra is inactive; do not re-enable it incidentally.

### Routing differs from repository examples

Nginx is not installed in LXC 120. LXC 106 runs Docker Nginx Proxy Manager.
Its `hexworld.eaguil.net` entry points to `192.168.68.80:14501`, an older
destination, not this Flask app. The repository Nginx example is not the live
configuration. LXC 101 runs Cloudflared. `https://hexworld.eaguil.com` responds
with Cloudflare Access authentication. Its exact tunnel-to-origin mapping has
not been verified; confirm it before any production routing change. Do not
replace the old proxy entry based solely on its similar hostname.

### Data and backups

SQLite: `instance/solo_tools.db`, overridable with `SOLO_TOOLS_DB`.
Existing custom card assets: `instance/card_uploads`, overridable with
`CARD_UPLOAD_DIR`. Current maps/hex regions are procedural application records,
not native projects for either requested editor. Keep those records untouched.
Authentication currently guards application routes; custom tools include CSRF
checks. New map routes must inherit those protections. Existing tool libraries
are shared among authenticated users; retain that policy unless changed explicitly.

Proxmox snapshot backup job includes CT 120 at 21:00, zstd, with
`keep-weekly=2, keep-monthly=1`. Archives found on `backups` storage:
2026-11-08 and 2026-11-11, about 568 MB each. Their existence was checked;
restoration was not tested. No scheduled application-level backup was established
by this inspection. Repository documentation describes SQLite online backups;
CUSTOM_TOOLS.md correctly requires backing up uploaded files as well.

## Upstream assessment and pins

### Gridmapper

Canonical source: <https://src.alexschroeder.ch/gridmapper.git>.
Reviewed commit: `4719813ff0e8d868828a6a86518950f52d4bbc61`.
The requested hosted SVG returned HTTP 402 from this environment; canonical Git
source was successfully cloned and inspected instead. GitHub's former
`kensanata/gridmapper` URL was not available during inspection.

Single JavaScript/SVG editor; no build toolchain required for basic editing.
Native editable export is TXT command code; SVG/PNG exports are also available.
Multiple levels are supported. Its native Save/Load buttons target Campaign Wiki
and are removed automatically outside `campaignwiki.org`. Thus merely embedding
the SVG cannot provide HexWorld persistence. A separate Perl/WebSocket server is
optional for collaboration; do not install it for this integration. Public wiki
and collaboration actions need clear labels so private maps are not sent externally
by mistake. Inspect these actions during the adapter work.

`LICENSE.md` dedicates the work to the public domain under CC0 1.0. Retain the
license and credit Alex Schroeder. Inspect bundled assets before packaging.

### Dungeon Mapper

Source: <https://github.com/evillollive/Dungeon-Mapper>.
Reviewed commit: `42d8dc09f0bf3dfa6f1d6ca4ab2abc47602107e5`.
React 19, TypeScript, Vite 7, fflate, Vite PWA/Workbox; npm lockfile present.
Build on workstation/CI with a supported Node release satisfying the pinned
package engines (prefer Node 22.12+); use `npm ci`. Serve compiled assets in
production without Node or a Vite development server.

The upstream build base, manifest start URL and scope are `/Dungeon-Mapper/`;
all must be adapted to `/dungeon-mapper/`, including icon paths and service worker
registration. Scope caches and navigation fallback strictly to that prefix.
Audit hardcoded paths rather than relying on a Vite base override alone.

Native saving uses IndexedDB database `dungeon-mapper`; it is device-local and
not a server backup. `src/utils/export.ts` uses `encodeProject`/`decodeProject`
for editable JSON. Preserve that versioned envelope, custom themes, embedded art,
levels and stair links. PNG/SVG exports cannot replace editable JSON. Separate
Run/session records are not included in a project backup; do not claim otherwise.
Browser database names are origin-wide: check for existing installs at this origin
before adapting storage, and never clear their IndexedDB as part of installation.

License: AGPL-3.0-or-later, copyright Alex Perrault, per the repository LICENSE.
Retain notices, include the full license, and provide users a prominent link to
the corresponding source for the exact deployed editor build and modifications.
Keep editor source/patches separate from the HexWorld wrapper. Separation alone
does not settle the licensing of a combined derivative work; assess the final
adapter boundary before distribution. Review dependency/asset notices too.

## Proposed implementation

1. Before implementation, create an external local backup of the checkout,
   SQLite via its backup API, and uploaded assets. Build in an isolated worktree.
   Production remains unchanged until implementation review and deployment approval.
2. Keep immutable pinned upstream trees under `vendor/` (or equivalent pinned
   source artifacts); keep reproducible path/build patches in `integrations/`.
   Record full revisions and SHA-256 hashes. Provide a source/license download.
3. Add authenticated launchers and pages at `/gridmapper/` and
   `/dungeon-mapper/`, and a common `/maps/` library. Use existing Flask service
   and navigation; preserve `/dungeon`, `/hex`, card decks, sparks, NPCs and login.
   Serve authenticated editor assets under dedicated prefixes; do not expose
   projects through Flask's public `/static/` directory. Test nested asset URLs.
4. Add new, additive SQLite tables for campaigns, map metadata and immutable
   project revisions. A map records campaign, name, editor, native format,
   upstream revision and current revision. Store bounded native payloads as SQLite
   BLOBs initially to keep metadata/project commits atomic. Preserve imported
   project bytes; validate without converting one editor format to the other.
   Store embedded art with the native project; if external assets are needed,
   use a private persistent directory with a transactional ownership manifest.
5. Support campaign/map create and rename, duplicate with a new identity,
   confirmed delete, native project upload/download, revision recovery, and level
   metadata. Retain whole native multi-level projects rather than flattening them.
   Bound sizes and retained revision storage. Restrict names to display values;
   use generated IDs for storage paths. Check auth, CSRF, membership, and payload
   limits on mutations and private downloads. Handle malformed imports safely.
6. Prototype small editor adapters: read/write Gridmapper native command code;
   call Dungeon Mapper's existing schema functions and state replacement workflow.
   Preserve undo, drawing and local recovery. Provide explicit **Save to HexWorld**,
   with unsaved/saving/saved/error/conflict states. Local IndexedDB success must
   never be presented as server-save success. Warn before discarding dirty work.
7. Require a revision token on saves; commit the new revision only if the current
   revision still matches. On conflict, preserve in-memory work and offer download
   or Save as copy; never silently overwrite a map from another tab/device.
8. Retain native PNG exporters, with per-level export where appropriate. Verify
   exported images with an image decoder and display them in an actual Obsidian
   vault. Provide native project export/import for restoration separately.

### Safe fallback if adapters are too invasive

Assess adapters before promising direct server saves. If safe state extraction
and replacement require broad upstream rewrites, stop that portion and document
a separate synchronization phase. A first release may provide native project
upload/download and a server library, but must explicitly tell users to export
from the editor and upload to HexWorld. That fallback does **not** satisfy direct
Save/reopen requirements and needs an explicit scope decision before deployment.
Never scrape IndexedDB blindly or substitute PNG for editable projects.

## Resource recommendation

No resize recommended at this stage. Static browser editors add little steady
server work; rendering and PNG generation consume client memory, especially on
tablets. Preliminary planning allowance: under 100 MiB additional runtime RAM
for ordinary bounded requests, plus static assets and map storage. These are
estimates to validate, not benchmark results. Keep Node builds and browser test
binaries off the 1 GiB container. Local source checkout sizes were approximately
47 MiB (Dungeon Mapper) and 3.8 MiB (Gridmapper), including Git history as fetched;
these are not built bundle sizes. Measure the final artifact before deployment.

Allow initially 1 GiB for projects, art and retained revisions, with monitoring.
Example: 100 maps × 5 MiB × 5 retained revisions is about 2.5 GiB before backups.
Set quotas/retention based on actual use. Consider 2 GiB RAM only if measured
concurrent uploads/exports cause pressure; consider a 16 GiB root disk or separate
backed-up data volume if growth warrants it. Any allocation change needs approval.

## Validation gates (not yet executed)

- Run the full existing pytest suite using an isolated temporary database and
  upload directory; add meaningful map CRUD, auth, CSRF, conflict, format round-trip,
  duplicate/delete, limits and migration-preservation tests.
- Load both prefixes and every asset; check browser console/network and PWA scope.
- Draw, undo, change levels, save, close/reopen and compare editable project data.
- Test stale saves from two tabs/devices, failed requests, expired login and dirty
  navigation; recovery must not replace newer server work.
- Refresh browser, restart staging Gunicorn and reopen projects; restore an
  exported project into a clean staging library, including art and levels.
- Export PNG, decode it and inspect it in Obsidian; confirm editable export import.
- Chromium/Firefox/WebKit desktop and tablet viewport tests, plus physical tablet
  touch/pen qualification. Emulation alone does not prove tablet compatibility.
- Compare CPU/RAM/disk before/after; measure upload peaks and large-map exports.
  Test existing dungeon/hex/emulator/deck/spark/admin behavior, preserving the
  deployment's disabled Hexroll state.

## Deployment and rollback procedure after approval

1. Identify the actual Cloudflare tunnel route and access policy; verify the
   authenticated hostname. Back up its routing configuration if changes are needed.
   No proxy changes should be needed if both new prefixes reach existing Flask.
2. Before touching production, take a fresh CT 120 backup and verify completion.
   Capture its config, active service unit and production Git diff in restricted
   backup storage. These files may contain secrets; never commit them.
3. Pause writes briefly for a consistent application snapshot: SQLite online backup
   plus card uploads and all new private map assets. Record a manifest/checksums
   outside the checkout. Prove restoration in isolation before rollout.
4. Deploy a reviewed pinned release to a separate directory, with a fresh venv
   and prebuilt editor assets. Point configuration at persistent data explicitly;
   never overwrite `instance/`. Carry forward disabled Hexroll customization.
5. Test migrations on a restored copy first; take a fresh production backup,
   perform additive migrations and switch the existing service to the release.
   Verify login, private downloads, editors, legacy tools and saves before reopening
   writes. Capture measured resource use and artifact versions.
6. Roll back code by restoring the previous service working directory/configuration
   and restarting. Keep new tables/revisions in place if compatible; do not
   restore an older database merely to undo code, as that loses post-release data.
   If data restoration is necessary, pause writes, preserve the failed deployment's
   current data, and restore a matching database/assets snapshot together under
   an explicit recovery decision. Full CT restore is a last resort with the same
   post-backup data-loss implications. Never destroy CT 120 to roll back.
7. Extend application backup documentation and checks to cover all projects,
   revisions and art; confirm configured external asset volumes are backed up.

## Approval requested

Approve this staged implementation plan to begin isolated installation and
integration. Production deployment remains a separate approval after reviewing
the implemented changes and test evidence. No resource resize is requested.
