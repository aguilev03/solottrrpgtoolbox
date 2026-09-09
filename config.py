"""Configuration for Solo TTRPG Tools."""

import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "solo-ttrpg-tools-dev-secret-key-change-in-prod")
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

    # Debug mode flag for dungeon generation rolls
    DEBUG_DUNGEON_ROLLS = os.environ.get("DEBUG_DUNGEON_ROLLS", "false").lower() in ("true", "1", "yes")

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
    DATABASE_PATH = os.environ.get("SOLO_TOOLS_DB", os.path.join(INSTANCE_DIR, "solo_tools.db"))

    # Hexroll 3 Xpra / Web stream URL
    # Defaults to relative path '/xpra/' so that requests from any device (tablet, phone, PC)
    # are forwarded by the LXC reverse proxy internally to 127.0.0.1:14501 on the LXC container.
    HEXROLL_URL = os.environ.get(
        "HEXROLL_URL",
        "/xpra/",
    )
