"""Server locale per la dashboard, con il pulsante "Aggiorna".

Ascolta solo su 127.0.0.1 (raggiungibile solo da questo computer) e serve
soltanto dashboard.html: .env.local e data/ non sono mai accessibili.
POST /refresh lancia pull.py e build.py.
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
ALLOWED_HOSTS = {"127.0.0.1:%d" % PORT, "localhost:%d" % PORT}
lock = threading.Lock()


def run(script):
    r = subprocess.run([sys.executable, os.path.join(ROOT, script)], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


class Handler(BaseHTTPRequestHandler):
    def _local_only(self):
        # Blocca richieste da altri siti (CSRF) e trucchi con nomi di dominio (DNS rebinding).
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.split("//", 1)[-1] in ALLOWED_HOSTS

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._local_only():
            return self._send(403, "Vietato", "text/plain; charset=utf-8")
        if self.path in ("/", "/index.html", "/dashboard.html"):
            with open(os.path.join(ROOT, "dashboard.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if self.path == "/ping":
            return self._send(200, "ok", "text/plain")
        self._send(404, "Non trovato", "text/plain; charset=utf-8")

    def do_POST(self):
        if not self._local_only() or self.path != "/refresh":
            return self._send(403, "Vietato", "text/plain; charset=utf-8")
        if not lock.acquire(blocking=False):
            return self._send(409, json.dumps({"ok": False, "msg": "Aggiornamento gia' in corso."}), "application/json")
        try:
            code, out = run("pull.py")
            if code == 0:
                code, out2 = run("build.py")
                out += out2
            tail = "\n".join(line for line in out.splitlines() if "  ok  " not in line)[-1500:]
            msg = "Fatto" if code == 0 else "Download non riuscito: controlla .env.local (la chiave potrebbe essere scaduta)."
            self._send(200, json.dumps({"ok": code == 0, "msg": msg, "log": tail}), "application/json")
        finally:
            lock.release()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("Dashboard su http://127.0.0.1:%d  (chiudi con Ctrl+C)" % PORT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
