"""Independent custom libraries. All mutable draw state lives in SQLite."""
import io
import json
import math
import secrets
import uuid
import warnings
from contextlib import contextmanager
from pathlib import Path

from flask import (Blueprint, abort, current_app, jsonify, redirect,
                   render_template, request, send_from_directory, session, url_for)
from PIL import Image, UnidentifiedImageError
from fate_oracle import ODDS, DEFAULT_ODDS, resolve as resolve_fate
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge, Conflict, NotFound, Unauthorized

bp = Blueprint('custom', __name__)
rng = secrets.SystemRandom()


def migrate(conn):
    """Additive, idempotent schema migration; never touches built-in tables."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS custom_decks (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            reversal_probability REAL NOT NULL DEFAULT 50 CHECK(reversal_probability BETWEEN 0 AND 100),
            back_file TEXT
        );
        CREATE TABLE IF NOT EXISTS custom_cards (
            id INTEGER PRIMARY KEY, deck_id INTEGER NOT NULL REFERENCES custom_decks(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT '', image_file TEXT NOT NULL,
            draw_rank INTEGER NOT NULL, drawn_order INTEGER,
            reversed INTEGER NOT NULL DEFAULT 0 CHECK(reversed IN (0,1)),
            x REAL NOT NULL DEFAULT 0, y REAL NOT NULL DEFAULT 0,
            UNIQUE(deck_id, draw_rank), UNIQUE(deck_id, drawn_order)
        );
        CREATE TABLE IF NOT EXISTS custom_spark_tables (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, entries_json TEXT NOT NULL,
            pool_json TEXT NOT NULL, replacement INTEGER NOT NULL DEFAULT 1, last_count INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS custom_spark_results (
            id INTEGER PRIMARY KEY, table_id INTEGER NOT NULL REFERENCES custom_spark_tables(id) ON DELETE CASCADE,
            result TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS custom_spark_favorites (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            table_id INTEGER NOT NULL REFERENCES custom_spark_tables(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, table_id)
        );
        CREATE TABLE IF NOT EXISTS custom_spark_log (
            id INTEGER PRIMARY KEY, table_name TEXT NOT NULL, result TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS custom_cards_deck ON custom_cards(deck_id);
        CREATE INDEX IF NOT EXISTS custom_results_table ON custom_spark_results(table_id, id);
        CREATE TABLE IF NOT EXISTS custom_dealer_tables (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            width INTEGER NOT NULL DEFAULT 2400, height INTEGER NOT NULL DEFAULT 1600
        );
        CREATE TABLE IF NOT EXISTS custom_table_saves (
            id INTEGER PRIMARY KEY,
            table_id INTEGER NOT NULL REFERENCES custom_dealer_tables(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            width INTEGER NOT NULL, height INTEGER NOT NULL,
            zoom REAL NOT NULL DEFAULT 1, view_x REAL NOT NULL DEFAULT 0, view_y REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    ''')
    # Dealer's-table placement and free rotation live on the card row, so a card is
    # always in exactly one place: its deck's pool, its deck's tabletop, or one table.
    columns = {row[1] for row in conn.execute('PRAGMA table_info(custom_cards)')}
    for column, ddl in (
        ('rotation', 'INTEGER NOT NULL DEFAULT 0 CHECK(rotation IN (0,90,180,270))'),
        ('table_id', 'INTEGER REFERENCES custom_dealer_tables(id) ON DELETE SET NULL'),
        ('table_x', 'REAL NOT NULL DEFAULT 0'),
        ('table_y', 'REAL NOT NULL DEFAULT 0'),
        ('table_z', 'INTEGER NOT NULL DEFAULT 0'),
        ('face_down', 'INTEGER NOT NULL DEFAULT 0 CHECK(face_down IN (0,1))'),
        # A suspended table layout ("save instance") holds its cards here, out of every deck's pool.
        ('save_id', 'INTEGER REFERENCES custom_table_saves(id) ON DELETE SET NULL'),
    ):
        if column not in columns:
            conn.execute(f'ALTER TABLE custom_cards ADD COLUMN {column} {ddl}')
    conn.execute('CREATE INDEX IF NOT EXISTS custom_cards_table ON custom_cards(table_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS custom_cards_save ON custom_cards(save_id)')


@contextmanager
def connection():
    # Resolve the app's existing database dynamically, including its test overrides.
    from app import db
    conn = db.get_connection()
    conn.execute("PRAGMA busy_timeout=15000")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def required(conn, table, item_id):
    row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (item_id,)).fetchone()
    if row is None:
        abort(404)
    return row


def payload():
    data = request.get_json() if request.is_json else request.form
    if not hasattr(data, 'get'):
        raise ValueError('Expected an object of named fields.')
    return data


def name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200:
        raise ValueError('Enter a name between 1 and 200 characters.')
    return value.strip()


def number(value, lower, upper):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'Enter a number from {lower} to {upper}.')
    if not math.isfinite(result) or not lower <= result <= upper:
        raise ValueError(f'Enter a number from {lower} to {upper}.')
    return result


def done(endpoint, result=None, **values):
    if request.is_json or request.headers.get('Accept') == 'application/json':
        return jsonify(result or {'ok': True})
    return redirect(url_for(endpoint, **values))


@bp.before_request
def protect_mutation():
    if request.method == 'POST':
        token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
        if not token or not secrets.compare_digest(token, session.get('custom_csrf', '')):
            abort(400, description='Page token expired. Reload this page and try again.')


@bp.context_processor
def csrf():
    session.setdefault('custom_csrf', secrets.token_hex(32))
    return {'custom_csrf': session['custom_csrf']}


@bp.errorhandler(ValueError)
@bp.errorhandler(BadRequest)
@bp.errorhandler(Conflict)
@bp.errorhandler(NotFound)
@bp.errorhandler(Unauthorized)
def invalid(error):
    message = str(error) if isinstance(error, ValueError) else error.description
    status = getattr(error, 'code', 400)
    if request.is_json or request.headers.get('Accept') == 'application/json':
        return jsonify(error=message), status
    return render_template('custom_error.html', message=message), status


@bp.errorhandler(RequestEntityTooLarge)
def too_large(error):
    return render_template('custom_error.html', message='Upload exceeds the request size limit.'), 413


def storage():
    path = Path(current_app.config['CARD_UPLOAD_DIR']).resolve()
    static = Path(current_app.static_folder).resolve()
    if path == static or static in path.parents:
        raise RuntimeError('CARD_UPLOAD_DIR must be outside static.')
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_image(upload):
    suffix = Path(upload.filename or '').suffix.lower()
    formats = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP'}
    if suffix not in formats:
        raise ValueError('Card images must be PNG, JPG, JPEG, or WebP.')
    content = upload.stream.read(current_app.config['CARD_MAX_IMAGE_BYTES'] + 1)
    if len(content) > current_app.config['CARD_MAX_IMAGE_BYTES']:
        raise ValueError('Each image must be within the configured image size limit.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as img:
                if img.format != formats[suffix] or img.width * img.height > current_app.config['CARD_MAX_PIXELS']:
                    raise ValueError('Image format does not match its extension or dimensions are too large.')
                if getattr(img, 'n_frames', 1) != 1:
                    raise ValueError('Use a still image rather than an animation.')
                img.verify()
            with Image.open(io.BytesIO(content)) as img:
                img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Image is damaged or is not a supported image.')
    return uuid.uuid4().hex + suffix, content


@bp.get('/decks')
def decks():
    with connection() as conn:
        decks = conn.execute('SELECT d.*, count(c.id) AS total FROM custom_decks d LEFT JOIN custom_cards c ON c.deck_id=d.id GROUP BY d.id ORDER BY d.id DESC').fetchall()
    return render_template('decks.html', decks=decks)


@bp.post('/decks')
def create_deck():
    title = name(payload().get('name'))
    with connection() as conn:
        item_id = conn.execute('INSERT INTO custom_decks(name) VALUES (?)', (title,)).lastrowid
    return done('custom.deck', {'id': item_id}, deck_id=item_id)


@bp.get('/decks/<int:deck_id>')
def deck(deck_id):
    with connection() as conn:
        # A read transaction gives a consistent snapshot during concurrent draws.
        conn.execute('BEGIN')
        deck = required(conn, 'custom_decks', deck_id)
        cards = conn.execute('SELECT * FROM custom_cards WHERE deck_id=? ORDER BY drawn_order IS NULL, drawn_order, id', (deck_id,)).fetchall()
    drawn = [c for c in cards if c['drawn_order'] is not None and c['table_id'] is None and c['save_id'] is None]
    on_tables = sum(1 for c in cards if c['table_id'] is not None or c['save_id'] is not None)
    remaining = sum(1 for c in cards if c['drawn_order'] is None)
    return render_template('deck.html', deck=deck, cards=cards, drawn=drawn, remaining=remaining, on_tables=on_tables)


@bp.post('/decks/<int:deck_id>/edit')
def edit_deck(deck_id):
    data = payload()
    title = name(data.get('name'))
    probability = number(data.get('reversal_probability', 50), 0, 100)
    with connection() as conn:
        required(conn, 'custom_decks', deck_id)
        conn.execute('UPDATE custom_decks SET name=?, reversal_probability=? WHERE id=?', (title, probability, deck_id))
    return done('custom.deck', deck_id=deck_id)


@bp.post('/decks/<int:deck_id>/upload')
def upload_cards(deck_id):
    uploads = [u for u in request.files.getlist('cards') if u.filename]
    back = request.files.get('back')
    if not uploads and not (back and back.filename):
        raise ValueError('Choose at least one card image or a card back.')
    if len(uploads) > current_app.config['CARD_MAX_UPLOAD_FILES']:
        raise ValueError('Too many images in one upload.')
    validated = [validate_image(u) for u in uploads]
    back_data = validate_image(back) if back and back.filename else None
    written = []
    old_back = None
    try:
        with connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            deck = required(conn, 'custom_decks', deck_id)
            count = conn.execute('SELECT count(*) FROM custom_cards WHERE deck_id=?', (deck_id,)).fetchone()[0]
            if count + len(uploads) > current_app.config['CARD_MAX_DECK_CARDS']:
                raise ValueError('This deck would exceed the configured card limit.')
            rank = conn.execute('SELECT coalesce(max(draw_rank),-1)+1 FROM custom_cards WHERE deck_id=?', (deck_id,)).fetchone()[0]
            rng.shuffle(validated)
            for offset, (filename, content) in enumerate(validated):
                target = storage() / filename
                written.append(target)
                target.write_bytes(content)
                conn.execute('INSERT INTO custom_cards(deck_id,image_file,draw_rank) VALUES (?,?,?)', (deck_id, filename, rank+offset))
            # Mix newly uploaded cards into the remaining pool immediately.
            ids = [r[0] for r in conn.execute('SELECT id FROM custom_cards WHERE deck_id=?', (deck_id,))]
            rng.shuffle(ids)
            conn.execute('UPDATE custom_cards SET draw_rank=-id WHERE deck_id=?', (deck_id,))
            conn.executemany('UPDATE custom_cards SET draw_rank=? WHERE id=?', enumerate(ids))
            if back_data:
                filename, content = back_data
                target = storage() / filename
                written.append(target)
                target.write_bytes(content)
                old_back = deck['back_file']
                conn.execute('UPDATE custom_decks SET back_file=? WHERE id=?', (filename, deck_id))
    except BaseException:
        for target in written:
            target.unlink(missing_ok=True)
        raise
    if old_back:
        (storage() / old_back).unlink(missing_ok=True)
    return done('custom.deck', deck_id=deck_id)


@bp.get('/decks/<int:deck_id>/images/<filename>')
def card_image(deck_id, filename):
    with connection() as conn:
        deck = required(conn, 'custom_decks', deck_id)
        card = conn.execute('SELECT id FROM custom_cards WHERE deck_id=? AND image_file=?', (deck_id, filename)).fetchone()
        if filename != deck['back_file'] and card is None:
            abort(404)
    response = send_from_directory(storage(), filename)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'private, no-cache'
    return response


def draw_next(conn, deck_id):
    """Draw the top card of a deck inside the caller's IMMEDIATE transaction."""
    deck = required(conn, 'custom_decks', deck_id)
    card = conn.execute('SELECT * FROM custom_cards WHERE deck_id=? AND drawn_order IS NULL ORDER BY draw_rank LIMIT 1', (deck_id,)).fetchone()
    if card is None:
        abort(409, description='Deck exhausted. Reshuffle to draw again.')
    order = conn.execute('SELECT coalesce(max(drawn_order),0)+1 FROM custom_cards WHERE deck_id=?', (deck_id,)).fetchone()[0]
    reverse = int(rng.random() * 100 < deck['reversal_probability'])
    conn.execute('UPDATE custom_cards SET drawn_order=?, reversed=?, rotation=0, face_down=0 WHERE id=?', (order, reverse, card['id']))
    return deck, card, order, reverse


