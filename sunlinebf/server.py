#!/usr/bin/env python3
"""Small LAN-only HTTP service for the SunlineBF test page and shared history."""

from __future__ import annotations

import json
import math
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SUNLINEBF_DB", ROOT / "data" / "results.sqlite3"))
HOST = os.environ.get("SUNLINEBF_HOST", "127.0.0.1")
PORT = int(os.environ.get("SUNLINEBF_PORT", "8081"))
MAX_BODY = 16 * 1024
MAX_PAGE_SIZE = 100
FIELDS = ("download", "upload", "ping", "jitter")
TEXT_LIMITS = {"technician": 80, "site": 120}
STATIC_FILES = {"index.html", "style.css", "app.js", "speedtest.js", "speedtest_worker.js", "LICENSE"}


def connect_db(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE,
            created_at TEXT NOT NULL,
            technician TEXT NOT NULL,
            site TEXT NOT NULL,
            download REAL NOT NULL CHECK(download >= 0),
            upload REAL NOT NULL CHECK(upload >= 0),
            ping REAL NOT NULL CHECK(ping >= 0),
            jitter REAL NOT NULL CHECK(jitter >= 0)
        )
    """)
    # Additive migration: preserve existing history rows when upgrading.
    columns = {row[1] for row in db.execute("PRAGMA table_info(results)")}
    if "request_id" not in columns:
        db.execute("ALTER TABLE results ADD COLUMN request_id TEXT")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_results_request_id ON results(request_id)")
    return db


def validate_result(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Le corps doit être un objet JSON.")
    result: dict[str, object] = {}
    for key, limit in TEXT_LIMITS.items():
        value = data.get(key, "")
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"Champ {key} invalide (maximum {limit} caractères).")
        result[key] = value.strip()
    for key in FIELDS:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Champ {key} doit être un nombre.")
        number = float(value)
        if not math.isfinite(number) or number < 0 or number > 1_000_000_000:
            raise ValueError(f"Champ {key} hors limites.")
        result[key] = number
    request_id = data.get("request_id")
    if request_id is not None:
        if not isinstance(request_id, str) or len(request_id) > 36:
            raise ValueError("Champ request_id invalide.")
        try:
            normalized_id = str(uuid.UUID(request_id))
        except (ValueError, AttributeError) as exc:
            raise ValueError("Champ request_id doit être un UUID.") from exc
        if normalized_id != request_id.lower():
            raise ValueError("Champ request_id doit être un UUID canonique.")
        result["request_id"] = normalized_id
    return result


class SunlineHandler(SimpleHTTPRequestHandler):
    server_version = "SunlineBF/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, status: int, value: object):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True  # Direct navigation and non-browser LAN clients.
        parsed = urlsplit(origin)
        return parsed.scheme in ("http", "https") and parsed.netloc.lower() == self.headers.get("Host", "").lower()

    def do_OPTIONS(self):
        if not self._same_origin():
            self._json(403, {"error": "Origine refusée."})
            return
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _serve_allowed_file(self):
        path = unquote(urlsplit(self.path).path).replace("\\", "/")
        if path == "/":
            path = "/index.html"
        name = path.lstrip("/")
        if name not in STATIC_FILES or "/" in name or "\x00" in name:
            self._json(404, {"error": "Fichier introuvable."})
            return
        self.path = "/" + name
        return super().do_GET()

    def do_HEAD(self):
        path = unquote(urlsplit(self.path).path).replace("\\", "/")
        if path == "/":
            path = "/index.html"
        name = path.lstrip("/")
        if name not in STATIC_FILES or "/" in name or "\x00" in name:
            self._json(404, {"error": "Fichier introuvable."})
            return
        self.path = "/" + name
        return super().do_HEAD()

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path != "/api/results":
            return self._serve_allowed_file()
        if not self._same_origin():
            self._json(403, {"error": "Origine refusée."})
            return
        query = parse_qs(parsed.query)
        try:
            limit = min(MAX_PAGE_SIZE, max(1, int(query.get("limit", ["50"])[0])))
            offset = max(0, int(query.get("offset", ["0"])[0]))
        except ValueError:
            self._json(400, {"error": "Pagination invalide."})
            return
        search = query.get("search", [""])[0].strip()[:120]
        where = ""
        params: list[object] = []
        if search:
            where = "WHERE technician LIKE ? ESCAPE '\\' OR site LIKE ? ESCAPE '\\'"
            term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params.extend((term, term))
        with closing(connect_db(self.server.db_path)) as db:
            total = db.execute(f"SELECT COUNT(*) FROM results {where}", params).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM results {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        self._json(200, {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset})

    def do_POST(self):
        if urlsplit(self.path).path != "/api/results":
            self._json(404, {"error": "Route introuvable."})
            return
        if not self._same_origin():
            self._json(403, {"error": "Origine refusée."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Taille de requête invalide."})
            return
        if length <= 0 or length > MAX_BODY:
            self._json(413, {"error": "Requête vide ou trop volumineuse."})
            return
        if "application/json" not in self.headers.get("Content-Type", "").lower():
            self._json(415, {"error": "Le contenu doit être au format JSON."})
            return
        try:
            data = json.loads(self.rfile.read(length))
            result = validate_result(data)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._json(400, {"error": str(exc) or "JSON invalide."})
            return
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(connect_db(self.server.db_path)) as db:
            with db:
                request_id = result.get("request_id")
                if request_id:
                    existing = db.execute("SELECT * FROM results WHERE request_id = ?", (request_id,)).fetchone()
                    if existing:
                        compared = ("technician", "site", *FIELDS)
                        if any(existing[key] != result[key] for key in compared):
                            self._json(409, {"error": "request_id déjà utilisé pour un autre résultat."})
                            return
                        self._json(200, dict(existing))
                        return
                cursor = db.execute(
                    "INSERT INTO results (request_id, created_at, technician, site, download, upload, ping, jitter) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (request_id, created_at, result["technician"], result["site"], *(result[key] for key in FIELDS)),
                )
                row = db.execute("SELECT * FROM results WHERE id = ?", (cursor.lastrowid,)).fetchone()
        self._json(201, dict(row))

    def log_message(self, fmt: str, *args):
        # Keep access logs useful without including submitted query values.
        super().log_message(fmt, *args)


def make_server(host: str = HOST, port: int = PORT, db_path: Path = DB_PATH):
    server = ThreadingHTTPServer((host, port), SunlineHandler)
    server.daemon_threads = True
    server.db_path = Path(db_path)
    # Initialize schema before accepting requests.
    with closing(connect_db(server.db_path)):
        pass
    return server


if __name__ == "__main__":
    service = make_server()
    print(f"SunlineBF history listening on http://{HOST}:{PORT} (database: {DB_PATH})")
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.server_close()
