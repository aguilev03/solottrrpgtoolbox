"""Dealer's table: multi-deck draws, free placement, rotation, flipping, growth."""
from tests.test_custom_tools import custom, deck_with_cards, post, rows  # noqa: F401 (fixture)


def make_table(client, token, name="Main table"):
    response = post(client, token, '/tables', {'name': name})
    assert response.status_code == 200
    return response.json['id']


def test_table_crud_and_listing(custom):
    client, db, token = custom
    table = make_table(client, token)
    assert b'Main table' in client.get('/tables').data
    page = client.get(f'/tables/{table}')
    assert page.status_code == 200 and b'dealer-felt' in page.data
    assert post(client, token, f'/tables/{table}/edit', {'name': 'Renamed'}).json['name'] == 'Renamed'
    assert client.get('/tables/999').status_code == 404
    # Default name when left blank
    blank = post(client, token, '/tables', {'name': ''}).json['id']
    assert rows(db, 'SELECT name FROM custom_dealer_tables WHERE id=?', (blank,))[0]['name'] == "Dealer's Table"


def test_draw_from_multiple_decks_onto_one_table(custom):
    client, db, token = custom
    deck_a = deck_with_cards(custom, 2)
    deck_b = deck_with_cards(custom, 3)
    table = make_table(client, token)
    a = post(client, token, f'/tables/{table}/draw', json={'deck_id': deck_a, 'x': 100, 'y': 120}).json
    b = post(client, token, f'/tables/{table}/draw', json={'deck_id': deck_b, 'x': 300, 'y': 50, 'face_down': True}).json
    assert a['deck_id'] == deck_a and b['deck_id'] == deck_b
    assert (a['x'], a['y'], a['face_down']) == (100, 120, False)
    assert b['face_down'] is True and b['back']
    assert b['z'] > a['z']
    assert a['remaining'] == 1 and b['remaining'] == 2
    on_table = rows(db, 'SELECT * FROM custom_cards WHERE table_id=?', (table,))
    assert {c['id'] for c in on_table} == {a['id'], b['id']}
    # Cards on the dealer's table do not show on their deck's own tabletop.
    deck_page = client.get(f'/decks/{deck_a}').data
    assert b'class="table-card"' not in deck_page
    assert b'1 / 2 cards remaining' in deck_page and b"dealer's table" in deck_page
    # Exhaustion is shared between the deck page and the table.
    post(client, token, f'/decks/{deck_a}/draw')
    assert post(client, token, f'/tables/{table}/draw', json={'deck_id': deck_a}).status_code == 409
    assert post(client, token, f'/tables/{table}/draw', json={'deck_id': 'nope'}).status_code == 400


def test_move_rotate_flip_and_validation(custom):
    client, db, token = custom
    deck = deck_with_cards(custom, 2)
    table = make_table(client, token)
    card = post(client, token, f'/tables/{table}/draw', json={'deck_id': deck}).json
    url = f'/tables/{table}/cards/{card["id"]}'
    moved = post(client, token, url, json={'x': 500, 'y': 400, 'raise': True}).json
    assert (moved['x'], moved['y']) == (500, 400) and moved['z'] >= card['z']
    assert post(client, token, url, json={'rotation': 90}).json['rotation'] == 90
    assert post(client, token, url, json={'rotation': 270}).json['rotation'] == 270
    assert post(client, token, url, json={'rotation': 45}).status_code == 400
    assert post(client, token, url, json={'face_down': True}).json['face_down'] is True
    assert post(client, token, url, json={'x': 999999}).status_code == 400   # off the table
    saved = rows(db, 'SELECT * FROM custom_cards WHERE id=?', (card['id'],))[0]
    assert (saved['table_x'], saved['table_y'], saved['rotation'], saved['face_down']) == (500, 400, 270, 1)
    # A card can only be moved on the table it is on.
    other = make_table(client, token, 'Other')
    assert post(client, token, f'/tables/{other}/cards/{card["id"]}', json={'x': 1}).status_code == 404


def test_table_grows_and_shrink_keeps_cards_on_surface(custom):
    client, db, token = custom
    deck = deck_with_cards(custom, 1)
    table = make_table(client, token)
    grown = post(client, token, f'/tables/{table}/edit', json={'width': 4000, 'height': 3000}).json
    assert (grown['width'], grown['height']) == (4000, 3000)
    card = post(client, token, f'/tables/{table}/draw', json={'deck_id': deck, 'x': 3500, 'y': 2800}).json
    assert post(client, token, f'/tables/{table}/edit', json={'width': 50000}).status_code == 400
    post(client, token, f'/tables/{table}/edit', json={'width': 1000, 'height': 800})
    saved = rows(db, 'SELECT table_x, table_y FROM custom_cards WHERE id=?', (card['id'],))[0]
    assert saved['table_x'] <= 1000 and saved['table_y'] <= 800


