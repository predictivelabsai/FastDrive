"""FastDrive AI — grounded chat + slash-commands over the file tree."""
from __future__ import annotations

import json
import os

import db

PROVIDER = os.getenv("MODEL_PROVIDER", "xai")
MODEL = os.getenv("MODEL_NAME", "grok-4-1-fast-reasoning")


def snapshot() -> str:
    st = db.stats()
    recent = db.rows("SELECT name, kind FROM entities WHERE kind!='folder' AND in_trash=0 ORDER BY modified DESC LIMIT 12")
    by_kind = db.rows("SELECT kind, COUNT(*) n FROM entities WHERE kind!='folder' AND in_trash=0 GROUP BY kind ORDER BY n DESC")
    lines = [
        "DRIVE SNAPSHOT (synthetic):",
        f"- {st['files']} files in {st['folders']} folders. Using {db.fmt_size(st['used'])} of {db.fmt_size(st['quota'])}. "
        f"{st['shared']} shared, {st['starred']} starred, {st['trash']} in trash.",
        "Files by type: " + ", ".join(f"{db.kind_label(k['kind'])} {k['n']}" for k in by_kind),
        "Recent files: " + ", ".join(r["name"] for r in recent),
    ]
    return "\n".join(lines)


SYSTEM_PROMPT = """You are the FastDrive assistant, embedded in a file-management app.
Help the user find, organise and understand their files. Be concise; use Markdown when it helps.
All files are synthetic demo data — never claim they're real. Base answers on the DRIVE SNAPSHOT
below; if a file isn't listed, suggest using search."""


def _table(headers, rows_):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows_:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def handle_command(text):
    if not text.startswith("/"):
        return None
    parts = text[1:].split()
    cmd = parts[0].lower() if parts else ""
    arg = " ".join(parts[1:])
    if cmd in ("help", "?"):
        return ("**FastDrive shortcuts**\n\n- `/recent` — recently modified files\n- `/find <text>` — search files\n"
                "- `/storage` — usage breakdown\n- `/shared` — files shared with you\n\nOr ask in plain English.")
    if cmd == "recent":
        r = db.rows("SELECT name, modified FROM entities WHERE kind!='folder' AND in_trash=0 ORDER BY modified DESC LIMIT 12")
        return "**Recent files**\n\n" + _table(["File", "Modified"], [[x["name"], x["modified"][:10]] for x in r])
    if cmd == "find":
        if not arg:
            return "Usage: `/find <text>`"
        r = db.rows("SELECT name, kind FROM entities WHERE name LIKE ? AND in_trash=0 LIMIT 15", (f"%{arg}%",))
        if not r:
            return f"No files matching '{arg}'."
        return f"**Results for '{arg}'**\n\n" + _table(["File", "Type"], [[x["name"], db.kind_label(x["kind"])] for x in r])
    if cmd == "storage":
        st = db.stats()
        r = db.rows("SELECT kind, COUNT(*) n, SUM(size_bytes) s FROM entities WHERE kind!='folder' AND in_trash=0 GROUP BY kind ORDER BY s DESC")
        return (f"**Storage:** {db.fmt_size(st['used'])} of {db.fmt_size(st['quota'])}\n\n" +
                _table(["Type", "Files", "Size"], [[db.kind_label(x["kind"]), x["n"], db.fmt_size(x["s"])] for x in r]))
    if cmd == "shared":
        r = db.rows("""SELECT DISTINCT e.name, COUNT(s.id) n FROM entities e JOIN shares s ON s.entity_id=e.id
                       GROUP BY e.id ORDER BY e.modified DESC LIMIT 15""")
        return "**Shared items**\n\n" + _table(["File", "Shared with"], [[x["name"], x["n"]] for x in r])
    return f"Unknown command `/{cmd}`. Try `/help`."


async def stream_chat(message):
    cmd = handle_command(message)
    if cmd is not None:
        yield f"data: {json.dumps({'token': cmd})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
        return
    system = SYSTEM_PROMPT + "\n\n" + snapshot()
    try:
        async for tok in _provider_stream(system, message):
            yield f"data: {json.dumps({'token': tok})}\n\n"
    except Exception as e:  # noqa: BLE001
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


async def _provider_stream(system, message):
    import httpx
    provider, model = PROVIDER, MODEL
    if provider in ("xai", "openai"):
        url = "https://api.x.ai/v1/chat/completions" if provider == "xai" else "https://api.openai.com/v1/chat/completions"
        key = os.getenv("XAI_API_KEY" if provider == "xai" else "OPENAI_API_KEY", "")
        if not key:
            yield _no_key(provider); return
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", url, headers={"Authorization": f"Bearer {key}"},
                                     json={"model": model, "stream": True,
                                           "messages": [{"role": "system", "content": system},
                                                        {"role": "user", "content": message}]}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            tok = json.loads(line[6:])["choices"][0]["delta"].get("content", "")
                            if tok: yield tok
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
    elif provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            yield _no_key(provider); return
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", "https://api.anthropic.com/v1/messages",
                                     headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                                     json={"model": model, "max_tokens": 1500, "stream": True, "system": system,
                                           "messages": [{"role": "user", "content": message}]}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            ev = json.loads(line[6:])
                            if ev.get("type") == "content_block_delta":
                                tok = ev.get("delta", {}).get("text", "")
                                if tok: yield tok
                        except json.JSONDecodeError:
                            pass
    elif provider == "google":
        key = os.getenv("GOOGLE_API_KEY", "")
        if not key:
            yield _no_key(provider); return
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={key}"
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", url, json={"system_instruction": {"parts": [{"text": system}]},
                                                        "contents": [{"role": "user", "parts": [{"text": message}]}]}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            tok = json.loads(line[6:])["candidates"][0]["content"]["parts"][0].get("text", "")
                            if tok: yield tok
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
    else:
        yield "No LLM provider configured. Slash-commands like /recent work without a key."


def _no_key(provider):
    env = {"xai": "XAI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_API_KEY"}[provider]
    return (f"⚠ No **{env}** set, so free-form chat is disabled. Add it to `.env` and restart. "
            "Slash-commands (`/recent`, `/find`, `/storage`) work without any key.")
