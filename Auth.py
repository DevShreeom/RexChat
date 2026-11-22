user_data = {
    "om" :"1234",
    "sai" :"2508"
}
import sqlite3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
ph = PasswordHasher()
db= sqlite3.connect("userdata.db")

db.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id  TEXT UNIQUE,
        user_pwd TEXT
    )
    """)
db.commit()
db.close()
def login_v2(user_id,user_pwd):
    db = sqlite3.connect("userdata.db")
    rows = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if rows is None: #the no user case is here
        return False
    else:
       try:
           ph.verify(rows[2], user_pwd)
           return True
       except VerifyMismatchError:
           return False

def register(user_id,user_pwd):
    try:
        hash_pwd =ph.hash(user_pwd)
        db = sqlite3.connect("userdata.db")
        db.execute("INSERT INTO users (user_id,user_pwd)VALUES(?,?)",(user_id,hash_pwd),)
        db.commit()
        return True
    except sqlite3.IntegrityError:
        #print("REGISTER ERROR:", exc)
        return False

'''
def CHECK_login(user_id,user_pwd):
    return user_id in user_data and user_data[user_id]== user_pwd

'''