"""End-to-end integration tests for Flask app, database persistence, routes, and progress display."""

import json
import os
import tempfile
from unittest.mock import patch
import pytest
from app import app
from database import Database
from dice import ProgressRollResult


@pytest.fixture
def test_client():
    # Use a temporary SQLite database file for isolation
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    app.config["TESTING"] = True
    app.config["DATABASE_PATH"] = temp_db_path
    test_db = Database(temp_db_path)

    # Patch the global db in app module
    with patch("app.db", test_db):
        with app.test_client() as client:
            yield client, test_db

    # Clean up
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


def test_main_menu(test_client):
    client, _ = test_client
    res = client.get("/")
    assert res.status_code == 200
    assert b"SOLO TTRPG TOOLS" in res.data
    assert b"Dungeon Crawler" in res.data
    assert b"Hexroll 3 Sandbox" in res.data


def test_hexroll_route(test_client):
    client, _ = test_client
    res = client.get("/hexroll")
    assert res.status_code == 200
    assert b"HEXROLL 3 (BACKER EDITION)" in res.data
    assert b"/xpra/" in res.data


def test_dungeon_menu_empty(test_client):
    client, _ = test_client
    res = client.get("/dungeon")
    assert res.status_code == 200
    assert b"No dungeons recorded yet" in res.data


def test_random_name_api(test_client):
    client, _ = test_client
    res = client.get("/api/random-name?type=Tomb")
    assert res.status_code == 200
    data = res.get_json()
    assert "name" in data
    assert len(data["name"]) > 0
    assert data["dungeon_type"] == "Tomb"