def return_to_pool(conn, deck_id, card_ids):
    """Put drawn cards back into a deck's undrawn pool at random positions."""
    if not card_ids:
        return
    conn.executemany('UPDATE custom_cards SET drawn_order=NULL, reversed=0, rotation=0, face_down=0, x=0, y=0, '
                     'table_id=NULL, save_id=NULL, table_x=0, table_y=0, table_z=0 WHERE id=? AND deck_id=?',
                     [(card_id, deck_id) for card_id in card_ids])
    pool = [r[0] for r in conn.execute('SELECT id FROM custom_cards WHERE deck_id=? AND drawn_order IS NULL', (deck_id,))]
    rng.shuffle(pool)
    start = conn.execute('SELECT coalesce(max(draw_rank),0)+1 FROM custom_cards WHERE deck_id=?', (deck_id,)).fetchone()[0]
    # Move the pool above every existing rank first so UNIQUE(deck_id, draw_rank) never collides.
    conn.executemany('UPDATE custom_cards SET draw_rank=? WHERE id=?', [(start + i, card_id) for i, card_id in enumerate(pool)])


@bp.post('/decks/<int:deck_id>/draw')
def draw(deck_id):
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        _, card, order, reverse = draw_next(conn, deck_id)
        result = {'id': card['id'], 'order': order, 'reversed': bool(reverse)}
    return done('custom.deck', result, deck_id=deck_id)


