"""Unit tests for Phase 1: dice, table loading, procedural engine, and compass directions."""

from unittest.mock import patch
import pytest
from dice import ProgressRollResult, roll_progress
from table_loader import TableManager, TableValidationError, get_table_manager
from dungeon_engine import COMPASS_DIRECTIONS, DungeonEngine, DungeonState, RoomState, format_dungeon_time


@pytest.fixture
def table_mgr():
    return get_table_manager()


@pytest.fixture
def engine(table_mgr):
    return DungeonEngine(table_mgr)


# ==========================================
# 1. PROGRESS MECHANIC TESTS
# ==========================================

def test_progress_pool_starts_at_one_die():
    """At progress 0, exactly 1d6 must be rolled."""
    result = roll_progress(0)
    assert result.dice_pool == 1
    assert len(result.rolls) == 1
    assert result.progress_before == 0


def test_progress_pool_scales_with_points():
    """Progress pool equals progress_points + 1."""
    result = roll_progress(3)
    assert result.dice_pool == 4
    assert len(result.rolls) == 4


def test_progress_failure_no_5_or_6():
    """Rolls with no 5 or 6 evaluate to Failure and leave progress unchanged."""
    with patch("dice.roll_die", return_value=3):
        result = roll_progress(2)
        assert result.successes == 0
        assert result.outcome == "failure"
        assert result.progress_after == 2
        assert result.progress_message is None


def test_progress_weak_success_single_5_or_6():
    """Exactly one 5 or 6 evaluates to Weak success, increments progress by 1, and sets progress message."""
    # Pool of 2 dice: roll a 6 and a 2 -> 1 success
    with patch("dice.roll_die", side_effect=[6, 2]):
        result = roll_progress(1)
        assert result.successes == 1
        assert result.outcome == "weak"
        assert result.progress_after == 2
        assert result.progress_message == "Progress made! 2 → 3"


def test_progress_strong_success_two_or_more():
    """Two or more 5 or 6 results evaluate to Strong success."""
    # Pool of 3 dice: roll 5, 6, 1 -> 2 successes
    with patch("dice.roll_die", side_effect=[5, 6, 1]):
        result = roll_progress(2)
        assert result.successes == 2
        assert result.outcome == "strong"
        assert result.progress_message is None


# ==========================================
# 2. DUNGEON CREATION & ENTRANCE TESTS
# ==========================================

def test_entrance_generation_no_progress_roll(engine):
    """The entrance room must not roll progress, begins at 00:00, and has unique compass routes."""
    dungeon = DungeonState(
        id=1,
        name="Ashgrave",
        dungeon_type="Tomb",
        size="Small",
        current_level=1,
        hidden_total_levels=1,
        current_room_number=1,
        elapsed_minutes=0,
        tension_dice=0,
        progress_points=0,
    )
    entrance = engine.generate_entrance_room(dungeon)
    assert entrance.is_entrance is True
    assert entrance.is_unique is False
    assert entrance.room_number == 1
    assert len(entrance.routes) >= 1
    assert entrance.descriptor != ""
    assert entrance.room_type != ""
    assert dungeon.elapsed_minutes == 0

    # Verify structured route directions
    directions = []
    valid_names = {c["name"] for c in COMPASS_DIRECTIONS}
    for r in entrance.routes:
        assert isinstance(r, dict)
        assert "direction" in r and "arrow" in r and "text" in r and "formatted" in r
        assert r["direction"] in valid_names
        directions.append(r["direction"])

    # Ensure no duplicates in the same room
    assert len(directions) == len(set(directions))


def test_dungeon_sizes_hidden_floors(engine):
    """Hidden floors must follow size specifications without leaking to player."""
    for _ in range(50):
        assert engine.determine_hidden_floors("Small") == 1
        assert engine.determine_hidden_floors("Medium") in (1, 2)
        assert engine.determine_hidden_floors("Large") in (2, 3)


# ==========================================
# 3. EXPLORATION & UNIQUE ROOM TESTS
# ==========================================

def test_explore_weak_generates_normal_room_and_increments_progress(engine):
    """Weak success generates normal room and increases progress points."""
    dungeon = DungeonState(
        id=1,
        name="Ashgrave",
        dungeon_type="Tomb",
        size="Medium",
        current_level=1,
        hidden_total_levels=2,
        current_room_number=1,
        elapsed_minutes=0,
        tension_dice=0,
        progress_points=0,
    )
    prev_room = engine.generate_entrance_room(dungeon)

    mock_res = ProgressRollResult(
        dice_pool=1,
        rolls=[5],
        successes=1,
        outcome="weak",
        progress_before=0,
        progress_after=1,
        progress_message="Progress made! 1 → 2",
    )
    with patch("dungeon_engine.roll_progress", return_value=mock_res):
        new_room, progress, _, _ = engine.explore(dungeon, prev_room)
        assert progress.outcome == "weak"
        assert dungeon.progress_points == 1
        assert new_room.is_unique is False
        assert dungeon.elapsed_minutes == 10
        assert dungeon.tension_dice == 1
        assert progress.progress_message == "Progress made! 1 → 2"


