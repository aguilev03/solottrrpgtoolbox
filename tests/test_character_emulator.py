"""Comprehensive Acceptance & Unit Tests for the Character Emulator module."""

import os
import tempfile
import pytest
from app import app
from database import Database
from dice import roll_d66
from emulator_engine import EmulatorEngine, roll_d6, roll_triple_o


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def emulator_engine():
    return EmulatorEngine("data")


@pytest.fixture
def client(temp_db):
    app.config["TESTING"] = True
    app.config["DATABASE_PATH"] = temp_db.db_path

    # Patch global db
    import app as app_module
    old_db = app_module.db
    app_module.db = temp_db

    with app.test_client() as client:
        yield client

    app_module.db = old_db


# ==========================================
# 1. ENGINE & RANDOMIZATION TESTS
# ==========================================

def test_d66_rolling_valid_range():
    """d66 rolling only generates valid two-digit results."""
    valid_d66 = {
        11, 12, 13, 14, 15, 16,
        21, 22, 23, 24, 25, 26,
        31, 32, 33, 34, 35, 36,
        41, 42, 43, 44, 45, 46,
        51, 52, 53, 54, 55, 56,
        61, 62, 63, 64, 65, 66,
    }
    for _ in range(500):
        val = roll_d66()
        assert val in valid_d66


def test_triple_o_check_mapping():
    """Acceptance Test 39: 1 = THE ODD, 2-3 = THE OPTION, 4-6 = THE OBVIOUS."""
    counts = {"THE ODD": 0, "THE OPTION": 0, "THE OBVIOUS": 0}
    for _ in range(3000):
        roll, classification = roll_triple_o()
        assert 1 <= roll <= 6
        if roll == 1:
            assert classification == "THE ODD"
        elif roll in (2, 3):
            assert classification == "THE OPTION"
        else:
            assert classification == "THE OBVIOUS"
        counts[classification] += 1

    # Approximate distribution checks (1/6 ~ 16.7%, 2/6 ~ 33.3%, 3/6 ~ 50%)
    assert 350 < counts["THE ODD"] < 650
    assert 800 < counts["THE OPTION"] < 1200
    assert 1200 < counts["THE OBVIOUS"] < 1800


def test_zero_traits_uses_default_placeholder(emulator_engine):
    """Acceptance Test 37: Zero traits uses display-only DEFAULT placeholder."""
    results = emulator_engine.roll_specific_action("downtime", [], count=3)
    assert len(results) == 3
    for r in results:
        assert r["trait"]["trait"] == "DEFAULT"
        assert r["trait"]["status"] == "Default"
        assert r["trait"]["is_placeholder"] is True
        assert r["d66"] in range(11, 67)
        assert r["triple_o_classification"] in ("THE ODD", "THE OPTION", "THE OBVIOUS")
        assert len(r["action"]) > 0


def test_traits_weighted_selection_prevalent_is_double(emulator_engine):
    """Acceptance Test 40: Prevalent traits are selected ~2x as often as Default/Temporary."""
    traits = [
        {"id": 1, "status": "default", "trait": "Trait A", "category": "PR"},
        {"id": 2, "status": "prevalent", "trait": "Trait B", "category": "BG"},
        {"id": 3, "status": "default", "trait": "Trait C", "category": "SK"},
    ]
    counts = {"Trait A": 0, "Trait B": 0, "Trait C": 0}
    for _ in range(6000):
        chosen = emulator_engine.select_weighted_trait(traits)
        counts[chosen["trait"]] += 1

    # Expected ratio: A=1, B=2, C=1 (Total weight 4: A=25%, B=50%, C=25%)
    # Out of 6000: A ~ 1500, B ~ 3000, C ~ 1500
    assert 1200 < counts["Trait A"] < 1800
    assert 2600 < counts["Trait B"] < 3400
    assert 1200 < counts["Trait C"] < 1800
    assert counts["Trait B"] > counts["Trait A"] * 1.5
    assert counts["Trait B"] > counts["Trait C"] * 1.5