@bp.post('/decks/<int:deck_id>/reshuffle')
def reshuffle(deck_id):
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        required(conn, 'custom_decks', deck_id)
        ids = [r[0] for r in conn.execute('SELECT id FROM custom_cards WHERE deck_id=?', (deck_id,))]
        rng.shuffle(ids)
        # Negative temporary ranks avoid collisions with UNIQUE during permutation.
        conn.execute('UPDATE custom_cards SET draw_rank=-id, drawn_order=NULL, reversed=0, x=0, y=0, rotation=0, face_down=0, '
                     'table_id=NULL, save_id=NULL, table_x=0, table_y=0, table_z=0 WHERE deck_id=?', (deck_id,))
        conn.executemany('UPDATE custom_cards SET draw_rank=? WHERE id=?', enumerate(ids))
    return done('custom.deck', deck_id=deck_id)


@bp.post('/decks/<int:deck_id>/cards/<int:card_id>/edit')
def edit_card(deck_id, card_id):
    data = payload()
    title = data.get('name', '')
    if not isinstance(title, str) or len(title) > 200:
        raise ValueError('Card names must be at most 200 characters.')
    with connection() as conn:
        result = conn.execute('UPDATE custom_cards SET name=? WHERE id=? AND deck_id=?', (title.strip(), card_id, deck_id))
        if not result.rowcount:
            abort(404)
    return done('custom.deck', deck_id=deck_id)


