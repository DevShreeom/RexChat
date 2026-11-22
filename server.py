from flask import request, jsonify, Flask
import  secrets
import base64
from Auth import login_v2
from Auth import register
from store_msgs import save_to_table
from store_msgs import lookup
from store_msgs import get_conversation
from store_msgs import get_inbox, mark_read
from store_msgs import set_key, get_key
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
socketio = SocketIO(app)
sid_user = {}
import hashlib
import sqlite3

TOKEN_DB = "tokens.db"

def init_token_db():
    with sqlite3.connect(TOKEN_DB) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tokens (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL)"
        )

init_token_db()

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def get_user_by_token(token: str | None) -> str | None:
    if not token:
        return None
    with sqlite3.connect(TOKEN_DB) as conn:
        row = conn.execute(
            "SELECT user_id FROM tokens WHERE token_hash = ?",
            (hash_token(token),),
        ).fetchone()
    return row[0] if row else None

def current_user():
    return get_user_by_token(request.headers.get("Authorization"))

def new_token(user_id: str) -> str:
    token = secrets.token_hex(32)
    with sqlite3.connect(TOKEN_DB) as conn:
        conn.execute(
            "INSERT INTO tokens (token_hash, user_id) VALUES (?, ?)",
            (hash_token(token), user_id),
        )
    return token

@app.route("/stat", methods=["POST"])
def test_connection():
     connection = request.get_json()
     data = connection["test"]
     return jsonify(data)
'''
@app.route("/login",methods=["POST"])
def login():
     data = request.get_json()
     ok = CHECK_login(data["user_id"],data["user_pwd"])
     return {"success": ok}
'''
@app.route("/loginv2",methods=["POST"])
def login():
     data = request.get_json()
     ok = login_v2(data["user_id"],data["user_pwd"])
     if not ok:
          return {"success": False}
     return {"success": True, "token": new_token(data["user_id"])}

@app.route("/register",methods=["POST"])
def register_route():
     data = request.get_json()
     ok = register(data["user_id"],data["user_pwd"])
     if not ok:
          return {"success": False}
     return {"success": True, "token": new_token(data["user_id"])}


@app.route("/finder",methods=["POST"])
def selecting_user():
     user = current_user()
     if not user:
          return {"error": "login first"}, 401
     data = request.get_json()
     rq = lookup(user,data["req_for"])
     return {"yay":rq,"message":"User Not Found!"}

@app.route("/history",methods=["POST"])
def user_history():
     user = current_user()
     if not user:
          return {"error": "login first"}, 401
     data = request.get_json()
     rq= get_conversation(user,data["b"],data["since_id"])
     return jsonify(rq)

@app.route("/inbox",methods=["POST"])
def inbox_route():
     user = current_user()
     if not user:
          return {"error": "login first"}, 401
     return jsonify(get_inbox(user))

@app.route("/mark_read",methods=["POST"])
def mark_read_route():
     user = current_user()
     if not user:
          return {"error": "login first"}, 401
     data = request.get_json()
     return {"success": mark_read(user,data["peer"])}

@app.route("/setkey",methods=["POST"])
def setkey_route():
     user = current_user()
     if not user:
          return {"error": "login first"}, 401
     data = request.get_json()
     try:
          ok = len(base64.b64decode(data["pub_key"])) == 32
     except ValueError:
          ok = False
     if not ok:
          return {"success": False}
     return {"success": set_key(user,data["pub_key"])}

@app.route("/getkey",methods=["POST"])
def getkey_route():
     user = current_user()
     if not user:
          return {"error": "login first"}, 401
     data = request.get_json()
     return {"pub_key": get_key(data["user"])}


@socketio.on("connect")
def on_connect(auth=None):
    token = auth.get("token") if isinstance(auth, dict) else None
    user = get_user_by_token(token)
    if not user:
        return False
    sid_user[request.sid] = user
    join_room(user)
    print("connected:", user)


@socketio.on("disconnect")
def on_disconnect(reason=None):
    sid_user.pop(request.sid, None)

@socketio.on("send")
def on_send(data):
    sender = sid_user.get(request.sid)
    receiver = data["to"]
    text = data["text"]
    if not sender or not lookup(sender, receiver):
        emit("send_error", {"to": receiver})
        return
    ts = save_to_table(sender, receiver, text)
    message = {"from": sender, "to": receiver, "text": text, "ts": ts}
    emit("new_message", message, to=receiver)

    if sender != receiver:            # messaging yourself: don't send two copies
        emit("new_message", message, to=sender)



if __name__ == "__main__":
     socketio.run(app, port=2000, allow_unsafe_werkzeug=True)
