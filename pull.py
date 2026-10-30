"""Scarica lo storico Garmin in data/ come JSON (sola lettura).

    python3 pull.py          primo giro: ultimi 12 mesi; dopo: solo il nuovo
    python3 pull.py --all    tutto lo storico

Ogni finestra viene salvata subito: se si ferma, al giro dopo riparte da li'.
"""
import datetime as dt
import json
import os
import sys
import time

import garmin_api as g

DATA = g.DATA
PAUSE = 0.3
OVERLAP_DAYS = 3  # riscarica sempre gli ultimi giorni (dati di oggi ancora parziali)
TODAY = dt.date.today()


# ---------- file ----------

def load(name, default):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    path = os.path.join(DATA, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def log(msg):
    print(msg, flush=True)


# ---------- chiamate con pause e nuovi tentativi ----------

def call(path):
    """GET con pausa; ritenta su 429/502/503 e problemi di rete. Rilancia 500 e altri errori."""
    for attempt in range(5):
        time.sleep(PAUSE)
        try:
            return g.get(path)
        except g.GarminError as e:
            if e.status in (429, 502, 503) and attempt < 4:
                wait = 5 * (attempt + 1)
                log("    server occupato (HTTP %s), riprovo tra %ds..." % (e.status, wait))
                time.sleep(wait)
                continue
            raise
        except OSError:
            if attempt < 4:
                log("    problema di rete, riprovo...")
                time.sleep(5 * (attempt + 1))
                continue
            raise


# ---------- attivita' ----------

def pull_activities(state, start):
    acts = load("activities.json", {})
    known_from = state.get("activities_from")
    # Se lo storico gia' scaricato copre il periodo richiesto, ci si ferma alla prima pagina gia' nota.
    stop_on_known = bool(acts) and known_from is not None and (start is None or known_from <= start.isoformat())
    offset, limit, new = 0, 20, 0
    log("[attivita'] scarico...")
    while True:
        try:
            page = call("/activitylist-service/activities/search/activities?start=%d&limit=%d" % (offset, limit)) or []
        except g.GarminError as e:
            if e.status == 500 and limit > 1:
                limit = max(1, limit // 2)
                log("    risposta troppo grande, pagina ridotta a %d" % limit)
                continue
            raise
        all_known = True
        oldest = None
        for a in page:
            aid = str(a["activityId"])
            if aid not in acts:
                all_known = False
                new += 1
            acts[aid] = a
            oldest = a.get("startTimeLocal", "")[:10] or oldest
        save("activities.json", acts)
        offset += len(page)
        log("    %d attivita' lette (fino al %s), %d nuove" % (offset, oldest or "-", new))
        if len(page) < limit:
            break
        if start is not None and oldest and oldest < start.isoformat():
            break
        if stop_on_known and all_known:
            break
        limit = 20
    dates = sorted(a["startTimeLocal"][:10] for a in acts.values() if a.get("startTimeLocal"))
    if dates:
        first = dates[0] if start is None else max(dates[0], start.isoformat())
        if known_from is None or first < known_from:
            state["activities_from"] = first
    save("state.json", state)
    return acts


# ---------- dati giornalieri a finestre ----------

def daily_items(r):
    return [d for d in (r or {}).get("data", [])
            if d.get("includesWellnessData") or d.get("includesActivityData")]


DATASETS = [
    # nome, file, finestra (giorni), url, estrattore -> lista di (data, elemento)
    ("riepiloghi giornalieri", "daily.json", 60,
     "/usersummary-service/v2/dailysummaries?startDate={a}&endDate={b}",
     lambda r: [(d["calendarDate"], d) for d in daily_items(r)]),
    ("sonno", "sleep.json", 31,
     "/sleep-service/sleep/dailySleepSummariesByDate?startDate={a}&endDate={b}",
     lambda r: [(d["calendarDate"], d) for d in (r or []) if d.get("sleepTimeSeconds")]),
    ("HRV", "hrv.json", 365,
     "/hrv-service/hrv/daily/{a}/{b}",
     lambda r: [(d["calendarDate"], d) for d in (r or {}).get("hrvSummaries", []) if d.get("lastNightAvg")]),
    ("peso", "weight.json", 90,
     "/weight-service/weight/range/{a}/{b}",
     lambda r: [(d["summaryDate"], d) for d in (r or {}).get("dailyWeightSummaries", []) if d.get("latestWeight")]),
]


def pull_windows(state, label, fname, window, url, extract, start):
    store = load(fname, {})
    done = state.setdefault("done", {}).get(fname)
    cur = start
    if done:
        cur = max(start, dt.date.fromisoformat(done) - dt.timedelta(days=OVERLAP_DAYS))
    total = max(1, (TODAY - cur).days + 1)
    first_day = cur
    log("[%s] dal %s al %s" % (label, cur, TODAY))
    size = window
    while cur <= TODAY:
        end = min(cur + dt.timedelta(days=size - 1), TODAY)
        try:
            r = call(url.format(a=cur.isoformat(), b=end.isoformat()))
        except g.GarminError as e:
            if e.status == 500 and size > 1:
                size = max(1, size // 2)
                log("    risposta troppo grande, finestra ridotta a %d giorni" % size)
                continue
            if e.status in (400, 404, 500):
                log("    salto %s - %s (HTTP %s)" % (cur, end, e.status))
                r = None
            else:
                raise
        for day, item in extract(r):
            store[day] = item
        save(fname, store)
        state["done"][fname] = end.isoformat()
        save("state.json", state)
        pct = 100 * ((end - first_day).days + 1) // total
        log("    %s - %s  ok  (%d%%)" % (cur, end, pct))
        cur = end + dt.timedelta(days=1)
        size = window
    return store


def pull_profile():
    profile = {}
    for key, path in (("fitnessAge", "/fitnessage-service/fitnessage/v2/" + TODAY.isoformat()),
                      ("hrZones", "/biometric-service/heartRateZones/v2")):
        try:
            profile[key] = call(path)
        except g.GarminError as e:
            log("    %s non disponibile (HTTP %s)" % (key, e.status))
    save("profile.json", profile)


# ---------- main ----------

def main():
    os.makedirs(DATA, exist_ok=True)
    want_all = "--all" in sys.argv
    state = load("state.json", {})

    if want_all:
        acts = pull_activities(state, None)
        dates = sorted(a["startTimeLocal"][:10] for a in acts.values() if a.get("startTimeLocal"))
        start = dt.date.fromisoformat(dates[0]) if dates else TODAY - dt.timedelta(days=365)
    elif state.get("start"):
        start = dt.date.fromisoformat(state["start"])
        acts = pull_activities(state, start)
    else:
        start = TODAY - dt.timedelta(days=365)
        acts = pull_activities(state, start)

    if state.get("start") and start.isoformat() < state["start"]:
        state["done"] = {}  # periodo allargato: riscarica i dati giornalieri dall'inizio
    if not state.get("start") or start.isoformat() < state["start"]:
        state["start"] = start.isoformat()
    save("state.json", state)

    results = {}
    for label, fname, window, url, extract in DATASETS:
        results[fname] = pull_windows(state, label, fname, window, url, extract, start)
    log("[profilo] eta' fitness e zone cardiache...")
    pull_profile()

    state["last_pull"] = dt.datetime.now().isoformat(timespec="seconds")
    save("state.json", state)

    def span(keys):
        keys = sorted(keys)
        return "dal %s al %s" % (keys[0], keys[-1]) if keys else "nessun dato"

    act_dates = [a["startTimeLocal"][:10] for a in acts.values() if a.get("startTimeLocal")]
    log("")
    log("FATTO. Ecco cosa c'e' in data/:")
    log("  Attivita':  %5d  %s" % (len(acts), span(act_dates)))
    log("  Giorni:     %5d  %s" % (len(results["daily.json"]), span(results["daily.json"])))
    log("  Notti:      %5d  %s" % (len(results["sleep.json"]), span(results["sleep.json"])))
    log("  HRV:        %5d  %s" % (len(results["hrv.json"]), span(results["hrv.json"])))
    log("  Pesate:     %5d  %s" % (len(results["weight.json"]), span(results["weight.json"])))


if __name__ == "__main__":
    try:
        main()
    except g.GarminError as e:
        log("ERRORE: %s" % e)
        sys.exit(1)
    except KeyboardInterrupt:
        log("\nInterrotto. Rilancia pull.py per riprendere da dove era arrivato.")
        sys.exit(1)