@bp.post('/decks/<int:deck_id>/cards/<int:card_id>/position')
def position(deck_id, card_id):
    data = payload()
    x, y = number(data.get('x'), -80, 80), number(data.get('y'), -200, 200)
    with connection() as conn:
        result = conn.execute('UPDATE custom_cards SET x=?,y=? WHERE id=? AND deck_id=? AND drawn_order IS NOT NULL AND table_id IS NULL AND save_id IS NULL', (x, y, card_id, deck_id))
        if not result.rowcount:
            abort(404)
    return jsonify(ok=True)


def rotation(value):
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValueError('Rotation must be 0, 90, 180 or 270 degrees.')
    if result not in (0, 90, 180, 270):
        raise ValueError('Rotation must be 0, 90, 180 or 270 degrees.')
    return result


@bp.post('/decks/<int:deck_id>/cards/<int:card_id>/rotate')
def rotate(deck_id, card_id):
    angle = rotation(payload().get('rotation'))
    with connection() as conn:
        result = conn.execute('UPDATE custom_cards SET rotation=? WHERE id=? AND deck_id=? AND drawn_order IS NOT NULL '
                              'AND table_id IS NULL AND save_id IS NULL', (angle, card_id, deck_id))
        if not result.rowcount:
            abort(404)
    return done('custom.deck', {'ok': True, 'rotation': angle}, deck_id=deck_id)


@bp.post('/decks/<int:deck_id>/cards/<int:card_id>/delete')
def delete_card(deck_id, card_id):
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        card = required(conn, 'custom_cards', card_id)
        if card['deck_id'] != deck_id:
            abort(404)
        conn.execute('DELETE FROM custom_cards WHERE id=?', (card_id,))
    (storage() / card['image_file']).unlink(missing_ok=True)
    return done('custom.deck', deck_id=deck_id)


@bp.post('/decks/<int:deck_id>/delete')
def delete_deck(deck_id):
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        deck = required(conn, 'custom_decks', deck_id)
        files = [r[0] for r in conn.execute('SELECT image_file FROM custom_cards WHERE deck_id=?', (deck_id,))]
        conn.execute('DELETE FROM custom_decks WHERE id=?', (deck_id,))
    for filename in files + ([deck['back_file']] if deck['back_file'] else []):
        (storage() / filename).unlink(missing_ok=True)
    return done('custom.decks')


# ---------------------------------------------------------------------------
# Dealer's tables: one large, growable surface shared by every deck.
# ---------------------------------------------------------------------------
TABLE_MIN = (800, 600)
TABLE_MAX = 20000


def table_card(row):
    return {
        'id': row['id'], 'deck_id': row['deck_id'], 'deck_name': row['deck_name'],
        'name': row['name'] or '', 'order': row['drawn_order'], 'reversed': bool(row['reversed']),
        'rotation': row['rotation'], 'face_down': bool(row['face_down']),
        'x': row['table_x'], 'y': row['table_y'], 'z': row['table_z'],
        'image': url_for('custom.card_image', deck_id=row['deck_id'], filename=row['image_file']),
        'back': url_for('custom.card_image', deck_id=row['deck_id'], filename=row['back_file']) if row['back_file'] else None,
    }


TABLE_CARD_QUERY = ('SELECT c.*, d.name AS deck_name, d.back_file FROM custom_cards c '
                    'JOIN custom_decks d ON d.id=c.deck_id ')


def deck_shelf(conn):
    return [dict(r) for r in conn.execute(
        'SELECT d.id, d.name, d.back_file, count(c.id) AS total, '
        'sum(CASE WHEN c.id IS NOT NULL AND c.drawn_order IS NULL THEN 1 ELSE 0 END) AS remaining '
        'FROM custom_decks d LEFT JOIN custom_cards c ON c.deck_id=d.id GROUP BY d.id ORDER BY d.name, d.id')]


