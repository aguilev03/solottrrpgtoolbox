"""Tests for Wilderness & Hex Generator, Perilous Tables, and Expanded Dungeon Perils."""

import json
import os
import tempfile
from unittest.mock import patch
import pytest

from app import app
from database import Database, get_db
from dungeon_engine import DungeonEngine, DungeonState, RoomState
from hex_engine import HexEngine, HexRegion, HexCell, BIOME_LIST
from table_loader import TableManager, get_table_manager


@pytest.fixture
def table_mgr():
    return get_table_manager(app.config["DATA_DIR"])


@pytest.fixture
def hex_eng(table_mgr):
    return HexEngine(table_mgr)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def client(temp_db):
    app.config["TESTING"] = True
    app.config["LOGIN_DISABLED"] = True
    app.config["DATABASE_PATH"] = temp_db.db_path

    with patch("app.db", temp_db):
        with app.test_client() as c:
            yield c, temp_db


# ====================================================================
# 1. Hex Engine Unit Tests
# ====================================================================

def test_hex_tables_loaded(table_mgr):
    """Verify all new JSON tables from Perilous Tables and Sandbox Generator are loaded."""
    assert "area_dressing" in table_mgr.tables
    assert "dungeon_themes" in table_mgr.tables
    assert "expanded_traps" in table_mgr.tables
    assert "hex_biomes" in table_mgr.tables
    assert "hex_landmarks" in table_mgr.tables
    assert "hex_settlements" in table_mgr.tables
    assert "hex_hazards" in table_mgr.tables
    assert "hex_sparks" in table_mgr.tables
    assert "hex_weather" in table_mgr.tables
    assert "hex_npcs" in table_mgr.tables

    # Verify expanded traps has 50 entries
    assert len(table_mgr.tables["expanded_traps"]["entries"]) == 50


def test_single_hex_generation(hex_eng):
    """Verify single hex generation with each biome and feature."""
    for biome in BIOME_LIST:
        cell = hex_eng.generate_single_hex(biome=biome, feature_type="Wilds")
        assert cell.biome == biome
        assert cell.feature_type == "Wilds"
        assert "hazard" in cell.details
        assert "spark" in cell.details
        assert "encounter" in cell.details
        assert cell.biome_color.startswith("#")
        assert len(cell.biome_icon) > 0

    # Specific feature types
    settlement_cell = hex_eng.generate_single_hex(biome="Grassland", feature_type="Settlement")
    assert settlement_cell.feature_type == "Settlement"
    assert "settlement" in settlement_cell.details

    dungeon_cell = hex_eng.generate_single_hex(biome="Mountains", feature_type="Dungeon")
    assert dungeon_cell.feature_type == "Dungeon"
    assert "dungeon" in dungeon_cell.details
    assert "dungeon_type" in dungeon_cell.details["dungeon"]


def test_19_hex_cluster_generation(hex_eng):
    """Verify 19-hex flower cluster follows Sandbox Generator structure."""
    region = hex_eng.generate_region(name="Valenwood Basin", layout_type="cluster_19", starting_biome="Forest")
    assert region.name == "Valenwood Basin"
    assert region.layout_type == "cluster_19"
    assert region.center_biome == "Forest"
    assert len(region.cells) == 19

    # Hex 1 is center settlement
    center = region.cells[0]
    assert center.hex_index == 1
    assert center.q == 0 and center.r == 0
    assert center.feature_type == "Settlement"

    # Hex 2 is dungeon delve
    hex2 = region.cells[1]
    assert hex2.hex_index == 2
    assert hex2.feature_type == "Dungeon"

    # Verify weather attached
    assert region.weather is not None
    assert "temperature" in region.weather
    assert "travel_impact" in region.weather


def test_7_hex_mini_cluster(hex_eng):
    """Verify 7-hex mini region."""
    region = hex_eng.generate_region(name="Tiny Valley", layout_type="cluster_7", starting_biome="Hills")
    assert len(region.cells) == 7


def test_hex_svg_math(hex_eng):
    """Verify axial hex SVG point calculation."""
    cell = HexCell(hex_index=1, q=0, r=0, biome="Grassland")
    cx, cy = cell.svg_center(x0=270, y0=240, r_radius=52)
    assert cx == 270.0
    assert cy == 240.0
    pts = cell.svg_points(x0=270, y0=240, r_radius=52)
    assert len(pts.split(" ")) == 6


def test_weather_and_npc_oracles(hex_eng):
    """Verify weather and NPC generation."""
    weather = hex_eng.roll_weather()
    assert "temperature" in weather
    assert "condition" in weather
    assert "travel_impact" in weather

    npc = hex_eng.roll_npc()
    assert "name" in npc
    assert "occupation" in npc
    assert "clothing" in npc
    assert "dream" in npc


# ====================================================================
# 2. Database Persistence Tests
# ====================================================================