def test_explore_failure_leaves_progress_unchanged(engine):
    """Failure generates normal room and does not increase progress points."""
    dungeon = DungeonState(
        id=1,
        name="Ashgrave",
        dungeon_type="Tomb",
        size="Medium",
        current_level=1,
        hidden_total_levels=2,
        current_room_number=1,
        elapsed_minutes=0,
        tension_dice=0,
        progress_points=1,
    )
    prev_room = engine.generate_entrance_room(dungeon)

    mock_res = ProgressRollResult(
        dice_pool=2,
        rolls=[2, 3],
        successes=0,
        outcome="failure",
        progress_before=1,
        progress_after=1,
        progress_message=None,
    )
    with patch("dungeon_engine.roll_progress", return_value=mock_res):
        new_room, progress, _, _ = engine.explore(dungeon, prev_room)
        assert progress.outcome == "failure"
        assert dungeon.progress_points == 1
        assert new_room.is_unique is False
        assert dungeon.elapsed_minutes == 10


def test_explore_strong_generates_unique_room(engine):
    """Strong success (2+ successes) generates the Unique Room."""
    dungeon = DungeonState(
        id=1,
        name="Ashgrave",
        dungeon_type="Tomb",
        size="Medium",
        current_level=1,
        hidden_total_levels=2,
        current_room_number=1,
        elapsed_minutes=0,
        tension_dice=0,
        progress_points=2,
    )
    prev_room = engine.generate_entrance_room(dungeon)

    mock_res = ProgressRollResult(
        dice_pool=3,
        rolls=[6, 6, 1],
        successes=2,
        outcome="strong",
        progress_before=2,
        progress_after=2,
        progress_message=None,
    )
    with patch("dungeon_engine.roll_progress", return_value=mock_res):
        new_room, progress, _, _ = engine.explore(dungeon, prev_room)
        assert progress.outcome == "strong"
        assert new_room.is_unique is True
        assert "unique_room" in new_room.contents_data
        assert new_room.next_level_exists is True
        assert new_room.is_final_room is False


def test_level_descent_resets_progress_to_zero(engine):
    """Descending after a Unique Room resets progress to 0 and generates a new Entrance."""
    dungeon = DungeonState(
        id=1,
        name="Ashgrave",
        dungeon_type="Tomb",
        size="Medium",
        current_level=1,
        hidden_total_levels=2,
        current_room_number=4,
        elapsed_minutes=40,
        tension_dice=4,
        progress_points=3,
    )
    # Simulate a unique room
    unique_room = RoomState(
        room_number=4,
        is_unique=True,
        next_level_exists=True,
    )

    new_room, progress, _, _ = engine.explore(dungeon, unique_room)
    assert dungeon.current_level == 2
    assert dungeon.progress_points == 0
    assert progress is None  # Entrance does not roll progress
    assert new_room.is_entrance is True
    assert new_room.level == 2


# ==========================================
# 4. TIME & TENSION CLOCK TESTS
# ==========================================

def test_time_advancement_and_tension_clock(engine):
    """Actions advance time by 10m and tension dice by 1; triggers event at 6."""
    dungeon = DungeonState(
        id=1,
        name="Ashgrave",
        dungeon_type="Tomb",
        size="Small",
        current_level=1,
        hidden_total_levels=1,
        current_room_number=1,
        elapsed_minutes=50,
        tension_dice=5,
        progress_points=0,
    )
    prev_room = engine.generate_entrance_room(dungeon)

    mock_res = ProgressRollResult(
        dice_pool=1,
        rolls=[1],
        successes=0,
        outcome="failure",
        progress_before=0,
        progress_after=0,
        progress_message=None,
    )
    with patch("dungeon_engine.roll_progress", return_value=mock_res):
        _, _, tension_event, _ = engine.explore(dungeon, prev_room)
        assert dungeon.elapsed_minutes == 60
        assert format_dungeon_time(dungeon.elapsed_minutes) == "01:00"
        assert dungeon.tension_dice == 0
        assert tension_event is not None
        assert tension_event["triggered"] is True
        assert "type" in tension_event["event"]


# ==========================================
# 5. SEARCH & SECRET ROUTE DIRECTION TESTS
# ==========================================

