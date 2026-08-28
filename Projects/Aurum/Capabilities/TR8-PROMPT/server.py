#!/usr/bin/env python3
import json
import os
import subprocess
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("AURUM_PROMPT_PORT", "8765"))
ROOT = Path(__file__).resolve().parent
HTML = ROOT / "index.html"


def reply_json(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def run_aurum_intent(prompt):
    candidates = ["/usr/local/bin/aurum-intent", "/usr/bin/aurum-intent"]
    cmd = next((p for p in candidates if os.path.isfile(p) and os.access(p, os.X_OK)), None)
    if not cmd:
        return {"ok": False, "kind": "not_configured", "message": "Local Aurum intent adapter is not installed yet."}
    try:
        result = subprocess.run([cmd, prompt], text=True, capture_output=True, timeout=30, check=False)
    except Exception as exc:
        return {"ok": False, "kind": "adapter_error", "message": str(exc)}
    text = (result.stdout or result.stderr).strip()
    return {"ok": result.returncode == 0, "kind": "aurum", "message": text or f"aurum-intent exited {result.returncode}"}


def run_gpt(prompt):
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return {"ok": False, "kind": "not_configured", "message": "GPT API is not configured on this Aurum system.", "fallback": "https://chatgpt.com/"}
    model = os.environ.get("AURUM_GPT_MODEL", "gpt-5.6")
    payload = json.dumps({"model": model, "input": prompt}).encode("utf-8")
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=payload, method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "kind": "provider_error", "message": str(exc), "fallback": "https://chatgpt.com/"}
    text = data.get("output_text")
    if not text:
        chunks = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(content["text"])
        text = "\n".join(chunks)
    return {"ok": True, "kind": "gpt", "message": text or "GPT returned no text."}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path == "/healthz":
            return reply_json(self, 200, {"ok": True, "service": "aurum-prompt"})
        if self.path == "/" or self.path.startswith("/?"):
            body = HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        reply_json(self, 404, {"ok": False, "message": "not found"})

    def do_POST(self):
        if self.path not in ("/api/aurum", "/api/gpt"):
            return reply_json(self, 404, {"ok": False, "message": "not found"})
        try:
            size = min(int(self.headers.get("Content-Length", "0")), 32768)
            data = json.loads(self.rfile.read(size).decode("utf-8"))
            prompt = str(data.get("prompt", "")).strip()
        except Exception:
            return reply_json(self, 400, {"ok": False, "message": "invalid request"})
        if not prompt:
            return reply_json(self, 400, {"ok": False, "message": "prompt required"})
        result = run_aurum_intent(prompt) if self.path == "/api/aurum" else run_gpt(prompt)
        reply_json(self, 200 if result.get("ok") else 503, result)


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
