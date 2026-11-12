# Pinned upstream source archives

These are unmodified `git archive --format=tar.gz <revision>` snapshots, kept
separate from HexWorld code. The archives include their upstream license files.

| Editor | Source | Commit | SHA-256 |
| --- | --- | --- | --- |
| Gridmapper | https://src.alexschroeder.ch/gridmapper.git | `4719813ff0e8d868828a6a86518950f52d4bbc61` | `4d3bf2125c55bf503f6c0d4824c5fba9c3331811453f7f73734191fe1cd907f3` |
| Dungeon Mapper | https://github.com/evillollive/Dungeon-Mapper | `42d8dc09f0bf3dfa6f1d6ca4ab2abc47602107e5` | `b28f802ea03713c94eec1351e63583d7bd2244ab5924af78bda093fa8769b41b` |

Gridmapper is CC0, by Alex Schroeder. Dungeon Mapper is AGPL-3.0-or-later,
by Alex Perrault. Personal, authenticated HexWorld use is the intended deployment.
Attributions and original license notices are retained. The source archive
download in each editor is authenticated just like the rest of HexWorld.

Run `python scripts/build_map_editors.py` with Python 3.12+ and Node 22.12+ to
verify archive hashes, extract immutable sources and build adapted copies. Build
patches live in that script and `integrations/dungeon-bridge.ts`; they never edit
these archives. The production server only needs the Python app, source archives
and built static editor files. The production `build/editors/` assets are tracked
for LXC deployment; intermediate sources and Node dependencies remain ignored.