def test_search_cannot_be_performed_twice(engine):
    """Searching a room once marks it searched; second attempt raises error."""
    dungeon = DungeonState(id=1, name="Test", dungeon_type="Tomb", elapsed_minutes=0, tension_dice=0)
    room = engine.generate_entrance_room(dungeon)

    assert room.searched is False
    res, _, _ = engine.search(dungeon, room)
    assert room.searched is True
    assert dungeon.elapsed_minutes == 10
    assert dungeon.tension_dice == 1

    with pytest.raises(ValueError, match="already been searched"):
        engine.search(dungeon, room)


def test_search_secret_route_appends_unique_direction(engine):
    """Secret Route receives a unique compass direction not used by other routes in the room."""
    dungeon = DungeonState(id=1, name="Test", dungeon_type="Tomb", elapsed_minutes=0, tension_dice=0)
    room = engine.generate_entrance_room(dungeon)
    initial_route_count = len(room.routes)
    initial_directions = {r["direction"] for r in room.routes if isinstance(r, dict)}

    # Force search roll 12 (Secret route on 2d6) in table_loader
    with patch("table_loader.roll_notation", return_value=(12, [6, 6])):
        res, _, _ = engine.search(dungeon, room)
        assert res["entry"]["result"] == "Secret route"
        assert len(room.routes) == initial_route_count + 1

        secret_route = room.routes[-1]
        assert isinstance(secret_route, dict)
        assert "(secret route)" in secret_route["text"]
        # Direction must be unique
        assert secret_route["direction"] not in initial_directions
        all_dirs = [r["direction"] for r in room.routes]
        assert len(all_dirs) == len(set(all_dirs))


def test_recursive_subtable_resolution(engine):
    """Hazard Discovered in Search recursively rolls on the Hazards table."""
    dungeon = DungeonState(id=1, name="Test", dungeon_type="Tomb", elapsed_minutes=0, tension_dice=0)
    room = engine.generate_entrance_room(dungeon)

    # Force search roll 3 (Hazard Discovered) then hazard roll 2 (Unstable ceiling)
    with patch("table_loader.roll_notation", side_effect=[(3, [1, 2]), (2, [2])]):
        res, _, _ = engine.search(dungeon, room)
        assert res["entry"]["result"] == "Hazard Discovered"
        assert "sub_result" in res
        assert res["sub_result"]["source_table"] == "hazards"


# ==========================================
# 5. TRAP REVEAL SYSTEM TESTS
# ==========================================

def test_traps_table_has_twenty_entries(table_mgr):
    """Verifies traps.json contains the exact 20 required traps with warning and description."""
    traps_data = table_mgr.tables.get("traps", {})
    assert traps_data.get("dice") == "d20"
    entries = traps_data.get("entries", [])
    assert len(entries) == 20
    names = [e["name"] for e in entries]
    expected_names = [
        "Swinging Blade", "Pitfall", "Dart Launcher", "Falling Block", "Poison Gas",
        "Swinging Weight", "Snare", "Crushing Walls", "Flame Jet", "Collapsing Ceiling",
        "Needle Lock", "False Door", "Flooding Chamber", "Rolling Boulder", "Net Trap",
        "Spiked Floor", "Magical Ward", "Alarm", "Sealing Doors", "Pendulum"
    ]
    assert names == expected_names
    for entry in entries:
        assert "warning" in entry and len(entry["warning"]) > 0
        assert "description" in entry and len(entry["description"]) > 0


def test_room_state_trap_display_name_and_warning():
    """RoomState surfaces trap_display_name and trap_warning."""
    room = RoomState(trap_data={
        "name": "Pitfall",
        "warning": "The floor gives a faint creak beneath your weight.",
        "description": "A section of flooring is nothing more than a carefully disguised cover over a deep pit."
    })
    assert room.trap_display_name == "Pitfall"
    assert room.trap_warning == "The floor gives a faint creak beneath your weight."

    # Fallback for uninitialized trap_data
    empty_room = RoomState(trap_data=None)
    assert empty_room.trap_display_name == "Trap"
    assert "click" in empty_room.trap_warning


def test_reveal_trap_engine_method(engine):
    """reveal_trap marks trap as revealed, retains or rolls trap_data, and generates log."""
    room = RoomState(
        room_number=3,
        has_trap=True,
        trap_revealed=False,
        trap_data={
            "name": "Swinging Blade",
            "warning": "You hear a click, as though something has just been activated.",
            "description": "A thin seam in the nearby wall conceals a heavy blade poised to sweep across the room."
        }
    )

    data, log_msg = engine.reveal_trap(room)
    assert room.trap_revealed is True
    assert data["name"] == "Swinging Blade"
    assert log_msg == "Trap revealed in Room 3: Swinging Blade."

    # Room without trap raises ValueError
    no_trap_room = RoomState(has_trap=False)
    with pytest.raises(ValueError, match="No trap exists"):
        engine.reveal_trap(no_trap_room)


