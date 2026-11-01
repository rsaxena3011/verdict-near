"""Zetaris REST client for VERDICT.

Reads credentials from ~/verdict/.env (never prints them). Every query is
recorded in self.query_log so the receipt can show exactly what was asked
of the federation layer and how many rows came back.
"""
import json
import os
import urllib.request
import uuid

ENV_PATH = os.path.expanduser("~/verdict/.env")


def load_env(path=ENV_PATH):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


class ZetarisClient:
    def __init__(self, env=None):
        self.env = env or load_env()
        self.base = self.env.get("ZETARIS_REST_URL", "http://localhost:8888/api/v1.0")
        self.key = self.env["ZETARIS_API_KEY"]
        self.org = self.env.get("ZETARIS_ORG_ID", "1")
        self.query_log = []

    def query(self, sql, limit=50):
        body = json.dumps({"sql": sql, "limit": limit}).encode()
        req = urllib.request.Request(
            self.base + "/sql-editor/sqls/run-query", data=body, method="POST"
        )
        req.add_header("Authorization", "Bearer " + self.key)
        req.add_header("X-Org-ID", self.org)
        req.add_header("X-Request-ID", str(uuid.uuid4()))
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        headers = data.get("headers", [])
        rows = [dict(zip(headers, row)) for row in data.get("data", [])]
        self.query_log.append({"sql": sql, "rows": len(rows)})
        return rows

    def fetch_store(self, store):
        return self.query(f"SELECT * FROM {store}.findings")
