# Skills

Capability reference for FastDrive + the shared **Frappe → FastHTML migration
playbook** (same recipe across `fasthtml-oss-migrations`; see `FastCRM/SKILLS.md`).

---

## Part 1 — FastDrive capabilities

**Entry:** `python web_app.py` → http://localhost:5012
(login `admin@fastdrive.example` / `FastDrive2026$`).

### Pages

| View | Route | What it shows |
|---|---|---|
| My Drive | `/`, `/folder/{id}` | tile browser with breadcrumbs; `?q=` searches all |
| File detail | `/e/{id}` | type/size/owner, shares, activity |
| Shared / Starred / Recent / Trash | `/shared` `/starred` `/recent` `/trash` | filtered table views |
| Upload | `/upload` | add a file (metadata only) |
| AI Assistant | `/ai` | file chat (right rail) |

### Data model (`db.py`)

One self-referential `entities` table (folders + files differ by `kind`), plus
`shares` and `activity`. Helpers: `children()`, `breadcrumbs()`,
`folder_size()` (recursive), `stats()`. Rebuild with `python seed.py`.

### AI (`web/ai.py`)

Grounded chat over `snapshot()` (counts, storage, recent files). Slash-commands
(no key): `/recent`, `/find <text>`, `/storage`, `/shared`.

---

## Part 2 — Frappe → FastHTML migration playbook

1. **Mine the schema** — `python scripts/frappe_doctype_to_schema.py /tmp/frappe-drive`.
2. **Model the tree** — Frappe Drive's `Drive Entity` is a self-referential
   tree; one table with `parent_id` + a `kind` column is the whole filesystem.
3. **FastHTML shell** — `fast_app(pico=False, hdrs=[Style(CSS)])`; `page()`
   wrapper (here it also computes live storage stats for the sidebar bar).
4. **HTMX over JS** — tiles are plain links; breadcrumbs are server-rendered;
   the storage bar is pure CSS width.
5. **Synthetic data** — a nested dict → recursive insert; fixed RNG seed; self-seed.
6. **LLM, key-optional** — reuse `_provider_stream`; slash-commands work with no key.
7. **Capture the demo** — Playwright MCP → frames → `build_demo_gif.sh`.
8. **Ship deploy paths** — `.env.sample`, `Dockerfile`, `docker-compose.yml`.

### Reusable assets

| File | Reuse |
|---|---|
| `scripts/frappe_doctype_to_schema.py` | DocType JSON → SQLite DDL |
| `scripts/build_demo_gif.sh` | frames → demo GIF |
| `db.py` tree helpers | self-referential tree: `children`/`breadcrumbs`/`folder_size` |
| `web/layout.py` | 3-pane shell + CSS tokens + SSE chat JS |
