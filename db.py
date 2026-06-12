"""FastDrive data layer — SQLite, a document-management model from Frappe Drive.

A single `entities` table is a file/folder tree (self-referential parent_id),
plus permission shares and an activity log. Files are synthetic metadata only —
no bytes on disk.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = os.getenv("FASTDRIVE_DB") or str(Path(__file__).parent / "fastdrive.sqlite")

ME = "you@fastdrive.example"
NOW = datetime(2026, 6, 12, 12, 0, 0)

FILE_KINDS = {
    "folder": ("📁", "Folder"), "doc": ("📄", "Document"), "sheet": ("📊", "Spreadsheet"),
    "slide": ("📽️", "Presentation"), "pdf": ("📕", "PDF"), "image": ("🖼️", "Image"),
    "video": ("🎬", "Video"), "audio": ("🎵", "Audio"), "zip": ("🗜️", "Archive"), "code": ("💻", "Code"),
}


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def cursor():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def db_exists() -> bool:
    p = Path(DB_PATH)
    return p.exists() and p.stat().st_size > 0


def rows(sql, params=()):
    with cursor() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(sql, params=()):
    with cursor() as conn:
        r = conn.execute(sql, params).fetchone()
        return dict(r) if r else None


def scalar(sql, params=()):
    with cursor() as conn:
        r = conn.execute(sql, params).fetchone()
        return r[0] if r else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL,          -- 'folder' or a file type
    parent_id     INTEGER REFERENCES entities(id),
    owner         TEXT,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    is_starred    INTEGER NOT NULL DEFAULT 0,
    in_trash      INTEGER NOT NULL DEFAULT 0,
    modified      TEXT
);
CREATE TABLE IF NOT EXISTS shares (
    id            INTEGER PRIMARY KEY,
    entity_id     INTEGER REFERENCES entities(id),
    shared_with   TEXT,
    role          TEXT NOT NULL DEFAULT 'Viewer'   -- Viewer | Editor
);
CREATE TABLE IF NOT EXISTS activity (
    id            INTEGER PRIMARY KEY,
    entity_id     INTEGER REFERENCES entities(id),
    actor         TEXT,
    action        TEXT,
    created       TEXT
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id            INTEGER PRIMARY KEY,
    thread_id     TEXT NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL,
    created       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ent_parent ON entities(parent_id);
CREATE INDEX IF NOT EXISTS idx_share_ent ON shares(entity_id);
"""


def init_schema():
    with cursor() as conn:
        conn.executescript(SCHEMA)


def icon(kind: str) -> str:
    return FILE_KINDS.get(kind, ("📄", "File"))[0]


def kind_label(kind: str) -> str:
    return FILE_KINDS.get(kind, ("📄", "File"))[1]


def fmt_size(b: int) -> str:
    if not b:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f} {unit}" if unit == "B" else f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


# --- reads ------------------------------------------------------------------

def children(parent_id):
    return rows("""SELECT * FROM entities WHERE in_trash=0 AND
                   (parent_id IS ? OR parent_id = ?)
                   ORDER BY (kind!='folder'), name""", (parent_id, parent_id))


def entity(eid):
    return one("SELECT * FROM entities WHERE id=?", (eid,))


def breadcrumbs(eid):
    crumbs = []
    cur = entity(eid) if eid else None
    while cur:
        crumbs.append(cur)
        cur = entity(cur["parent_id"]) if cur["parent_id"] else None
    return list(reversed(crumbs))


def folder_size(eid):
    """Recursive size of a folder."""
    total = 0
    stack = [eid]
    while stack:
        pid = stack.pop()
        for c in rows("SELECT id,kind,size_bytes FROM entities WHERE parent_id=? AND in_trash=0", (pid,)):
            if c["kind"] == "folder":
                stack.append(c["id"])
            else:
                total += c["size_bytes"]
    return total


def shares_for(eid):
    return rows("SELECT * FROM shares WHERE entity_id=?", (eid,))


def activity_for(eid):
    return rows("SELECT * FROM activity WHERE entity_id=? ORDER BY created DESC LIMIT 20", (eid,))


def stats():
    total = scalar("SELECT COALESCE(SUM(size_bytes),0) FROM entities WHERE in_trash=0") or 0
    return {
        "files": scalar("SELECT COUNT(*) FROM entities WHERE kind!='folder' AND in_trash=0") or 0,
        "folders": scalar("SELECT COUNT(*) FROM entities WHERE kind='folder' AND in_trash=0") or 0,
        "used": total,
        "quota": 15 * 1024 ** 3,
        "shared": scalar("SELECT COUNT(DISTINCT entity_id) FROM shares") or 0,
        "starred": scalar("SELECT COUNT(*) FROM entities WHERE is_starred=1 AND in_trash=0") or 0,
        "trash": scalar("SELECT COUNT(*) FROM entities WHERE in_trash=1") or 0,
    }


# --- file operations (transactional) ----------------------------------------

def _log_activity(eid, action, actor=None):
    with cursor() as conn:
        actor = actor or ME
        conn.execute("INSERT INTO activity(entity_id,actor,action,created) VALUES(?,?,?,datetime('now'))",
                     (eid, actor, action))


def rename_entity(eid: int, name: str):
    name = (name or "").strip()
    if not name:
        return
    with cursor() as conn:
        conn.execute("UPDATE entities SET name=?, modified=datetime('now') WHERE id=?", (name, eid))
    _log_activity(eid, "renamed")


def trash_entity(eid: int):
    """Soft-delete: move the entity (and, if a folder, its descendants) to trash."""
    ids = _descendants(eid)
    with cursor() as conn:
        qmarks = ",".join("?" * len(ids))
        conn.execute(f"UPDATE entities SET in_trash=1 WHERE id IN ({qmarks})", tuple(ids))
    _log_activity(eid, "moved to trash")


def restore_entity(eid: int):
    ids = _descendants(eid)
    with cursor() as conn:
        qmarks = ",".join("?" * len(ids))
        conn.execute(f"UPDATE entities SET in_trash=0 WHERE id IN ({qmarks})", tuple(ids))
    _log_activity(eid, "restored")


def delete_forever(eid: int):
    ids = _descendants(eid)
    with cursor() as conn:
        qmarks = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM shares WHERE entity_id IN ({qmarks})", tuple(ids))
        conn.execute(f"DELETE FROM activity WHERE entity_id IN ({qmarks})", tuple(ids))
        conn.execute(f"DELETE FROM entities WHERE id IN ({qmarks})", tuple(ids))


def _descendants(eid: int) -> list[int]:
    """eid plus all descendant ids (for folder operations)."""
    ids, stack = [eid], [eid]
    while stack:
        pid = stack.pop()
        for r in rows("SELECT id FROM entities WHERE parent_id=?", (pid,)):
            ids.append(r["id"])
            stack.append(r["id"])
    return ids
