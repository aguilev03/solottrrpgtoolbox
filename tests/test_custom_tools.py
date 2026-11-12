"""End-to-end custom library acceptance, safety, concurrency and restart checks."""
import io
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from PIL import Image
from app import app
from database import Database


@pytest.fixture
def custom(tmp_path):
    db = Database(str(tmp_path / 'tools.db'))
    config = dict(app.config)
    app.config.update(TESTING=True, LOGIN_DISABLED=True, CARD_UPLOAD_DIR=str(tmp_path / 'uploads'))
    with patch('app.db', db):
        with app.test_client() as client:
            client.get('/decks')
            with client.session_transaction() as session:
                token = session['custom_csrf']
            yield client, db, token
    app.config.clear()
    app.config.update(config)


def post(client, token, path, data=None, **kwargs):
    return client.post(path, headers={'X-CSRF-Token': token, 'Accept': 'application/json'}, data=data, **kwargs)


def image(filename='card.png', fmt='PNG', size=(60, 100)):
    stream = io.BytesIO()
    Image.new('RGB', size, 'red').save(stream, format=fmt)
    stream.seek(0)
    return stream, filename


def deck_with_cards(custom, count=3):
    client, db, token = custom
    item_id = post(client, token, '/decks', {'name': 'My deck'}).json['id']
    response = post(client, token, f'/decks/{item_id}/upload', {'cards': [image() for _ in range(count)], 'back': image('back.webp', 'WEBP')})
    assert response.status_code == 200
    return item_id


def rows(db, query, args=()):
    with db.get_connection() as conn:
        return conn.execute(query, args).fetchall()


def test_deck_library_and_safe_images(custom):
    client, db, token = custom
    deck = deck_with_cards(custom)
    cards = rows(db, 'SELECT * FROM custom_cards WHERE deck_id=?', (deck,))
    assert len(cards) == 3
    assert client.get('/decks').status_code == 200
    assert client.get(f'/decks/{deck}').status_code == 200
    response = client.get(f'/decks/{deck}/images/{cards[0]["image_file"]}')
    assert response.status_code == 200
    assert Image.open(io.BytesIO(response.data)).size == (60, 100)
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert client.get(f'/decks/{deck}/images/../../config.py').status_code == 404
    post(client, token, f'/decks/{deck}/edit', {'name':'Renamed', 'reversal_probability':0})
    assert b'Renamed' in client.get(f'/decks/{deck}').data
    card_id = cards[0]['id']
    post(client, token, f'/decks/{deck}/cards/{card_id}/edit', {'name':'The sun'})
    assert b'The sun' in client.get(f'/decks/{deck}').data
    post(client, token, f'/decks/{deck}/cards/{card_id}/delete')
    assert len(rows(db, 'SELECT * FROM custom_cards')) == 2
    post(client, token, f'/decks/{deck}/delete')
    assert rows(db, 'SELECT * FROM custom_cards') == []
    assert not list(__import__('pathlib').Path(app.config['CARD_UPLOAD_DIR']).iterdir())


def test_draw_exhaustion_reversal_reshuffle_and_positions(custom):
    client, db, token = custom
    deck = deck_with_cards(custom)
    post(client, token, f'/decks/{deck}/edit', {'name':'Deck', 'reversal_probability':100})
    first = post(client, token, f'/decks/{deck}/draw').json
    assert first['reversed'] is True
    assert b'class="reversed"' in client.get(f'/decks/{deck}').data
    response = post(client, token, f'/decks/{deck}/cards/{first["id"]}/position', json={'x':42, 'y':90})
    assert response.status_code == 200
    post(client, token, f'/decks/{deck}/edit', {'name':'Deck', 'reversal_probability':0})
    rest = [post(client, token, f'/decks/{deck}/draw').json for _ in range(2)]
    assert all(not c['reversed'] for c in rest)
    assert len({first['id'], *(c['id'] for c in rest)}) == 3
    assert post(client, token, f'/decks/{deck}/draw').status_code == 409
    page = client.get(f'/decks/{deck}').data
    assert b'disabled' in page and b'0 / 3 cards remaining' in page
    assert b'data-x="42.0"' in page
    post(client, token, f'/decks/{deck}/reshuffle')
    cards = rows(db, 'SELECT * FROM custom_cards')
    assert all(c['drawn_order'] is None and c['x']==0 and c['y']==0 and c['reversed']==0 for c in cards)
    assert len({c['draw_rank'] for c in cards}) == 3
    assert b'class="table-card"' not in client.get(f'/decks/{deck}').data
    assert post(client, token, f'/decks/{deck}/draw').status_code == 200


