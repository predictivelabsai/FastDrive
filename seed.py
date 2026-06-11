"""Generate a synthetic FastDrive tree (deterministic, no real files)."""
from __future__ import annotations

import random
from datetime import timedelta

import db

RNG = random.Random(20260612)
NOW = db.NOW
PEOPLE = ["alex@team.example", "sam@team.example", "jordan@team.example",
          "robin@team.example", "casey@team.example", "morgan@team.example"]

TREE = {
    "Documents": {
        "_files": [("Company Handbook.pdf", "pdf"), ("Q2 Board Pack.pdf", "pdf"),
                   ("Meeting Notes.doc", "doc"), ("Brand Guidelines.pdf", "pdf")],
        "Contracts": {"_files": [("MSA - Northwind.pdf", "pdf"), ("NDA Template.doc", "doc"),
                                 ("SOW - Apex.pdf", "pdf")]},
        "Policies": {"_files": [("Travel Policy.doc", "doc"), ("Security Policy.doc", "doc")]},
    },
    "Projects": {
        "Website Redesign": {"_files": [("Wireframes.fig", "image"), ("Copy Deck.doc", "doc"),
                                        ("Launch Plan.sheet", "sheet"), ("Hero Render.png", "image")]},
        "Mobile App": {"_files": [("Roadmap.sheet", "sheet"), ("API Spec.code", "code"),
                                  ("Demo.mp4", "video")]},
        "_files": [("Project Tracker.sheet", "sheet")],
    },
    "Finance": {
        "_files": [("Budget 2026.sheet", "sheet"), ("Invoices.zip", "zip"),
                   ("Forecast Model.sheet", "sheet"), ("Expenses Q1.sheet", "sheet")],
    },
    "Marketing": {
        "Campaigns": {"_files": [("Spring Launch.slide", "slide"), ("Ad Creatives.zip", "zip"),
                                 ("Webinar Deck.slide", "slide")]},
        "_files": [("Content Calendar.sheet", "sheet"), ("Logo Pack.zip", "zip"),
                   ("Promo Video.mp4", "video")],
    },
    "_files": [("Welcome.doc", "doc"), ("Team Photo.jpg", "image"), ("Onboarding.slide", "slide")],
}

SIZES = {"pdf": (200_000, 8_000_000), "doc": (30_000, 1_500_000), "sheet": (40_000, 3_000_000),
         "slide": (500_000, 25_000_000), "image": (200_000, 12_000_000), "video": (5_000_000, 400_000_000),
         "zip": (1_000_000, 80_000_000), "code": (2_000, 200_000), "audio": (1_000_000, 20_000_000)}


def _modified():
    return (NOW - timedelta(days=RNG.randint(0, 120), hours=RNG.randint(0, 23))).strftime("%Y-%m-%d %H:%M:%S")


def build():
    db.init_schema()
    with db.cursor() as conn:
        for t in ("chat_messages", "activity", "shares", "entities"):
            conn.execute(f"DELETE FROM {t}")

    created = []  # (id, kind)

    def insert(name, kind, parent_id):
        with db.cursor() as conn:
            size = 0
            if kind != "folder":
                lo, hi = SIZES.get(kind, (10_000, 1_000_000))
                size = RNG.randint(lo, hi)
            owner = db.ME if RNG.random() < 0.7 else RNG.choice(PEOPLE)
            conn.execute(
                """INSERT INTO entities(name,kind,parent_id,owner,size_bytes,is_starred,modified)
                   VALUES (?,?,?,?,?,?,?)""",
                (name, kind, parent_id, owner, size, 1 if RNG.random() < 0.12 else 0, _modified()))
            eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        created.append((eid, kind, name, owner if 'owner' in dir() else db.ME))
        return eid

    def walk(node, parent_id):
        for name, child in node.items():
            if name == "_files":
                for fname, kind in child:
                    insert(fname, kind, parent_id)
            else:
                fid = insert(name, "folder", parent_id)
                walk(child, fid)

    walk(TREE, None)

    # shares + activity
    ents = db.rows("SELECT id,name,kind,owner FROM entities")
    with db.cursor() as conn:
        for e in ents:
            if RNG.random() < 0.3:
                for who in RNG.sample(PEOPLE, RNG.randint(1, 3)):
                    conn.execute("INSERT INTO shares(entity_id,shared_with,role) VALUES (?,?,?)",
                                 (e["id"], who, RNG.choice(["Viewer", "Viewer", "Editor"])))
            n_act = RNG.randint(1, 4)
            for _ in range(n_act):
                actor = e["owner"] if RNG.random() < 0.5 else RNG.choice(PEOPLE)
                action = RNG.choice(["created", "edited", "viewed", "shared", "renamed", "commented on"])
                conn.execute("INSERT INTO activity(entity_id,actor,action,created) VALUES (?,?,?,?)",
                             (e["id"], actor, action,
                              (NOW - timedelta(days=RNG.randint(0, 60), hours=RNG.randint(0, 23))).strftime("%Y-%m-%d %H:%M:%S")))

    print(f"FastDrive seeded → {db.DB_PATH}")
    print(f"  {len(ents)} entities ({sum(1 for e in ents if e['kind']=='folder')} folders)")


if __name__ == "__main__":
    build()