def test_three_independent_action_prompts_generated(emulator_engine):
    """Acceptance Test 38: Exactly 3 independent prompts with Trait, d66 Action, and Triple-O."""
    john_traits = [
        {"id": 1, "status": "prevalent", "trait": "Grew up on a farm", "category": "BG"},
        {"id": 2, "status": "default", "trait": "Protective", "category": "PR"},
        {"id": 3, "status": "temporary", "trait": "Homesick", "category": "CN"},
    ]
    results = emulator_engine.roll_specific_action("combat", john_traits, count=3)
    assert len(results) == 3

    # Check each prompt format
    for r in results:
        assert "trait" in r
        assert r["trait"]["trait"] in ["Grew up on a farm", "Protective", "Homesick"]
        assert r["d66"] in range(11, 67)
        assert len(r["action"]) > 0
        assert r["triple_o_roll"] in range(1, 7)
        assert r["triple_o_classification"] in ("THE ODD", "THE OPTION", "THE OBVIOUS")


def test_spark_tables_single_and_combination(emulator_engine):
    """Acceptance Test 46: Spark roll generates valid single or combo results."""
    # Single table: Method
    spark_method = emulator_engine.roll_spark("method")
    assert spark_method["type"] == "single"
    assert spark_method["display_name"] == "Method"
    assert len(spark_method["rolls"]) == 1
    assert spark_method["rolls"][0]["table"] == "Method"
    assert len(spark_method["rolls"][0]["result"]) > 0

    # Combination: Action + Focus
    spark_combo = emulator_engine.roll_spark("action_focus")
    assert spark_combo["type"] == "combination"
    assert len(spark_combo["rolls"]) == 2
    assert spark_combo["rolls"][0]["table"] == "Action"
    assert spark_combo["rolls"][1]["table"] == "Focus"
    assert len(spark_combo["rolls"][0]["result"]) > 0
    assert len(spark_combo["rolls"][1]["result"]) > 0


# ==========================================
# 2. DATABASE & PARTY MEMBER RULES TESTS
# ==========================================

def test_party_member_forces_current(temp_db):
    """Acceptance Test 41: Setting Party Member = true automatically sets Current = true."""
    npc_id = temp_db.create_npc(name="John", party_member=True, current=False)
    npc = temp_db.get_npc(npc_id)
    assert npc["party_member"] is True
    assert npc["current"] is True


def test_cannot_uncheck_current_while_party_member(temp_db):
    """Acceptance Test 41: Attempting current = false while party_member = true raises ValueError."""
    npc_id = temp_db.create_npc(name="John", party_member=True)
    with pytest.raises(ValueError, match="Party Members are always Current"):
        temp_db.update_npc(npc_id, current=False)

    # NPC remains intact
    npc = temp_db.get_npc(npc_id)
    assert npc["current"] is True
    assert npc["party_member"] is True


def test_leave_party_keeps_current(temp_db):
    """Acceptance Test 42: Unchecking party member keeps current = true."""
    npc_id = temp_db.create_npc(name="John", party_member=True)
    # Uncheck party_member
    temp_db.update_npc(npc_id, party_member=False)
    npc = temp_db.get_npc(npc_id)
    assert npc["party_member"] is False
    assert npc["current"] is True


def test_remove_current_leaves_npc_in_library(temp_db):
    """Acceptance Test 43: Unchecking Current hides NPC from scene but preserves in DB."""
    npc_id = temp_db.create_npc(name="Harven", party_member=False, current=True)
    temp_db.update_npc(npc_id, current=False)

    # Not in current list
    current_list = temp_db.list_npcs(current_only=True)
    assert all(n["id"] != npc_id for n in current_list)

    # Present in full library
    all_npcs = temp_db.list_npcs()
    assert any(n["id"] == npc_id and n["current"] is False for n in all_npcs)


def test_make_current_restores_npc(temp_db):
    """Acceptance Test 44: Setting current = true restores NPC to current scene."""
    npc_id = temp_db.create_npc(name="Old Marcus", current=False)
    temp_db.update_npc(npc_id, current=True)
    current_list = temp_db.list_npcs(current_only=True)
    assert any(n["id"] == npc_id for n in current_list)