def test_create_dungeon_and_entrance(test_client):
    client, test_db = test_client
    res = client.post("/dungeon/new", data={
        "name": "Ashgrave",
        "dungeon_type": "Tomb",
        "size": "Small",
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"ASHGRAVE" in res.data
    assert b"Level 1" in res.data
    assert b"Progress: 1" in res.data
    assert b"00:00" in res.data
    assert b"ROOM 1" in res.data
    assert b"ROUTES" in res.data
    assert b"CONTENTS" in res.data

    # Verify structured route directions rendered in HTML
    assert b"route-direction" in res.data
    assert b"route-arrow" in res.data

    # Verify no internal dice pool / raw details leak
    assert b"progress_points" not in res.data
    assert b"hidden_total_levels" not in res.data

    # Verify in DB
    dungeons = test_db.list_dungeons()
    assert len(dungeons) == 1
    assert dungeons[0]["name"] == "Ashgrave"
    assert dungeons[0]["elapsed_minutes"] == 0


def test_player_visible_progress_advancement_and_logging(test_client):
    """Test that weak success advances Progress: 1 -> 2, surfaces message, and logs it."""
    client, test_db = test_client
    client.post("/dungeon/new", data={
        "name": "Bone Vault",
        "dungeon_type": "Tomb",
        "size": "Medium",
    })
    d_id = test_db.list_dungeons()[0]["id"]

    weak_res = ProgressRollResult(
        dice_pool=1,
        rolls=[5],
        successes=1,
        outcome="weak",
        progress_before=0,
        progress_after=1,
        progress_message="Progress made! 1 → 2",
    )

    with patch("dungeon_engine.roll_progress", return_value=weak_res):
        res = client.post(f"/dungeon/{d_id}/explore", follow_redirects=True)
        assert res.status_code == 200
        assert b"Progress: 2" in res.data
        assert b"Progress made! 1 \xe2\x86\x92 2" in res.data  # "Progress made! 1 → 2" utf-8

        # Verify it was logged in SQLite
        logs = test_db.get_dungeon_logs(d_id)
        logged_entries = [entry["entry"] for entry in logs]
        assert any("Progress made! 1 → 2" in e for e in logged_entries)


def test_explore_adds_ten_minutes_and_saves(test_client):
    client, test_db = test_client
    # Create dungeon
    client.post("/dungeon/new", data={
        "name": "Sunken Grotto",
        "dungeon_type": "Cave",
        "size": "Medium",
    })
    dungeon = test_db.list_dungeons()[0]
    d_id = dungeon["id"]

    # Explore next room
    res = client.post(f"/dungeon/{d_id}/explore", follow_redirects=True)
    assert res.status_code == 200
    assert b"00:10" in res.data
    assert b"ROOM 2" in res.data

    # DB state verified
    d_updated = test_db.get_dungeon(d_id)
    assert d_updated.elapsed_minutes == 10
    assert d_updated.current_room_number == 2


def test_search_mechanic_and_restriction(test_client):
    client, test_db = test_client
    client.post("/dungeon/new", data={
        "name": "Iron Keep",
        "dungeon_type": "Fort",
        "size": "Small",
    })
    d_id = test_db.list_dungeons()[0]["id"]

    # Perform first search
    res = client.post(f"/dungeon/{d_id}/search", follow_redirects=True)
    assert res.status_code == 200
    assert b"00:10" in res.data
    assert b"Searched" in res.data
    assert b"SEARCH RESULT" in res.data

    # Try searching second time (should be blocked / no extra time)
    res2 = client.post(f"/dungeon/{d_id}/search", follow_redirects=True)
    assert res2.status_code == 200
    d_updated = test_db.get_dungeon(d_id)
    # Time must still be 10 minutes (not 20)
    assert d_updated.elapsed_minutes == 10


def test_tension_clock_hourly_trigger(test_client):
    client, test_db = test_client
    client.post("/dungeon/new", data={
        "name": "Crypt of Shadows",
        "dungeon_type": "Tomb",
        "size": "Large",
    })
    d_id = test_db.list_dungeons()[0]["id"]

    fail_res = ProgressRollResult(
        dice_pool=1,
        rolls=[1],
        successes=0,
        outcome="failure",
        progress_before=0,
        progress_after=0,
        progress_message=None,
    )

    # Perform 5 explore actions (50 minutes elapsed, tension_dice = 5)
    with patch("dungeon_engine.roll_progress", return_value=fail_res):
        for _ in range(5):
            client.post(f"/dungeon/{d_id}/explore")

        d_check = test_db.get_dungeon(d_id)
        assert d_check.elapsed_minutes == 50
        assert d_check.tension_dice == 5

        # 6th action (60 minutes elapsed, triggers tension clock event and resets tension_dice to 0)
        res = client.post(f"/dungeon/{d_id}/explore", follow_redirects=True)
        assert res.status_code == 200
        assert b"01:00" in res.data
        assert b"The Clock Advances" in res.data

    d_final = test_db.get_dungeon(d_id)
    assert d_final.elapsed_minutes == 60
    assert d_final.tension_dice == 0


def test_log_view_and_exports(test_client):
    client, test_db = test_client
    client.post("/dungeon/new", data={
        "name": "Forgotten Crypt",
        "dungeon_type": "Tomb",
        "size": "Small",
    })
    d_id = test_db.list_dungeons()[0]["id"]

    client.post(f"/dungeon/{d_id}/explore")
    client.post(f"/dungeon/{d_id}/search")

    # Check JSON log API
    res_api = client.get(f"/dungeon/{d_id}/log")
    assert res_api.status_code == 200
    log_data = res_api.get_json()
    assert len(log_data["logs"]) >= 3  # Entrance + Explore + Search

    # Check Plain Text export
    res_txt = client.get(f"/dungeon/{d_id}/export?format=txt")
    assert res_txt.status_code == 200
    assert b"FORGOTTEN CRYPT" in res_txt.data
    assert b"00:00" in res_txt.data
    assert b"00:10" in res_txt.data

    # Check Markdown export
    res_md = client.get(f"/dungeon/{d_id}/export?format=md")
    assert res_md.status_code == 200
    assert b"# Forgotten Crypt" in res_md.data
    assert b"## Exploration Log" in res_md.data


def test_delete_dungeon(test_client):
    client, test_db = test_client
    client.post("/dungeon/new", data={
        "name": "Ruined Bastion",
        "dungeon_type": "Ruins",
        "size": "Small",
    })
    dungeons = test_db.list_dungeons()
    assert len(dungeons) == 1
    d_id = dungeons[0]["id"]

    # Delete
    res = client.post(f"/dungeon/{d_id}/delete", follow_redirects=True)
    assert res.status_code == 200
    assert len(test_db.list_dungeons()) == 0


def test_resume_preserves_exact_state(test_client):
    client, test_db = test_client
    client.post("/dungeon/new", data={
        "name": "Ancient Sewers",
        "dungeon_type": "Sewers",
        "size": "Medium",
    })
    d_id = test_db.list_dungeons()[0]["id"]

    client.post(f"/dungeon/{d_id}/explore")
    client.post(f"/dungeon/{d_id}/search")

    # Resume dungeon play screen
    res = client.get(f"/dungeon/{d_id}/play")
    assert res.status_code == 200
    assert b"ANCIENT SEWERS" in res.data
    assert b"00:20" in res.data
    assert b"ROOM 2" in res.data
    assert b"Searched" in res.data


def test_trap_initial_unidentified_state_and_reveal_flow(test_client):
    client, test_db = test_client
    client.post("/dungeon/new", data={
        "name": "Sunken Crypt",
        "dungeon_type": "Tomb",
        "size": "Small",
    })
    d_id = test_db.list_dungeons()[0]["id"]
    dungeon = test_db.get_dungeon(d_id)
    room = test_db.get_room(dungeon.current_room_id)

    # Configure the room with a trap from contents
    room.has_trap = True
    room.trap_revealed = False
    room.trap_data = {
        "name": "Swinging Blade",
        "warning": "You hear a click, as though something has just been activated.",
        "description": "A thin seam in the nearby wall conceals a heavy blade poised to sweep across the room."
    }
    test_db.save_room(room)

    # 1. Verify Unidentified / Hidden state in UI
    res = client.get(f"/dungeon/{d_id}/play")
    assert res.status_code == 200
    assert b"Trap" in res.data
    assert b"You hear a click, as though something has just been activated." in res.data
    assert b"Reveal" in res.data
    # Specific type and description must NOT be revealed yet
    assert b"Swinging Blade" not in res.data
    assert b"A thin seam in the nearby wall conceals a heavy blade" not in res.data

    # 2. Click Reveal
    res_reveal = client.post(f"/dungeon/{d_id}/reveal-trap", follow_redirects=True)
    assert res_reveal.status_code == 200

    # Specific trap is now revealed
    assert b"Swinging Blade" in res_reveal.data
    assert b"A thin seam in the nearby wall conceals a heavy blade" in res_reveal.data
    # Click quote and Reveal button should no longer be present
    assert b"You hear a click, as though something has just been activated." not in res_reveal.data
    assert b'class="btn btn-reveal"' not in res_reveal.data

    # 3. Verify SQLite persistence
    updated_room = test_db.get_room(room.id)
    assert updated_room.has_trap is True
    assert updated_room.trap_revealed is True
    assert updated_room.trap_data["name"] == "Swinging Blade"

    # 4. Verify log entry was recorded
    logs = test_db.get_dungeon_logs(d_id)
    trap_logs = [l for l in logs if "Trap revealed" in l["entry"]]
    assert len(trap_logs) == 1
    assert "Trap revealed in Room 1: Swinging Blade." in trap_logs[0]["entry"]


def test_trap_revealed_state_persists_across_reloads(test_client):
    client, test_db = test_client
    client.post("/dungeon/new", data={
        "name": "Forgotten Tomb",
        "dungeon_type": "Tomb",
        "size": "Small",
    })
    d_id = test_db.list_dungeons()[0]["id"]
    dungeon = test_db.get_dungeon(d_id)
    room = test_db.get_room(dungeon.current_room_id)

    room.has_trap = True
    room.trap_revealed = True
    room.trap_data = {
        "name": "Poison Gas",
        "warning": "You hear a quiet hiss that wasn't there a moment ago.",
        "description": "Narrow vents hidden in the masonry are beginning to release a strange vapor into the chamber."
    }
    test_db.save_room(room)

    # Reloading/resuming the screen preserves revealed state
    res = client.get(f"/dungeon/{d_id}/play")
    assert res.status_code == 200
    assert b"Poison Gas" in res.data
    assert b"Narrow vents hidden in the masonry are beginning to release a strange vapor into the chamber." in res.data
    assert b"You hear a quiet hiss" not in res.data


def test_search_trap_reveal_flow(test_client):
    client, test_db = test_client
    client.post("/dungeon/new", data={
        "name": "Dead Crypt",
        "dungeon_type": "Tomb",
        "size": "Small",
    })
    d_id = test_db.list_dungeons()[0]["id"]

    # Search roll 3 (Hazard Discovered) -> 1 (Trap) -> 5 (Poison Gas on d20)
    with patch("table_loader.roll_notation", side_effect=[(3, [1, 2]), (1, [1]), (5, [5])]):
        res_search = client.post(f"/dungeon/{d_id}/search", follow_redirects=True)
        assert res_search.status_code == 200
        assert b"SEARCH RESULT" in res_search.data
        assert b"You hear a quiet hiss" in res_search.data
        assert b"Poison Gas" not in res_search.data

    # Reveal the search trap
    res_reveal = client.post(f"/dungeon/{d_id}/reveal-trap", follow_redirects=True)
    assert res_reveal.status_code == 200
    assert b"Poison Gas" in res_reveal.data
    assert b"Narrow vents hidden in the masonry are beginning to release a strange vapor into the chamber." in res_reveal.data


def test_room_objects_persisted_and_displayed(test_client):
    client, test_db = test_client
    res = client.post("/dungeon/new", data={
        "name": "Dusty Vault",
        "dungeon_type": "Tomb",
        "size": "Small",
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"OBJECTS" in res.data
    d_id = test_db.list_dungeons()[0]["id"]
    dungeon = test_db.get_dungeon(d_id)
    room = test_db.get_room(dungeon.current_room_id)

    # 3 distinct objects in room state
    assert len(room.objects) == 3
    assert len(set(room.objects)) == 3
    for obj in room.objects:
        assert obj.encode("utf-8") in res.data

    # Explore and verify objects on the next room
    res_explore = client.post(f"/dungeon/{d_id}/explore", follow_redirects=True)
    assert res_explore.status_code == 200
    assert b"OBJECTS" in res_explore.data
    updated_dungeon = test_db.get_dungeon(d_id)
    room2 = test_db.get_room(updated_dungeon.current_room_id)
    assert len(room2.objects) == 3
    assert len(set(room2.objects)) == 3
    for obj in room2.objects:
        assert obj.encode("utf-8") in res_explore.data