@bp.get('/tables')
def tables():
    with connection() as conn:
        items = conn.execute('SELECT t.*, count(c.id) AS cards, '
                             '(SELECT count(*) FROM custom_table_saves s WHERE s.table_id=t.id) AS saves '
                             'FROM custom_dealer_tables t LEFT JOIN custom_cards c ON c.table_id=t.id '
                             'GROUP BY t.id ORDER BY t.id DESC').fetchall()
    return render_template('tables.html', tables=items)


@bp.post('/tables')
def create_table():
    title = name(payload().get('name') or "Dealer's Table")
    with connection() as conn:
        item_id = conn.execute('INSERT INTO custom_dealer_tables(name) VALUES (?)', (title,)).lastrowid
    return done('custom.dealer_table', {'id': item_id}, table_id=item_id)


@bp.get('/tables/<int:table_id>')
def dealer_table(table_id):
    with connection() as conn:
        conn.execute('BEGIN')
        table = required(conn, 'custom_dealer_tables', table_id)
        cards = [table_card(r) for r in conn.execute(TABLE_CARD_QUERY + 'WHERE c.table_id=? ORDER BY c.table_z, c.id', (table_id,))]
        shelf = deck_shelf(conn)
        saves = conn.execute('SELECT s.*, count(c.id) AS cards FROM custom_table_saves s LEFT JOIN custom_cards c ON c.save_id=s.id '
                             'WHERE s.table_id=? GROUP BY s.id ORDER BY s.id DESC', (table_id,)).fetchall()
    for deck in shelf:
        deck['back'] = url_for('custom.card_image', deck_id=deck['id'], filename=deck['back_file']) if deck['back_file'] else None
    return render_template('dealer_table.html', table=table, cards=cards, shelf=shelf, saves=saves)


@bp.post('/tables/<int:table_id>/edit')
def edit_table(table_id):
    data = payload()
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        table = required(conn, 'custom_dealer_tables', table_id)
        title = name(data.get('name')) if data.get('name') is not None else table['name']
        width = int(number(data.get('width', table['width']), TABLE_MIN[0], TABLE_MAX))
        height = int(number(data.get('height', table['height']), TABLE_MIN[1], TABLE_MAX))
        conn.execute('UPDATE custom_dealer_tables SET name=?, width=?, height=? WHERE id=?', (title, width, height, table_id))
        # Keep every card on the surface if the table shrinks.
        conn.execute('UPDATE custom_cards SET table_x=min(table_x, ?), table_y=min(table_y, ?) WHERE table_id=?',
                     (max(0, width - 120), max(0, height - 120), table_id))
    return done('custom.dealer_table', {'ok': True, 'width': width, 'height': height, 'name': title}, table_id=table_id)


def gather(conn, table_id=None, save_id=None):
    """Shuffle every card on a table (or in a saved layout) back into its deck."""
    column, value = ('table_id', table_id) if save_id is None else ('save_id', save_id)
    by_deck = {}
    for row in conn.execute(f'SELECT id, deck_id FROM custom_cards WHERE {column}=?', (value,)):
        by_deck.setdefault(row['deck_id'], []).append(row['id'])
    for deck_id, ids in by_deck.items():
        return_to_pool(conn, deck_id, ids)


@bp.post('/tables/<int:table_id>/clear')
def clear_table(table_id):
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        required(conn, 'custom_dealer_tables', table_id)
        gather(conn, table_id)
    return done('custom.dealer_table', table_id=table_id)


@bp.post('/tables/<int:table_id>/delete')
def delete_table(table_id):
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        required(conn, 'custom_dealer_tables', table_id)
        gather(conn, table_id)
        for (save_id,) in conn.execute('SELECT id FROM custom_table_saves WHERE table_id=?', (table_id,)).fetchall():
            gather(conn, save_id=save_id)
        conn.execute('DELETE FROM custom_dealer_tables WHERE id=?', (table_id,))
    return done('custom.tables')


def suspend(conn, table, title, zoom=1.0, view_x=0.0, view_y=0.0):
    """Move every card on the table into a new saved layout and clear the table."""
    count = conn.execute('SELECT count(*) FROM custom_cards WHERE table_id=?', (table['id'],)).fetchone()[0]
    if not count:
        raise ValueError('The table is empty. Deal some cards before saving.')
    save_id = conn.execute('INSERT INTO custom_table_saves(table_id, name, width, height, zoom, view_x, view_y) '
                           'VALUES (?,?,?,?,?,?,?)',
                           (table['id'], title, table['width'], table['height'], zoom, view_x, view_y)).lastrowid
    conn.execute('UPDATE custom_cards SET save_id=?, table_id=NULL WHERE table_id=?', (save_id, table['id']))
    return save_id, count


def view_fields(data):
    return (number(data.get('zoom', 1), 0.1, 4),
            number(data.get('view_x', 0), 0, TABLE_MAX),
            number(data.get('view_y', 0), 0, TABLE_MAX))


