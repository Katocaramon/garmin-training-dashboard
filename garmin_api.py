"""Piccolo client in sola lettura per la Garmin Personal API (solo libreria standard).

La chiave viene letta da .env.local e non viene mai stampata.
Il token di accesso (valido 24 ore) viene salvato in data/token.json.
"""
import json
import os
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
ENV_FILE = os.path.join(ROOT, ".env.local")
TOKEN_FILE = os.path.join(DATA, "token.json")

BASE = "https://personal.connectapi.garmin.com"
TOKEN_URL = BASE + "/personalapitoken-service/personal-api/personal-api-key/token"
TOKEN_MAX_AGE = 20 * 3600  # rinnova dopo 20 ore (il token dura 24)


class GarminError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _read_key():
    if not os.path.exists(ENV_FILE):
        raise GarminError(None, "File .env.local non trovato.")
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            if line.startswith("GARMIN_PERSONAL_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    raise GarminError(None, "La chiave in .env.local e' vuota.")


def _new_token():
    req = urllib.request.Request(
        TOKEN_URL, data=b"", method="POST",
        headers={"Authorization": "ApiKey " + _read_key()},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            token = r.read().decode("utf-8").strip().strip('"')
    except urllib.error.HTTPError as e:
        raise GarminError(e.code, "Richiesta del token rifiutata (HTTP %d): la chiave "
                          "manca, e' sbagliata o e' scaduta." % e.code) from None
    os.makedirs(DATA, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"token": token, "created": time.time()}, f)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return token


def get_token(force=False):
    if not force and os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            if time.time() - saved["created"] < TOKEN_MAX_AGE:
                return saved["token"]
        except (ValueError, KeyError):
            pass
    return _new_token()


def get(path, accept="application/json", raw=False, _retried=False):
    """GET in sola lettura. Ritorna JSON (o bytes se raw), None se 204/vuoto."""
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": "Bearer " + get_token(force=_retried), "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            if r.status == 204 or not body:
                return None
    except urllib.error.HTTPError as e:
        if e.code == 401 and not _retried:
            return get(path, accept, raw, _retried=True)
        raise GarminError(e.code, "HTTP %d su %s" % (e.code, path.split("?")[0])) from None
    if raw:
        return body
    return json.loads(body.decode("utf-8"))
