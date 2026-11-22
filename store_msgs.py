import time
import sqlite3

db = sqlite3.connect("session.db")

db.execute("""
    CREATE TABLE IF NOT EXISTS msgs(
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        sender      TEXT,
        receiver    TEXT,
        text        TEXT,
        ts          REAL
    )
""")
db.execute("""
    CREATE TABLE IF NOT EXISTS reads(
        user_id       TEXT,
        peer          TEXT,
        last_read_id  INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, peer)
    )
""")
db.execute("""
    CREATE TABLE IF NOT EXISTS keys(
        user_id   TEXT PRIMARY KEY,
        pub_key   TEXT
    )
""")
db.commit()
db.close()

def save_to_table(send_by,received_by,content):
    db = sqlite3.connect("session.db")
    ts = time.time()
    db.execute("INSERT INTO msgs(sender,receiver,text,ts) VALUES(?,?,?,?)",
               (send_by, received_by, content, ts,)
               )
    db.commit()
    db.close()
    return ts


def lookup(req_by, req_for):
    db = sqlite3.connect("userdata.db")
    try:
        row = db.execute(
            "SELECT user_id FROM users WHERE user_id IN (?, ?)",
            (req_by, req_for),
        ).fetchall()
        return len(row) == 2
    except sqlite3.DatabaseError:
        return False

    finally:
        db.close()

def get_conversation(a, b, since_id):
    db = sqlite3.connect("session.db")
    db.row_factory = sqlite3.Row            # set BEFORE the query
    try:
        rows = db.execute(
            "SELECT * FROM msgs "
            "WHERE ((sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)) "
            "AND id > ? ORDER BY id",
            (a, b, b, a, since_id),
        ).fetchall()
        return [dict(r) for r in rows]      # return the list of dicts
    finally:
        db.close()

def get_inbox(user_id):
    db = sqlite3.connect("session.db")
    db.row_factory = sqlite3.Row
    try:
        # "peer" is worked out in the inner query on purpose, the reads
        # table also has a peer column and GROUP BY would pick that one
        rows = db.execute(
            """
            SELECT t.peer AS peer,
                   MAX(t.id) AS last_id,
                   MAX(t.ts) AS last_ts,
                   SUM(CASE WHEN t.receiver = ? AND t.id > COALESCE(r.last_read_id, 0)
                            THEN 1 ELSE 0 END) AS unread
            FROM (
                SELECT id, ts, receiver,
                       CASE WHEN sender = ? THEN receiver ELSE sender END AS peer
                FROM msgs
                WHERE sender = ? OR receiver = ?
            ) t
            LEFT JOIN reads r ON r.user_id = ? AND r.peer = t.peer
            GROUP BY t.peer
            ORDER BY last_id DESC
            """,
            (user_id,) * 5,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()

def mark_read(user_id, peer):
    db = sqlite3.connect("session.db")
    try:
        row = db.execute(
            "SELECT MAX(id) FROM msgs WHERE sender = ? AND receiver = ?",
            (peer, user_id),
        ).fetchone()
        latest = row[0] or 0
        db.execute(
            """
            INSERT INTO reads(user_id, peer, last_read_id) VALUES(?,?,?)
            ON CONFLICT(user_id, peer)
            DO UPDATE SET last_read_id = MAX(last_read_id, excluded.last_read_id)
            """,
            (user_id, peer, latest),
        )
        db.commit()
        return True
    finally:
        db.close()

def set_key(user_id, pub_key):
    db = sqlite3.connect("session.db")
    db.execute("INSERT OR REPLACE INTO keys(user_id, pub_key) VALUES(?,?)",
               (user_id, pub_key))
    db.commit()
    db.close()
    return True

def get_key(user_id):
    db = sqlite3.connect("session.db")
    try:
        row = db.execute("SELECT pub_key FROM keys WHERE user_id = ?",
                         (user_id,)).fetchone()
        return row[0] if row else None
    finally:
        db.close()

if __name__ == "__main__":
    print(get_conversation("shree", "sai", 0))