@bp.post('/tables/<int:table_id>/saves')
def save_table(table_id):
    """Save instance: suspend the current layout under a name and clear the table."""
    data = payload()
    zoom, view_x, view_y = view_fields(data)
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        table = required(conn, 'custom_dealer_tables', table_id)
        existing = conn.execute('SELECT count(*) FROM custom_table_saves WHERE table_id=?', (table_id,)).fetchone()[0]
        title = name(data.get('name') or f'Save {existing + 1}')
        save_id, count = suspend(conn, table, title, zoom, view_x, view_y)
    return done('custom.dealer_table', {'id': save_id, 'name': title, 'cards': count}, table_id=table_id)


@bp.post('/tables/<int:table_id>/saves/<int:save_id>/resume')
def resume_table(table_id, save_id):
    """Restore a saved layout. Cards currently on the table are auto-saved first."""
    data = payload()
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        table = required(conn, 'custom_dealer_tables', table_id)
        saved = conn.execute('SELECT * FROM custom_table_saves WHERE id=? AND table_id=?', (save_id, table_id)).fetchone()
        if saved is None:
            abort(404)
        auto = None
        if conn.execute('SELECT count(*) FROM custom_cards WHERE table_id=?', (table_id,)).fetchone()[0]:
            zoom, view_x, view_y = view_fields(data)
            title = name(data.get('autosave_name') or f'Auto-saved before resuming {saved["name"]}'[:200])
            auto, _ = suspend(conn, table, title, zoom, view_x, view_y)
        conn.execute('UPDATE custom_cards SET table_id=?, save_id=NULL WHERE save_id=?', (table_id, save_id))
        conn.execute('UPDATE custom_dealer_tables SET width=?, height=? WHERE id=?', (saved['width'], saved['height'], table_id))
        conn.execute('DELETE FROM custom_table_saves WHERE id=?', (save_id,))
    view = {'zoom': saved['zoom'], 'x': round(saved['view_x']), 'y': round(saved['view_y'])}
    if request.is_json or request.headers.get('Accept') == 'application/json':
        return jsonify(ok=True, name=saved['name'], autosave_id=auto, view=view)
    return redirect(url_for('custom.dealer_table', table_id=table_id, **view))


@bp.post('/tables/<int:table_id>/saves/<int:save_id>/rename')
def rename_save(table_id, save_id):
    title = name(payload().get('name'))
    with connection() as conn:
        result = conn.execute('UPDATE custom_table_saves SET name=? WHERE id=? AND table_id=?', (title, save_id, table_id))
        if not result.rowcount:
            abort(404)
    return done('custom.dealer_table', {'ok': True, 'name': title}, table_id=table_id)


@bp.post('/tables/<int:table_id>/saves/<int:save_id>/delete')
def discard_save(table_id, save_id):
    """Delete a saved layout and shuffle its cards back into their decks."""
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM custom_table_saves WHERE id=? AND table_id=?', (save_id, table_id)).fetchone() is None:
            abort(404)
        gather(conn, save_id=save_id)
        conn.execute('DELETE FROM custom_table_saves WHERE id=?', (save_id,))
    return done('custom.dealer_table', table_id=table_id)


@bp.post('/tables/<int:table_id>/draw')
def table_draw(table_id):
    data = payload()
    try:
        deck_id = int(data.get('deck_id'))
    except (TypeError, ValueError):
        raise ValueError('Choose a deck to draw from.')
    face_down = str(data.get('face_down', '0')).lower() in ('1', 'true', 'on', 'yes')
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        table = required(conn, 'custom_dealer_tables', table_id)
        x = number(data.get('x', 40), 0, table['width'])
        y = number(data.get('y', 40), 0, table['height'])
        _, card, _, _ = draw_next(conn, deck_id)
        z = conn.execute('SELECT coalesce(max(table_z),0)+1 FROM custom_cards WHERE table_id=?', (table_id,)).fetchone()[0]
        conn.execute('UPDATE custom_cards SET table_id=?, table_x=?, table_y=?, table_z=?, face_down=? WHERE id=?',
                     (table_id, x, y, z, int(face_down), card['id']))
        result = table_card(conn.execute(TABLE_CARD_QUERY + 'WHERE c.id=?', (card['id'],)).fetchone())
        result['remaining'] = conn.execute('SELECT count(*) FROM custom_cards WHERE deck_id=? AND drawn_order IS NULL', (deck_id,)).fetchone()[0]
    return done('custom.dealer_table', result, table_id=table_id)


def table_card_row(conn, table_id, card_id):
    card = conn.execute('SELECT * FROM custom_cards WHERE id=? AND table_id=?', (card_id, table_id)).fetchone()
    if card is None:
        abort(404)
    return card