def test_persistence_in_fresh_process(custom):
    client, db, token = custom
    deck = deck_with_cards(custom)
    first = post(client, token, f'/decks/{deck}/draw').json
    post(client, token, f'/decks/{deck}/cards/{first["id"]}/position', json={'x':15, 'y':22})
    table = post(client, token, '/sparks', {'name':'Ideas','entries':'A\nB'}).json['id']
    post(client, token, f'/sparks/{table}/generate', {'replacement':'0'})
    script = '''
import app
with app.app.test_client() as client:
    assert b'2 / 3 cards remaining' in client.get('/decks/1').data
    assert b'data-x="15.0"' in client.get('/decks/1').data
    assert client.get('/sparks?table=1').status_code == 200
with app.db.get_connection() as conn:
    assert conn.execute('SELECT count(*) FROM custom_spark_results').fetchone()[0] == 1
    assert len(__import__('json').loads(conn.execute('SELECT pool_json FROM custom_spark_tables').fetchone()[0])) == 1
'''
    env = dict(os.environ, SOLO_TOOLS_DB=db.db_path, LOGIN_DISABLED='true', CARD_UPLOAD_DIR=app.config['CARD_UPLOAD_DIR'])
    subprocess.run([sys.executable, '-c', script], env=env, check=True, capture_output=True)


def test_concurrent_draws(custom):
    _, db, token = custom
    deck = deck_with_cards(custom, 12)
    def draw(_):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session['custom_csrf'] = token
            response = post(client, token, f'/decks/{deck}/draw')
            return response.status_code, response.json
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(draw, range(20)))
    successes = [r for code,r in results if code==200]
    assert len(successes) == 12
    assert len({r['id'] for r in successes}) == 12
    assert sorted(r['order'] for r in successes) == list(range(1,13))
    assert sum(code==409 for code,_ in results) == 8


@pytest.mark.parametrize('filename,content', [('bad.svg',b'<svg/>'), ('bad.png',b'not an image'), ('fake.jpg',None), ('truncated.png',b'\x89PNG\r\n\x1a\n')])
def test_invalid_images_atomic(custom, filename, content):
    client, db, token = custom
    deck = post(client, token, '/decks', {'name':'Deck'}).json['id']
    bad = (io.BytesIO(content),filename) if content is not None else image(filename)
    response = post(client, token, f'/decks/{deck}/upload', {'cards':[image(),bad]})
    assert response.status_code == 400
    assert rows(db, 'SELECT * FROM custom_cards') == []
    assert not __import__('pathlib').Path(app.config['CARD_UPLOAD_DIR']).exists()


def test_upload_limits_and_filenames(custom):
    client, db, token = custom
    deck = post(client, token, '/decks', {'name':'Deck'}).json['id']
    app.config['CARD_MAX_UPLOAD_FILES'] = 1
    assert post(client, token, f'/decks/{deck}/upload', {'cards':[image(),image()]}).status_code == 400
    app.config['CARD_MAX_IMAGE_BYTES'] = 5
    assert post(client, token, f'/decks/{deck}/upload', {'cards':image()}).status_code == 400
    app.config['CARD_MAX_IMAGE_BYTES'] = 10000
    app.config['CARD_MAX_PIXELS'] = 50
    assert post(client, token, f'/decks/{deck}/upload', {'cards':image()}).status_code == 400
    app.config['CARD_MAX_PIXELS'] = 10000
    assert post(client, token, f'/decks/{deck}/upload', {'cards':image('../../escape.png')}).status_code == 200
    stored = rows(db, 'SELECT image_file FROM custom_cards')[0][0]
    assert '/' not in stored and stored != 'escape.png'
    app.config['CARD_MAX_DECK_CARDS'] = 1
    assert post(client, token, f'/decks/{deck}/upload', {'cards':image()}).status_code == 400
    app.config['MAX_CONTENT_LENGTH'] = 10
    assert post(client, token, f'/decks/{deck}/upload', {'cards':image()}).status_code == 413


@pytest.mark.parametrize('extension,text,expected_name', [
    ('txt',' one\n\n two \n','Ideas'),
    ('json','["one","two"]','Ideas'),
    ('json','{"name":"Omens","entries":["one","two"]}','Omens'),
    ('json','{"Omens":["one","two"]}','Omens'),
])
def test_spark_import_selection_and_edit(custom, extension, text, expected_name):
    client, db, token = custom
    data = {'file':(io.BytesIO(text.encode()),'table.'+extension)}
    if expected_name == 'Ideas': data['name'] = 'Ideas'
    response = post(client, token, '/sparks', data)
    assert response.status_code == 200
    item = response.json['id']
    table = rows(db,'SELECT * FROM custom_spark_tables')[0]
    assert table['name'] == expected_name
    assert json.loads(table['entries_json']) == ['one','two']
    assert client.get(f'/sparks?table={item}').status_code == 200
    generated = post(client, token, f'/sparks/{item}/generate', {'count':20}).json['results']
    assert len(generated) == 20 and set(generated) <= {'one','two'}
    generated = post(client, token, f'/sparks/{item}/generate', {'count':2,'replacement':'0'}).json['results']
    assert set(generated) == {'one','two'}
    assert post(client, token, f'/sparks/{item}/generate', {'replacement':'0'}).status_code == 409
    post(client, token, f'/sparks/{item}/reset')
    assert post(client, token, f'/sparks/{item}/generate', {'replacement':'0'}).status_code == 200
    post(client, token, f'/sparks/{item}/edit', {'name':'Updated','entries':'new\nentry'})
    assert json.loads(rows(db,'SELECT entries_json FROM custom_spark_tables')[0][0]) == ['new','entry']
    assert rows(db,'SELECT * FROM custom_spark_results') == []
    post(client, token, f'/sparks/{item}/delete')
    assert rows(db,'SELECT * FROM custom_spark_tables') == []