def test_explore_hazard_trap_populates_unrevealed_trap(engine):
    """When exploration rolls Hazard -> Trap, the chamber gets has_trap=True, trap_revealed=False and warning."""
    dungeon = DungeonState(id=1, name="Test", dungeon_type="Tomb", elapsed_minutes=0, tension_dice=0, progress_points=0)
    current_room = engine.generate_entrance_room(dungeon)

    mock_res = ProgressRollResult(
        dice_pool=1,
        rolls=[5],
        successes=1,
        outcome="weak",
        progress_before=0,
        progress_after=1,
        progress_message="Progress made! 1 → 2",
    )
    fake_contents = {
        "roll": 4,
        "entry": {"min": 4, "max": 4, "type": "Hazard", "subtable": "hazards"},
        "source_table": "contents",
        "sub_result": {
            "roll": 1,
            "entry": {"min": 1, "max": 1, "name": "Trap", "subtable": "traps", "description": "A concealed snare."},
            "source_table": "hazards",
            "sub_result": {
                "roll": 1,
                "entry": {
                    "min": 1,
                    "max": 1,
                    "name": "Swinging Blade",
                    "warning": "You hear a click, as though something has just been activated.",
                    "description": "A thin seam in the nearby wall conceals a heavy blade poised to sweep across the room.",
                },
                "source_table": "traps",
            },
        },
    }
    with patch("dungeon_engine.roll_progress", return_value=mock_res):
        orig_resolve = engine.tables.resolve_table

        def mock_resolve(table_name, recursive=True):
            if table_name == "contents":
                return fake_contents
            return orig_resolve(table_name, recursive=recursive)

        with patch.object(engine.tables, "resolve_table", side_effect=mock_resolve):
            new_room, prog_res, _, _ = engine.explore(dungeon, current_room)
            assert new_room.has_trap is True
            assert new_room.trap_revealed is False
            assert new_room.trap_data is not None
            assert new_room.trap_data["name"] == "Swinging Blade"
            assert new_room.trap_warning == "You hear a click, as though something has just been activated."
            assert new_room.contents_has_trap is True


def test_search_trap_populates_unrevealed_trap_and_no_spoiler_log(engine):
    """When search uncovers a Trap, has_trap is set to True, trap_revealed=False, and log does not leak trap name."""
    dungeon = DungeonState(id=1, name="Test", dungeon_type="Tomb", elapsed_minutes=0, tension_dice=0)
    room = RoomState(room_number=2, has_trap=False, searched=False)

    # Force search roll 3 (Hazard Discovered), hazard roll 1 (Trap), traps roll 2 (Pitfall)
    with patch("table_loader.roll_notation", side_effect=[(3, [1, 2]), (1, [1]), (2, [2])]):
        search_res, _, log_msg = engine.search(dungeon, room)
        assert room.has_trap is True
        assert room.trap_revealed is False
        assert room.trap_data is not None
        assert room.trap_data["name"] == "Pitfall"
        assert room.trap_warning == "The floor gives a faint creak beneath your weight."
        assert room.search_has_trap is True
        # Log should NOT contain the specific trap name "(Pitfall)"
        assert "(Pitfall)" not in log_msg
        assert "Pitfall" not in log_msg
        assert "Trap" in log_msg


# ==========================================
# 6. ROOM OBJECTS ROLL TABLE TESTS
# ==========================================

def test_room_objects_table_valid_and_has_100_entries(table_mgr):
    """Verifies room_objects.json table is properly loaded with 100 atmospheric objects."""
    objects_data = table_mgr.tables.get("room_objects", {})
    assert objects_data.get("dice") == "d100"
    entries = objects_data.get("entries", [])
    assert len(entries) == 100
    for e in entries:
        assert "name" in e and len(e["name"]) > 0


def test_roll_room_objects_returns_three_distinct_items(engine):
    """roll_room_objects(3) selects 3 unique items without replacement."""
    objects = engine.roll_room_objects(3)
    assert len(objects) == 3
    assert len(set(objects)) == 3  # All distinct
    for item in objects:
        assert isinstance(item, str) and len(item) > 0


def test_entrance_and_explored_rooms_contain_three_objects(engine):
    """Every generated room receives exactly 3 random objects."""
    dungeon = DungeonState(id=1, name="Test", dungeon_type="Tomb", elapsed_minutes=0, tension_dice=0, progress_points=0)
    entrance = engine.generate_entrance_room(dungeon)
    assert len(entrance.objects) == 3
    assert len(set(entrance.objects)) == 3

    # Explore room
    new_room, _, _, _ = engine.explore(dungeon, entrance)
    assert len(new_room.objects) == 3
    assert len(set(new_room.objects)) == 3