def test_quick_add_trait(temp_db):
    """Acceptance Test 45: Adding a trait stores it and associates with NPC."""
    npc_id = temp_db.create_npc(name="Mira")
    trait_id = temp_db.add_npc_trait(npc_id, status="temporary", trait="Injured leg", category="CN")
    assert trait_id > 0

    npc = temp_db.get_npc(npc_id)
    assert len(npc["traits"]) == 1
    t = npc["traits"][0]
    assert t["status"] == "temporary"
    assert t["trait"] == "Injured leg"
    assert t["category"] == "CN"


def test_persistence_across_database_reloads(temp_db):
    """Acceptance Test 47: NPCs and traits survive database reloads."""
    npc_id = temp_db.create_npc(
        name="Elena",
        details="Ranger scout",
        current=True,
        party_member=True,
        traits=[
            {"status": "prevalent", "trait": "Keen senses", "category": "SK"},
            {"status": "default", "trait": "Quiet", "category": "PR"},
        ],
    )

    # Create a fresh database connection pointing to the same file
    new_conn_db = Database(temp_db.db_path)
    npc = new_conn_db.get_npc(npc_id)
    assert npc is not None
    assert npc["name"] == "Elena"
    assert npc["details"] == "Ranger scout"
    assert npc["current"] is True
    assert npc["party_member"] is True
    assert len(npc["traits"]) == 2
    assert npc["traits"][0]["trait"] == "Keen senses"
    assert npc["traits"][0]["status"] == "prevalent"


# ==========================================
# 3. HTTP / ENDPOINT INTEGRATION TESTS
# ==========================================

