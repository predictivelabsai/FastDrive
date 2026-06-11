"""Center-pane renderers for FastDrive."""
from __future__ import annotations

from datetime import datetime

from fasthtml.common import (
    Div, H1, H3, P, Span, A, Table, Thead, Tbody, Tr, Th, Td, Form, Input, Button, NotStr, Strong, Ul, Li,
)

import db


def _when(ts):
    if not ts:
        return "—"
    try:
        dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts[:10]
    days = (db.NOW - dt).days
    if days == 0:
        return dt.strftime("Today %H:%M")
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return dt.strftime("%d %b %Y")


def _title(title, sub="", *actions):
    return Div(Div(H1(title), P(sub, cls="sub") if sub else None),
               Div(*actions) if actions else None, cls="page-title")


def _pill(text, kind=""):
    return Span(text, cls="pill " + (kind or str(text)).lower())


def _tile(e):
    is_folder = e["kind"] == "folder"
    size = db.folder_size(e["id"]) if is_folder else e["size_bytes"]
    return A(
        Span(NotStr("&#9733;"), cls="star") if e["is_starred"] else None,
        Div(db.icon(e["kind"]), cls="ic"),
        Div(e["name"], cls="nm", title=e["name"]),
        Div(f"{db.fmt_size(size)} · {_when(e['modified'])}" if not is_folder else _when(e["modified"]), cls="meta"),
        href=f"/folder/{e['id']}" if is_folder else f"/e/{e['id']}", cls="tile")


# ---------- folder browser --------------------------------------------------

def folder_view(folder_id=None, q=""):
    crumbs = db.breadcrumbs(folder_id) if folder_id else []
    crumb_els = [A("My Drive", href="/")]
    for c in crumbs:
        crumb_els += [Span("›", cls="sep"), A(c["name"], href=f"/folder/{c['id']}")]
    crumbnav = Div(*crumb_els, cls="crumbs")

    if q:
        ents = db.rows("SELECT * FROM entities WHERE in_trash=0 AND name LIKE ? ORDER BY (kind!='folder'), name", (f"%{q}%",))
    else:
        ents = db.children(folder_id)
    title = crumbs[-1]["name"] if crumbs else "My Drive"
    search = Form(Input(type="search", name="q", value=q, placeholder="Search all files…"),
                  cls="toolbar", method="get", action="/")
    if not ents:
        return (_title(title), crumbnav if not q else None, search,
                Div(P("This folder is empty." if not q else "No files match."), cls="empty"))
    return (_title(title, f"{len(ents)} items"), (crumbnav if not q else None), search,
            Div(*[_tile(e) for e in ents], cls="grid"))


# ---------- file detail -----------------------------------------------------

def entity_view(eid):
    e = db.entity(eid)
    if not e:
        return Div(P("Not found."), cls="empty")
    shares = db.shares_for(eid)
    acts = db.activity_for(eid)
    parent = db.entity(e["parent_id"]) if e["parent_id"] else None
    back = A("← Back", href=f"/folder/{e['parent_id']}" if e["parent_id"] else "/", cls="btn")

    info = Div(Div(H3("Details"), cls="card-header"),
               Div(Span("Type", cls="k"), Span(db.kind_label(e["kind"])),
                   Span("Size", cls="k"), Span(db.fmt_size(e["size_bytes"])),
                   Span("Owner", cls="k"), Span(e["owner"]),
                   Span("Location", cls="k"), Span(parent["name"] if parent else "My Drive"),
                   Span("Modified", cls="k"), Span(_when(e["modified"])),
                   Span("Starred", cls="k"), Span("Yes" if e["is_starred"] else "No"),
                   cls="kv"), cls="card")

    share_card = Div(Div(H3(f"Shared with ({len(shares)})"), cls="card-header"),
                     Table(Tbody(*[Tr(Td(s["shared_with"]), Td(_pill(s["role"])))
                                   for s in shares] or [Tr(Td("Not shared.", colspan="2"))]), cls="tbl"),
                     cls="card")
    acts_card = Div(Div(H3("Activity"), cls="card-header"),
                    Ul(*[Li(Div(Strong(a["actor"]), " ", a["action"]),
                            Div(_when(a["created"]), cls="when")) for a in acts] or [Li("No activity.")],
                       cls="timeline"), cls="card")
    return Div(
        _title(e["name"], db.kind_label(e["kind"]), back),
        Div(Div(Div(db.icon(e["kind"]), cls="preview"), info,
                Div(Div(H3("Activity"), cls="card-header"),
                    Ul(*[Li(Div(Strong(a["actor"]), " ", a["action"]), Div(_when(a["created"]), cls="when"))
                         for a in acts] or [Li("No activity.")], cls="timeline"), cls="card")),
            Div(share_card), cls="detail-grid"))


# ---------- filtered views --------------------------------------------------

def _table_view(title, sub, ents):
    head = _title(title, sub)
    rows_ = [Tr(Td(Span(db.icon(e["kind"]) + " "), A(e["name"], href=f"/folder/{e['id']}" if e["kind"] == "folder" else f"/e/{e['id']}")),
                Td(e.get("owner", "—")), Td(db.kind_label(e["kind"])),
                Td(db.fmt_size(e["size_bytes"]) if e["kind"] != "folder" else "—", cls="num"),
                Td(_when(e["modified"]))) for e in ents]
    tbl = Table(Thead(Tr(Th("Name"), Th("Owner"), Th("Type"), Th("Size", cls="num"), Th("Modified"))),
                Tbody(*rows_) if rows_ else Tbody(Tr(Td("Nothing here.", colspan="5"))), cls="tbl")
    return head, Div(tbl, cls="card")


def shared_view():
    ents = db.rows("""SELECT DISTINCT e.* FROM entities e JOIN shares s ON s.entity_id=e.id
                      WHERE e.in_trash=0 ORDER BY e.modified DESC""")
    return _table_view("Shared with me", f"{len(ents)} items", ents)


def starred_view():
    ents = db.rows("SELECT * FROM entities WHERE is_starred=1 AND in_trash=0 ORDER BY modified DESC")
    return _table_view("Starred", f"{len(ents)} items", ents)


def recent_view():
    ents = db.rows("SELECT * FROM entities WHERE kind!='folder' AND in_trash=0 ORDER BY modified DESC LIMIT 25")
    return _table_view("Recent", "Recently modified files", ents)


def trash_view():
    ents = db.rows("SELECT * FROM entities WHERE in_trash=1 ORDER BY modified DESC")
    head = _title("Trash", f"{len(ents)} items")
    if not ents:
        return head, Div(P("Trash is empty."), cls="empty")
    return _table_view("Trash", f"{len(ents)} items", ents)


def upload_view(done=False):
    notice = Div("✓ Uploaded — your file is now in My Drive.", cls="notice") if done else None
    return (_title("Upload", "Add a file to your drive (demo — metadata only)."),
            notice,
            Div(Form(
                Div(NotStr("Drag &amp; drop is decorative in this demo. Pick a name and type below."),
                    style="margin-bottom:12px;color:var(--text-mute);"),
                Input(name="name", placeholder="File name (e.g. Notes.doc)", style="width:100%;padding:10px;border:1px solid var(--border);border-radius:8px;margin-bottom:10px;"),
                Input(name="kind", placeholder="Type: doc / sheet / slide / pdf / image …", style="width:100%;padding:10px;border:1px solid var(--border);border-radius:8px;margin-bottom:10px;"),
                Div(Button("Upload", cls="btn primary", type="submit"), A("Cancel", href="/", cls="btn")),
                method="post", action="/upload"), cls="card", style="max-width:520px;"))
