# RexChat

A self-hosted, end-to-end encrypted terminal chat app with a 3-column TUI. You run the server, you hold your own keys, and nobody else touches your messages.

## How it works

### Key-file verification (no cloud recovery)
RexChat uses local key files for E2EE. Your key stays on your machine—it is never backed up to the server.

This is intentional: **if you delete or lose your key file, your chat history is permanently unreadable.** There is no "forgot key" button or server-side recovery. If someone gets access to the server database, all they get is ciphertext.

### Self-hosted
There is no central RexChat server. Host `server.py` on your own machine, VPS, or local network, point the client's `config.txt` to your server's IP/URL, and you're good to go.

### Other details
- **3-column TUI:** Chats list, active conversation, and user search/results in one terminal window.
- **Persistent sessions:** Auth tokens are generated with `secrets.token_hex(32)`, hashed with SHA-256, and stored in SQLite (`tokens.db`) so logins survive server restarts.
- **Local chat cache:** Recent chats are cached per user in `recent_chats.json`.

---

## Tech Stack

- **Client UI:** Python, [Textual](https://textual.textualize.io/)
- **Networking:** `requests`, `python-socketio`
- **Backend:** Flask, Flask-SocketIO, SQLite
- **Packaging & CI:** `uv`, PyInstaller, Inno Setup (Windows installer), GitHub Actions

---

## Running the Client

Download the latest build for your OS from the [Releases](https://github.com/DevShreeom/RexChat/releases) page.

Before launching, open `config.txt` (in the install folder) and set it to your server's address:

```text
http://YOUR_SERVER_IP:2000
```

- **Windows:** Run `RexChat-Setup.exe`. It installs to `%LOCALAPPDATA%\RexChat` and creates a desktop shortcut.
- **Linux:** Extract `RexChat-Linux.tar.gz` and run:
  ```bash
  ./RexChat/RexChat
  ```
- **macOS:** Unzip `RexChat-macOS.zip`, open Terminal inside the `RexChat` folder, and run:
  ```bash
  xattr -cr . && ./RexChat
  ```
  *(Needed once because the binary isn't signed with an Apple Developer certificate.)*

---

## Self-Hosting the Server

Requires Python 3.10+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone [https://github.com/DevShreeom/RexChat.git](https://github.com/DevShreeom/RexChat.git)
cd RexChat
uv run server.py
```

By default, the server listens on port `2000`. Make sure that port is open/forwarded if friends are connecting over the internet, and update their `config.txt` with your server's IP or domain.

---

## Running Client from Source

If you don't want to use the prebuilt binaries:

```bash
git clone [https://github.com/DevShreeom/RexChat.git](https://github.com/DevShreeom/RexChat.git)
cd RexChat
uv run rex_chat_ui.py
```
