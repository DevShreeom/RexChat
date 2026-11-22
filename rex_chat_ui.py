import threading
from datetime import datetime, timedelta

import requests
import socketio
from requests import RequestException
from requests.exceptions import RequestException

import e2ee
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

try:
    with open("config.txt") as f:
        SERVER_URL = f.read().strip() or "http://127.0.0.1:2000"
except FileNotFoundError:
    SERVER_URL = "http://127.0.0.1:2000"
GAP = 30 * 60   # seconds of silence before a new time divider


class SessionExpired(Exception):
    pass


def divider_text(ts: float) -> str:
    t = datetime.fromtimestamp(ts)
    today = datetime.now().date()
    if t.date() == today:
        day = "Today"
    elif t.date() == today - timedelta(days=1):
        day = "Yesterday"
    elif t.year == datetime.now().year:
        day = t.strftime("%d %b")
    else:
        day = t.strftime("%d %b %Y")
    return f"── {day} {t.strftime('%H:%M')} ──"


# ─────────────────────────────────────────────────────────────
# 1. LOGIN / REGISTER SCREEN
# ─────────────────────────────────────────────────────────────
class AuthScreen(Screen):
    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                with Vertical(id="auth-box", classes="pane") as box:
                    box.border_title = "Rex Chat"
                    yield Static("Login or Register to continue", id="auth-subtitle")

                    user_in = Input(placeholder="Enter your User ID", id="auth-user")
                    user_in.border_title = "User ID"
                    yield user_in

                    pwd_in = Input(
                        placeholder="Enter your Password",
                        password=True,
                        id="auth-pwd",
                    )
                    pwd_in.border_title = "Password"
                    yield pwd_in

                    with Horizontal(id="auth-buttons"):
                        yield Button("Login", id="btn-login", classes="auth-btn")
                        yield Button("Register", id="btn-register", classes="auth-btn")

                    yield Static("Checking server status...", id="auth-status")

    def on_mount(self) -> None:
        self.query_one("#auth-user", Input).focus()
        self.check_server()

    @work(thread=True)
    def check_server(self) -> None:
        try:
            res = requests.post(f"{SERVER_URL}/stat", json={"test": 100}, timeout=4)
            if res.status_code == 200:
                self.app.call_from_thread(
                    self.set_status, "Connected to server.", "status-ok"
                )
            else:
                self.app.call_from_thread(
                    self.set_status, "Server connection failed.", "status-err"
                )
        except RequestException:
            self.app.call_from_thread(
                self.set_status, f"Server offline ({SERVER_URL}).", "status-err"
            )

    def set_status(self, message: str, css_class: str = "") -> None:
        status = self.query_one("#auth-status", Static)
        status.remove_class("status-ok", "status-err")
        if css_class:
            status.add_class(css_class)
        status.update(message)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        user_id = self.query_one("#auth-user", Input).value.strip()
        user_pwd = self.query_one("#auth-pwd", Input).value.strip()

        if not user_id or not user_pwd:
            self.set_status("Please enter both User ID and Password.", "status-err")
            return

        if event.button.id == "btn-login":
            self.set_status("Logging in...")
            self.do_auth("/loginv2", user_id, user_pwd, "Invalid credentials.")
        elif event.button.id == "btn-register":
            self.set_status("Registering...")
            self.do_auth(
                "/register", user_id, user_pwd, "Registration failed (ID might be taken)."
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Pressing Enter in Password triggers Login; in User ID moves to Password
        if event.input.id == "auth-user":
            self.query_one("#auth-pwd", Input).focus()
        elif event.input.id == "auth-pwd":
            self.query_one("#btn-login", Button).press()

    @work(thread=True)
    def do_auth(
        self, endpoint: str, user_id: str, user_pwd: str, fail_msg: str
    ) -> None:
        try:
            res = requests.post(
                f"{SERVER_URL}{endpoint}",
                json={"user_id": user_id, "user_pwd": user_pwd},
                timeout=5,
            )
            data = res.json()
            if data.get("success"):
                self.app.call_from_thread(
                    self.app.enter_chat, user_id, data["token"], user_pwd
                )
            else:
                self.app.call_from_thread(self.set_status, fail_msg, "status-err")
        except RequestException as exc:
            self.app.call_from_thread(
                self.set_status, f"Request failed: {exc}", "status-err"
            )


# ─────────────────────────────────────────────────────────────
# 2. MAIN CHAT SCREEN
# ─────────────────────────────────────────────────────────────
class ChatScreen(Screen):
    def __init__(self, user_id: str, token: str, password: str) -> None:
        super().__init__()
        self.user_id = user_id
        self.token = token
        self.password = password          # only used to unlock the key file
        self.priv = None
        self.my_pub = None
        self.keys_ready = threading.Event()
        self.peer_keys: dict[str, str] = {}
        self.active_chat: str | None = None
        self.last_ts: float | None = None   # time of the last message drawn
        # chats[username] = {"unread": int, "messages": list[tuple[sender, text, ts]]}
        self.chats: dict[str, dict] = {}
        self.search_results: list[str] = []
        self.sio = socketio.Client()

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-row"):
            # Left: Chats list
            chats_list = ListView(id="chats-list", classes="pane")
            chats_list.border_title = f"Chats ({self.user_id})"
            yield chats_list

            # Middle: Active chat history
            chat_view = VerticalScroll(id="chat-view", classes="pane")
            chat_view.border_title = "Select or search a user"
            yield chat_view

            # Right: Search + Results
            with Vertical(id="right-col"):
                search_input = Input(
                    placeholder="find a user (Enter)...", id="search-input"
                )
                search_input.border_title = "Search"
                yield search_input

                results_list = ListView(id="results-list", classes="pane")
                results_list.border_title = "Results"
                yield results_list

        # Bottom: Type a message
        msg_input = Input(placeholder="Type a message...", id="message-input")
        msg_input.border_title = "Type a message"
        yield msg_input

    def on_mount(self) -> None:
        self.refresh_chats_list()
        self.setup_keys()
        self.load_inbox()
        self.connect_socket()
        self.query_one("#search-input", Input).focus()

    def on_unmount(self) -> None:
        if self.sio.connected:
            self.sio.disconnect()

    def remember_peer(self, peer: str) -> None:
        # Put the most recent peer at the top of the list
        peers = [p for p in self.chats.keys() if p != peer]
        peers.insert(0, peer)
        self.chats = {p: self.chats[p] for p in peers}

    # --- talking to the server (the token goes with every request) ---
    def api(self, path: str, **payload):
        res = requests.post(
            f"{SERVER_URL}{path}",
            json=payload,
            headers={"Authorization": self.token},
            timeout=5,
        )
        if res.status_code == 401:
            raise SessionExpired()
        return res.json()

    def fail(self, exc: Exception, what: str) -> None:
        if isinstance(exc, SessionExpired):
            msg = "Session expired, log in again"
        else:
            msg = f"{what}: {exc}"
        self.app.call_from_thread(self.notify, msg, severity="error")

    # --- encryption keys ---
    @work(thread=True)
    def setup_keys(self) -> None:
        try:
            priv, pub, created = e2ee.load_or_create_keys(self.user_id, self.password)
            self.password = None
            res = self.api("/setkey", pub_key=pub)
            if not res.get("success"):
                raise RequestException("server refused the public key")
        except e2ee.KeyFileError as exc:
            self.app.call_from_thread(self.notify, str(exc), severity="error")
            return
        except (RequestException, SessionExpired) as exc:
            self.fail(exc, "Could not set up encryption")
            return
        self.priv, self.my_pub = priv, pub
        self.keys_ready.set()
        if created:
            self.app.call_from_thread(
                self.notify,
                "New encryption key created on this computer. "
                "Older messages from another computer can't be read here.",
            )

    def peer_key(self, peer: str):
        if peer not in self.peer_keys:
            key = self.api("/getkey", user=peer).get("pub_key")
            if key:
                self.peer_keys[peer] = key
        return self.peer_keys.get(peer)

    def read(self, peer: str, blob: str) -> str:
        pub = self.peer_key(peer)
        text = e2ee.decrypt(self.priv, pub, blob) if pub else None
        return text if text is not None else "(could not decrypt)"

    @work(thread=True)
    def check_key(self, peer: str) -> None:
        try:
            self.peer_key(peer)
        except (RequestException, SessionExpired):
            pass

    # --- Inbox (who has written to me, and how many unread) ---
    @work(thread=True)
    def load_inbox(self) -> None:
        try:
            rows = self.api("/inbox")
        except (RequestException, SessionExpired) as exc:
            self.fail(exc, "Failed to load your chats")
            return
        self.app.call_from_thread(self.apply_inbox, rows)

    def apply_inbox(self, rows: list[dict]) -> None:
        # rows arrive newest conversation first
        order = []
        for r in rows:
            peer = r["peer"]
            order.append(peer)
            if peer not in self.chats:
                self.chats[peer] = {"unread": 0, "messages": []}
            # a chat that is open right now has nothing unread
            self.chats[peer]["unread"] = 0 if peer == self.active_chat else r["unread"]
        rest = [p for p in self.chats if p not in order]
        self.chats = {p: self.chats[p] for p in order + rest}
        self.refresh_chats_list()

    @work(thread=True)
    def mark_read_remote(self, peer: str) -> None:
        try:
            self.api("/mark_read", peer=peer)
        except (RequestException, SessionExpired):
            pass

    # --- Socket.IO ---
    @work(thread=True)
    def connect_socket(self) -> None:
        @self.sio.on("new_message")
        def on_new_message(data):
            sender = data["from"]
            receiver = data["to"]
            # Figure out which conversation this belongs to
            peer = receiver if sender == self.user_id else sender
            self.keys_ready.wait(10)
            try:
                text = self.read(peer, data["text"])
            except (RequestException, SessionExpired):
                text = "(could not decrypt)"
            self.app.call_from_thread(
                self.handle_incoming, peer, sender, text, data["ts"]
            )

        @self.sio.on("send_error")
        def on_send_error(data):
            self.app.call_from_thread(
                self.notify, f"Message to {data['to']} was not sent", severity="error"
            )

        try:
            self.sio.connect(SERVER_URL, auth={"token": self.token})
        except socketio.exceptions.ConnectionError:
            self.app.call_from_thread(
                self.notify,
                "Could not connect to the chat server (is your login still valid?)",
                severity="error",
            )

    def handle_incoming(self, peer: str, sender: str, text: str, ts: float) -> None:
        if peer not in self.chats:
            self.chats[peer] = {"unread": 0, "messages": []}

        self.chats[peer]["messages"].append((sender, text, ts))
        self.remember_peer(peer)

        if peer == self.active_chat:
            self.append_message_widget(sender, text, ts)
            if sender != self.user_id:
                self.mark_read_remote(peer)
        elif sender != self.user_id:
            self.chats[peer]["unread"] += 1
            self.notify(f"New message from {peer}")

        self.refresh_chats_list()

    # --- UI Helpers ---
    def refresh_chats_list(self) -> None:
        chats_list = self.query_one("#chats-list", ListView)
        chats_list.clear()
        for user, data in self.chats.items():
            unread = f" ({data['unread']})" if data["unread"] > 0 else ""
            prefix = "> " if user == self.active_chat else "  "
            chats_list.append(
                ListItem(Label(f"{prefix}{user:<10}{unread}", markup=False), name=user)
            )

    def refresh_results_list(self) -> None:
        results_list = self.query_one("#results-list", ListView)
        results_list.clear()
        for user in self.search_results:
            results_list.append(ListItem(Label(f"  {user}", markup=False), name=user))

    def needs_divider(self, ts: float) -> bool:
        if self.last_ts is None or ts - self.last_ts > GAP:
            return True
        return datetime.fromtimestamp(ts).date() != datetime.fromtimestamp(self.last_ts).date()

    def append_message_widget(self, sender: str, text: str, ts: float) -> None:
        chat_view = self.query_one("#chat-view", VerticalScroll)
        if self.needs_divider(ts):
            chat_view.mount(Static(divider_text(ts), classes="divider", markup=False))
        self.last_ts = ts
        # markup=False: message text is never read as styling codes
        if sender == self.user_id:
            chat_view.mount(Static(f"you: {text}", classes="msg-me", markup=False))
        else:
            chat_view.mount(Static(f"{sender}: {text}", classes="msg-them", markup=False))
        chat_view.scroll_end(animate=False)

    def open_chat(self, peer: str) -> None:
        self.active_chat = peer
        if peer not in self.chats:
            self.chats[peer] = {"unread": 0, "messages": []}
        self.chats[peer]["unread"] = 0
        self.remember_peer(peer)
        self.mark_read_remote(peer)

        chat_view = self.query_one("#chat-view", VerticalScroll)
        chat_view.border_title = peer
        chat_view.remove_children()
        self.last_ts = None

        self.refresh_chats_list()
        self.fetch_history(peer)
        self.query_one("#message-input", Input).focus()

    # --- Backend API Calls ---
    @work(thread=True)
    def fetch_history(self, peer: str) -> None:
        if not self.keys_ready.wait(10):
            self.app.call_from_thread(
                self.notify, "Encryption is not ready yet", severity="error"
            )
            return
        try:
            history = self.api("/history", b=peer, since_id=0)
            msgs = [(m["sender"], self.read(peer, m["text"]), m["ts"]) for m in history]
        except (RequestException, SessionExpired) as exc:
            self.fail(exc, "Failed to load chat history")
            return
        self.app.call_from_thread(self.render_history, peer, msgs)

    def render_history(self, peer: str, msgs: list[tuple[str, str, float]]) -> None:
        self.chats[peer]["messages"] = msgs
        if self.active_chat != peer:
            return
        chat_view = self.query_one("#chat-view", VerticalScroll)
        chat_view.remove_children()
        self.last_ts = None
        pub = self.peer_keys.get(peer)
        if pub:
            # both people should see the same number, if not a key was swapped
            number = e2ee.safety_number(self.my_pub, pub)
            chat_view.border_title = f"{peer}  |  e2ee {number}"
        else:
            chat_view.border_title = f"{peer}  |  no key yet"
        for sender, text, ts in msgs:
            self.append_message_widget(sender, text, ts)

    @work(thread=True)
    def find_user(self, target: str) -> None:
        try:
            data = self.api("/finder", req_for=target)
        except (RequestException, SessionExpired) as exc:
            self.fail(exc, "Search error")
            return
        if data.get("yay"):
            self.app.call_from_thread(self.add_search_result, target)
        else:
            self.app.call_from_thread(
                self.notify, f"User '{target}' not found", severity="warning"
            )

    def add_search_result(self, user: str) -> None:
        if user not in self.search_results:
            self.search_results.insert(0, user)
        self.refresh_results_list()

    # --- Events ---
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.name:
            self.open_chat(event.item.name)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            return

        if event.input.id == "search-input":
            event.input.value = ""
            self.find_user(value)

        elif event.input.id == "message-input":
            if not self.active_chat:
                self.notify("Search and select a user first!", severity="warning")
                return
            pub = self.peer_keys.get(self.active_chat)
            if self.priv is None or not pub:
                self.check_key(self.active_chat)
                self.notify(
                    f"No encryption key for {self.active_chat} yet "
                    "(they have to log in once). Try again in a moment.",
                    severity="warning",
                )
                return
            event.input.value = ""
            if self.sio.connected:
                self.sio.emit(
                    "send",
                    {
                        "to": self.active_chat,
                        "text": e2ee.encrypt(self.priv, pub, value),
                    },
                )
            else:
                self.notify("Not connected to server", severity="error")


# ─────────────────────────────────────────────────────────────
# 3. MAIN APP & SHARED AESTHETIC CSS
# ─────────────────────────────────────────────────────────────
class RexChatApp(App):
    CSS = """
    Screen {
        background: #141414;
        color: #e6dfd5;
        padding: 1 2;
    }

    /* Shared rounded-border pane styling */
    .pane {
        border: round #6e675f;
        border-title-color: #d4b895;
        border-title-align: left;
        background: #141414;
        padding: 0 1;
    }

    .pane:focus, .pane:focus-within {
        border: round #e8c9a0;
        border-title-color: #f5dec0;
    }

    /* ── Auth Screen ── */
    #auth-box {
        width: 48;
        height: auto;
        padding: 1 2;
    }

    #auth-subtitle {
        text-align: center;
        color: #a89f91;
        margin-bottom: 1;
    }

    #auth-user, #auth-pwd {
        height: 3;
        margin-bottom: 1;
        border: round #6e675f;
        border-title-color: #d4b895;
        background: #141414;
        color: #e6dfd5;
    }

    #auth-user:focus, #auth-pwd:focus {
        border: round #e8c9a0;
        border-title-color: #f5dec0;
    }

    #auth-buttons {
        height: 3;
        margin-top: 1;
        align: center middle;
    }

    .auth-btn {
        width: 1fr;
        margin: 0 1;
        background: #242220;
        color: #e6dfd5;
        border: round #6e675f;
    }

    .auth-btn:hover, .auth-btn:focus {
        background: #e6dfd5;
        color: #141414;
        border: round #e8c9a0;
        text-style: bold;
    }

    #auth-status {
        text-align: center;
        margin-top: 1;
        height: 1;
        color: #a89f91;
    }

    .status-ok { color: #a3be8c; }
    .status-err { color: #bf616a; }

    /* ── Chat Screen ── */
    #main-row {
        height: 1fr;
    }

    #chats-list {
        width: 24;
        margin-right: 1;
    }

    #chat-view {
        width: 1fr;
        margin-right: 1;
        padding: 1 2;
    }

    #right-col {
        width: 28;
    }

    #search-input, #message-input {
        height: 3;
        border: round #6e675f;
        border-title-color: #d4b895;
        background: #141414;
        color: #e6dfd5;
    }

    #search-input { margin-bottom: 1; }
    #message-input { margin-top: 1; }

    #search-input:focus, #message-input:focus {
        border: round #e8c9a0;
        border-title-color: #f5dec0;
    }

    #results-list {
        height: 1fr;
    }

    /* ListView item highlight */
    ListView > ListItem {
        padding: 0 1;
        background: transparent;
        color: #cfc6ba;
    }

    ListView > ListItem.--highlight {
        background: #e6dfd5;
        color: #141414;
        text-style: bold;
    }

    /* time divider between messages */
    .divider {
        width: 100%;
        text-align: center;
        color: #a89f91;
        margin-bottom: 1;
    }

    /* Chat messages */
    .msg-them {
        width: 100%;
        text-align: left;
        color: #e6dfd5;
        margin-bottom: 1;
    }

    .msg-me {
        width: 100%;
        text-align: right;
        color: #e8c9a0;
        margin-bottom: 1;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(AuthScreen())

    def enter_chat(self, user_id: str, token: str, password: str) -> None:
        self.switch_screen(ChatScreen(user_id, token, password))


if __name__ == "__main__":
    RexChatApp().run()
