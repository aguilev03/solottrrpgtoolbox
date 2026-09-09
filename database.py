"""SQLite database management and persistence layer for Solo TTRPG Tools."""

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional
from dungeon_engine import DungeonState, RoomState, format_dungeon_time
from hex_engine import HexCell, HexRegion


class Database:
    def __init__(self, db_path: str = "instance/solo_tools.db"):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dungeons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    dungeon_type TEXT NOT NULL,
                    size TEXT NOT NULL,
                    current_level INTEGER NOT NULL DEFAULT 1,
                    hidden_total_levels INTEGER NOT NULL DEFAULT 1,
                    current_room_number INTEGER NOT NULL DEFAULT 1,
                    elapsed_minutes INTEGER NOT NULL DEFAULT 0,
                    tension_dice INTEGER NOT NULL DEFAULT 0,
                    progress_points INTEGER NOT NULL DEFAULT 0,
                    current_room_id INTEGER,
                    is_complete INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dungeon_id INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    room_number INTEGER NOT NULL,
                    descriptor TEXT NOT NULL,
                    room_type TEXT NOT NULL,
                    is_unique INTEGER NOT NULL DEFAULT 0,
                    is_entrance INTEGER NOT NULL DEFAULT 0,
                    is_final_room INTEGER NOT NULL DEFAULT 0,
                    next_level_exists INTEGER NOT NULL DEFAULT 0,
                    contents_type TEXT NOT NULL,
                    contents_data_json TEXT NOT NULL,
                    routes_json TEXT NOT NULL,
                    searched INTEGER NOT NULL DEFAULT 0,
                    search_result_json TEXT,
                    has_trap INTEGER NOT NULL DEFAULT 0,
                    trap_revealed INTEGER NOT NULL DEFAULT 0,
                    trap_data_json TEXT,
                    objects_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (dungeon_id) REFERENCES dungeons(id) ON DELETE CASCADE
                );
            """)

            # Migration check for existing dungeons table
            cursor.execute("PRAGMA table_info(dungeons)")
            dungeon_cols = [c[1] for c in cursor.fetchall()]
            if "danger_mode" not in dungeon_cols:
                cursor.execute("ALTER TABLE dungeons ADD COLUMN danger_mode TEXT DEFAULT 'standard'")
            if "theme" not in dungeon_cols:
                cursor.execute("ALTER TABLE dungeons ADD COLUMN theme TEXT DEFAULT ''")

            # Migration check for existing rooms table
            cursor.execute("PRAGMA table_info(rooms)")
            room_cols = [c[1] for c in cursor.fetchall()]
            if "has_trap" not in room_cols:
                cursor.execute("ALTER TABLE rooms ADD COLUMN has_trap INTEGER NOT NULL DEFAULT 0")
            if "trap_revealed" not in room_cols:
                cursor.execute("ALTER TABLE rooms ADD COLUMN trap_revealed INTEGER NOT NULL DEFAULT 0")
            if "trap_data_json" not in room_cols:
                cursor.execute("ALTER TABLE rooms ADD COLUMN trap_data_json TEXT")
            if "objects_json" not in room_cols:
                cursor.execute("ALTER TABLE rooms ADD COLUMN objects_json TEXT")
            if "dressing" not in room_cols:
                cursor.execute("ALTER TABLE rooms ADD COLUMN dressing TEXT DEFAULT ''")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dungeon_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dungeon_id INTEGER NOT NULL,
                    elapsed_minutes INTEGER NOT NULL,
                    entry TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (dungeon_id) REFERENCES dungeons(id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS npcs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    current INTEGER NOT NULL DEFAULT 1,
                    party_member INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS npc_traits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    npc_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'default',
                    trait TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'PR',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hex_regions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    layout_type TEXT NOT NULL DEFAULT 'cluster_19',
                    center_biome TEXT NOT NULL DEFAULT 'Grassland',
                    weather_json TEXT,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hex_cells (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    region_id INTEGER NOT NULL,
                    hex_index INTEGER NOT NULL,
                    q INTEGER NOT NULL DEFAULT 0,
                    r INTEGER NOT NULL DEFAULT 0,
                    biome TEXT NOT NULL,
                    feature_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    discovered INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (region_id) REFERENCES hex_regions(id) ON DELETE CASCADE
                );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rooms_dungeon ON rooms(dungeon_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_dungeon ON dungeon_logs(dungeon_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_npcs_current ON npcs(current);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_npcs_party ON npcs(party_member);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_npc_traits_npc ON npc_traits(npc_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_hex_cells_region ON hex_cells(region_id);")
            conn.commit()

    def create_dungeon(self, dungeon: DungeonState) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO dungeons (
                    name, dungeon_type, size, current_level, hidden_total_levels,
                    current_room_number, elapsed_minutes, tension_dice, progress_points,
                    is_complete, danger_mode, theme
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dungeon.name,
                dungeon.dungeon_type,
                dungeon.size,
                dungeon.current_level,
                dungeon.hidden_total_levels,
                dungeon.current_room_number,
                dungeon.elapsed_minutes,
                dungeon.tension_dice,
                dungeon.progress_points,
                1 if dungeon.is_complete else 0,
                dungeon.danger_mode,
                dungeon.theme,
            ))
            dungeon_id = cursor.lastrowid
            conn.commit()
            dungeon.id = dungeon_id
            return dungeon_id

    def update_dungeon(self, dungeon: DungeonState) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE dungeons SET
                    name = ?,
                    dungeon_type = ?,
                    size = ?,
                    current_level = ?,
                    hidden_total_levels = ?,
                    current_room_number = ?,
                    elapsed_minutes = ?,
                    tension_dice = ?,
                    progress_points = ?,
                    current_room_id = ?,
                    is_complete = ?,
                    danger_mode = ?,
                    theme = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                dungeon.name,
                dungeon.dungeon_type,
                dungeon.size,
                dungeon.current_level,
                dungeon.hidden_total_levels,
                dungeon.current_room_number,
                dungeon.elapsed_minutes,
                dungeon.tension_dice,
                dungeon.progress_points,
                dungeon.current_room_id,
                1 if dungeon.is_complete else 0,
                dungeon.danger_mode,
                dungeon.theme,
                dungeon.id,
            ))
            conn.commit()

    def get_dungeon(self, dungeon_id: int) -> Optional[DungeonState]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dungeons WHERE id = ?", (dungeon_id,))
            row = cursor.fetchone()
            if not row:
                return None
            keys = row.keys()
            return DungeonState(
                id=row["id"],
                name=row["name"],
                dungeon_type=row["dungeon_type"],
                size=row["size"],
                current_level=row["current_level"],
                hidden_total_levels=row["hidden_total_levels"],
                current_room_number=row["current_room_number"],
                elapsed_minutes=row["elapsed_minutes"],
                tension_dice=row["tension_dice"],
                progress_points=row["progress_points"],
                current_room_id=row["current_room_id"],
                is_complete=bool(row["is_complete"]),
                danger_mode=row["danger_mode"] if "danger_mode" in keys else "standard",
                theme=row["theme"] if "theme" in keys else "",
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_dungeons(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, dungeon_type, size, current_level, elapsed_minutes, is_complete, danger_mode, theme, updated_at
                FROM dungeons
                ORDER BY updated_at DESC
            """)
            rows = cursor.fetchall()
            dungeons = []
            for r in rows:
                keys = r.keys()
                elapsed_mins = r["elapsed_minutes"]
                hours = elapsed_mins // 60
                mins = elapsed_mins % 60
                if hours > 0:
                    time_str = f"{hours}h {mins:02d}m explored" if mins else f"{hours}h explored"
                else:
                    time_str = f"{mins}m explored"

                dungeons.append({
                    "id": r["id"],
                    "name": r["name"],
                    "dungeon_type": r["dungeon_type"],
                    "size": r["size"],
                    "current_level": r["current_level"],
                    "elapsed_minutes": elapsed_mins,
                    "explored_time_str": time_str,
                    "is_complete": bool(r["is_complete"]),
                    "danger_mode": r["danger_mode"] if "danger_mode" in keys else "standard",
                    "theme": r["theme"] if "theme" in keys else "",
                    "updated_at": r["updated_at"],
                })
            return dungeons

    def delete_dungeon(self, dungeon_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM dungeons WHERE id = ?", (dungeon_id,))
            conn.commit()
            return cursor.rowcount > 0

    def save_room(self, room: RoomState) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if room.id is None:
                cursor.execute("""
                    INSERT INTO rooms (
                        dungeon_id, level, room_number, descriptor, room_type, dressing,
                        is_unique, is_entrance, is_final_room, next_level_exists,
                        contents_type, contents_data_json, routes_json,
                        searched, search_result_json,
                        has_trap, trap_revealed, trap_data_json, objects_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    room.dungeon_id,
                    room.level,
                    room.room_number,
                    room.descriptor,
                    room.room_type,
                    room.dressing,
                    1 if room.is_unique else 0,
                    1 if room.is_entrance else 0,
                    1 if room.is_final_room else 0,
                    1 if room.next_level_exists else 0,
                    room.contents_type,
                    json.dumps(room.contents_data),
                    json.dumps(room.routes),
                    1 if room.searched else 0,
                    json.dumps(room.search_result) if room.search_result else None,
                    1 if room.has_trap else 0,
                    1 if room.trap_revealed else 0,
                    json.dumps(room.trap_data) if room.trap_data else None,
                    json.dumps(room.objects),
                ))
                room.id = cursor.lastrowid
            else:
                cursor.execute("""
                    UPDATE rooms SET
                        descriptor = ?,
                        room_type = ?,
                        dressing = ?,
                        is_unique = ?,
                        is_entrance = ?,
                        is_final_room = ?,
                        next_level_exists = ?,
                        contents_type = ?,
                        contents_data_json = ?,
                        routes_json = ?,
                        searched = ?,
                        search_result_json = ?,
                        has_trap = ?,
                        trap_revealed = ?,
                        trap_data_json = ?,
                        objects_json = ?
                    WHERE id = ?
                """, (
                    room.descriptor,
                    room.room_type,
                    room.dressing,
                    1 if room.is_unique else 0,
                    1 if room.is_entrance else 0,
                    1 if room.is_final_room else 0,
                    1 if room.next_level_exists else 0,
                    room.contents_type,
                    json.dumps(room.contents_data),
                    json.dumps(room.routes),
                    1 if room.searched else 0,
                    json.dumps(room.search_result) if room.search_result else None,
                    1 if room.has_trap else 0,
                    1 if room.trap_revealed else 0,
                    json.dumps(room.trap_data) if room.trap_data else None,
                    json.dumps(room.objects),
                    room.id,
                ))
            conn.commit()
            return room.id

    def get_room(self, room_id: int) -> Optional[RoomState]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
            row = cursor.fetchone()
            if not row:
                return None
            keys = row.keys()
            return RoomState(
                id=row["id"],
                dungeon_id=row["dungeon_id"],
                level=row["level"],
                room_number=row["room_number"],
                descriptor=row["descriptor"],
                room_type=row["room_type"],
                dressing=row["dressing"] if "dressing" in keys else "",
                is_unique=bool(row["is_unique"]),
                is_entrance=bool(row["is_entrance"]),
                is_final_room=bool(row["is_final_room"]),
                next_level_exists=bool(row["next_level_exists"]),
                contents_type=row["contents_type"],
                contents_data=json.loads(row["contents_data_json"]) if row["contents_data_json"] else {},
                routes=json.loads(row["routes_json"]) if row["routes_json"] else [],
                searched=bool(row["searched"]),
                search_result=json.loads(row["search_result_json"]) if row["search_result_json"] else None,
                has_trap=bool(row["has_trap"]) if "has_trap" in keys else False,
                trap_revealed=bool(row["trap_revealed"]) if "trap_revealed" in keys else False,
                trap_data=json.loads(row["trap_data_json"]) if ("trap_data_json" in keys and row["trap_data_json"]) else None,
                objects=json.loads(row["objects_json"]) if ("objects_json" in keys and row["objects_json"]) else [],
            )

    def get_rooms_for_dungeon(self, dungeon_id: int) -> List[RoomState]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE dungeon_id = ? ORDER BY room_number ASC", (dungeon_id,))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                keys = row.keys()
                result.append(RoomState(
                    id=row["id"],
                    dungeon_id=row["dungeon_id"],
                    level=row["level"],
                    room_number=row["room_number"],
                    descriptor=row["descriptor"],
                    room_type=row["room_type"],
                    dressing=row["dressing"] if "dressing" in keys else "",
                    is_unique=bool(row["is_unique"]),
                    is_entrance=bool(row["is_entrance"]),
                    is_final_room=bool(row["is_final_room"]),
                    next_level_exists=bool(row["next_level_exists"]),
                    contents_type=row["contents_type"],
                    contents_data=json.loads(row["contents_data_json"]) if row["contents_data_json"] else {},
                    routes=json.loads(row["routes_json"]) if row["routes_json"] else [],
                    searched=bool(row["searched"]),
                    search_result=json.loads(row["search_result_json"]) if row["search_result_json"] else None,
                    has_trap=bool(row["has_trap"]) if "has_trap" in keys else False,
                    trap_revealed=bool(row["trap_revealed"]) if "trap_revealed" in keys else False,
                    trap_data=json.loads(row["trap_data_json"]) if ("trap_data_json" in keys and row["trap_data_json"]) else None,
                    objects=json.loads(row["objects_json"]) if ("objects_json" in keys and row["objects_json"]) else [],
                ))
            return result

    # ==========================================
    # HEX REGIONS & WILDERNESS PERSISTENCE
    # ==========================================

    def save_hex_region(self, region: HexRegion) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if region.id is None:
                cursor.execute("""
                    INSERT INTO hex_regions (
                        name, layout_type, center_biome, weather_json, notes
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    region.name,
                    region.layout_type,
                    region.center_biome,
                    json.dumps(region.weather) if region.weather else None,
                    region.notes,
                ))
                region.id = cursor.lastrowid
            else:
                cursor.execute("""
                    UPDATE hex_regions SET
                        name = ?,
                        layout_type = ?,
                        center_biome = ?,
                        weather_json = ?,
                        notes = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    region.name,
                    region.layout_type,
                    region.center_biome,
                    json.dumps(region.weather) if region.weather else None,
                    region.notes,
                    region.id,
                ))
                cursor.execute("DELETE FROM hex_cells WHERE region_id = ?", (region.id,))

            for cell in region.cells:
                cursor.execute("""
                    INSERT INTO hex_cells (
                        region_id, hex_index, q, r, biome, feature_type,
                        title, summary, details_json, discovered
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    region.id,
                    cell.hex_index,
                    cell.q,
                    cell.r,
                    cell.biome,
                    cell.feature_type,
                    cell.title,
                    cell.summary,
                    json.dumps(cell.details),
                    1 if cell.discovered else 0,
                ))
                cell.region_id = region.id
                cell.id = cursor.lastrowid

            conn.commit()
            return region.id

    def get_hex_region(self, region_id: int) -> Optional[HexRegion]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hex_regions WHERE id = ?", (region_id,))
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute("SELECT * FROM hex_cells WHERE region_id = ? ORDER BY hex_index ASC", (region_id,))
            cell_rows = cursor.fetchall()
            cells = []
            for cr in cell_rows:
                cells.append(HexCell(
                    id=cr["id"],
                    region_id=cr["region_id"],
                    hex_index=cr["hex_index"],
                    q=cr["q"],
                    r=cr["r"],
                    biome=cr["biome"],
                    feature_type=cr["feature_type"],
                    title=cr["title"],
                    summary=cr["summary"],
                    details=json.loads(cr["details_json"]) if cr["details_json"] else {},
                    discovered=bool(cr["discovered"]),
                    created_at=cr["created_at"],
                ))

            return HexRegion(
                id=row["id"],
                name=row["name"],
                layout_type=row["layout_type"],
                center_biome=row["center_biome"],
                weather=json.loads(row["weather_json"]) if row["weather_json"] else {},
                notes=row["notes"] or "",
                cells=cells,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_hex_regions(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT hr.id, hr.name, hr.layout_type, hr.center_biome, hr.notes, hr.created_at, hr.updated_at,
                       COUNT(hc.id) as hex_count
                FROM hex_regions hr
                LEFT JOIN hex_cells hc ON hr.id = hc.region_id
                GROUP BY hr.id
                ORDER BY hr.updated_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def delete_hex_region(self, region_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hex_regions WHERE id = ?", (region_id,))
            conn.commit()
            return cursor.rowcount > 0

    def add_log_entry(self, dungeon_id: int, elapsed_minutes: int, entry: str) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO dungeon_logs (dungeon_id, elapsed_minutes, entry)
                VALUES (?, ?, ?)
            """, (dungeon_id, elapsed_minutes, entry))
            conn.commit()

    def get_dungeon_logs(self, dungeon_id: int) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, elapsed_minutes, entry, created_at
                FROM dungeon_logs
                WHERE dungeon_id = ?
                ORDER BY id ASC
            """, (dungeon_id,))
            rows = cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "elapsed_minutes": r["elapsed_minutes"],
                    "formatted_time": format_dungeon_time(r["elapsed_minutes"]),
                    "entry": r["entry"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    # ==========================================
    # CHARACTER EMULATOR (NPCs & TRAITS)
    # ==========================================

    def create_npc(
        self,
        name: str,
        details: str = "",
        current: bool = True,
        party_member: bool = False,
        traits: Optional[List[Dict[str, str]]] = None,
    ) -> int:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("NPC name cannot be empty.")

        # Rule: If party_member is True, current MUST be True
        if party_member:
            current = True

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO npcs (name, details, current, party_member)
                VALUES (?, ?, ?, ?)
            """, (clean_name, details.strip(), 1 if current else 0, 1 if party_member else 0))
            npc_id = cursor.lastrowid

            if traits:
                for t in traits:
                    status = (t.get("status") or "default").strip().lower()
                    trait_text = (t.get("trait") or "").strip()
                    category = (t.get("category") or "PR").strip().upper()
                    if trait_text:
                        cursor.execute("""
                            INSERT INTO npc_traits (npc_id, status, trait, category)
                            VALUES (?, ?, ?, ?)
                        """, (npc_id, status, trait_text, category))

            conn.commit()
            return npc_id

    def get_npc(self, npc_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, details, current, party_member, created_at, updated_at
                FROM npcs WHERE id = ?
            """, (npc_id,))
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute("""
                SELECT id, status, trait, category, created_at
                FROM npc_traits
                WHERE npc_id = ?
                ORDER BY id ASC
            """, (npc_id,))
            trait_rows = cursor.fetchall()

            return {
                "id": row["id"],
                "name": row["name"],
                "details": row["details"],
                "current": bool(row["current"]),
                "party_member": bool(row["party_member"]),
                "traits": [
                    {
                        "id": t["id"],
                        "status": t["status"],
                        "trait": t["trait"],
                        "category": t["category"],
                    }
                    for t in trait_rows
                ],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def update_npc(
        self,
        npc_id: int,
        name: Optional[str] = None,
        details: Optional[str] = None,
        current: Optional[bool] = None,
        party_member: Optional[bool] = None,
    ) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, details, current, party_member FROM npcs WHERE id = ?", (npc_id,))
            existing = cursor.fetchone()
            if not existing:
                return False

            new_name = name.strip() if name is not None else existing["name"]
            if not new_name:
                raise ValueError("NPC name cannot be empty.")
            new_details = details.strip() if details is not None else existing["details"]

            # Rule: Cannot set current = False while party_member is True (or will be True)
            if current is False:
                will_be_party = party_member if party_member is not None else bool(existing["party_member"])
                if will_be_party:
                    raise ValueError("Party Members are always Current. Uncheck Party Member first.")

            # Rule: If party_member is checked (set to True), current MUST automatically become True
            if party_member is True:
                current_val = True
            elif current is not None:
                current_val = current
            else:
                current_val = bool(existing["current"])

            if party_member is not None:
                party_val = party_member
            else:
                party_val = bool(existing["party_member"])

            cursor.execute("""
                UPDATE npcs
                SET name = ?, details = ?, current = ?, party_member = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                new_name,
                new_details,
                1 if current_val else 0,
                1 if party_val else 0,
                npc_id,
            ))
            conn.commit()
            return True

    def delete_npc(self, npc_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

    def list_npcs(
        self,
        current_only: Optional[bool] = None,
        party_only: Optional[bool] = None,
        search_query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT id, name, details, current, party_member, created_at, updated_at FROM npcs WHERE 1=1"
            params: List[Any] = []

            if current_only is True:
                query += " AND current = 1"
            elif current_only is False:
                query += " AND current = 0"

            if party_only is True:
                query += " AND party_member = 1"
            elif party_only is False:
                query += " AND party_member = 0"

            if search_query:
                term = f"%{search_query.strip()}%"
                query += " AND (name LIKE ? OR details LIKE ? OR id IN (SELECT npc_id FROM npc_traits WHERE trait LIKE ?))"
                params.extend([term, term, term])

            # Party members first, then alphabetical by name
            query += " ORDER BY party_member DESC, LOWER(name) ASC"

            cursor.execute(query, params)
            npc_rows = cursor.fetchall()
            if not npc_rows:
                return []

            npc_ids = [r["id"] for r in npc_rows]
            placeholders = ",".join("?" for _ in npc_ids)
            cursor.execute(f"""
                SELECT id, npc_id, status, trait, category
                FROM npc_traits
                WHERE npc_id IN ({placeholders})
                ORDER BY id ASC
            """, npc_ids)
            all_traits = cursor.fetchall()

            traits_by_npc: Dict[int, List[Dict[str, Any]]] = {nid: [] for nid in npc_ids}
            for t in all_traits:
                traits_by_npc[t["npc_id"]].append({
                    "id": t["id"],
                    "status": t["status"],
                    "trait": t["trait"],
                    "category": t["category"],
                })

            results = []
            for r in npc_rows:
                results.append({
                    "id": r["id"],
                    "name": r["name"],
                    "details": r["details"],
                    "current": bool(r["current"]),
                    "party_member": bool(r["party_member"]),
                    "traits": traits_by_npc.get(r["id"], []),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                })
            return results

    def add_npc_trait(self, npc_id: int, status: str, trait: str, category: str) -> int:
        clean_trait = trait.strip()
        if not clean_trait:
            raise ValueError("Trait cannot be empty.")
        clean_status = (status or "default").strip().lower()
        clean_category = (category or "PR").strip().upper()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO npc_traits (npc_id, status, trait, category)
                VALUES (?, ?, ?, ?)
            """, (npc_id, clean_status, clean_trait, clean_category))
            trait_id = cursor.lastrowid
            cursor.execute("UPDATE npcs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (npc_id,))
            conn.commit()
            return trait_id

    def delete_npc_trait(self, trait_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT npc_id FROM npc_traits WHERE id = ?", (trait_id,))
            row = cursor.fetchone()
            if not row:
                return False
            npc_id = row["npc_id"]
            cursor.execute("DELETE FROM npc_traits WHERE id = ?", (trait_id,))
            cursor.execute("UPDATE npcs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (npc_id,))
            conn.commit()
            return True

    def set_npc_traits(self, npc_id: int, traits: List[Dict[str, str]]) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM npc_traits WHERE npc_id = ?", (npc_id,))
            for t in traits:
                trait_text = (t.get("trait") or "").strip()
                if trait_text:
                    status = (t.get("status") or "default").strip().lower()
                    category = (t.get("category") or "PR").strip().upper()
                    cursor.execute("""
                        INSERT INTO npc_traits (npc_id, status, trait, category)
                        VALUES (?, ?, ?, ?)
                    """, (npc_id, status, trait_text, category))
            cursor.execute("UPDATE npcs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (npc_id,))
            conn.commit()

    # ==========================================
    # USER & AUTH MANAGEMENT
    # ==========================================

    def create_user(self, username: str, password_hash: str, is_admin: bool = False) -> int:
        """Create a new user account."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (username, password_hash, is_admin)
                VALUES (?, ?, ?)
            """, (username.strip(), password_hash, 1 if is_admin else 0))
            conn.commit()
            return cursor.lastrowid

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a user by their ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password_hash, is_admin, created_at, last_login FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieve a user by their username (case-insensitive)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password_hash, is_admin, created_at, last_login FROM users WHERE username = ?", (username.strip(),))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def list_users(self) -> List[Dict[str, Any]]:
        """List all users."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, is_admin, created_at, last_login FROM users ORDER BY id ASC")
            return [dict(r) for r in cursor.fetchall()]

    def update_user_password(self, user_id: int, password_hash: str) -> bool:
        """Update a user's password hash."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
            conn.commit()
            return cursor.rowcount > 0

    def update_user_last_login(self, user_id: int) -> None:
        """Update last_login timestamp for a user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
            conn.commit()

    def delete_user(self, user_id: int) -> bool:
        """Delete a user by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    def count_users(self) -> int:
        """Count total registered users."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM users")
            return cursor.fetchone()["count"]


_DEFAULT_DB: Optional[Database] = None

def get_db(db_path: Optional[str] = None) -> Database:
    global _DEFAULT_DB
    if _DEFAULT_DB is None:
        db_file = db_path or os.environ.get("SOLO_TOOLS_DB", "instance/solo_tools.db")
        _DEFAULT_DB = Database(db_file)
    return _DEFAULT_DB
