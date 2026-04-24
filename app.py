from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import configparser
import sqlite3
import os

# ── Config ────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))
_cfg  = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
_cfg.read(os.path.join(_BASE, 'config.ini'))

_USERNAME      = _cfg.get('auth',   'username', fallback='admin')
_PASSWORD_HASH = generate_password_hash(_cfg.get('auth', 'password', fallback='changeme'))
_PORT          = int(_cfg.get('server', 'port', fallback='5000'))

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cv-secret-k3y-2025-local')
CORS(app)

DB_PATH = os.path.join(_BASE, 'colder.db')


# ── Auth ─────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Não autenticado'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET'])
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login_submit():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if username == _USERNAME and check_password_hash(_PASSWORD_HASH, password):
        session['logged_in'] = True
        return jsonify({'ok': True})
    return jsonify({'error': 'Usuário ou senha incorretos'}), 401


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


# ── Database ─────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                language TEXT DEFAULT 'plaintext',
                draft_content TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                label TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
        ''')
        cols = [r[1] for r in conn.execute('PRAGMA table_info(documents)').fetchall()]
        if 'draft_content' not in cols:
            conn.execute('ALTER TABLE documents ADD COLUMN draft_content TEXT')
            conn.commit()


# ── Routes ───────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/api/documents', methods=['GET'])
@login_required
def list_documents():
    with get_db() as conn:
        rows = conn.execute('''
            SELECT d.id, d.title, d.language, d.created_at, d.updated_at,
                   MAX(v.version_number) as latest_version
            FROM documents d
            LEFT JOIN versions v ON d.id = v.document_id
            GROUP BY d.id
            ORDER BY d.updated_at DESC
        ''').fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/documents', methods=['POST'])
@login_required
def create_document():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    language = data.get('language', 'plaintext')

    if not title:
        return jsonify({'error': 'Título é obrigatório'}), 400

    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO documents (title, language) VALUES (?, ?)',
            (title, language)
        )
        doc_id = cur.lastrowid
        conn.commit()
        doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
        return jsonify(dict(doc)), 201


@app.route('/api/documents/<int:doc_id>', methods=['GET'])
@login_required
def get_document(doc_id):
    with get_db() as conn:
        doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
        if not doc:
            return jsonify({'error': 'Documento não encontrado'}), 404

        latest = conn.execute(
            'SELECT * FROM versions WHERE document_id = ? ORDER BY version_number DESC LIMIT 1',
            (doc_id,)
        ).fetchone()

        result = dict(doc)
        result['current_version'] = dict(latest) if latest else None
        return jsonify(result)


@app.route('/api/documents/<int:doc_id>', methods=['PUT'])
@login_required
def update_document(doc_id):
    with get_db() as conn:
        doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
        if not doc:
            return jsonify({'error': 'Documento não encontrado'}), 404

        data = request.get_json() or {}
        title = data.get('title', doc['title'])
        language = data.get('language', doc['language'])

        conn.execute(
            'UPDATE documents SET title = ?, language = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (title, language, doc_id)
        )
        conn.commit()
        doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
        return jsonify(dict(doc))


@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@login_required
def delete_document(doc_id):
    with get_db() as conn:
        doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
        if not doc:
            return jsonify({'error': 'Documento não encontrado'}), 404

        conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        conn.commit()
        return jsonify({'message': 'Documento deletado'})


@app.route('/api/documents/<int:doc_id>/versions', methods=['GET'])
@login_required
def list_versions(doc_id):
    with get_db() as conn:
        if not conn.execute('SELECT id FROM documents WHERE id = ?', (doc_id,)).fetchone():
            return jsonify({'error': 'Documento não encontrado'}), 404

        rows = conn.execute(
            'SELECT id, document_id, version_number, label, created_at FROM versions WHERE document_id = ? ORDER BY version_number DESC',
            (doc_id,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/documents/<int:doc_id>/versions/<int:version_id>', methods=['GET'])
@login_required
def get_version(doc_id, version_id):
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM versions WHERE id = ? AND document_id = ?',
            (version_id, doc_id)
        ).fetchone()
        if not row:
            return jsonify({'error': 'Versão não encontrada'}), 404
        return jsonify(dict(row))


@app.route('/api/documents/<int:doc_id>/versions', methods=['POST'])
@login_required
def create_version(doc_id):
    with get_db() as conn:
        if not conn.execute('SELECT id FROM documents WHERE id = ?', (doc_id,)).fetchone():
            return jsonify({'error': 'Documento não encontrado'}), 404

        data = request.get_json() or {}
        content = data.get('content', '')
        label = data.get('label', '')

        latest = conn.execute(
            'SELECT MAX(version_number) as max_v FROM versions WHERE document_id = ?',
            (doc_id,)
        ).fetchone()
        next_num = (latest['max_v'] or 0) + 1

        cur = conn.execute(
            'INSERT INTO versions (document_id, content, version_number, label) VALUES (?, ?, ?, ?)',
            (doc_id, content, next_num, label)
        )
        conn.execute(
            'UPDATE documents SET draft_content = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (doc_id,)
        )
        conn.commit()

        row = conn.execute('SELECT * FROM versions WHERE id = ?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


@app.route('/api/documents/<int:doc_id>/draft', methods=['PUT'])
@login_required
def save_draft(doc_id):
    with get_db() as conn:
        if not conn.execute('SELECT id FROM documents WHERE id = ?', (doc_id,)).fetchone():
            return jsonify({'error': 'Documento não encontrado'}), 404
        content = (request.get_json() or {}).get('content', '')
        conn.execute('UPDATE documents SET draft_content = ? WHERE id = ?', (content, doc_id))
        conn.commit()
        return jsonify({'ok': True})


@app.route('/api/documents/<int:doc_id>/restore/<int:version_id>', methods=['POST'])
@login_required
def restore_version(doc_id, version_id):
    with get_db() as conn:
        if not conn.execute('SELECT id FROM documents WHERE id = ?', (doc_id,)).fetchone():
            return jsonify({'error': 'Documento não encontrado'}), 404

        src = conn.execute(
            'SELECT * FROM versions WHERE id = ? AND document_id = ?',
            (version_id, doc_id)
        ).fetchone()
        if not src:
            return jsonify({'error': 'Versão não encontrada'}), 404

        latest = conn.execute(
            'SELECT MAX(version_number) as max_v FROM versions WHERE document_id = ?',
            (doc_id,)
        ).fetchone()
        next_num = (latest['max_v'] or 0) + 1
        label = f'Restaurado da v{src["version_number"]}'

        cur = conn.execute(
            'INSERT INTO versions (document_id, content, version_number, label) VALUES (?, ?, ?, ?)',
            (doc_id, src['content'], next_num, label)
        )
        conn.execute(
            'UPDATE documents SET draft_content = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (doc_id,)
        )
        conn.commit()

        row = conn.execute('SELECT * FROM versions WHERE id = ?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=_PORT, debug=True)
