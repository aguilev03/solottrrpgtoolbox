"""Tests for the Fantasy / Sci-Fi UI theme system."""

import os
import tempfile
from unittest.mock import patch

import pytest

from app import DEFAULT_THEME, THEMES, app
from database import Database


@pytest.fixture
def client():
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app.config["TESTING"] = True
    app.config["LOGIN_DISABLED"] = True
    app.config["DATABASE_PATH"] = temp_db_path
    with patch("app.db", Database(temp_db_path)):
        with app.test_client() as c:
            yield c
    os.remove(temp_db_path)


def test_themes_registry():
    assert set(THEMES) == {"fantasy", "scifi"}
    assert DEFAULT_THEME == "fantasy"


def test_default_theme_is_fantasy(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b'data-theme="fantasy"' in res.data
    # Switcher offers both themes, with fantasy marked active
    assert b'data-theme-choice="fantasy"' in res.data
    assert b'data-theme-choice="scifi"' in res.data


def test_scifi_cookie_renders_scifi(client):
    client.set_cookie("ui_theme", "scifi")
    for path in ("/", "/dungeon", "/emulator", "/hex"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert b'data-theme="scifi"' in res.data, path


def test_unknown_theme_cookie_falls_back(client):
    client.set_cookie("ui_theme", '"><script>alert(1)</script>')
    res = client.get("/")
    assert b'data-theme="fantasy"' in res.data
    assert b"<script>alert(1)" not in res.data


def test_stylesheet_defines_both_themes():
    css_path = os.path.join(os.path.dirname(__file__), "..", "static", "css", "style.css")
    with open(css_path, encoding="utf-8") as fh:
        css = fh.read()
    assert ':root[data-theme="fantasy"]' in css
    assert ':root[data-theme="scifi"]' in css
