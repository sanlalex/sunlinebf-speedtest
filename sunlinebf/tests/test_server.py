import json
from pathlib import Path
from contextlib import closing
import sys
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class HistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "history.sqlite3"
        self.httpd = server.make_server("127.0.0.1", 0, self.db)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        request_headers = dict(headers or {})
        if data is not None:
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(self.base + path, data=data, headers=request_headers)
        return urlopen(request)

    @staticmethod
    def payload(**overrides):
        value = {"technician": "Awa", "site": "Site A", "download": 45.2,
                 "upload": 7.1, "ping": 12.0, "jitter": 1.5}
        value.update(overrides)
        return value

    def test_create_and_read_history_with_pagination_and_search(self):
        for site in ("Site A", "Site B"):
            response = self.request("/api/results", self.payload(site=site))
            self.assertEqual(response.status, 201)
            saved = json.load(response)
            self.assertEqual(saved["site"], site)
            self.assertIn("+00:00", saved["created_at"])
        result = json.load(self.request("/api/results?limit=1&offset=0&search=Site%20A"))
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["site"], "Site A")

    def test_persists_after_server_restart(self):
        payload = self.payload(request_id="d3584b64-9ee2-4e3c-9a73-5ba243167103")
        response = self.request("/api/results", payload)
        response.close()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = server.make_server("127.0.0.1", 0, self.db)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"
        result = json.load(self.request("/api/results"))
        self.assertEqual(result["total"], 1)
        retry = self.request("/api/results", payload)
        self.assertEqual(retry.status, 200)
        self.assertEqual(json.load(retry)["id"], result["items"][0]["id"])

    def test_idempotent_retry_and_conflicting_reuse(self):
        payload = self.payload(request_id="2c947041-68d0-4d25-aeb5-510bc8fc9735")
        first = self.request("/api/results", payload)
        saved = json.load(first)
        retry = self.request("/api/results", payload)
        self.assertEqual(retry.status, 200)
        self.assertEqual(json.load(retry)["id"], saved["id"])
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/results", {**payload, "download": 999})
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(json.load(self.request("/api/results"))["total"], 1)

    def test_additive_migration_keeps_old_rows(self):
        legacy_path = Path(self.temp.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy_path)) as db:
            with db:
                db.execute("""CREATE TABLE results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                    technician TEXT NOT NULL, site TEXT NOT NULL,
                    download REAL NOT NULL, upload REAL NOT NULL,
                    ping REAL NOT NULL, jitter REAL NOT NULL)""")
                db.execute("INSERT INTO results VALUES (1, '2026-01-01T00:00:00+00:00', 'Awa', 'Ancien', 1, 2, 3, 4)")
        with closing(server.connect_db(legacy_path)) as db:
            saved = db.execute("SELECT site, request_id FROM results WHERE id = 1").fetchone()
        self.assertEqual(saved["site"], "Ancien")
        self.assertIsNone(saved["request_id"])

    def test_rejects_invalid_metrics_and_foreign_origin(self):
        for invalid in (-1, float("nan"), float("inf"), "fast", True):
            with self.assertRaises(HTTPError) as caught:
                self.request("/api/results", self.payload(download=invalid))
            self.assertEqual(caught.exception.code, 400)
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/results", self.payload(), {"Origin": "https://outside.example"})
        self.assertEqual(caught.exception.code, 403)
        result = json.load(self.request("/api/results"))
        self.assertEqual(result["total"], 0)

    def test_only_explicit_frontend_files_are_served(self):
        secret = server.ROOT / "data" / "private-test.txt"
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text("private database adjacent file", encoding="utf-8")
        try:
            for path in ("/server.py", "/tests/test_server.py", "/data/private-test.txt",
                         "/%2e%2e/server.py", "/%252e%252e/server.py"):
                with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                    self.request(path)
                self.assertEqual(caught.exception.code, 404)
            with self.assertRaises(HTTPError) as caught:
                self.request("/api/results.sqlite3")
            self.assertEqual(caught.exception.code, 404)
        finally:
            secret.unlink(missing_ok=True)

    def test_rejects_oversized_text_and_request_body(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/results", self.payload(site="x" * 121))
        self.assertEqual(caught.exception.code, 400)
        request = Request(self.base + "/api/results", data=b"x" * (server.MAX_BODY + 1),
                          headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 413)


if __name__ == "__main__":
    unittest.main()
