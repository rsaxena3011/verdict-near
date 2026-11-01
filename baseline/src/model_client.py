"""Nemotron access for VERDICT, via the local Meterless Nightshift runtime.

The agent process runs inside WSL, which cannot reach the Windows host's
Nightshift port (127.0.0.1:8088) directly. The proven bridge is Windows
curl.exe invoked through WSL interop from a Windows working directory,
with the JSON payload passed as a file. The runtime key is read from the
Nightshift state file on the PC and never printed.

Every call returns a receipt: the model we ASKED for (a named Nemotron
lane, never bare auto), the model that actually answered (Meterless may
route), token usage, and the Meterless receipt block when present.
"""
import json
import os
import subprocess
import time

BRIDGE_DIR = "/mnt/c/Users/user/verdict_bridge"
TOKEN_PATH = "/mnt/c/Users/user/AppData/Local/ai.meterless.runtime/proxy-token"
CURL = "/mnt/c/Windows/System32/curl.exe"
PINNED_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
BASE_URL = "http://127.0.0.1:8088"


class ModelClient:
    def __init__(self, model=PINNED_MODEL):
        self.model = model
        os.makedirs(BRIDGE_DIR, exist_ok=True)

    def _token(self):
        with open(TOKEN_PATH) as f:
            return f.read().strip()

    def chat(self, messages, max_tokens=2500):
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        last_timeout = None
        for attempt in range(3):
            # Fresh payload filename per attempt: a zombie curl.exe from a
            # timed-out attempt may still hold the previous file open.
            name = f"payload_{os.getpid()}_{attempt}.json"
            payload_path = os.path.join(BRIDGE_DIR, name)
            with open(payload_path, "w") as f:
                json.dump(payload, f)
            try:
                r = subprocess.run(
                    [
                        CURL, "-s", "--max-time", "240",
                        "-X", "POST", BASE_URL + "/v1/chat/completions",
                        "-H", "Authorization: Bearer " + self._token(),
                        "-H", "Content-Type: application/json",
                        "-H", "meterless-app: verdict",
                        "-H", "meterless-scope: user",
                        "-d", r"@C:\Users\user\verdict_bridge" + "\\" + name,
                    ],
                    capture_output=True, text=True, cwd=BRIDGE_DIR, timeout=300,
                )
            except subprocess.TimeoutExpired as e:
                # One hung bridge call must not kill the caller (it took out
                # the whole 28-case harness run on 2026-10-23). Retry; only
                # three consecutive hangs propagate.
                last_timeout = e
                time.sleep(5)
                continue
            if r.returncode != 0:
                raise RuntimeError(f"model bridge failed rc={r.returncode}: {r.stderr[:200]}")
            data = json.loads(r.stdout)
            choice = (data.get("choices") or [{}])[0]
            text = ((choice.get("message") or {}).get("content")) or ""
            receipt = {
                "requested_model": self.model,
                "routed_model": data.get("model"),
                "usage": data.get("usage"),
                "meterless": data.get("meterless"),
                "cross_check": data.get("meterless_cross_check"),
            }
            return text, receipt
        raise RuntimeError(f"model bridge timed out on all 3 attempts: {last_timeout}")


def _balanced_span(text, start):
    """End index of the balanced {...} span starting at `start`, aware of
    string literals and escapes (reasoning text is full of stray braces
    inside quotes). None if unbalanced."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def extract_json(text, key=None):
    """Pull a JSON object out of a model reply. Reasoning models leak long
    monologues (with draft JSON fragments inside) into the visible reply,
    so every '{' is tried as a candidate start; among the spans that
    parse, prefer the LAST one carrying the expected top-level key, since
    the final answer comes after the reasoning."""
    parsed = []
    for start in range(len(text)):
        if text[start] != "{":
            continue
        end = _balanced_span(text, start)
        if end is None:
            continue
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            parsed.append(obj)
    if not parsed:
        raise ValueError("no parseable JSON object in model reply")
    if key:
        with_key = [o for o in parsed if key in o]
        if with_key:
            return with_key[-1]
    return parsed[-1]
