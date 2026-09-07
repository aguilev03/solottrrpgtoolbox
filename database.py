"""SQLite database management and persistence layer for Solo TTRPG Tools."""

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional
from dungeon_engine import DungeonState, RoomState, format_dungeon_time


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

            # Migration check for existing databases
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

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rooms_dungeon ON rooms(dungeon_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_dungeon ON dungeon_logs(dungeon_id);")
            conn.commit()

    def create_dungeon(self, dungeon: DungeonState) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO dungeons (
                    name, dungeon_type, size, current_level, hidden_total_levels,
                    current_room_number, elapsed_minutes, tension_dice, progress_points,
                    is_complete
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_dungeons(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, dungeon_type, size, current_level, elapsed_minutes, is_complete, updated_at
                FROM dungeons
                ORDER BY updated_at DESC
            """)
            rows = cursor.fetchall()
            dungeons = []
            for r in rows:
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
                        dungeon_id, level, room_number, descriptor, room_type,
                        is_unique, is_entrance, is_final_room, next_level_exists,
                        contents_type, contents_data_json, routes_json,
                        searched, search_result_json,
                        has_trap, trap_revealed, trap_data_json, objects_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    room.dungeon_id,
                    room.level,
                    room.room_number,
                    room.descriptor,
                    room.room_type,
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


_DEFAULT_DB: Optional[Database] = None

def get_db(db_path: Optional[str] = None) -> Database:
    global _DEFAULT_DB
    if _DEFAULT_DB is None:
        db_file = db_path or os.environ.get("SOLO_TOOLS_DB", "instance/solo_tools.db")
        _DEFAULT_DB = Database(db_file)
    return _DEFAULT_DB
