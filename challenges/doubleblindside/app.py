#!/usr/bin/exec-suid -- /usr/bin/python3 -I

from __future__ import annotations

import datetime as dt
import os
import sqlite3
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import jwt
import requests
from flask import (
    Flask,
    abort,
    current_app,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

DB_PATH = "/challenge/conference.db"
MASTER_SECRET_PATH = Path("/challenge/jwt_master.secret")
JWT_COOKIE_NAME = "session_token"
JWT_ALGORITHM = "HS256"
JWT_LIFETIME = dt.timedelta(hours=2)
FLAG_VALUE = open("/flag", "r").read().strip()
ROLE_ORDER = {"author": 1, "reviewer": 2, "admin": 3}


def _load_master_secret() -> str:
    """Load the JWT signing key from env/file; generate if missing."""
    env_secret = os.environ.get("JWT_MASTER_SECRET")
    if env_secret:
        return env_secret
    path = Path(os.environ.get("JWT_MASTER_SECRET_FILE", MASTER_SECRET_PATH))
    if path.exists():
        existing = path.read_text().strip()
        if existing:
            return existing
    secret = os.urandom(32).hex()
    try:
        path.write_text(secret)
    except OSError:
        # If the filesystem is read-only, keep the generated secret in memory only.
        pass
    return secret


def get_db() -> sqlite3.Connection:
    """Return a SQLite connection tied to the current request context."""
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_db(_: Optional[BaseException] = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _get_request_data() -> Dict[str, Any]:
    """Unify JSON/form payload parsing for simple endpoints."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    if request.form:
        return request.form.to_dict(flat=True)
    return {}


def _get_jwt_secret(conn: sqlite3.Connection) -> str:
    """Fetch the JWT secret used for signing."""
    return current_app.config["JWT_MASTER_SECRET"]


def _apply_invite_code(
    conn: sqlite3.Connection, code: str, user_id: int
) -> Dict[str, Any]:
    """Attempt to redeem a reviewer invite for the given user without committing."""
    invite = conn.execute(
        "SELECT code, role, used, expires_at FROM review_invites WHERE code = ?",
        (code,),
    ).fetchone()
    if not invite:
        return {"status": 404, "error": "invalid invite"}
    if invite["used"]:
        return {"status": 409, "error": "invite already redeemed"}
    expires_raw = invite["expires_at"]
    try:
        expires_at = dt.datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    except ValueError:
        expires_at = None
    now_utc = dt.datetime.now(dt.timezone.utc)
    if expires_at and now_utc > expires_at:
        return {"status": 410, "error": "invite no longer valid"}
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (invite["role"], user_id))
    conn.execute(
        "UPDATE review_invites SET used = 1, used_by = ? WHERE code = ?",
        (user_id, code),
    )
    return {"status": 200, "role": invite["role"]}


def _issue_token_response(user_row: sqlite3.Row, message: str) -> Any:
    """Create a JWT for the given user row and return a JSON response with cookie."""
    conn = get_db()
    token_payload = {
        "sub": user_row["id"],
        "username": user_row["username"],
        "role": user_row["role"],
        "iat": dt.datetime.utcnow(),
        "exp": dt.datetime.utcnow() + JWT_LIFETIME,
    }
    token = jwt.encode(token_payload, _get_jwt_secret(conn), algorithm=JWT_ALGORITHM)

    response = jsonify(
        {
            "message": message,
            "token": token,
            "user": {
                "id": user_row["id"],
                "username": user_row["username"],
                "role": user_row["role"],
            },
        }
    )
    response.set_cookie(JWT_COOKIE_NAME, token, httponly=True, samesite="Lax")
    return response


def _decode_token(token: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    try:
        return jwt.decode(token, _get_jwt_secret(conn), algorithms=[JWT_ALGORITHM])
    except (jwt.InvalidTokenError, sqlite3.Error):
        return None


def require_role(min_role: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator ensuring the requester has at least the required role."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            user = g.get("current_user")
            if not user:
                return jsonify({"error": "authentication required"}), 401
            if ROLE_ORDER.get(user["role"], 0) < ROLE_ORDER.get(min_role, 0):
                return jsonify({"error": "insufficient privileges"}), 403
            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_page_role(
    min_role: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator enforcing minimum role for template routes."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            user = g.get("current_user")
            if not user:
                return redirect(url_for("login_page"))
            if ROLE_ORDER.get(user["role"], 0) < ROLE_ORDER.get(min_role, 0):
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.setdefault("DATABASE", str(DB_PATH))
    app.config.setdefault("JWT_MASTER_SECRET", _load_master_secret())
    app.config.setdefault("FLAG_VALUE", os.environ.get("FLAG_VALUE", FLAG_VALUE))

    @app.before_request
    def load_current_user() -> None:
        token = request.cookies.get(JWT_COOKIE_NAME)
        g.current_user = None
        if not token:
            return
        payload = _decode_token(token)
        if not payload:
            return
        try:
            user_row = (
                get_db()
                .execute(
                    "SELECT id, username, role FROM users WHERE id = ?",
                    (payload.get("sub"),),
                )
                .fetchone()
            )
        except sqlite3.OperationalError:
            return
        if user_row:
            g.current_user = dict(user_row)

    @app.teardown_appcontext
    def teardown_db(exception: Optional[BaseException]) -> None:  # noqa: ARG001
        close_db()

    @app.context_processor
    def inject_user() -> Dict[str, Any]:
        user = g.get("current_user")
        return {
            "current_user": user,
            "current_role": user["role"] if user else "guest",
        }

    @app.route("/")
    def index() -> str:
        return render_template("index.html", page_title="Portal")

    @app.route("/login")
    def login_page() -> str:
        return render_template("login.html", page_title="Login")

    @app.route("/dashboard")
    @require_page_role("author")
    def dashboard_page() -> str:
        return render_template("dashboard.html", page_title="Dashboard")

    @app.route("/search")
    @require_page_role("author")
    def search_page() -> str:
        return render_template("search.html", page_title="Search")

    @app.route("/reviewer/tools")
    @require_page_role("reviewer")
    def reviewer_tools_page() -> str:
        return render_template("reviewer_tools.html", page_title="Reviewer Utilities")

    @app.route("/admin")
    @require_page_role("admin")
    def admin_page() -> str:
        return render_template("admin.html", page_title="Admin Panel")

    # --------------------------- Auth API ---------------------------

    @app.post("/api/register")
    def api_register() -> Any:
        data = _get_request_data()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        invite_code = (data.get("invite_code") or "").strip()
        if not username or not password:
            return jsonify({"error": "username and password required"}), 400
        if not username.isascii() or not password.isascii():
            return jsonify({"error": "username and password must be ASCII"}), 400
        if invite_code and not invite_code.isascii():
            return jsonify({"error": "invite code must be ASCII"}), 400
        if len(password) < 6:
            return jsonify({"error": "password must be at least 6 characters"}), 400
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, 'author')",
                (username, password),
            )
            user_id = cur.lastrowid
        except sqlite3.IntegrityError:
            return jsonify({"error": "username already taken"}), 400

        if invite_code:
            invite_result = _apply_invite_code(conn, invite_code, user_id)
            if invite_result.get("error"):
                conn.rollback()
                return jsonify({"error": invite_result["error"]}), invite_result[
                    "status"
                ]

        conn.commit()
        user_row = conn.execute(
            "SELECT id, username, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return _issue_token_response(user_row, "registered")

    @app.post("/api/login")
    def api_login() -> Any:
        data = _get_request_data()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        if not username or not password:
            return jsonify({"error": "username and password required"}), 400
        conn = get_db()
        try:
            user_row = conn.execute(
                "SELECT id, username, password, role FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            return jsonify({"error": str(exc)}), 500
        if not user_row or user_row["password"] != password:
            return jsonify({"error": "invalid credentials"}), 403
        if user_row["role"] == "admin":
            return jsonify({"error": "direct admin login disabled"}), 403
        return _issue_token_response(user_row, "logged in")

    @app.post("/api/logout")
    def api_logout() -> Any:
        response = jsonify({"message": "logged out"})
        response.delete_cookie(JWT_COOKIE_NAME)
        return response

    @app.get("/api/me")
    def api_me() -> Any:
        user = g.get("current_user")
        if not user:
            return jsonify({"user": None})
        return jsonify({"user": user})

    # --------------------------- Papers ---------------------------

    @app.post("/api/papers")
    @require_role("author")
    def api_submit_paper() -> Any:
        data = _get_request_data()
        title = (data.get("title") or "").strip()
        abstract = (data.get("abstract") or "").strip()
        if not title or not abstract:
            return jsonify({"error": "title and abstract required"}), 400
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO papers (title, abstract, author_id) VALUES (?, ?, ?)",
            (title, abstract, g.current_user["id"]),
        )
        conn.commit()
        paper_id = cur.lastrowid
        paper = conn.execute(
            "SELECT id, title, abstract, status FROM papers WHERE id = ?",
            (paper_id,),
        ).fetchone()
        return jsonify({"paper": dict(paper)})

    @app.get("/api/papers/mine")
    @require_role("author")
    def api_my_papers() -> Any:
        conn = get_db()
        rows = conn.execute(
            "SELECT id, title, status, created_at FROM papers WHERE author_id = ? ORDER BY created_at DESC",
            (g.current_user["id"],),
        ).fetchall()
        return jsonify({"papers": [dict(row) for row in rows]})

    @app.get("/api/search")
    @require_role("author")
    def api_search() -> Any:
        query = request.args.get("query", "")
        conn = get_db()
        sql = (
            "SELECT id, title, abstract, status, author_id FROM papers "
            f"WHERE title LIKE '%{query}%' OR abstract LIKE '%{query}%' "
            "ORDER BY created_at DESC"
        )
        try:
            rows = conn.execute(sql).fetchall()
        except sqlite3.Error as exc:
            return jsonify({"error": str(exc), "sql": sql}), 500
        user = g.get("current_user")
        visible_rows = rows
        if user and ROLE_ORDER.get(user["role"], 0) < ROLE_ORDER.get("reviewer", 0):
            visible_rows = [row for row in rows if row["author_id"] == user["id"]]
        sanitized = [
            {key: row[key] for key in ("id", "title", "abstract", "status")}
            for row in visible_rows
        ]
        return jsonify({"results": sanitized})

    # --------------------------- Reviewer Flows ---------------------------

    @app.post("/api/reviewers/redeem")
    @require_role("author")
    def api_redeem_invite() -> Any:
        data = _get_request_data()
        code = (data.get("code") or "").strip()
        if not code:
            return jsonify({"error": "invite code required"}), 400
        conn = get_db()
        result = _apply_invite_code(conn, code, g.current_user["id"])
        if result.get("error"):
            conn.rollback()
            return jsonify({"error": result["error"]}), result["status"]
        conn.commit()
        updated_user = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?",
            (g.current_user["id"],),
        ).fetchone()
        return _issue_token_response(updated_user, "role upgraded")

    @app.post("/api/reviewer/materials/check")
    @require_role("reviewer")
    def api_reviewer_materials_check() -> Any:
        data = _get_request_data()
        url = (data.get("url") or "").strip()
        purpose = (data.get("purpose") or "").strip()
        if not url:
            return jsonify({"error": "url required"}), 400
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return jsonify({"error": "only http/https targets allowed"}), 400
        allowed_hosts = {
            "openreview.internal.localhost",
            "openreview.internal",
            "localhost",
            "127.0.0.1",
        }
        if (parsed.hostname or "").lower() not in allowed_hosts:
            return jsonify({"error": "external host rejected"}), 400
        if parsed.path and not parsed.path.startswith("/internal/"):
            return jsonify({"error": "path rejected"}), 400
        if parsed.port not in (None, 80, 5000):
            return jsonify({"error": "port rejected"}), 400
        try:
            resp = requests.get(url, timeout=4, allow_redirects=True)
        except requests.RequestException as exc:
            return jsonify({"error": str(exc)}), 502
        body_preview = (
            resp.text[:2048]
            if resp.text
            else resp.content[:2048].decode("latin-1", "ignore")
        )
        return jsonify(
            {
                "fetched_url": url,
                "purpose": purpose or "not provided",
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "body_preview": body_preview,
            }
        )

    # --------------------------- Internal + Admin ---------------------------

    @app.route("/internal/config")
    def internal_config() -> Any:
        if request.remote_addr not in {"127.0.0.1", "::1"}:
            abort(403)
        conn = get_db()
        try:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
        except sqlite3.OperationalError:
            rows = []
        return jsonify(
            {
                "config": {row["key"]: row["value"] for row in rows},
                "secrets": {
                    "jwt_master_secret": current_app.config["JWT_MASTER_SECRET"]
                },
            }
        )

    @app.get("/api/admin/papers")
    @require_role("admin")
    def api_admin_papers() -> Any:
        conn = get_db()
        rows = conn.execute(
            """
            SELECT papers.id, papers.title, papers.abstract, papers.status, users.username AS author
            FROM papers
            JOIN users ON users.id = papers.author_id
            ORDER BY papers.created_at DESC
            """
        ).fetchall()
        return jsonify({"papers": [dict(row) for row in rows]})

    @app.post("/admin/papers/<int:paper_id>/accept")
    @require_role("admin")
    def api_admin_accept(paper_id: int) -> Any:
        conn = get_db()
        cur = conn.execute(
            "UPDATE papers SET status = 'accepted' WHERE id = ?", (paper_id,)
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "paper not found"}), 404
        return jsonify(
            {
                "message": f"paper {paper_id} accepted",
                "flag": current_app.config["FLAG_VALUE"],
            }
        )

    @app.post("/admin/papers/<int:paper_id>/reject")
    @require_role("admin")
    def api_admin_reject(paper_id: int) -> Any:
        conn = get_db()
        cur = conn.execute(
            "UPDATE papers SET status = 'rejected' WHERE id = ?", (paper_id,)
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "paper not found"}), 404
        return jsonify({"message": f"paper {paper_id} rejected"})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
