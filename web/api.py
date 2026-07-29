"""FastDrive public reads and token-gated integration writes."""

import db

from .api_core import Resource, SQLiteBackend, create_sqlite_api

RESOURCES = (
    Resource("files", "entities", "Files and folders", "Drive entities including files and folders.", write_fields=("name", "kind", "parent_id", "owner", "size_bytes", "is_starred", "in_trash"), search_fields=("name", "kind", "owner")),
    Resource("shares", "shares", "Shares", "Role-based file and folder shares.", search_fields=("shared_with", "role")),
    Resource("public-links", "public_links", "Public links", "Public sharing links and their access roles.", search_fields=("token", "role"), primary_key="entity_id"),
    Resource("activity", "activity", "Activity", "Auditable file and sharing activity.", search_fields=("actor", "action")),
)

backend = SQLiteBackend(db.DB_PATH, RESOURCES, initialize=db.init_schema)
api = create_sqlite_api(
    product="FastDrive", version="1.0.0",
    description="Open integration access to FastDrive files, folders, shares, and activity.",
    base_url="https://drive.fastsme.com", backend=backend, resources=RESOURCES,
)
