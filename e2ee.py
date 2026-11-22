import base64
import hashlib
from pathlib import Path

from nacl import pwhash, utils
from nacl.exceptions import CryptoError
from nacl.public import Box, PrivateKey, PublicKey
from nacl.secret import SecretBox

KEY_DIR = Path(__file__).parent / "keys"


class KeyFileError(Exception):
    pass


def _lock_key(password, salt):
    # turns the login password into a key that locks the private key file
    return pwhash.argon2id.kdf(
        SecretBox.KEY_SIZE,
        password.encode(),
        salt,
        opslimit=pwhash.argon2id.OPSLIMIT_INTERACTIVE,
        memlimit=pwhash.argon2id.MEMLIMIT_INTERACTIVE,
    )


def _key_path(user_id):
    # hashed so a weird username can never point outside the keys folder
    name = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    return KEY_DIR / f"{name}.key"


def load_or_create_keys(user_id, password):
    """returns (private_key, public_key_b64, created_new)"""
    KEY_DIR.mkdir(exist_ok=True)
    path = _key_path(user_id)
    n = pwhash.argon2id.SALTBYTES

    if path.exists():
        raw = path.read_bytes()
        salt, locked = raw[:n], raw[n:]
        try:
            secret = SecretBox(_lock_key(password, salt)).decrypt(locked)
        except CryptoError:
            raise KeyFileError("could not unlock the key file for this account")
        priv = PrivateKey(secret)
        return priv, base64.b64encode(bytes(priv.public_key)).decode(), False

    priv = PrivateKey.generate()
    salt = utils.random(n)
    locked = SecretBox(_lock_key(password, salt)).encrypt(bytes(priv))
    path.write_bytes(salt + bytes(locked))
    path.chmod(0o600)
    return priv, base64.b64encode(bytes(priv.public_key)).decode(), True


def encrypt(priv, their_pub_b64, text):
    box = Box(priv, PublicKey(base64.b64decode(their_pub_b64)))
    return base64.b64encode(bytes(box.encrypt(text.encode("utf-8")))).decode()


def decrypt(priv, their_pub_b64, blob):
    # works for messages I sent AND messages I received: both sides of a
    # Box get the same shared key. returns None if it can't be read
    try:
        box = Box(priv, PublicKey(base64.b64decode(their_pub_b64)))
        return box.decrypt(base64.b64decode(blob)).decode("utf-8")
    except (CryptoError, ValueError):
        return None


def safety_number(pub_a_b64, pub_b_b64):
    # same number on both screens. if it differs, someone swapped a key
    a, b = sorted([pub_a_b64, pub_b_b64])
    h = hashlib.sha256((a + b).encode()).hexdigest()
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}"
