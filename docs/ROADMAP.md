# FastDrive Roadmap — Frappe Drive feature comparison

FastDrive ports the core of [Frappe Drive](https://github.com/frappe/drive)
(~12 doctypes) to a FastHTML demonstrator.

## Implemented ✅

| Capability | Upstream doctype(s) | FastDrive |
|---|---|---|
| Files & folders | `Drive Entity` (tree) | `entities` (self-referential) |
| Folder navigation | parent/child | breadcrumbs + tile browser |
| Sharing | `Drive Permission` | `shares` (Viewer/Editor) + "Shared with me" |
| Starred | `Drive Favourite` | `is_starred` + Starred view |
| Activity log | `Drive Entity Activity Log` | `activity` per entity |
| Trash | soft-delete | `in_trash` + Trash view |
| Storage usage | quota/settings | sidebar storage bar |
| Upload | file upload | metadata-only upload form |
| **AI assistant** | *(not upstream)* | grounded file Q&A |

## Near-term roadmap 🔜

1. **Real file storage** — currently metadata only; store/serve actual bytes from
   a mounted volume, with previews for images/PDF/text.
2. **Move / rename / delete** — drag-to-folder, rename inline, soft-delete to
   Trash and restore (Trash view exists; actions are read-only).
3. **Share dialog** — add/remove people and change role from the UI
   (`Drive Permission` write path), plus public share links.
4. **In-browser docs** — Frappe Drive has a built-in document editor; add a
   simple markdown/rich-text editor for `doc` entities.
5. **Teams** — `Drive Team`/`Drive Team Member` (team drives separate from My Drive).
6. **Notifications** — `Drive Notification` (someone shared / commented).

## Later / out-of-scope 🗓️

- **Real-time collaborative editing** of documents (needs an OT/CRDT layer —
  see FastSheets' note).
- **Versioning / file history** with diffs.
- **Full-text search** inside file contents (FastDrive searches names).
- **Desktop sync client**, **WebDAV**, external storage backends
  (`Drive Disk Settings`).

## Design notes

The whole drive is one self-referential `entities` table; folders and files
differ only by `kind`. Recursive folder size (`db.folder_size`) and breadcrumbs
(`db.breadcrumbs`) walk that tree. The natural next step is wiring **real bytes**
behind the metadata so previews and downloads work — the data model is already
shaped for it.
