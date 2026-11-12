#!/usr/bin/env python3
"""Back up SQLite (including native projects/revisions) and private card assets.

Pause application writes first so the database and filesystem share one snapshot.
The destination must be outside the checkout and must not already exist.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import Config


def backup(destination, db_path, cards):
    destination = Path(destination).resolve()
    root = Path(__file__).resolve().parents[1]
    if destination == root or root in destination.parents:
        raise ValueError('Choose a backup directory outside the checkout.')
    card_root = Path(cards).resolve()
    if destination == card_root or card_root in destination.parents:
        raise ValueError('Choose a backup directory outside the source card assets.')
    database = Path(db_path).resolve()
    if not database.is_file():
        raise ValueError('Configured database does not exist; refusing an empty backup.')
    destination.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True) as src, sqlite3.connect(destination / 'solo_tools.db') as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup integrity check failed.')
    if Path(cards).is_dir():
        shutil.copytree(cards, destination / 'card_uploads')
    manifest = {str(path.relative_to(destination)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(destination.rglob('*')) if path.is_file()}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Backup verified: {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    args = parser.parse_args()
    backup(args.destination, Config.DATABASE_PATH, Config.CARD_UPLOAD_DIR)