@bp.post('/tables/<int:table_id>/cards/<int:card_id>')
def update_table_card(table_id, card_id):
    data = payload()
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        table = required(conn, 'custom_dealer_tables', table_id)
        card = table_card_row(conn, table_id, card_id)
        x = number(data.get('x', card['table_x']), 0, table['width'])
        y = number(data.get('y', card['table_y']), 0, table['height'])
        angle = rotation(data.get('rotation', card['rotation']))
        face_down = card['face_down']
        if 'face_down' in data:
            face_down = int(str(data.get('face_down')).lower() in ('1', 'true', 'on', 'yes'))
        z = card['table_z']
        if str(data.get('raise', '')).lower() in ('1', 'true'):
            z = conn.execute('SELECT coalesce(max(table_z),0)+1 FROM custom_cards WHERE table_id=?', (table_id,)).fetchone()[0]
        conn.execute('UPDATE custom_cards SET table_x=?, table_y=?, rotation=?, face_down=?, table_z=? WHERE id=?',
                     (x, y, angle, face_down, z, card_id))
    return jsonify(ok=True, x=x, y=y, rotation=angle, face_down=bool(face_down), z=z)


@bp.post('/tables/<int:table_id>/cards/<int:card_id>/return')
def return_table_card(table_id, card_id):
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        required(conn, 'custom_dealer_tables', table_id)
        card = table_card_row(conn, table_id, card_id)
        return_to_pool(conn, card['deck_id'], [card_id])
        remaining = conn.execute('SELECT count(*) FROM custom_cards WHERE deck_id=? AND drawn_order IS NULL', (card['deck_id'],)).fetchone()[0]
    return done('custom.dealer_table', {'ok': True, 'deck_id': card['deck_id'], 'remaining': remaining}, table_id=table_id)


def parse_entries(text, is_json=False):
    if not isinstance(text, str) or len(text.encode('utf-8')) > current_app.config['SPARK_MAX_IMPORT_BYTES']:
        raise ValueError('Table text exceeds the import size limit.')
    imported_name = None
    if is_json:
        try:
            entries = json.loads(text)
        except (ValueError, RecursionError):
            raise ValueError('Malformed JSON. Use an array of strings or a named table object.')
        if isinstance(entries, dict):
            if set(entries) == {'name', 'entries'}:
                imported_name = name(entries['name'])
                entries = entries['entries']
            elif len(entries) == 1:
                imported_name, entries = next(iter(entries.items()))
                imported_name = name(imported_name)
            else:
                raise ValueError('Use {"name":"Title","entries":["one","two"]} or {"Title":["one","two"]}.')
        if not isinstance(entries, list) or any(not isinstance(e, str) or not e.strip() for e in entries):
            raise ValueError('JSON entries must be nonempty strings in an array.')
        entries = [e.strip() for e in entries]
    else:
        entries = [e.strip() for e in text.splitlines() if e.strip()]
    if not entries or len(entries) > current_app.config['SPARK_MAX_ENTRIES'] or any(len(e) > 4000 for e in entries):
        raise ValueError('Provide 1–10,000 entries, each at most 4,000 characters (or the configured entry limit).')
    return imported_name, entries


def spark_input():
    data = payload()
    upload = request.files.get('file')
    text = data.get('entries', '')
    is_json = data.get('format') == 'json'
    if upload and upload.filename:
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in ('.txt', '.json'):
            raise ValueError('Import a .txt or .json file.')
        raw = upload.stream.read(current_app.config['SPARK_MAX_IMPORT_BYTES'] + 1)
        if len(raw) > current_app.config['SPARK_MAX_IMPORT_BYTES']:
            raise ValueError('Import file exceeds the configured size limit.')
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ValueError('Save the import file as UTF-8 text.')
        is_json = suffix == '.json'
    imported_name, entries = parse_entries(text, is_json)
    return name(data.get('name') or imported_name), entries


@bp.get('/sparks')
def sparks():
    selected = request.args.get('table', type=int)
    search_query = request.args.get('q', '').strip()
    with connection() as conn:
        tables = conn.execute('SELECT id,name FROM custom_spark_tables ORDER BY name,id').fetchall()
        favorite_ids = {row['table_id'] for row in conn.execute(
            'SELECT table_id FROM custom_spark_favorites WHERE user_id=?', (session.get('user_id'),))}
        table = required(conn, 'custom_spark_tables', selected) if selected else None
        spark_log = conn.execute('SELECT id,table_name,result FROM custom_spark_log ORDER BY id DESC').fetchall()
        results = conn.execute('SELECT result FROM custom_spark_results WHERE table_id=? ORDER BY id DESC LIMIT 30', (selected,)).fetchall() if selected else []
    return render_template('sparks.html', tables=tables, table=table, entries=json.loads(table['entries_json']) if table else [], entries_text=json.dumps(json.loads(table['entries_json']), ensure_ascii=False, indent=2) if table else '', remaining=len(json.loads(table['pool_json'])) if table else 0, results=results, spark_log=spark_log, favorite_ids=favorite_ids, search_query=search_query, oracle_odds=ODDS, selected_odds=session.get('fate_odds', DEFAULT_ODDS), regular_matches=any(row['id'] not in favorite_ids and search_query.lower() in row['name'].lower() for row in tables))


