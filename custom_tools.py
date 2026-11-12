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
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge, Conflict, NotFound

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
        CREATE TABLE IF NOT EXISTS custom_spark_log (
            id INTEGER PRIMARY KEY, table_name TEXT NOT NULL, result TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS custom_cards_deck ON custom_cards(deck_id);
        CREATE INDEX IF NOT EXISTS custom_results_table ON custom_spark_results(table_id, id);
    ''')


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
    drawn = [c for c in cards if c['drawn_order'] is not None]
    return render_template('deck.html', deck=deck, cards=cards, drawn=drawn, remaining=len(cards)-len(drawn))


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


@bp.post('/decks/<int:deck_id>/draw')
def draw(deck_id):
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        deck = required(conn, 'custom_decks', deck_id)
        card = conn.execute('SELECT * FROM custom_cards WHERE deck_id=? AND drawn_order IS NULL ORDER BY draw_rank LIMIT 1', (deck_id,)).fetchone()
        if card is None:
            abort(409, description='Deck exhausted. Reshuffle to draw again.')
        order = conn.execute('SELECT coalesce(max(drawn_order),0)+1 FROM custom_cards WHERE deck_id=?', (deck_id,)).fetchone()[0]
        reverse = int(rng.random() * 100 < deck['reversal_probability'])
        conn.execute('UPDATE custom_cards SET drawn_order=?, reversed=? WHERE id=?', (order, reverse, card['id']))
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
        conn.execute('UPDATE custom_cards SET draw_rank=-id, drawn_order=NULL, reversed=0, x=0, y=0 WHERE deck_id=?', (deck_id,))
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
        result = conn.execute('UPDATE custom_cards SET x=?,y=? WHERE id=? AND deck_id=? AND drawn_order IS NOT NULL', (x, y, card_id, deck_id))
        if not result.rowcount:
            abort(404)
    return jsonify(ok=True)


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
    with connection() as conn:
        tables = conn.execute('SELECT id,name FROM custom_spark_tables ORDER BY name,id').fetchall()
        table = required(conn, 'custom_spark_tables', selected) if selected else None
        spark_log = conn.execute('SELECT id,table_name,result FROM custom_spark_log ORDER BY id').fetchall()
        results = conn.execute('SELECT result FROM custom_spark_results WHERE table_id=? ORDER BY id DESC LIMIT 30', (selected,)).fetchall() if selected else []
    return render_template('sparks.html', tables=tables, table=table, entries=json.loads(table['entries_json']) if table else [], entries_text=json.dumps(json.loads(table['entries_json']), ensure_ascii=False, indent=2) if table else '', remaining=len(json.loads(table['pool_json'])) if table else 0, results=results, spark_log=spark_log)


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
