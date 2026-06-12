"""FastDrive — an open-source file-management app built with FastHTML.

A server-side, HTMX-driven port of the core of Frappe Drive: a file/folder
browser with breadcrumbs, shared/starred/recent/trash views, file detail with
shares + activity, upload, and an AI assistant grounded in the (synthetic) tree.

Run:
    python web_app.py            # http://localhost:5012

Login: admin@fastdrive.example / FastDrive2026$  (override via .env)
"""
from __future__ import annotations

import os
import json
import secrets
import uuid
import logging

from dotenv import load_dotenv
load_dotenv()

from fasthtml.common import (
    fast_app, serve, Div, H1, P, A, Form, Input, Button, NotStr,
    RedirectResponse, Script, Style, Link, Title,
)
from starlette.responses import StreamingResponse, Response

import db
from web.layout import page, LAYOUT_CSS
from web import views, ai

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("fastdrive")

VALID_EMAIL = os.getenv("FASTDRIVE_ADMIN_EMAIL", "admin@fastdrive.example")
VALID_PASSWORD = os.getenv("FASTDRIVE_ADMIN_PASSWORD", "FastDrive2026$")
ENV_LABEL = os.getenv("FASTDRIVE_ENV_LABEL", "FastDrive")
SECRET = os.getenv("FASTDRIVE_SECRET", secrets.token_hex(32))
PORT = int(os.getenv("FASTDRIVE_PORT", "5012"))

app, rt = fast_app(live=False, pico=False, secret_key=SECRET, hdrs=[Style(LAYOUT_CSS)])


def _user(session):
    return session.get("user")


def _thread(session):
    if "thread" not in session:
        session["thread"] = uuid.uuid4().hex
    return session["thread"]


def _guard(session, active, builder):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    content = builder() if callable(builder) else builder
    if not isinstance(content, tuple):
        content = (content,)
    return page(active, ENV_LABEL, _user(session), _thread(session), *content)


def _login_card(error="", email=""):
    return Title("FastDrive — Sign in"), Style(LAYOUT_CSS), Div(
        Form(H1("FastDrive"), P("Sign in to your files"),
             Input(name="email", type="email", placeholder="Email", value=email, required=True),
             Input(name="password", type="password", placeholder="Password", required=True),
             P(error, cls="error") if error else None,
             Button("Sign in", cls="btn primary", type="submit"),
             P(NotStr("Demo: <code>admin@fastdrive.example</code> / <code>FastDrive2026$</code>"), cls="hint"),
             method="post", action="/login", cls="login-card"), cls="login-wrap")


@rt("/login")
def get(session):
    if _user(session):
        return RedirectResponse("/", status_code=303)
    return _login_card()


@rt("/login")
def post(session, email: str = "", password: str = ""):
    if email.strip().lower() == VALID_EMAIL.lower() and password == VALID_PASSWORD:
        session["user"] = email.strip().lower()
        return RedirectResponse("/", status_code=303)
    return _login_card("Invalid email or password.", email)


@rt("/logout")
def get(session):
    session.pop("user", None)
    return RedirectResponse("/login", status_code=303)


@rt("/")
def get(session, q: str = ""):
    return _guard(session, "drive", lambda: views.folder_view(None, q))


@rt("/folder/{fid}")
def get(session, fid: int):
    return _guard(session, "drive", lambda: views.folder_view(fid))


@rt("/e/{eid}")
def get(session, eid: int):
    return _guard(session, "drive", lambda: views.entity_view(eid))


@rt("/e/{eid}/rename")
def post(session, eid: int, name: str = ""):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    db.rename_entity(eid, name)
    return Response(headers={"HX-Redirect": f"/e/{eid}"})


@rt("/e/{eid}/trash")
def post(session, eid: int):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    e = db.entity(eid)
    db.trash_entity(eid)
    dest = f"/folder/{e['parent_id']}" if e and e["parent_id"] else "/"
    return Response(headers={"HX-Redirect": dest})


@rt("/e/{eid}/restore")
def post(session, eid: int):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    db.restore_entity(eid)
    return Response(headers={"HX-Redirect": "/trash"})


@rt("/e/{eid}/delete")
def post(session, eid: int):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    db.delete_forever(eid)
    return Response(headers={"HX-Redirect": "/trash"})


@rt("/shared")
def get(session):
    return _guard(session, "shared", views.shared_view)