@pytest.mark.parametrize('text', ['{bad','{}','[1]','[""]','null','{"name":"X","entries":"bad"}'])
def test_invalid_spark_edit_preserves_data(custom,text):
    client, db, token = custom
    item = post(client,token,'/sparks',{'name':'Keep','entries':'one\ntwo'}).json['id']
    response = post(client,token,f'/sparks/{item}/edit',{'name':'Changed','entries':text,'format':'json'})
    assert response.status_code == 400
    table = rows(db,'SELECT * FROM custom_spark_tables')[0]
    assert table['name']=='Keep' and json.loads(table['entries_json'])==['one','two']


def test_json_api_csrf_auth_and_missing_records(custom):
    client, db, token = custom
    assert client.post('/decks',json={'name':'Bad'}).status_code == 400
    assert post(client,token,'/decks',json={'name':'Good'}).status_code == 200
    assert post(client,token,'/decks',json=[]).status_code == 400
    assert client.post('/decks',data='{',content_type='application/json',headers={'X-CSRF-Token':token}).status_code == 400
    assert post(client,token,'/decks/999/draw').status_code == 404
    assert post(client,token,'/sparks',{'name':'X','entries':'\n'}).status_code == 400
    app.config['LOGIN_DISABLED'] = False
    for path in ('/decks','/decks/1','/decks/1/images/f.png','/sparks'):
        assert client.get(path).status_code == 302
    assert post(client,token,'/decks/1/draw').status_code == 302


def test_additive_migration_preserves_records(custom):
    _, db, _ = custom
    with db.get_connection() as conn:
        conn.execute("INSERT INTO npcs(name) VALUES ('Existing NPC')")
    reopened = Database(db.db_path)
    assert rows(reopened,'SELECT name FROM npcs')[0][0] == 'Existing NPC'


@pytest.mark.parametrize('filename,fmt', [('face.png','PNG'),('face.jpg','JPEG'),('face.jpeg','JPEG'),('face.webp','WEBP')])
def test_supported_image_types_and_default_probability(custom,filename,fmt):
    client,db,token=custom
    deck=post(client,token,'/decks',{'name':'Formats'}).json['id']
    assert rows(db,'SELECT reversal_probability FROM custom_decks')[0][0] == 50
    assert post(client,token,f'/decks/{deck}/upload',{'cards':image(filename,fmt)}).status_code == 200
    stored=rows(db,'SELECT image_file FROM custom_cards')[0][0]
    assert Image.open(io.BytesIO(client.get(f'/decks/{deck}/images/{stored}').data)).format==fmt


def test_upload_after_drawing_preserves_tabletop_and_back_replacement(custom):
    client,db,token=custom
    deck=deck_with_cards(custom)
    post(client,token,f'/decks/{deck}/draw')
    before=rows(db,'SELECT * FROM custom_cards WHERE drawn_order IS NOT NULL')[0]
    old_back=rows(db,'SELECT back_file FROM custom_decks')[0][0]
    assert post(client,token,f'/decks/{deck}/upload',{'cards':image(),'back':image()}).status_code==200
    after=rows(db,'SELECT * FROM custom_cards WHERE drawn_order IS NOT NULL')[0]
    assert (before['id'],before['drawn_order'],before['reversed'])==(after['id'],after['drawn_order'],after['reversed'])
    assert client.get(f'/decks/{deck}/images/{old_back}').status_code==404
    assert len(rows(db,'SELECT * FROM custom_cards WHERE drawn_order IS NULL'))==3


def test_spark_limits_unicode_multiline_and_recent_history(custom):
    client,db,token=custom
    entries=['A\nmultiline omen','Étoile <script>alert(1)</script>']
    table=post(client,token,'/sparks',{'name':'Unicode','format':'json','entries':json.dumps(entries)}).json['id']
    response=client.get(f'/sparks?table={table}')
    assert response.status_code==200 and b'&lt;script&gt;' in response.data
    for _ in range(3):
        assert post(client,token,f'/sparks/{table}/generate',{'count':20}).status_code==200
    assert len(rows(db,'SELECT * FROM custom_spark_results'))==30
    assert post(client,token,f'/sparks/{table}/generate',{'count':1.5}).status_code==400
    assert post(client,token,f'/sparks/{table}/generate',{'count':21}).status_code==400
    app.config['SPARK_MAX_ENTRIES']=1
    assert post(client,token,'/sparks',{'name':'Large','entries':'a\nb'}).status_code==400
    app.config['SPARK_MAX_IMPORT_BYTES']=4
    assert post(client,token,'/sparks',{'name':'Large','file':(io.BytesIO(b'long text'),'a.txt')}).status_code==400
    assert post(client,token,'/sparks',{'name':'Bad','file':(io.BytesIO(b'\xff'),'a.txt')}).status_code==400
    assert post(client,token,'/sparks',{'name':'Bad','file':(io.BytesIO(b'x'),'a.csv')}).status_code==400