@bp.post('/sparks/oracle/roll')
def roll_fate_oracle():
    odds = payload().get('odds')
    if not isinstance(odds, str) or odds not in ODDS:
        raise ValueError('Choose one of the nine Fate Oracle odds settings.')
    roll = rng.randint(1, 100)
    outcome = resolve_fate(odds, roll)
    result = f'{outcome} · Odds: {odds} · d100: {roll}'
    with connection() as conn:
        log_id = conn.execute('INSERT INTO custom_spark_log(table_name,result) VALUES (?,?)',
                              ('Fate Oracle', result)).lastrowid
    session['fate_odds'] = odds
    return done('custom.sparks', {'odds': odds, 'roll': roll, 'outcome': outcome,
                                'log_entries': [{'id': log_id, 'table_name': 'Fate Oracle', 'result': result}]})


@bp.post('/sparks/<int:table_id>/favorite')
def favorite_spark(table_id):
    # Always derive ownership from the authenticated session, never request fields.
    user_id = session.get('user_id')
    data = payload()
    favorite = data.get('favorite')
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not user_id or not conn.execute('SELECT id FROM users WHERE id=?', (user_id,)).fetchone():
            abort(401, description='Sign in to save favorite tables.')
        required(conn, 'custom_spark_tables', table_id)
        if favorite not in ('0', '1'):
            raise ValueError('Favorite must be 0 or 1.')
        if favorite == '1':
            conn.execute('INSERT OR IGNORE INTO custom_spark_favorites(user_id,table_id) VALUES (?,?)', (user_id, table_id))
        else:
            conn.execute('DELETE FROM custom_spark_favorites WHERE user_id=? AND table_id=?', (user_id, table_id))
    return done('custom.sparks', {'favorite': favorite == '1', 'table_id': table_id})


@bp.post('/sparks/log/reset')
def reset_spark_log():
    with connection() as conn:
        conn.execute('DELETE FROM custom_spark_log')
    return done('custom.sparks')


@bp.post('/sparks')
def create_spark():
    title, entries = spark_input()
    with connection() as conn:
        item_id = conn.execute('INSERT INTO custom_spark_tables(name,entries_json,pool_json) VALUES (?,?,?)', (title, json.dumps(entries), json.dumps(list(range(len(entries)))))).lastrowid
    return done('custom.sparks', {'id': item_id}, table=item_id)


@bp.post('/sparks/<int:table_id>/edit')
def edit_spark(table_id):
    title, entries = spark_input()
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        required(conn, 'custom_spark_tables', table_id)
        conn.execute('UPDATE custom_spark_tables SET name=?,entries_json=?,pool_json=? WHERE id=?', (title,json.dumps(entries),json.dumps(list(range(len(entries)))),table_id))
        conn.execute('DELETE FROM custom_spark_results WHERE table_id=?', (table_id,))
    return done('custom.sparks', table=table_id)


@bp.post('/sparks/<int:table_id>/generate')
def generate(table_id):
    data = payload()
    count = number(data.get('count', 1), 1, 20)
    if not count.is_integer():
        raise ValueError('Spark count must be a whole number.')
    replacement = data.get('replacement', '1') in ('1', True, 1)
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        table = required(conn, 'custom_spark_tables', table_id)
        entries = json.loads(table['entries_json'])
        pool = json.loads(table['pool_json'])
        if not replacement and count > len(pool):
            abort(409, description=f'Only {len(pool)} entries remain. Reset the table or request fewer sparks.')
        indexes = [rng.randrange(len(entries)) for _ in range(int(count))] if replacement else rng.sample(pool, int(count))
        results = [entries[i] for i in indexes]
        if not replacement:
            pool = [i for i in pool if i not in indexes]
        conn.execute('UPDATE custom_spark_tables SET pool_json=?,replacement=?,last_count=? WHERE id=?', (json.dumps(pool),int(replacement),int(count),table_id))
        conn.executemany('INSERT INTO custom_spark_results(table_id,result) VALUES (?,?)', [(table_id,r) for r in results])
        log_entries = []
        for result in results:
            log_id = conn.execute('INSERT INTO custom_spark_log(table_name,result) VALUES (?,?)', (table['name'], result)).lastrowid
            log_entries.append({'id': log_id, 'table_name': table['name'], 'result': result})
        conn.execute('DELETE FROM custom_spark_results WHERE table_id=? AND id NOT IN (SELECT id FROM custom_spark_results WHERE table_id=? ORDER BY id DESC LIMIT 30)', (table_id,table_id))
    return done('custom.sparks', {'results':results, 'log_entries':log_entries}, table=table_id)


@bp.post('/sparks/<int:table_id>/reset')
def reset_spark(table_id):
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        table = required(conn, 'custom_spark_tables', table_id)
        conn.execute('UPDATE custom_spark_tables SET pool_json=? WHERE id=?', (json.dumps(list(range(len(json.loads(table['entries_json']))))),table_id))
    return done('custom.sparks', table=table_id)


@bp.post('/sparks/<int:table_id>/delete')
def delete_spark(table_id):
    with connection() as conn:
        required(conn, 'custom_spark_tables', table_id)
        conn.execute('DELETE FROM custom_spark_tables WHERE id=?', (table_id,))
    return done('custom.sparks')
