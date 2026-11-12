"""Configuration for Solo TTRPG Tools."""

import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "solo-ttrpg-tools-dev-secret-key-change-in-prod")
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

    # Debug mode flag for dungeon generation rolls
    DEBUG_DUNGEON_ROLLS = os.environ.get("DEBUG_DUNGEON_ROLLS", "false").lower() in ("true", "1", "yes")

    # Production cookie security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1", "yes")

    # Flag to disable auth checks (useful in automated tests)
    LOGIN_DISABLED = os.environ.get("LOGIN_DISABLED", "false").lower() in ("true", "1", "yes")

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

    # Permanent custom library storage, separate from publicly served static assets.
    CARD_UPLOAD_DIR = os.environ.get("CARD_UPLOAD_DIR", os.path.join(INSTANCE_DIR, "card_uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 32 * 1024 * 1024))
    CARD_MAX_IMAGE_BYTES = int(os.environ.get("CARD_MAX_IMAGE_BYTES", 8 * 1024 * 1024))
    CARD_MAX_PIXELS = int(os.environ.get("CARD_MAX_PIXELS", 20_000_000))
    CARD_MAX_UPLOAD_FILES = int(os.environ.get("CARD_MAX_UPLOAD_FILES", 100))
    CARD_MAX_DECK_CARDS = int(os.environ.get("CARD_MAX_DECK_CARDS", 2000))
    SPARK_MAX_IMPORT_BYTES = int(os.environ.get("SPARK_MAX_IMPORT_BYTES", 1024 * 1024))
    SPARK_MAX_ENTRIES = int(os.environ.get("SPARK_MAX_ENTRIES", 10_000))
    EDITOR_BUILD_DIR = os.environ.get("EDITOR_BUILD_DIR", os.path.join(BASE_DIR, "build", "editors"))
    MAP_MAX_PROJECT_BYTES = int(os.environ.get("MAP_MAX_PROJECT_BYTES", 16 * 1024 * 1024))
    MAP_LIBRARY_MAX_BYTES = int(os.environ.get("MAP_LIBRARY_MAX_BYTES", 512 * 1024 * 1024))
    MAP_RETAIN_REVISIONS = int(os.environ.get("MAP_RETAIN_REVISIONS", 5))
