"""Dungeon engine: procedural room generation, hidden Progress mechanic, time and tension clock."""

from __future__ import annotations
import random
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from dice import ProgressRollResult, roll_progress
from table_loader import TableManager, get_table_manager


def format_dungeon_time(minutes: int) -> str:
    """Format in-game elapsed minutes into 'HH:MM' string (e.g. 00:00, 00:10, 01:20)."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


COMPASS_DIRECTIONS = [
    {"arrow": "↑", "name": "North"},
    {"arrow": "↗", "name": "Northeast"},
    {"arrow": "→", "name": "East"},
    {"arrow": "↘", "name": "Southeast"},
    {"arrow": "↓", "name": "South"},
    {"arrow": "↙", "name": "Southwest"},
    {"arrow": "←", "name": "West"},
    {"arrow": "↖", "name": "Northwest"},
]


@dataclass
class RoomState:
    id: Optional[int] = None
    dungeon_id: Optional[int] = None
    level: int = 1
    room_number: int = 1
    descriptor: str = ""
    room_type: str = ""
    is_unique: bool = False
    is_entrance: bool = False
    is_final_room: bool = False
    next_level_exists: bool = False
    contents_type: str = ""
    contents_data: Dict[str, Any] = field(default_factory=dict)
    routes: List[Any] = field(default_factory=list)
    searched: bool = False
    search_result: Optional[Dict[str, Any]] = None
    has_trap: bool = False
    trap_revealed: bool = False
    trap_data: Optional[Dict[str, Any]] = None
    objects: List[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        if self.descriptor and self.room_type:
            return f"{self.descriptor} {self.room_type}"
        return self.room_type or self.descriptor or "Chamber"

    @property
    def trap_warning(self) -> str:
        if self.trap_data:
            if "warning" in self.trap_data and self.trap_data["warning"]:
                return self.trap_data["warning"]
            if "initial_warning" in self.trap_data and self.trap_data["initial_warning"]:
                return self.trap_data["initial_warning"]
        return "You hear a click, as though something has just been activated."

    @property
    def trap_display_name(self) -> str:
        if not self.trap_data:
            return "Trap"
        return self.trap_data.get("name", "Trap")

    @property
    def contents_has_trap(self) -> bool:
        if self.has_trap and not self.search_has_trap:
            return True
        if not self.contents_data:
            return False
        sub = self.contents_data.get("sub_result")
        if sub:
            sub_entry = sub.get("entry", {})
            if sub_entry.get("name") == "Trap" or sub_entry.get("type") == "Trap":
                return True
        entry = self.contents_data.get("entry", {})
        if entry.get("name") == "Trap" or entry.get("type") == "Trap":
            return True
        return False

    @property
    def search_has_trap(self) -> bool:
        if not self.search_result:
            return False
        sub = self.search_result.get("sub_result")
        if sub:
            sub_entry = sub.get("entry", {})
            if sub_entry.get("name") == "Trap" or sub_entry.get("type") == "Trap":
                return True
            nested = sub.get("sub_result")
            if nested:
                nested_entry = nested.get("entry", {})
                if nested_entry.get("name") == "Trap" or nested_entry.get("type") == "Trap":
                    return True
        return False


@dataclass
class DungeonState:
    id: Optional[int] = None
    name: str = ""
    dungeon_type: str = "Tomb"
    size: str = "Medium"
    current_level: int = 1
    hidden_total_levels: int = 2
    current_room_number: int = 1
    elapsed_minutes: int = 0
    tension_dice: int = 0
    progress_points: int = 0
    current_room_id: Optional[int] = None
    is_complete: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DungeonEngine:
    """Core procedural referee and generator."""

    def __init__(self, table_mgr: Optional[TableManager] = None):
        self.tables = table_mgr or get_table_manager()

    def generate_dungeon_name(self, dungeon_type: str) -> str:
        """Generates a thematic name for the chosen dungeon type."""
        names_data = self.tables.tables.get("dungeon_names", {}).get("types", {})
        type_key = dungeon_type.capitalize()
        config = names_data.get(type_key)
        if not config:
            return f"The {type_key}"

        fmt = config.get("format", "separate")
        prefix = random.choice(config.get("prefixes", ["Ancient"]))
        suffix = random.choice(config.get("suffixes", ["Chamber"]))

        if fmt == "compound":
            return f"{prefix}{suffix.lower()}"
        return f"{prefix} {suffix}"

    def determine_hidden_floors(self, size: str) -> int:
        """
        Determines the hidden floor count based on size:
        Small: exactly 1 floor
        Medium: randomly 1-2 floors
        Large: randomly 2-3 floors
        Never reveals the floor count to the player.
        """
        sizes_config = self.tables.tables.get("dungeon_sizes", {}).get("sizes", {})
        spec = sizes_config.get(size.capitalize())
        if not spec or "hidden_floors" not in spec:
            return 1
        floor_range = spec["hidden_floors"]
        min_f = floor_range.get("min", 1)
        max_f = floor_range.get("max", 1)
        return random.randint(min_f, max_f)

    def resolve_random_type(self) -> str:
        """Rolls a random dungeon type from dungeon_types.json."""
        res = self.tables.resolve_table("dungeon_types", recursive=False)
        return res["entry"]["value"]

    def resolve_random_size(self) -> str:
        """Rolls a random dungeon size from dungeon_sizes.json."""
        size_table = self.tables.tables.get("dungeon_sizes", {}).get("random_table", [])
        entry, _ = self.tables.roll_entry_from_table({"dice": "d6", "entries": size_table})
        return entry["value"]

    def compose_routes(self) -> List[Dict[str, Any]]:
        """
        Compositional route generator:
        A. Route structure roll from routes.json
        B. Route physical description vocabulary
        C. Condition modifier (normal, locked, stuck, blocked, unusual)
        D. Unique compass directions without replacement (↑ North, ↗ Northeast, etc.)
        """
        routes_data = self.tables.tables.get("routes", {})
        struct_table = routes_data.get("structure_table", [])
        struct_dice = routes_data.get("structure_dice", "2d6")

        entry, _ = self.tables.roll_entry_from_table({"dice": struct_dice, "entries": struct_table})
        conditions: List[str] = entry.get("conditions", ["normal"])

        phys_vocab = routes_data.get("physical_descriptions", ["Stone passage"])
        unusual_spec = routes_data.get("unusual_routes", {})

        count = len(conditions)
        chosen_dirs = random.sample(COMPASS_DIRECTIONS, min(count, len(COMPASS_DIRECTIONS)))

        result_routes: List[Dict[str, Any]] = []
        for i, cond in enumerate(conditions):
            dir_info = chosen_dirs[i]

            # Pick physical description
            phys_entry, _ = self.tables.roll_entry_from_table(phys_vocab)
            phys_text = phys_entry["value"] if isinstance(phys_entry, dict) else str(phys_entry)

            if cond == "unusual":
                if unusual_spec:
                    unusual_entry, _ = self.tables.roll_entry_from_table(unusual_spec)
                    desc = unusual_entry["value"] if isinstance(unusual_entry, dict) else str(unusual_entry)
                else:
                    desc = f"{phys_text} (unusual)"
            elif cond == "normal":
                desc = phys_text
            else:
                # locked, stuck, blocked
                desc = f"{phys_text} ({cond})"

            result_routes.append({
                "arrow": dir_info["arrow"],
                "direction": dir_info["name"],
                "text": desc,
                "formatted": f"{dir_info['arrow']} {dir_info['name']} — {desc}",
            })

        return result_routes

    def generate_secret_route(self, existing_routes: List[Any]) -> Dict[str, Any]:
        """
        Generates a thematic secret route assigned a unique compass direction
        not already used by other routes in the room.
        """
        used_directions = set()
        for r in existing_routes:
            if isinstance(r, dict):
                used_directions.add(r.get("direction"))
            elif isinstance(r, str):
                for d in COMPASS_DIRECTIONS:
                    if d["name"] in r:
                        used_directions.add(d["name"])

        available_dirs = [d for d in COMPASS_DIRECTIONS if d["name"] not in used_directions]
        if not available_dirs:
            available_dirs = COMPASS_DIRECTIONS

        dir_info = random.choice(available_dirs)

        routes_data = self.tables.tables.get("routes", {})
        secret_vocab = routes_data.get("secret_route_descriptions", ["Concealed stone door"])
        entry, _ = self.tables.roll_entry_from_table(secret_vocab)
        val = entry["value"] if isinstance(entry, dict) else str(entry)
        desc = f"{val} (secret route)"

        return {
            "arrow": dir_info["arrow"],
            "direction": dir_info["name"],
            "text": desc,
            "formatted": f"{dir_info['arrow']} {dir_info['name']} — {desc}",
        }

    def _extract_trap_from_contents(self, contents_data: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Checks if rolled contents contains a trap and returns (has_trap, trap_data)."""
        if not contents_data:
            return False, None
        sub = contents_data.get("sub_result")
        if sub:
            sub_entry = sub.get("entry", {})
            if sub_entry.get("name") == "Trap" or sub_entry.get("type") == "Trap":
                trap_entry = sub.get("sub_result", {}).get("entry")
                if not trap_entry:
                    trap_entry = self.roll_trap()
                return True, trap_entry
        entry = contents_data.get("entry", {})
        if entry.get("name") == "Trap" or entry.get("type") == "Trap":
            trap_entry = contents_data.get("sub_result", {}).get("entry")
            if not trap_entry:
                trap_entry = self.roll_trap()
            return True, trap_entry
        return False, None

    def _extract_trap_from_search(self, search_data: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Checks if rolled search result contains a trap and returns (has_trap, trap_data)."""
        if not search_data:
            return False, None
        sub = search_data.get("sub_result")
        if sub:
            sub_entry = sub.get("entry", {})
            if sub_entry.get("name") == "Trap" or sub_entry.get("type") == "Trap":
                trap_entry = sub.get("sub_result", {}).get("entry")
                if not trap_entry:
                    trap_entry = self.roll_trap()
                return True, trap_entry
            nested = sub.get("sub_result")
            if nested:
                nested_entry = nested.get("entry", {})
                if nested_entry.get("name") == "Trap" or nested_entry.get("type") == "Trap":
                    trap_entry = nested.get("sub_result", {}).get("entry")
                    if not trap_entry:
                        trap_entry = self.roll_trap()
                    return True, trap_entry
        return False, None

    def roll_trap(self) -> Dict[str, Any]:
        """Rolls a trap directly from traps.json."""
        res = self.tables.resolve_table("traps", recursive=False)
        return res["entry"]

    def roll_room_objects(self, count: int = 3) -> List[str]:
        """
        Rolls `count` distinct room objects (furniture, fixtures, and misc junk) from room_objects.json.
        """
        table = self.tables.tables.get("room_objects", {})
        entries = table.get("entries", [])
        if not entries:
            return []
        k = min(count, len(entries))
        chosen = random.sample(entries, k)
        return [entry.get("name", entry.get("value", str(entry))) for entry in chosen]

    def reveal_trap(self, room: RoomState) -> Tuple[Dict[str, Any], str]:
        """
        Reveals the trap in the room:
        - If trap_data is not yet determined, rolls from traps.json.
        - Sets room.trap_revealed = True.
        - Returns (trap_data, log_message).
        """
        if not room.has_trap:
            raise ValueError("No trap exists in this chamber.")
        if not room.trap_data:
            room.trap_data = self.roll_trap()
        room.trap_revealed = True

        trap_title = room.trap_display_name
        log_msg = f"Trap revealed in Room {room.room_number}: {trap_title}."
        return room.trap_data, log_msg

    def generate_entrance_room(self, dungeon: DungeonState) -> RoomState:
        """
        Entrance room generation:
        - Entrance does NOT roll Progress.
        - Generates Descriptor, Room Type, Routes, Contents, and 3 Room Objects.
        - Time is 00:00 (for level 1) or current elapsed time.
        """
        descriptor_res = self.tables.resolve_table("descriptors", recursive=False)
        descriptor = descriptor_res["entry"]["value"]

        room_type = self.tables.get_room_type(dungeon.dungeon_type)
        routes = self.compose_routes()
        objects = self.roll_room_objects(3)
        contents_res = self.tables.resolve_table("contents", recursive=True)
        has_trap, trap_data = self._extract_trap_from_contents(contents_res)

        return RoomState(
            dungeon_id=dungeon.id,
            level=dungeon.current_level,
            room_number=dungeon.current_room_number,
            descriptor=descriptor,
            room_type=room_type,
            is_unique=False,
            is_entrance=True,
            is_final_room=False,
            next_level_exists=dungeon.current_level < dungeon.hidden_total_levels,
            contents_type=contents_res["entry"].get("type", "Normal"),
            contents_data=contents_res,
            routes=routes,
            objects=objects,
            searched=False,
            search_result=None,
            has_trap=has_trap,
            trap_revealed=False,
            trap_data=trap_data,
        )

    def advance_time_and_tension(self, dungeon: DungeonState) -> Optional[Dict[str, Any]]:
        """
        Advances elapsed_minutes by 10 and tension_dice by 1.
        When tension_dice reaches 6:
        - 1 hour has elapsed!
        - Triggers tension event roll
        - Resets tension_dice to 0
        Returns tension event info if triggered, else None.
        """
        dungeon.elapsed_minutes += 10
        dungeon.tension_dice += 1

        if dungeon.tension_dice >= 6:
            dungeon.tension_dice = 0
            event_res = self.tables.resolve_table("tension_events", recursive=True)
            return {
                "triggered": True,
                "elapsed_minutes": dungeon.elapsed_minutes,
                "event": event_res["entry"],
            }
        return None

    def explore(
        self,
        dungeon: DungeonState,
        previous_room: RoomState,
    ) -> Tuple[RoomState, Optional[ProgressRollResult], Optional[Dict[str, Any]], str]:
        """
        Performs the hidden EXPLORE action:
        1. Advances time (+10 min) and tension clock (+1).
        2. If previous room was a Unique Room:
           - If another level exists:
             current_level += 1
             progress_points = 0
             Generate Entrance Room for the next floor!
           - Else:
             Dungeon is complete.
        3. Else (normal explore):
           - Rolls hidden Progress dice pool (progress_points + 1 D6s):
             0 successes (Failure): normal room, progress unchanged.
             1 success (Weak): normal room, progress_points += 1.
             2+ successes (Strong): generate Unique Room!
        Returns (new_room, progress_roll_result, tension_event, log_message).
        """
        if dungeon.is_complete:
            raise ValueError("Dungeon is already complete. No further rooms can be generated.")

        tension_event = self.advance_time_and_tension(dungeon)
        dungeon.current_room_number += 1

        # Case A: Transitioning from a Unique Room
        if previous_room.is_unique:
            if dungeon.current_level < dungeon.hidden_total_levels:
                # Descend to next floor!
                dungeon.current_level += 1
                dungeon.progress_points = 0  # Resets to 0 for new floor

                new_room = self.generate_entrance_room(dungeon)
                log_msg = f"Descended to Level {dungeon.current_level}. Reached the entrance: {new_room.title}."
                return new_room, None, tension_event, log_msg
            else:
                dungeon.is_complete = True
                raise ValueError("Dungeon is already complete.")

        # Case B: Standard exploration room with hidden Progress mechanic
        progress_result = roll_progress(dungeon.progress_points)

        # Standard descriptor and room type
        desc_res = self.tables.resolve_table("descriptors", recursive=False)
        descriptor = desc_res["entry"]["value"]
        room_type = self.tables.get_room_type(dungeon.dungeon_type)
        routes = self.compose_routes()
        objects = self.roll_room_objects(3)

        if progress_result.outcome == "strong":
            # STRONG SUCCESS: Generate Unique Room!
            unique_data = self.tables.get_unique_room(dungeon.dungeon_type)
            unique_entry = unique_data["entry"]

            has_next_floor = dungeon.current_level < dungeon.hidden_total_levels
            is_final = not has_next_floor

            new_room = RoomState(
                dungeon_id=dungeon.id,
                level=dungeon.current_level,
                room_number=dungeon.current_room_number,
                descriptor=descriptor,
                room_type=room_type,
                is_unique=True,
                is_entrance=False,
                is_final_room=is_final,
                next_level_exists=has_next_floor,
                contents_type="Unique Room",
                contents_data={"unique_room": unique_entry, "roll": unique_data["roll"]},
                routes=routes,
                objects=objects,
                searched=False,
                search_result=None,
            )

            if is_final:
                dungeon.is_complete = True
                log_msg = f"Discovered the final Unique Room: {unique_entry.get('name', 'Inner Sanctum')} ({new_room.title}). Dungeon Complete!"
            else:
                log_msg = f"Discovered the Unique Room: {unique_entry.get('name', 'Unique Chamber')} ({new_room.title}). A way deeper descends."

            return new_room, progress_result, tension_event, log_msg

        elif progress_result.outcome == "weak":
            # WEAK SUCCESS: Normal room, +1 Progress
            dungeon.progress_points = progress_result.progress_after
            contents_res = self.tables.resolve_table("contents", recursive=True)
            has_trap, trap_data = self._extract_trap_from_contents(contents_res)

            new_room = RoomState(
                dungeon_id=dungeon.id,
                level=dungeon.current_level,
                room_number=dungeon.current_room_number,
                descriptor=descriptor,
                room_type=room_type,
                is_unique=False,
                is_entrance=False,
                is_final_room=False,
                next_level_exists=dungeon.current_level < dungeon.hidden_total_levels,
                contents_type=contents_res["entry"].get("type", "Normal"),
                contents_data=contents_res,
                routes=routes,
                objects=objects,
                searched=False,
                search_result=None,
                has_trap=has_trap,
                trap_revealed=False,
                trap_data=trap_data,
            )
            log_msg = f"Entered Room {new_room.room_number}: {new_room.title}."
            return new_room, progress_result, tension_event, log_msg

        else:
            # FAILURE: Normal room, progress unchanged
            dungeon.progress_points = progress_result.progress_after
            contents_res = self.tables.resolve_table("contents", recursive=True)
            has_trap, trap_data = self._extract_trap_from_contents(contents_res)

            new_room = RoomState(
                dungeon_id=dungeon.id,
                level=dungeon.current_level,
                room_number=dungeon.current_room_number,
                descriptor=descriptor,
                room_type=room_type,
                is_unique=False,
                is_entrance=False,
                is_final_room=False,
                next_level_exists=dungeon.current_level < dungeon.hidden_total_levels,
                contents_type=contents_res["entry"].get("type", "Normal"),
                contents_data=contents_res,
                routes=routes,
                objects=objects,
                searched=False,
                search_result=None,
                has_trap=has_trap,
                trap_revealed=False,
                trap_data=trap_data,
            )
            log_msg = f"Entered Room {new_room.room_number}: {new_room.title}."
            return new_room, progress_result, tension_event, log_msg

    def search(
        self,
        dungeon: DungeonState,
        room: RoomState,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], str]:
        """
        Searches the current room:
        - Validates room has not already been searched.
        - Advances time (+10 min) and tension clock (+1).
        - Rolls on search.json and recursively resolves any subtables.
        - If Secret route rolled: appends new route to room.routes.
        - If Trap rolled: sets room trap state to unrevealed.
        - Marks room.searched = True.
        Returns (search_result, tension_event, log_message).
        """
        if room.searched:
            raise ValueError("This chamber has already been searched.")

        tension_event = self.advance_time_and_tension(dungeon)

        # Roll on search table with recursive subtable resolution
        search_res = self.tables.resolve_table("search", recursive=True)
        entry = search_res["entry"]
        result_title = entry.get("result", "Nothing")

        # Check for secret route action
        if entry.get("action") == "add_secret_route":
            new_route = self.generate_secret_route(room.routes)
            room.routes.append(new_route)

        # Check if search rolled a trap
        has_search_trap, search_trap_data = self._extract_trap_from_search(search_res)
        if has_search_trap:
            room.has_trap = True
            room.trap_revealed = False
            room.trap_data = search_trap_data

        room.searched = True
        room.search_result = search_res

        # Format descriptive log message (avoiding trap spoilers)
        details = []
        if "sub_result" in search_res:
            sub = search_res["sub_result"]
            sub_entry = sub.get("entry", {})
            sub_name = sub_entry.get("name") or sub_entry.get("type") or ""
            if sub_name:
                details.append(f"{sub_name}")
            if "sub_result" in sub and not has_search_trap:
                sub_sub = sub["sub_result"].get("entry", {})
                sub_sub_name = sub_sub.get("name") or sub_sub.get("type") or ""
                if sub_sub_name:
                    details.append(f"({sub_sub_name})")

        detail_str = f" — {' '.join(details)}" if details else ""
        log_msg = f"Searched Room {room.room_number}. Result: {result_title}{detail_str}."

        return search_res, tension_event, log_msg
