#!/usr/bin/exec-suid -- /usr/bin/python3 -I

from __future__ import annotations

import datetime as dt
import os
import random
import sqlite3
import string
import uuid
from pathlib import Path
from random import randint

DB_PATH = "./conference.db"
MASTER_SECRET_PATH = Path("./jwt_master.secret")

RESET_SQL = """
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS review_invites;
DROP TABLE IF EXISTS papers;
DROP TABLE IF EXISTS config;
DROP TABLE IF EXISTS users;
"""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'author'
);

CREATE TABLE papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    author_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'under_review',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (author_id) REFERENCES users(id)
);

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    reviewer_id INTEGER NOT NULL,
    comments TEXT,
    rating INTEGER,
    FOREIGN KEY (paper_id) REFERENCES papers(id),
    FOREIGN KEY (reviewer_id) REFERENCES users(id)
);

CREATE TABLE review_invites (
    code TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    note TEXT,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    used_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (used_by) REFERENCES users(id)
);

CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

admin_password = "".join(random.choices(string.ascii_letters + string.digits, k=10))
# Generate random invite codes on each run
hidden_intake_code = f"rev-hidden-intake-{uuid.uuid4()}"
internal_probe_code = f"rev-internal-probe-{uuid.uuid4()}"


USERS = [
    (1, "admin", admin_password, "admin"),
    (None, "author_claire", "paperpower", "author"),
    (None, "author_dina", "ml4life", "author"),
]

PAPERS = [
    (
        "Oblivious Backchannels",
        "Measuring metadata leakage in double-blind review workflows.",
        "author_claire",
        "under_review",
    ),
    (
        "Reviewer-in-the-Middle",
        "How malicious reviewers can weaponize supplemental fetchers.",
        "author_dina",
        "needs_revision",
    ),
]

REVIEWS: list[tuple[str, str, str, int]] = []

REVIEW_INVITES = [
    (
        hidden_intake_code,
        "reviewer",
        "Unlisted program committee invite",
        "2025-12-31T23:59:59Z",
        0,
        None,
    ),
    (
        internal_probe_code,
        "reviewer",
        "Shadow pool invite",
        "2025-12-31T23:59:59Z",
        0,
        None,
    ),
    (
        "rev-internal-b4b4b4",
        "reviewer",
        "reviewer invite",
        "2023-01-01T00:00:00Z",
        0,
        None,
    ),
    (
        "rev-internal-a1b2c3",
        "reviewer",
        "reviewer invite",
        "2025-10-31T23:59:59Z",
        1,
        1,
    ),
]

CONFIG_ENTRIES = [
    ("banner_message", "All reviews must be completed by Dec 1."),
    ("jwt_secret", "jwt_secret_peer_review_sup3r_s3cret"),
    ("jwt_hint", "rotated_to_internal_service_only"),
    ("debug_mode", "false"),
]


def seed_data(conn: sqlite3.Connection) -> None:
    """Populate the database with default users, papers, invites, and config."""
    for user_id, username, password, role in USERS:
        if user_id is None:
            conn.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, password, role),
            )
        else:
            conn.execute(
                "INSERT INTO users (id, username, password, role) VALUES (?, ?, ?, ?)",
                (user_id, username, password, role),
            )

    user_map = {
        row["username"]: row["id"]
        for row in conn.execute("SELECT id, username FROM users")
    }

    for title, abstract, author_username, status in PAPERS:
        conn.execute(
            "INSERT INTO papers (title, abstract, author_id, status) VALUES (?, ?, ?, ?)",
            (title, abstract, user_map[author_username], status),
        )

    paper_map = {
        row["title"]: row["id"] for row in conn.execute("SELECT id, title FROM papers")
    }

    for paper_title, reviewer_username, comments, rating in REVIEWS:
        conn.execute(
            "INSERT INTO reviews (paper_id, reviewer_id, comments, rating) VALUES (?, ?, ?, ?)",
            (paper_map[paper_title], user_map[reviewer_username], comments, rating),
        )

    now = dt.datetime.utcnow().isoformat()
    for code, role, note, expires_at, used, used_by in REVIEW_INVITES:
        conn.execute(
            """
            INSERT INTO review_invites (code, role, note, expires_at, used, used_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (code, role, note, expires_at, used, used_by, now),
        )

    for key, value in CONFIG_ENTRIES:
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)",
            (key, value),
        )


def init_db(db_path: Path = DB_PATH) -> None:
    """Reset and seed the SQLite database with challenge fixtures."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(RESET_SQL)
    conn.executescript(SCHEMA_SQL)
    seed_data(conn)
    conn.commit()
    conn.close()
    with open(MASTER_SECRET_PATH, "w") as f:
        f.write(os.urandom(32).hex())


if __name__ == "__main__":
    print(f"[*] Initializing database at {DB_PATH}")
    init_db()
    print("[*] Schema reset and seeded with default data.")
