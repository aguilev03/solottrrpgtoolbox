"""Generic roll-table loader, validator, and recursive resolution engine."""

import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple
from dice import roll_notation


class TableValidationError(Exception):
    """Raised when a roll-table JSON file is malformed or invalid."""
    pass


class TableManager:
    """Loads, validates, and rolls against JSON roll tables."""

    def __init__(self, data_dir: str):
        self.data_dir = os.path.abspath(data_dir)
        self.tables: Dict[str, Any] = {}
        self.room_types: Dict[str, Any] = {}
        self.load_all()

    def load_all(self) -> None:
        """Loads and validates all table files in the data directory."""
        if not os.path.isdir(self.data_dir):
            raise TableValidationError(f"Data directory not found: {self.data_dir}")

        # Top-level JSON tables
        for filename in os.listdir(self.data_dir):
            if filename.endswith(".json"):
                table_id = filename[:-5]
                filepath = os.path.join(self.data_dir, filename)
                self.tables[table_id] = self._load_and_validate_json(filepath)

        # Rooms directory
        rooms_dir = os.path.join(self.data_dir, "rooms")
        if os.path.isdir(rooms_dir):
            for filename in os.listdir(rooms_dir):
                if filename.endswith(".json"):
                    room_type_key = filename[:-5].capitalize()
                    filepath = os.path.join(rooms_dir, filename)
                    data = self._load_and_validate_json(filepath)
                    self.room_types[room_type_key] = data

        self._validate_required_tables()

    def _load_and_validate_json(self, filepath: str) -> Any:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise TableValidationError(f"JSON syntax error in {filepath}: {e}")
        except Exception as e:
            raise TableValidationError(f"Failed to read table file {filepath}: {e}")
        return data

    def _validate_required_tables(self) -> None:
        required = [
            "dungeon_types",
            "dungeon_sizes",
            "dungeon_names",
            "descriptors",
            "routes",
            "contents",
            "hazards",
            "traps",
            "curios",
            "puzzles",
            "search",
            "search_trouble",
            "tension_events",
            "unique_rooms",
            "room_objects",
        ]
        missing = [t for t in required if t not in self.tables]
        if missing:
            raise TableValidationError(f"Missing required roll tables: {', '.join(missing)}")

        required_room_types = ["Tomb", "Cave", "Fort", "Temple", "Ruins", "Sewers"]
        missing_rooms = [r for r in required_room_types if r not in self.room_types]
        if missing_rooms:
            raise TableValidationError(f"Missing required room type tables in rooms/: {', '.join(missing_rooms)}")

    def roll_entry_from_table(self, table_spec: Any) -> Tuple[Any, Optional[int]]:
        """
        Generic roll against a table specification.
        Supports:
        - Range tables: {'dice': '2d6', 'entries': [{'min': 2, 'max': 2, ...}]}
        - Weighted tables: {'entries': [{'value': '...', 'weight': 2}, ...]} or list of dicts with 'weight'
        - Direct list: selects uniformly
        """
        if isinstance(table_spec, list):
            # Check if elements are weighted dicts
            if table_spec and isinstance(table_spec[0], dict) and "weight" in table_spec[0]:
                weights = [entry.get("weight", 1) for entry in table_spec]
                chosen = random.choices(table_spec, weights=weights, k=1)[0]
                return chosen, None
            return random.choice(table_spec), None

        if isinstance(table_spec, dict):
            # Range table with dice notation
            if "dice" in table_spec and "entries" in table_spec:
                dice_str = table_spec["dice"]
                roll_val, _ = roll_notation(dice_str)
                for entry in table_spec["entries"]:
                    if entry.get("min", 1) <= roll_val <= entry.get("max", 999):
                        return dict(entry), roll_val
                # Fallback if range gap exists
                return dict(table_spec["entries"][-1]), roll_val

            # Weighted entries
            if "entries" in table_spec:
                entries = table_spec["entries"]
                if entries and isinstance(entries[0], dict) and "weight" in entries[0]:
                    weights = [entry.get("weight", 1) for entry in entries]
                    chosen = random.choices(entries, weights=weights, k=1)[0]
                    return dict(chosen), None
                return dict(random.choice(entries)), None

        raise TableValidationError(f"Unrecognized table specification: {type(table_spec)}")

    def resolve_table(self, table_id: str, context: Optional[Dict[str, Any]] = None, recursive: bool = True) -> Dict[str, Any]:
        """
        Resolves a roll on a table by its identifier (e.g. 'contents', 'search', 'hazards').
        Recursively resolves any 'subtable' reference found on the rolled entry.
        """
        if table_id not in self.tables:
            raise ValueError(f"Table '{table_id}' not found")

        table_data = self.tables[table_id]
        rolled_entry, roll_val = self.roll_entry_from_table(table_data)

        result: Dict[str, Any] = {
            "source_table": table_id,
            "roll": roll_val,
            "entry": rolled_entry,
        }

        # Recursive subtable resolution
        if recursive and isinstance(rolled_entry, dict) and "subtable" in rolled_entry:
            subtable_id = rolled_entry["subtable"]
            if subtable_id:
                sub_result = self.resolve_table(subtable_id, context=context, recursive=recursive)
                result["sub_result"] = sub_result

        return result

    def get_room_type(self, dungeon_type: str) -> str:
        """Rolls a room type for the specified dungeon type (e.g. Tomb -> Burial Chamber)."""
        dt_key = dungeon_type.capitalize()
        if dt_key not in self.room_types:
            raise ValueError(f"Unknown room type category: {dungeon_type}")
        table_data = self.room_types[dt_key]
        entry, _ = self.roll_entry_from_table(table_data)
        return entry["value"] if isinstance(entry, dict) else str(entry)

    def get_unique_room(self, dungeon_type: str) -> Dict[str, Any]:
        """Rolls a Unique Room for the given dungeon type from unique_rooms.json."""
        dt_key = dungeon_type.capitalize()
        ur_table = self.tables.get("unique_rooms", {}).get("dungeon_types", {})
        if dt_key not in ur_table:
            raise ValueError(f"No unique room table found for dungeon type: {dungeon_type}")
        entry, roll_val = self.roll_entry_from_table(ur_table[dt_key])
        return {"entry": entry, "roll": roll_val}


# Singleton instance helper
_DEFAULT_MANAGER: Optional[TableManager] = None

def get_table_manager(data_dir: Optional[str] = None) -> TableManager:
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        if data_dir is None:
            # Default to data folder adjacent to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(base_dir, "data")
        _DEFAULT_MANAGER = TableManager(data_dir)
    return _DEFAULT_MANAGER