def test_database_hex_crud(temp_db, hex_eng):
    """Verify full CRUD lifecycle of hex region in SQLite database."""
    region = hex_eng.generate_region(name="The Sunken Mire", layout_type="cluster_19", starting_biome="Marsh")
    region_id = temp_db.save_hex_region(region)
    assert region_id > 0

    # Fetch
    fetched = temp_db.get_hex_region(region_id)
    assert fetched is not None
    assert fetched.name == "The Sunken Mire"
    assert fetched.center_biome == "Marsh"
    assert len(fetched.cells) == 19
    assert fetched.cells[0].hex_index == 1
    assert fetched.cells[0].feature_type == "Settlement"

    # List
    regions_list = temp_db.list_hex_regions()
    assert len(regions_list) == 1
    assert regions_list[0]["id"] == region_id
    assert regions_list[0]["hex_count"] == 19

    # Delete
    deleted = temp_db.delete_hex_region(region_id)
    assert deleted is True
    assert temp_db.get_hex_region(region_id) is None
    assert len(temp_db.list_hex_regions()) == 0


# ====================================================================
# 3. Flask Route Integration Tests
# ====================================================================

def test_hex_menu_route(client):
    c, db = client
    res = c.get("/hex")
    assert res.status_code == 200
    assert b"WILDERNESS &amp; HEX GENERATOR" in res.data
    assert b"Generate Hex Region" in res.data

    # Alternative /wilderness alias
    res_alias = c.get("/wilderness")
    assert res_alias.status_code == 200
    assert b"WILDERNESS &amp; HEX GENERATOR" in res_alias.data


def test_hex_region_create_and_view(client):
    c, db = client
    # POST to create
    post_res = c.post(
        "/hex/region/new",
        data={
            "name": "High Crag Peaks",
            "layout_type": "cluster_7",
            "starting_biome": "Mountains",
        },
        follow_redirects=True,
    )
    assert post_res.status_code == 200
    assert b"HIGH CRAG PEAKS" in post_res.data
    assert b"REGIONAL HEX MAP" in post_res.data

    # Verify listed in menu
    menu_res = c.get("/hex")
    assert b"High Crag Peaks" in menu_res.data


def test_hex_quick_route(client):
    c, db = client
    # GET default single hex
    res = c.get("/hex/quick")
    assert res.status_code == 200
    assert b"QUICK HEX EXPLORE" in res.data
    assert b"STANDALONE HEX" in res.data

    # POST with specific parameters
    post_res = c.post(
        "/hex/quick",
        data={"biome": "Forest", "feature_type": "Dungeon"},
    )
    assert post_res.status_code == 200
    assert b"Forest" in post_res.data
    assert b"Delve into this Dungeon" in post_res.data


def test_hex_oracle_route(client):
    c, db = client
    # GET default weather
    res = c.get("/hex/oracle")
    assert res.status_code == 200
    assert b"TRAVEL &amp; ORACLE REFEREE" in res.data
    assert b"Temperature:" in res.data

    # POST weather action
    w_res = c.post("/hex/oracle", data={"action": "weather"})
    assert w_res.status_code == 200
    assert b"Temperature:" in w_res.data

    # POST encounter action
    enc_res = c.post("/hex/oracle", data={"action": "encounter", "biome": "Marsh"})
    assert enc_res.status_code == 200
    assert b"Threat:" in enc_res.data

    # POST wandering NPC action
    npc_res = c.post("/hex/oracle", data={"action": "npc"})
    assert npc_res.status_code == 200
    assert b"Clothing:" in npc_res.data
    assert b"First Impression:" in npc_res.data


# ====================================================================
# 4. Dungeon Delve & Expanded Perils Tests
# ====================================================================

def test_dungeon_theme_and_dressing(table_mgr):
    d_eng = DungeonEngine(table_mgr)
    theme = d_eng.roll_theme()
    assert ":" in theme
    category = theme.split(":")[0].strip()
    assert category in ["Hopeful", "Mysterious", "Grim", "Gonzo"]

    dressing = d_eng.roll_dressing()
    assert isinstance(dressing, str)
    assert len(dressing) > 10


def test_dungeon_expanded_traps(table_mgr):
    d_eng = DungeonEngine(table_mgr)
    # Test roll_trap in standard mode
    std_trap = d_eng.roll_trap(danger_mode="standard")
    assert "name" in std_trap

    # Test roll_trap in expanded mode
    exp_trap = d_eng.roll_trap(danger_mode="expanded")
    assert "name" in exp_trap
    assert "danger_type" in exp_trap
    assert "trigger" in exp_trap
    assert "countermeasure" in exp_trap


def test_dungeon_creation_with_theme_and_prefill(client):
    c, db = client
    # Test pre-fill via query args from hex view
    res = c.get("/dungeon/new?type=Cave&name=Cavern%20of%20Whispers")
    assert res.status_code == 200
    assert b'value="Cavern of Whispers"' in res.data
    assert b'<option value="Cave" selected>' in res.data

    # Create dungeon with expanded danger mode and theme
    post_res = c.post(
        "/dungeon/new",
        data={
            "dungeon_type": "Cave",
            "name": "Cavern of Whispers",
            "size": "Small",
            "danger_mode": "expanded",
            "theme": "Grim",
        },
        follow_redirects=True,
    )
    assert post_res.status_code == 200
    assert b"Cavern of Whispers" in post_res.data
