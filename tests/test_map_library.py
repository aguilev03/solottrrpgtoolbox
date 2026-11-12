"""Persistent native formats, conflict handling, isolation and failure atomicity."""
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from app import app
from database import Database


@pytest.fixture
def maps(tmp_path):
    database = Database(str(tmp_path / 'maps.db'))
    config = dict(app.config)
    app.config.update(TESTING=True, LOGIN_DISABLED=True)
    with patch('app.db', database), app.test_client() as client:
        assert client.get('/maps/').status_code == 200
        with client.session_transaction() as session:
            token = session['maps_csrf']
        yield client, database, token
    app.config.clear()
    app.config.update(config)


def post(maps, path, data):
    return maps[0].post('/maps/api/' + path, json=data, headers={'X-CSRF-Token': maps[2]})


def create(maps, editor='gridmapper', project=None):
    campaign = post(maps, 'campaigns', {'name': 'Campaign'}).json['id']
    response = post(maps, 'maps', {'campaign_id': campaign, 'name': 'Dungeon', 'editor': editor, 'project': project})
    assert response.status_code == 200, response.json
    return response.json['id']


def test_native_roundtrip_levels_rename_duplicate_delete_restart(maps):
    client, database, token = maps
    native = '(1,1)ffz(2,2)fff(2,2,1)\n'
    item = create(maps, project=native)
    record = client.get(f'/maps/api/maps/{item}').json
    assert record['project'] == native and record['editor'] == 'gridmapper'
    assert post(maps, f'maps/{item}/rename', {'name':'Renamed', 'revision':1}).json['revision'] == 2
    assert post(maps, f'maps/{item}/save', {'project':'stale', 'revision':1}).status_code == 409
    assert client.get(f'/maps/api/maps/{item}/export').data.decode() == native
    duplicate = post(maps, f'maps/{item}/duplicate', {'name':'Copy', 'revision':2}).json['id']
    assert client.get(f'/maps/api/maps/{duplicate}').json['project'] == native
    assert post(maps, f'maps/{item}/delete', {'revision':2}).status_code == 400
    assert post(maps, f'maps/{item}/delete', {'revision':2, 'confirm':True}).status_code == 200
    # A newly initialized database/app connection preserves maps and native bytes.
    reopened = Database(database.db_path)
    with patch('app.db', reopened):
        assert client.get(f'/maps/api/maps/{duplicate}').json['project'] == native
        assert client.get(f'/maps/api/maps/{item}').status_code == 404
    assert create(maps) > duplicate  # Deleted editor-local caches cannot attach to a reused ID.


def test_json_bytes_assets_unknown_fields_and_levels_preserved(maps):
    native = json.dumps({'schemaVersion':1, 'project': {'name':'🗝', 'levels':[
        {'meta':{'width':8,'height':8}, 'tiles':[], 'customAsset':'data:image/png;base64,example'},
        {'meta':{'width':8,'height':8}, 'tiles':[]}], 'unknownFutureField':{'x':1}}}, indent=3)
    item = create(maps, 'dungeon-mapper', native)
    response = maps[0].get(f'/maps/api/maps/{item}/export')
    assert response.data == native.encode()
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert 'attachment' in response.headers['Content-Disposition']


def test_invalid_imports_quota_and_size_fail_without_losing_snapshot(maps):
    item = create(maps, 'dungeon-mapper')
    for project in ['{bad', '[]', '{"schemaVersion":99}', '{}', '{"levels":[null]}']:
        assert post(maps, f'maps/{item}/save', {'revision':0, 'project':project}).status_code == 400
    assert maps[0].get(f'/maps/api/maps/{item}').json['revision'] == 0
    grid = create(maps, project='ffff')
    app.config['MAP_MAX_PROJECT_BYTES'] = 5
    assert post(maps, f'maps/{grid}/save', {'revision':1, 'project':'fffffff'}).status_code == 413
    app.config['MAP_LIBRARY_MAX_BYTES'] = 5
    assert post(maps, f'maps/{grid}/save', {'revision':1, 'project':'ffff'}).status_code == 413
    assert maps[0].get(f'/maps/api/maps/{grid}').json['revision'] == 1
    assert maps[0].get(f'/maps/api/maps/{grid}').json['project'] == 'ffff'


def test_revisions_export_and_bounded_retention(maps):
    item = create(maps, project='f')
    app.config['MAP_RETAIN_REVISIONS'] = 2
    for revision in range(1, 4):
        assert post(maps, f'maps/{item}/save', {'revision':revision,'project':'f'*(revision+1)}).status_code == 200
    assert maps[0].get(f'/maps/api/maps/{item}').json['revisions'] == [4,3]
    assert maps[0].get(f'/maps/api/maps/{item}/export?revision=3').data == b'fff'
    assert maps[0].get(f'/maps/api/maps/{item}/export?revision=1').status_code == 404


def test_concurrent_writers_one_succeeds(maps):
    item = create(maps, project='f')
    def save(value):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session['maps_csrf'] = maps[2]
            return client.post(f'/maps/api/maps/{item}/save', json={'revision':1,'project':value}, headers={'X-CSRF-Token':maps[2]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, ['ff','fff'])) == [200,409]
    assert maps[0].get(f'/maps/api/maps/{item}').json['revision'] == 2


def test_auth_csrf_routes_and_no_changes_to_existing_data(maps):
    client, database, token = maps
    with database.get_connection() as conn:
        before = {r[0]:conn.execute(f'SELECT COUNT(*) FROM "{r[0]}"').fetchone()[0]
                  for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'map_%' AND name != 'library_maps'")}
    assert client.post('/maps/api/campaigns', json={'name':'No token'}).status_code == 400
    assert post(maps, 'campaigns', []).status_code == 400
    assert post(maps, 'maps', {'name':'Bad', 'editor':'unknown'}).status_code == 400
    assert client.get('/gridmapper/').status_code == 200
    assert client.get('/dungeon-mapper/').status_code == 200
    assert client.get('/gridmapper/app/../../config.py').status_code == 404
    create(maps)
    Database(database.db_path)  # Additive migration is repeatable.
    with database.get_connection() as conn:
        for table, count in before.items():
            if table != 'sqlite_sequence':
                assert conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == count
    app.config['LOGIN_DISABLED'] = False
    for path in ['/maps/', '/gridmapper/', '/dungeon-mapper/', '/maps/api/library', '/gridmapper/app/gridmapper.svg', '/maps/upstream/gridmapper.tar.gz']:
        assert client.get(path).status_code == 302


def test_application_backup_restores_native_projects_and_assets(maps, tmp_path):
    import hashlib
    import sqlite3
    from scripts.backup_data import backup
    item = create(maps, project='(0,0)ffz(1,1)f(0,0,1)\n')
    cards = tmp_path / 'cards'
    cards.mkdir()
    (cards / 'original.webp').write_bytes(b'original uploaded bytes')
    target = tmp_path / 'snapshot'
    backup(target, maps[1].db_path, cards)
    manifest = json.loads((target / 'manifest.json').read_text())
    for path, expected in manifest.items():
        assert hashlib.sha256((target / path).read_bytes()).hexdigest() == expected
    assert (target / 'card_uploads/original.webp').read_bytes() == b'original uploaded bytes'
    with sqlite3.connect(target / 'solo_tools.db') as restored:
        assert restored.execute('SELECT project FROM map_revisions WHERE map_id=?',(item,)).fetchone()[0].startswith(b'(0,0)ffz')
    with pytest.raises(FileExistsError):
        backup(target, maps[1].db_path, cards)
    with pytest.raises(ValueError):
        backup(cards / 'recursive-backup', maps[1].db_path, cards)
