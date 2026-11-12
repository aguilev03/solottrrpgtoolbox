"""Private native map projects; additive schema and atomic revision checks."""
import io
import json
import secrets
from pathlib import Path

from flask import (Blueprint, abort, current_app, jsonify, render_template,
                   request, send_file, send_from_directory, session)
from werkzeug.exceptions import HTTPException

from custom_tools import connection, name

bp = Blueprint('maps', __name__)
EDITORS = {
    'gridmapper': {'label': 'Gridmapper', 'extension': 'txt',
                   'revision': '4719813ff0e8d868828a6a86518950f52d4bbc61'},
    'dungeon-mapper': {'label': 'Dungeon Mapper', 'extension': 'json',
                       'revision': '42d8dc09f0bf3dfa6f1d6ca4ab2abc47602107e5'},
}


def migrate(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS map_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS library_maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL REFERENCES map_campaigns(id),
            name TEXT NOT NULL, editor TEXT NOT NULL,
            upstream_revision TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS map_revisions (
            map_id INTEGER NOT NULL REFERENCES library_maps(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL, project BLOB NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(map_id, revision));
        CREATE INDEX IF NOT EXISTS library_maps_campaign ON library_maps(campaign_id);
    ''')


@bp.before_request
def protect():
    if request.method == 'POST':
        token = request.headers.get('X-CSRF-Token', '')
        if not token or not secrets.compare_digest(token, session.get('maps_csrf', '')):
            abort(400, description='Page token expired. Reload the library.')


@bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@bp.errorhandler(ValueError)
@bp.errorhandler(HTTPException)
def invalid(error):
    return jsonify(error=str(error) if isinstance(error, ValueError) else error.description), getattr(error, 'code', 400)


def body():
    value = request.get_json()
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object.')
    return value


def required(conn, table, item_id):
    if type(item_id) is not int or not 0 < item_id <= 2**63 - 1:
        abort(404, description='Campaign or map no longer exists.')
    row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (item_id,)).fetchone()
    if row is None:
        abort(404, description='Campaign or map no longer exists.')
    return row


def check_revision(row, data):
    if type(data.get('revision')) is not int:
        raise ValueError('A revision number is required.')
    if row['revision'] != data['revision']:
        abort(409, description='Another tab or device changed this map. Download your work or save a copy; reload to open the server version.')


def validate_project(editor, project):
    if not isinstance(project, str) or not project.strip():
        raise ValueError('Provide the native editable project, not an image.')
    encoded = project.encode('utf-8')
    if len(encoded) > current_app.config['MAP_MAX_PROJECT_BYTES']:
        abort(413, description='Project exceeds the configured size limit.')
    if editor == 'dungeon-mapper':
        try:
            obj = json.loads(project, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid JSON number.')))
        except (ValueError, RecursionError):
            raise ValueError('Invalid Dungeon Mapper JSON.')
        if not isinstance(obj, dict):
            raise ValueError('Expected a Dungeon Mapper project object.')
        if 'schemaVersion' in obj and obj['schemaVersion'] != 1:
            raise ValueError('Unsupported project schema. Keep the original backup.')
        native = obj.get('project', obj)
        if not isinstance(native, dict) or not (isinstance(native.get('levels'), list) and native['levels']):
            raise ValueError('Expected a native multi-level Dungeon Mapper project.')
        if len(native['levels']) > 100:
            raise ValueError('Too many levels.')
        for level in native['levels']:
            if not isinstance(level, dict) or not isinstance(level.get('meta'), dict) or not isinstance(level.get('tiles'), list):
                raise ValueError('Invalid map level.')
        # The upstream browser decoder performs full field/schema validation before opening.
    elif '\x00' in project:
        raise ValueError('Gridmapper projects must be UTF-8 command text.')
    return encoded


def save_revision(conn, row, encoded):
    revision = row['revision'] + 1
    conn.execute('INSERT INTO map_revisions(map_id,revision,project) VALUES(?,?,?)',
                 (row['id'], revision, encoded))
    keep = max(1, current_app.config['MAP_RETAIN_REVISIONS'])
    conn.execute('DELETE FROM map_revisions WHERE map_id=? AND revision<=?', (row['id'], revision - keep))
    total = conn.execute('SELECT COALESCE(SUM(length(project)),0) FROM map_revisions').fetchone()[0]
    if total > current_app.config['MAP_LIBRARY_MAX_BYTES']:
        abort(413, description='Map library storage quota exceeded. Export and remove unused maps.')
    conn.execute('UPDATE library_maps SET revision=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (revision, row['id']))
    return revision


@bp.get('/maps/')
def library():
    session.setdefault('maps_csrf', secrets.token_hex(32))
    return render_template('map_library.html', maps_csrf=session['maps_csrf'], editors=EDITORS)


@bp.get('/gridmapper/')
@bp.get('/dungeon-mapper/')
def editor():
    session.setdefault('maps_csrf', secrets.token_hex(32))
    kind = request.path.strip('/')
    return render_template('map_editor.html', editor=kind, editors=EDITORS,
                           maps_csrf=session['maps_csrf'])


@bp.get('/gridmapper/app/<path:filename>')
@bp.get('/dungeon-mapper/app/<path:filename>')
def assets(filename):
    kind = request.path.split('/')[1]
    response = send_from_directory(Path(current_app.config['EDITOR_BUILD_DIR']) / kind, filename)
    # Editors contain active scripts; prevent third-party framing without breaking the wrapper.
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
    return response


@bp.get('/dungeon-mapper/app/')
def app_index():
    return assets('index.html')


@bp.get('/maps/upstream/<editor>.tar.gz')
def upstream(editor):
    if editor not in EDITORS:
        abort(404)
    return send_from_directory(Path(current_app.root_path) / 'vendor', editor + '-source.tar.gz', as_attachment=True)


@bp.get('/maps/api/library')
def listing():
    with connection() as conn:
        return jsonify(campaigns=[dict(r) for r in conn.execute('SELECT * FROM map_campaigns ORDER BY id')],
                       maps=[dict(r) for r in conn.execute('SELECT * FROM library_maps ORDER BY id')])


@bp.post('/maps/api/campaigns')
def create_campaign():
    data = body()
    with connection() as conn:
        item = conn.execute('INSERT INTO map_campaigns(name) VALUES(?)', (name(data.get('name')),)).lastrowid
    return jsonify(id=item)


@bp.post('/maps/api/campaigns/<int:item_id>/rename')
def rename_campaign(item_id):
    data = body()
    with connection() as conn:
        required(conn, 'map_campaigns', item_id)
        conn.execute('UPDATE map_campaigns SET name=? WHERE id=?', (name(data.get('name')), item_id))
    return jsonify(ok=True)


@bp.post('/maps/api/maps')
def create_map():
    data = body()
    kind = data.get('editor')
    if not isinstance(kind, str) or kind not in EDITORS:
        raise ValueError('Choose an editor.')
    if type(data.get('campaign_id')) is not int:
        raise ValueError('Choose a campaign.')
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        required(conn, 'map_campaigns', data.get('campaign_id'))
        item = conn.execute('INSERT INTO library_maps(campaign_id,name,editor,upstream_revision) VALUES(?,?,?,?)',
                            (data['campaign_id'], name(data.get('name')), kind, EDITORS[kind]['revision'])).lastrowid
        revision = 0
        if data.get('project') is not None:
            encoded = validate_project(kind, data['project'])
            revision = save_revision(conn, required(conn, 'library_maps', item), encoded)
    return jsonify(id=item, revision=revision)


@bp.get('/maps/api/maps/<int:item_id>')
def get_map(item_id):
    with connection() as conn:
        row = dict(required(conn, 'library_maps', item_id))
        project = conn.execute('SELECT project FROM map_revisions WHERE map_id=? AND revision=?', (item_id, row['revision'])).fetchone()
        row['project'] = bytes(project[0]).decode('utf-8') if project else None
        row['revisions'] = [r[0] for r in conn.execute('SELECT revision FROM map_revisions WHERE map_id=? ORDER BY revision DESC', (item_id,))]
    return jsonify(row)


@bp.post('/maps/api/maps/<int:item_id>/<action>')
def mutate_map(item_id, action):
    data = body()
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = required(conn, 'library_maps', item_id)
        check_revision(row, data)
        if action == 'save':
            revision = save_revision(conn, row, validate_project(row['editor'], data.get('project')))
            return jsonify(revision=revision)
        if action == 'rename':
            conn.execute('UPDATE library_maps SET name=? WHERE id=?', (name(data.get('name')), item_id))
            # Metadata edits also advance concurrency tokens; copy the current native snapshot.
            if row['revision']:
                native = conn.execute('SELECT project FROM map_revisions WHERE map_id=? AND revision=?', (item_id, row['revision'])).fetchone()[0]
                revision = save_revision(conn, row, native)
            else:
                revision = 0
            return jsonify(revision=revision)
        if action == 'duplicate':
            new_id = conn.execute('INSERT INTO library_maps(campaign_id,name,editor,upstream_revision) VALUES(?,?,?,?)',
                                  (row['campaign_id'], name(data.get('name')), row['editor'], row['upstream_revision'])).lastrowid
            if row['revision']:
                native = conn.execute('SELECT project FROM map_revisions WHERE map_id=? AND revision=?', (item_id, row['revision'])).fetchone()[0]
                save_revision(conn, required(conn, 'library_maps', new_id), native)
            return jsonify(id=new_id)
        if action == 'delete':
            if data.get('confirm') is not True:
                raise ValueError('Confirm deletion first.')
            conn.execute('DELETE FROM library_maps WHERE id=?', (item_id,))
            return jsonify(ok=True)
        abort(404)


@bp.get('/maps/api/maps/<int:item_id>/export')
def export_project(item_id):
    with connection() as conn:
        row = required(conn, 'library_maps', item_id)
        revision = request.args.get('revision', row['revision'], type=int)
        native = conn.execute('SELECT project FROM map_revisions WHERE map_id=? AND revision=?', (item_id, revision)).fetchone()
        if native is None:
            abort(404, description='No project saved at this revision.')
        data = bytes(native[0])
    return send_file(io.BytesIO(data), as_attachment=True,
                     download_name=f'map-{item_id}-r{revision}.{EDITORS[row["editor"]]["extension"]}',
                     mimetype='text/plain' if row['editor'] == 'gridmapper' else 'application/json')
