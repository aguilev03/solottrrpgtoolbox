# HexWorld editor boundary

The private single-user application retains upstream drawing/rendering code.
`vendor/` contains the exact source snapshots. `scripts/build_map_editors.py`
contains checked, deterministic build transformations; extracted upstream trees
remain unchanged in `build/editor-sources/`. Adapted source is inspectable under
`build/dungeon-mapper-work/`.

Gridmapper runs directly from its original SVG. The parent page calls its native
`getSource`, `Map.reset`, `interpretMap` and `download` functions; its live pen
coordinates are ignored for dirty-status comparisons. Public wiki/collaboration
launchers are hidden in this private wrapper. Native TXT preserves all levels.
Imports require exported TXT, rather than scripted demos with pause commands.
The wrapper normalizes touch coordinates before calling the original pen code;
upstream's mouse-coordinate lookup otherwise produces NaN on real TouchEvents
and can hang its drawing loop. The source SVG remains unmodified.

Dungeon Mapper receives a small React hook exposing native encode/decode/import
and PNG-export operations to its same-origin parent. The hook reads current
state through a ref, and waits for React to commit imports. It uses the existing
replacement workflow, undo/history initialization and local save coordinator.
IndexedDB is namespaced per HexWorld map ID, avoiding other installed copies.
The source format is still upstream schema v1 JSON, including art and levels.

The build sets Vite and the PWA manifest to `/dungeon-mapper/app/`. Offline worker
registration is disabled in the embedded workspace: server authentication and
explicit HexWorld saves remain authoritative. Session/Run features remain
upstream device-local functionality and are not included in map project saves.

The iframe is trusted same-origin editor code. The parent only loads projects
after checking editor/map identity, and locks the workspace until loading succeeds.
Native downloads in the wrapper export current in-memory work, including unsaved
changes, so users can recover after conflicts or failed network requests.

Server persistence uses independent campaign/map/revision tables. SQLite stores
native UTF-8 bytes atomically with metadata. The server bounds payloads and checks
basic JSON structure; Dungeon Mapper's full decoder validates before opening.
Future/unreadable projects remain downloadable instead of being overwritten.
Assets embedded in native JSON need no separate map upload directory. Existing
card assets remain in their original private persistent directory.
