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
    actions = Div(
        Form(Input(name="name", value=e["name"], cls="rename-inp"),
             Button("Rename", cls="btn", type="submit"),
             **{"hx-post": f"/e/{eid}/rename"}, cls="inline-form"),
        Button("🗑 Delete", cls="btn danger", **{"hx-post": f"/e/{eid}/trash"}),
        cls="file-actions")

    info = Div(Div(H3("Details"), cls="card-header"),
               Div(Span("Type", cls="k"), Span(db.kind_label(e["kind"])),
                   Span("Size", cls="k"), Span(db.fmt_size(e["size_bytes"])),
                   Span("Owner", cls="k"), Span(e["owner"]),
                   Span("Location", cls="k"), Span(parent["name"] if parent else "My Drive"),
                   Span("Modified", cls="k"), Span(_when(e["modified"])),
                   Span("Starred", cls="k"), Span("Yes" if e["is_starred"] else "No"),
                   cls="kv"), cls="card")

    return Div(
        _title(e["name"], db.kind_label(e["kind"]), back),
        actions,
        Div(Div(Div(db.icon(e["kind"]), cls="preview"), info,
                Div(Div(H3("Activity"), cls="card-header"),
                    Ul(*[Li(Div(Strong(a["actor"]), " ", a["action"]), Div(_when(a["created"]), cls="when"))
                         for a in acts] or [Li("No activity.")], cls="timeline"), cls="card")),
            Div(share_panel(eid)), cls="detail-grid"))


def _role_select(name, current, **attrs):
    opts = "".join(f'<option value="{r}"{" selected" if r == current else ""}>{r}</option>'
                   for r in db.SHARE_ROLES)
    attr_str = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return NotStr(f'<select name="{name}" {attr_str} '
                  f'style="padding:5px 8px;border:1px solid var(--border);border-radius:7px;font-size:12px;">{opts}</select>')


def share_panel(eid):
    """The share dialog body: people with access, an add-person form, and a
    public-link section. Swapped in place (id=share-panel) on every change."""
    e = db.entity(eid)
    shares = db.shares_for(eid)
    link = db.public_link(eid)

    people_rows = []
    for s in shares:
        people_rows.append(Tr(
            Td(s["shared_with"]),
            Td(_role_select("role", s["role"],
                            hx_post=f"/e/{eid}/share/{s['id']}/role",
                            hx_target="#share-panel", hx_swap="innerHTML", hx_trigger="change")),
            Td(Button("✕", cls="btn sm danger", title="Remove access",
                      **{"hx-post": f"/e/{eid}/share/{s['id']}/remove",
                         "hx-target": "#share-panel", "hx-swap": "innerHTML"}))))
    people_tbl = Table(Tbody(*people_rows) if people_rows
                       else Tbody(Tr(Td("No one yet — add a person below.", colspan="3",
                                        style="color:var(--text-mute);"))), cls="tbl")

    add_form = Form(
        Input(name="email", type="email", placeholder="name@example.com", required=True,
              style="flex:1;min-width:160px;padding:7px 10px;border:1px solid var(--border);border-radius:8px;"),
        _role_select("role", "Viewer"),
        Button("Share", cls="btn primary", type="submit"),
        **{"hx-post": f"/e/{eid}/share", "hx-target": "#share-panel", "hx-swap": "innerHTML"},
        style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px;")

    # public link section
    if link:
        url = f"/public/{link['token']}"
        link_bits = [
            Div(Span("🌐 Anyone with the link", style="font-weight:600;"),
                _role_select("role", link["role"],
                             hx_post=f"/e/{eid}/link/role", hx_target="#share-panel",
                             hx_swap="innerHTML", hx_trigger="change"),
                style="display:flex;gap:8px;align-items:center;justify-content:space-between;"),
            Div(Input(value=url, readonly=True, id="public-link-input",
                      style="flex:1;min-width:160px;padding:7px 10px;border:1px solid var(--border);border-radius:8px;font-size:12px;background:var(--surface-2);"),
                Button("Copy", cls="btn sm", type="button",
                       onclick="var i=document.getElementById('public-link-input');i.select();"
                               "navigator.clipboard&&navigator.clipboard.writeText(location.origin+i.value);"
                               "this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1200);"),
                style="display:flex;gap:8px;align-items:center;margin-top:8px;"),
            Button("Disable link", cls="btn sm danger",
                   **{"hx-post": f"/e/{eid}/link/disable", "hx-target": "#share-panel", "hx-swap": "innerHTML"},
                   style="margin-top:8px;"),
        ]
    else:
        link_bits = [
            P("This file is private. Create a link anyone can open.", cls="sub"),
            Button("🔗 Create public link", cls="btn",
                   **{"hx-post": f"/e/{eid}/link", "hx-target": "#share-panel", "hx-swap": "innerHTML"}),
        ]

    return Div(
        Div(Div(H3(f"People with access ({len(shares)})"), cls="card-header"),
            people_tbl, add_form, cls="card"),
        Div(Div(H3("Public link"), cls="card-header"), *link_bits, cls="card"),
        id="share-panel")


# ---------- public (unauthenticated) link view ------------------------------

def public_view(token):
    e = db.entity_by_token(token)
    if not e:
        return Div(
            Div(Div("🔒", style="font-size:48px;"),
                H1("Link unavailable"),
                P("This link has been disabled or the file no longer exists.", cls="sub"),
                style="text-align:center;padding:60px 20px;"),
            cls="public-wrap")
    is_folder = e["kind"] == "folder"
    size = db.folder_size(e["id"]) if is_folder else e["size_bytes"]
    body = Div(
        Div("Shared via FastDrive", cls="public-badge"),
        Div(db.icon(e["kind"]), cls="preview", style="font-size:64px;"),
        H1(e["name"]),
        Div(Span(db.kind_label(e["kind"])), Span(" · "), Span(db.fmt_size(size)),
            Span(" · "), Span(f"{e['public_role']} access"), cls="sub",
            style="margin-bottom:8px;"),
        P(f"Shared by {e['owner']}.", cls="sub"),
        (P("📁 Folder contents are visible to people you invite directly.", cls="sub")
         if is_folder else
         P("This is a public preview. The file itself is synthetic demo metadata.", cls="sub")),
        cls="card", style="max-width:560px;margin:40px auto;text-align:center;")
    return Div(body, cls="public-wrap")


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
    rows_ = [Tr(Td(Span(db.icon(e["kind"]) + " "), e["name"]),
                Td(db.kind_label(e["kind"])),
                Td(db.fmt_size(e["size_bytes"]) if e["kind"] != "folder" else "—", cls="num"),
                Td(Div(Button("♻ Restore", cls="btn sm", **{"hx-post": f"/e/{e['id']}/restore"}),
                       Button("✕ Delete forever", cls="btn sm danger", **{"hx-post": f"/e/{e['id']}/delete"}),
                       style="display:flex;gap:6px;")))
             for e in ents]
    tbl = Table(Thead(Tr(Th("Name"), Th("Type"), Th("Size", cls="num"), Th("Action"))),
                Tbody(*rows_), cls="tbl")
    return head, Div(tbl, cls="card")


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