def test_return_gather_delete_and_reshuffle(custom):
    client, db, token = custom
    deck = deck_with_cards(custom, 3)
    table = make_table(client, token)
    drawn = [post(client, token, f'/tables/{table}/draw', json={'deck_id': deck}).json for _ in range(3)]
    back = post(client, token, f'/tables/{table}/cards/{drawn[0]["id"]}/return').json
    assert back['remaining'] == 1
    assert rows(db, 'SELECT drawn_order, table_id FROM custom_cards WHERE id=?', (drawn[0]['id'],))[0]['table_id'] is None
    # The returned card can be drawn again.
    assert post(client, token, f'/tables/{table}/draw', json={'deck_id': deck}).json['id'] == drawn[0]['id']
    post(client, token, f'/tables/{table}/clear')
    cards = rows(db, 'SELECT * FROM custom_cards WHERE deck_id=?', (deck,))
    assert all(c['table_id'] is None and c['drawn_order'] is None for c in cards)
    assert len({c['draw_rank'] for c in cards}) == 3
    # Deleting a table returns its cards; reshuffling a deck pulls cards off tables too.
    post(client, token, f'/tables/{table}/draw', json={'deck_id': deck})
    post(client, token, f'/tables/{table}/delete')
    assert rows(db, 'SELECT count(*) AS n FROM custom_dealer_tables')[0]['n'] == 0
    assert all(c['table_id'] is None and c['drawn_order'] is None for c in rows(db, 'SELECT * FROM custom_cards'))
    table = make_table(client, token)
    post(client, token, f'/tables/{table}/draw', json={'deck_id': deck})
    post(client, token, f'/decks/{deck}/reshuffle')
    assert rows(db, 'SELECT count(*) AS n FROM custom_cards WHERE table_id IS NOT NULL')[0]['n'] == 0


def test_rotate_on_deck_tabletop(custom):
    client, db, token = custom
    deck = deck_with_cards(custom, 2)
    card = post(client, token, f'/decks/{deck}/draw').json
    assert post(client, token, f'/decks/{deck}/cards/{card["id"]}/rotate', json={'rotation': 90}).json['rotation'] == 90
    assert b'data-rotation="90"' in client.get(f'/decks/{deck}').data
    assert post(client, token, f'/decks/{deck}/cards/{card["id"]}/rotate', json={'rotation': 30}).status_code == 400
    undrawn = rows(db, 'SELECT id FROM custom_cards WHERE deck_id=? AND drawn_order IS NULL', (deck,))[0]['id']
    assert post(client, token, f'/decks/{deck}/cards/{undrawn}/rotate', json={'rotation': 90}).status_code == 404
    post(client, token, f'/decks/{deck}/reshuffle')
    assert all(c['rotation'] == 0 for c in rows(db, 'SELECT rotation FROM custom_cards'))


def test_migration_adds_columns_to_existing_database(tmp_path):
    import sqlite3
    from custom_tools import migrate
    path = tmp_path / 'old.db'
    conn = sqlite3.connect(path)
    conn.executescript('''
        CREATE TABLE custom_decks (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            reversal_probability REAL NOT NULL DEFAULT 50, back_file TEXT);
        CREATE TABLE custom_cards (id INTEGER PRIMARY KEY, deck_id INTEGER NOT NULL, name TEXT NOT NULL DEFAULT '',
            image_file TEXT NOT NULL, draw_rank INTEGER NOT NULL, drawn_order INTEGER,
            reversed INTEGER NOT NULL DEFAULT 0, x REAL NOT NULL DEFAULT 0, y REAL NOT NULL DEFAULT 0);
        INSERT INTO custom_decks(name) VALUES ('Old');
        INSERT INTO custom_cards(deck_id, image_file, draw_rank, drawn_order, x) VALUES (1, 'a.png', 0, 1, 12);
    ''')
    migrate(conn)
    migrate(conn)  # idempotent
    row = conn.execute('SELECT x, rotation, table_id, face_down FROM custom_cards').fetchone()
    assert row == (12, 0, None, 0)
    conn.close()
