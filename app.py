import os, sqlite3
from datetime import datetime
from flask import Flask, render_template, abort

APP_VERSION = "vweb-1.0"
DB_PATH = os.path.join(os.path.dirname(__file__), "guild_ledger.db")
GUILD_NAME = "GUILDA"

def db():
    con = sqlite3.connect(DB_PATH, timeout=5.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con

def ensure_db():
    con = db(); cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS players(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id INTEGER NOT NULL,
        ttype TEXT NOT NULL CHECK(ttype IN ('Credito','Debito')),
        amount REAL NOT NULL,
        category TEXT,
        note TEXT,
        split_id INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS splits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bruto INTEGER NOT NULL DEFAULT 0,
        reparo INTEGER NOT NULL DEFAULT 0,
        cobrar_taxa INTEGER NOT NULL DEFAULT 1,
        taxa_pct REAL NOT NULL DEFAULT 25.0,
        reparo_payer TEXT NOT NULL DEFAULT 'JOGADORES',
        note TEXT,
        created_at TEXT NOT NULL,
        pulled_by TEXT,
        status TEXT NOT NULL DEFAULT 'Vendendo',
        approved INTEGER NOT NULL DEFAULT 0
    )""")
    # índices úteis
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_player ON transactions(player_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_split  ON transactions(split_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_players_active ON players(active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_splits_created ON splits(id)")
    # conta da guilda
    if not cur.execute("SELECT 1 FROM players WHERE name=?", (GUILD_NAME,)).fetchone():
        cur.execute("INSERT INTO players(name,active,created_at) VALUES(?,?,?)",
                    (GUILD_NAME,1,datetime.utcnow().isoformat()))
    con.commit(); con.close()

def balances():
    con = db()
    rows = con.execute("""
        SELECT p.id, p.name,
               COALESCE(SUM(CASE WHEN t.ttype='Credito' THEN t.amount ELSE 0 END),0) -
               COALESCE(SUM(CASE WHEN t.ttype='Debito'  THEN t.amount ELSE 0 END),0) AS saldo
        FROM players p
        LEFT JOIN transactions t ON t.player_id = p.id
        WHERE p.active=1
        GROUP BY p.id
        ORDER BY CASE WHEN p.name=? THEN 1 ELSE 0 END, saldo DESC, p.name ASC
    """, (GUILD_NAME,)).fetchall()
    con.close()
    return rows

# ------- compat com bancos antigos -------
def row_to_dict(row): return {k: row[k] for k in row.keys()}
def normalize_split(d):
    return {
        "id": d.get("id"),
        "bruto": d.get("bruto", 0) or 0,
        "reparo": d.get("reparo", 0) or 0,
        "cobrar_taxa": d.get("cobrar_taxa", 1),
        "taxa_pct": d.get("taxa_pct", 25.0),
        "reparo_payer": d.get("reparo_payer", "JOGADORES"),
        "note": d.get("note"),
        "created_at": d.get("created_at"),
        "pulled_by": d.get("pulled_by"),
        "status": d.get("status", "Vendendo"),
        "approved": d.get("approved", 0),
    }

def splits_list():
    con = db()
    rows = [normalize_split(row_to_dict(r))
            for r in con.execute("SELECT * FROM splits ORDER BY id DESC LIMIT 500").fetchall()]
    con.close()
    return rows

def split_detail(sid:int):
    con = db()
    srow = con.execute("SELECT * FROM splits WHERE id=?", (sid,)).fetchone()
    if not srow:
        con.close(); return None, None
    s = normalize_split(row_to_dict(srow))
    tx = con.execute("""
        SELECT t.id, p.name as player_name, t.ttype, t.amount, t.category, t.note, t.created_at
        FROM transactions t
        JOIN players p ON p.id = t.player_id
        WHERE t.split_id=?
        ORDER BY t.amount DESC
    """, (sid,)).fetchall()
    con.close()
    return s, tx

app = Flask(__name__)
app.config["APP_VERSION"] = APP_VERSION
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-" + os.urandom(16).hex())

@app.template_filter("fmt_int")
def fmt_int(v):
    try: v = int(round(float(v)))
    except: v = int(v or 0)
    return f"{v:,}".replace(",", ".")

@app.route("/healthz")
def healthz():
    try:
        con = db(); con.execute("SELECT 1"); con.close()
        return {"status":"ok","version":APP_VERSION}, 200
    except Exception as e:
        return {"status":"error","detail":str(e)}, 500

# ---------------- rotas públicas ----------------
@app.route("/")
def home():
    ensure_db()
    bals = balances()
    total = sum(int(round(r["saldo"] or 0)) for r in bals)
    guild_cash = next((int(round(r["saldo"])) for r in bals if r["name"] == GUILD_NAME), 0)
    players = [r for r in bals if r["name"] != GUILD_NAME]
    return render_template("index.html",
                           balances=players, guild_cash=guild_cash, total=total,
                           guild_name=GUILD_NAME, version=APP_VERSION)

@app.route("/splits")
def view_splits():
    return render_template("splits.html", splits=splits_list(), version=APP_VERSION)

@app.route("/splits/<int:sid>")
def view_split(sid):
    s, tx = split_detail(sid)
    if not s: abort(404)
    return render_template("split_detail.html", s=s, tx=tx, version=APP_VERSION)

@app.errorhandler(404)
def _404(e): 
    return render_template("404.html", version=APP_VERSION), 404

@app.errorhandler(500)
def _500(e):
    return render_template("500.html", version=APP_VERSION), 500

if __name__ == "__main__":
    ensure_db()
    app.run(host="0.0.0.0", port=5000)
