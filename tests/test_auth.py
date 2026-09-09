"""Comprehensive tests for authentication, user management, and admin panel."""

import os
import tempfile
from unittest.mock import patch
import pytest
from app import app
from database import Database


@pytest.fixture
def auth_client():
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    app.config["TESTING"] = True
    app.config["LOGIN_DISABLED"] = False
    app.config["DATABASE_PATH"] = temp_db_path
    test_db = Database(temp_db_path)

    with patch("app.db", test_db):
        with app.test_client() as client:
            yield client, test_db

    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


def test_first_run_redirects_to_setup(auth_client):
    client, db = auth_client
    res = client.get("/")
    assert res.status_code == 302
    assert "/setup" in res.headers["Location"]


def test_initial_setup_creates_admin(auth_client):
    client, db = auth_client
    # Passwords do not match
    res = client.post("/setup", data={
        "username": "admin",
        "password": "password123",
        "confirm_password": "different",
    }, follow_redirects=True)
    assert b"Passwords do not match" in res.data
    assert db.count_users() == 0

    # Successful setup
    res = client.post("/setup", data={
        "username": "admin",
        "password": "password123",
        "confirm_password": "password123",
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"SOLO TTRPG TOOLS" in res.data
    assert db.count_users() == 1

    user = db.get_user_by_username("admin")
    assert user is not None
    assert user["is_admin"] == 1

    # Now that user exists, /setup redirects to login
    client.get("/logout")
    res_setup = client.get("/setup")
    assert res_setup.status_code == 302
    assert "/login" in res_setup.headers["Location"]


def test_login_flow_and_auth_check(auth_client):
    client, db = auth_client
    # Create initial admin
    client.post("/setup", data={
        "username": "admin",
        "password": "password123",
        "confirm_password": "password123",
    })

    # Log out
    client.get("/logout")

    # Accessing protected page redirects to login
    res = client.get("/hexroll")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

    # Auth check endpoint returns 401 when logged out
    res_check = client.get("/auth/check")
    assert res_check.status_code == 401

    # Failed login
    res_fail = client.post("/login", data={
        "username": "admin",
        "password": "wrongpassword",
    })
    assert res_fail.status_code == 200
    assert b"Invalid username or password" in res_fail.data

    # Successful login
    res_login = client.post("/login", data={
        "username": "admin",
        "password": "password123",
    }, follow_redirects=True)
    assert res_login.status_code == 200
    assert b"SOLO TTRPG TOOLS" in res_login.data
    assert b"admin" in res_login.data

    # Auth check endpoint returns 200 when logged in
    res_check_ok = client.get("/auth/check")
    assert res_check_ok.status_code == 200

    # Protected hexroll page now accessible
    res_hexroll = client.get("/hexroll")
    assert res_hexroll.status_code == 200


def test_admin_panel_permissions_and_user_crud(auth_client):
    client, db = auth_client
    # 1. Setup admin account
    client.post("/setup", data={
        "username": "master",
        "password": "password123",
        "confirm_password": "password123",
    })

    # 2. Access admin panel
    res_admin = client.get("/admin")
    assert res_admin.status_code == 200
    assert b"ADMINISTRATION PANEL" in res_admin.data
    assert b"master" in res_admin.data

    # 3. Create a standard user
    res_create = client.post("/admin/user/new", data={
        "username": "player1",
        "password": "playerpass",
    }, follow_redirects=True)
    assert b"User &#39;player1&#39; created successfully." in res_create.data or b"User 'player1' created" in res_create.data
    assert db.count_users() == 2
    p1 = db.get_user_by_username("player1")
    assert p1["is_admin"] == 0

    # 4. Standard user cannot access admin panel
    client.get("/logout")
    client.post("/login", data={"username": "player1", "password": "playerpass"})
    res_forbidden = client.get("/admin", follow_redirects=True)
    assert b"Administrator privileges required." in res_forbidden.data

    # 5. Log back in as admin
    client.get("/logout")
    client.post("/login", data={"username": "master", "password": "password123"})

    # 6. Admin updates standard user password
    client.post(f"/admin/user/{p1['id']}/password", data={"password": "newpass123"}, follow_redirects=True)
    client.get("/logout")
    # Old password fails
    res_bad = client.post("/login", data={"username": "player1", "password": "playerpass"})
    assert b"Invalid username or password" in res_bad.data
    # New password succeeds
    res_good = client.post("/login", data={"username": "player1", "password": "newpass123"}, follow_redirects=True)
    assert res_good.status_code == 200

    # 7. Admin deletion and safeguards
    client.get("/logout")
    client.post("/login", data={"username": "master", "password": "password123"})
    master_user = db.get_user_by_username("master")

    # Cannot delete self
    res_del_self = client.post(f"/admin/user/{master_user['id']}/delete", follow_redirects=True)
    assert b"You cannot delete your own active account" in res_del_self.data

    # Delete player1 succeeds
    res_del = client.post(f"/admin/user/{p1['id']}/delete", follow_redirects=True)
    assert b"deleted" in res_del.data
    assert db.count_users() == 1