@rt("/starred")
def get(session):
    return _guard(session, "starred", views.starred_view)


@rt("/recent")
def get(session):
    return _guard(session, "recent", views.recent_view)


@rt("/trash")
def get(session):
    return _guard(session, "trash", views.trash_view)


@rt("/upload")
def get(session):
    return _guard(session, "drive", lambda: views.upload_view())


@rt("/upload")
def post(session, name: str = "", kind: str = ""):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    name = (name or "Untitled.doc").strip()
    kind = (kind or "doc").strip().lower()
    if kind not in db.FILE_KINDS:
        kind = "doc"
    import random
    with db.cursor() as conn:
        conn.execute("""INSERT INTO entities(name,kind,parent_id,owner,size_bytes,modified)
                        VALUES (?,?,NULL,?,?,datetime('now'))""",
                     (name, kind, db.ME, random.randint(20000, 5_000_000)))
        eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO activity(entity_id,actor,action,created) VALUES (?,?,?,datetime('now'))",
                     (eid, db.ME, "uploaded"))
    return _guard(session, "drive", lambda: views.upload_view(done=True))


@rt("/ai")
def get(session):
    body = (views._title("AI Assistant", "Chat lives in the right rail. Ask in plain English or use slash-commands."),
            Div(NotStr(
                "<div class='card'><h3>What you can ask</h3><ul style='line-height:1.8;'>"
                "<li>“What did I work on recently?”</li><li>“Find all finance spreadsheets.”</li>"
                "<li>“How much storage am I using, and what's taking the most?”</li></ul>"
                "<p style='color:var(--text-mute)'>Slash-commands (no API key): "
                "<code>/recent</code> <code>/find &lt;text&gt;</code> <code>/storage</code> <code>/shared</code></p></div>")))
    return _guard(session, "ai", body)


@rt("/guide")
def get(session):
    body = (views._title("User Guide", "How to drive FastDrive"), Div(NotStr("""
<div class='card'><h3>My Drive</h3><p>Browse folders and files as tiles, with breadcrumbs. Search across all files
from the bar. Click a folder to open it, a file to see its details.</p></div>
<div class='card'><h3>File detail</h3><p>Type, size, owner, location, who it's shared with (Viewer/Editor),
and an activity history.</p></div>
<div class='card'><h3>Shared / Starred / Recent / Trash</h3><p>Quick views into the parts of your drive that matter.</p></div>
<div class='card'><h3>Upload</h3><p>Add a file (demo — metadata only) to My Drive.</p></div>
<div class='card'><h3>AI Assistant</h3><p>The right rail chats over a live snapshot of your drive. Set <code>MODEL_PROVIDER</code>
+ a key in <code>.env</code> for free-form chat; slash-commands always work.</p></div>""")))
    return _guard(session, "guide", body)


@rt("/chat/new")
def get(session):
    session["thread"] = uuid.uuid4().hex
    return P("Ask about your files — or use /recent /find /storage /help.", cls="chat-empty-hint")


@rt("/chat/stream")
async def post(session, message: str = "", thread_id: str = ""):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    message = (message or "").strip()
    if not message:
        return Response("No message", status_code=400)
    tid = thread_id or _thread(session)

    async def gen():
        with db.cursor() as conn:
            conn.execute("INSERT INTO chat_messages(thread_id,role,content,created) VALUES(?,?,?,datetime('now'))",
                         (tid, "user", message))
        full = []
        async for chunk in ai.stream_chat(message):
            if chunk.startswith("data: "):
                try:
                    tok = json.loads(chunk[6:]).get("token")
                    if tok:
                        full.append(tok)
                except Exception:
                    pass
            yield chunk
        with db.cursor() as conn:
            conn.execute("INSERT INTO chat_messages(thread_id,role,content,created) VALUES(?,?,?,datetime('now'))",
                         (tid, "assistant", "".join(full)))

    return StreamingResponse(gen(), media_type="text/event-stream")


def _ensure_db():
    if not db.db_exists():
        logger.info("No database found — seeding synthetic drive…")
        import seed
        seed.build()


_ensure_db()

if __name__ == "__main__":
    logger.info("FastDrive on http://localhost:%s  (login %s)", PORT, VALID_EMAIL)
    serve(port=PORT, reload=os.getenv("FASTDRIVE_RELOAD", "0") == "1")