def test_index_page_shows_character_emulator_card(client):
    """Main page contains Character Emulator tool directly under Dungeon Crawler."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Dungeon Crawler" in html
    assert "Character Emulator" in html
    assert "/emulator" in html


def test_emulator_main_empty_state(client):
    """Character Emulator renders without errors when empty."""
    res = client.get("/emulator")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "CHARACTER EMULATOR" in html
    assert "+ Add NPC" in html
    assert "Find NPC" in html
    assert "Manage NPCs" in html
    # Empty state prompt
    assert "No Active NPCs in the Scene" in html


def test_create_npc_and_render_sections(client):
    """Creates party member and regular current NPC, verifies sections render correctly."""
    # Create Party Member
    res1 = client.post("/emulator/npc/new", json={
        "name": "John",
        "details": "Fighter",
        "current": True,
        "party_member": True,
        "traits": [{"status": "prevalent", "trait": "Brave", "category": "PR"}]
    })
    assert res1.status_code == 200

    # Create Non-Party Current NPC
    res2 = client.post("/emulator/npc/new", json={
        "name": "Harven",
        "details": "Merchant",
        "current": True,
        "party_member": False,
        "traits": []
    })
    assert res2.status_code == 200

    # View emulator page
    res_page = client.get("/emulator")
    assert res_page.status_code == 200
    html = res_page.get_data(as_text=True)
    assert "PARTY MEMBERS" in html
    assert "CURRENT NPCs" in html
    assert "John" in html
    assert "Harven" in html


def test_roll_action_api_zero_traits(client):
    """Acceptance Test 37 via API: Rolling action on NPC with 0 traits returns 3 prompts with DEFAULT."""
    res = client.post("/emulator/npc/new", json={"name": "Bob", "current": True, "party_member": False})
    npc_id = res.get_json()["npc"]["id"]

    roll_res = client.post(f"/emulator/npc/{npc_id}/roll-action", json={"action_type": "downtime"})
    assert roll_res.status_code == 200
    data = roll_res.get_json()
    assert data["success"] is True
    assert len(data["results"]) == 3
    for r in data["results"]:
        assert r["trait"]["trait"] == "DEFAULT"
        assert r["triple_o_classification"] in ("THE ODD", "THE OPTION", "THE OBVIOUS")


def test_toggle_status_api_prevents_unchecking_current_while_party(client):
    """API rejects setting current=False when party_member=True with 400 status."""
    res = client.post("/emulator/npc/new", json={"name": "Alden", "party_member": True})
    npc_id = res.get_json()["npc"]["id"]

    bad_toggle = client.post(f"/emulator/npc/{npc_id}/toggle-status", json={"current": False})
    assert bad_toggle.status_code == 400
    err_data = bad_toggle.get_json()
    assert err_data["success"] is False
    assert "Party Members are always Current" in err_data["error"]


def test_quick_add_trait_api(client):
    """Acceptance Test 45 via API: Quick add trait immediately associates trait with NPC."""
    res = client.post("/emulator/npc/new", json={"name": "Mira", "current": True})
    npc_id = res.get_json()["npc"]["id"]

    add_trait_res = client.post(f"/emulator/npc/{npc_id}/traits/add", json={
        "status": "temporary",
        "trait": "Injured leg",
        "category": "CN"
    })
    assert add_trait_res.status_code == 200
    data = add_trait_res.get_json()
    assert data["success"] is True
    assert data["trait"]["trait"] == "Injured leg"
    assert data["trait"]["status"] == "Temporary"
    assert data["trait"]["category"] == "CN"
    assert len(data["npc"]["traits"]) == 1


def test_edit_npc_api(client):
    """Edit NPC updates name, details, statuses, and traits."""
    res = client.post("/emulator/npc/new", json={"name": "Marcus", "details": "Old guard"})
    npc_id = res.get_json()["npc"]["id"]

    edit_res = client.post(f"/emulator/npc/{npc_id}/edit", json={
        "name": "Marcus the Wise",
        "details": "Veteran scholar and guard",
        "current": True,
        "party_member": True,
        "traits": [
            {"status": "prevalent", "trait": "Ancient knowledge", "category": "SK"}
        ]
    })
    assert edit_res.status_code == 200
    updated = edit_res.get_json()["npc"]
    assert updated["name"] == "Marcus the Wise"
    assert updated["details"] == "Veteran scholar and guard"
    assert updated["party_member"] is True
    assert updated["current"] is True
    assert len(updated["traits"]) == 1
    assert updated["traits"][0]["trait"] == "Ancient knowledge"


def test_delete_npc_api(client):
    """Deleting NPC removes it and cascades deletion of traits."""
    res = client.post("/emulator/npc/new", json={
        "name": "Doomed NPC",
        "traits": [{"status": "default", "trait": "Cursed", "category": "CN"}]
    })
    npc_id = res.get_json()["npc"]["id"]

    del_res = client.post(f"/emulator/npc/{npc_id}/delete", json={})
    assert del_res.status_code == 200
    assert del_res.get_json()["success"] is True

    # Verify not found in API
    list_res = client.get("/emulator/api/npcs")
    all_npcs = list_res.get_json()["npcs"]
    assert all(n["id"] != npc_id for n in all_npcs)


def test_make_current_and_remove_current_api(client):
    """Make Current and Remove Current endpoints work as expected."""
    res = client.post("/emulator/npc/new", json={"name": "Tavern Keeper", "current": False, "party_member": False})
    npc_id = res.get_json()["npc"]["id"]

    # Make Current
    mc_res = client.post(f"/emulator/npc/{npc_id}/make-current")
    assert mc_res.status_code == 200
    assert mc_res.get_json()["npc"]["current"] is True

    # Remove Current
    rc_res = client.post(f"/emulator/npc/{npc_id}/remove-current")
    assert rc_res.status_code == 200
    assert rc_res.get_json()["npc"]["current"] is False


def test_spark_roll_api(client):
    """Acceptance Test 46 via API: Roll spark returns structured single and combo sparks."""
    res = client.post("/emulator/npc/new", json={"name": "Kael"})
    npc_id = res.get_json()["npc"]["id"]

    # Single spark: Disposition
    s1 = client.post(f"/emulator/npc/{npc_id}/roll-spark", json={"spark_type": "disposition"})
    assert s1.status_code == 200
    d1 = s1.get_json()
    assert d1["success"] is True
    assert d1["spark"]["type"] == "single"
    assert len(d1["spark"]["rolls"]) == 1

    # Combo spark: Action + Method
    s2 = client.post(f"/emulator/npc/{npc_id}/roll-spark", json={"spark_type": "action_method"})
    assert s2.status_code == 200
    d2 = s2.get_json()
    assert d2["success"] is True
    assert d2["spark"]["type"] == "combination"
    assert len(d2["spark"]["rolls"]) == 2

