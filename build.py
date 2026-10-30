"""Legge data/ e crea dashboard.html (un solo file, si apre senza server)."""
import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "dashboard.html")

# ---- le tue impostazioni: settings.json (privato), modello in settings.example.json ----
_cfg_path = os.path.join(ROOT, "settings.json")
if not os.path.exists(_cfg_path):
    _cfg_path = os.path.join(ROOT, "settings.example.json")
with open(_cfg_path, encoding="utf-8") as _f:
    CFG = json.load(_f)
RACE_NAME = CFG["race_name"]
RACE_DATE = dt.date.fromisoformat(CFG["race_date"])
PLAN_START = dt.date.fromisoformat(CFG["plan_start"])  # lunedi' della prima settimana del piano
HALF_KM = 21.0975

TODAY = dt.date.today()

RUN = {"running", "treadmill_running", "track_running", "virtual_run", "trail_running", "indoor_running"}
GYM = {"strength_training", "hiit", "indoor_cardio", "yoga", "indoor_rowing", "pilates", "fitness_equipment"}
BIKE = {"cycling", "e_bike_fitness", "cyclocross", "road_biking", "virtual_ride", "indoor_cycling",
        "mountain_biking", "gravel_cycling", "e_bike_mountain"}
GROUPS = ["Corsa", "Palestra", "Bici", "Altro"]


def group_of(type_key):
    if type_key in RUN:
        return "Corsa"
    if type_key in GYM:
        return "Palestra"
    if type_key in BIKE:
        return "Bici"
    return "Altro"


def load(name, default):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def monday(d):
    return d - dt.timedelta(days=d.weekday())


def r1(v, n=1):
    return None if v is None else round(v, n)


def avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def main():
    raw_acts = load("activities.json", {})
    daily = load("daily.json", {})
    sleep = load("sleep.json", {})
    hrv = load("hrv.json", {})
    weight = load("weight.json", {})
    profile = load("profile.json", {})
    state = load("state.json", {})

    # ---- attivita' compatte ----
    acts = []
    for a in raw_acts.values():
        if not a.get("startTimeLocal"):
            continue
        tk = (a.get("activityType") or {}).get("typeKey", "")
        acts.append({
            "id": a["activityId"],
            "d": a["startTimeLocal"][:10],
            "g": group_of(tk),
            "name": a.get("activityName") or tk,
            "km": (a.get("distance") or 0) / 1000,
            "sec": a.get("duration") or 0,
            "elev": a.get("elevationGain") or 0,
            "hr": a.get("averageHR"),
            "load": a.get("activityTrainingLoad") or 0,
            "splits": {k: a.get("fastestSplit_" + k) for k in ("1000", "1609", "5000", "10000", "21098")},
        })
    acts.sort(key=lambda x: x["d"])

    # ---- settimane ----
    weeks = {}
    for a in acts:
        w = monday(dt.date.fromisoformat(a["d"])).isoformat()
        g = weeks.setdefault(w, {k: {"km": 0, "sec": 0, "n": 0} for k in GROUPS})[a["g"]]
        g["km"] += a["km"]
        g["sec"] += a["sec"]
        g["n"] += 1
    empty = {k: {"km": 0, "sec": 0, "n": 0} for k in GROUPS}
    this_w = monday(TODAY)
    week_rows = []
    for i in range(15, -1, -1):
        w = (this_w - dt.timedelta(weeks=i)).isoformat()
        wk = weeks.get(w, empty)
        week_rows.append({"w": w, **{g: {k: r1(v, 2) for k, v in wk[g].items()} for g in GROUPS}})

    compare = []
    prev = [weeks.get((this_w - dt.timedelta(weeks=i)).isoformat(), empty) for i in range(1, 5)]
    cur = weeks.get(this_w.isoformat(), empty)
    for g in GROUPS:
        p = {k: sum(w[g][k] for w in prev) / 4 for k in ("km", "sec", "n")}
        if cur[g]["n"] or p["n"]:
            compare.append({"g": g, "cur": cur[g], "prev": p})

    # ---- serie giornaliere ----
    load_by_day = {}
    for a in acts:
        load_by_day[a["d"]] = load_by_day.get(a["d"], 0) + a["load"]

    all_dates = list(daily) + list(sleep) + list(hrv)
    first = dt.date.fromisoformat(min(all_dates)) if all_dates else TODAY
    first_act = dt.date.fromisoformat(acts[0]["d"]) if acts else TODAY
    rows = []
    d = first
    hist = {"rhr": [], "sl": []}
    while d <= TODAY:
        k = d.isoformat()
        r = {"d": k}
        ds = daily.get(k) or {}
        rhr = (ds.get("heartRate") or {}).get("restingValue")
        if rhr:
            r["rhr"] = rhr
        bb = ds.get("bodyBattery") or {}
        if bb.get("maxValue") is not None:
            r["bb"] = bb.get("maxValue")
        st = (ds.get("stress") or {}).get("avgLevel")
        if st is not None and st >= 0:
            r["stress"] = st
        h = hrv.get(k)
        if h:
            r["hrv"] = h.get("lastNightAvg")
            if h.get("weeklyAvg"):
                r["hrv7"] = h["weeklyAvg"]
            b = h.get("baseline") or {}
            if b.get("balancedLow") and b.get("balancedUpper"):
                r["lo"], r["hi"] = b["balancedLow"], b["balancedUpper"]
            r["st"] = h.get("status")
        s = sleep.get(k)
        if s and s.get("sleepTimeSeconds"):
            r["sl"] = round(s["sleepTimeSeconds"] / 3600, 2)
            sc = ((s.get("sleepScores") or {}).get("overall") or {}).get("value")
            if sc:
                r["ss"] = sc
            r["deep"] = round((s.get("deepSleepSeconds") or 0) / 3600, 2)
            r["rem"] = round((s.get("remSleepSeconds") or 0) / 3600, 2)
        # medie mobili su 7 giorni
        for key in ("rhr", "sl"):
            hist[key] = (hist[key] + [r.get(key)])[-7:]
            vals = [v for v in hist[key] if v is not None]
            if len(vals) >= 3:
                r[key + "7"] = round(sum(vals) / len(vals), 2 if key == "sl" else 1)
        if d >= first_act:
            r["ac"] = round(sum(load_by_day.get((d - dt.timedelta(days=i)).isoformat(), 0) for i in range(7)))
            r["ch"] = round(sum(load_by_day.get((d - dt.timedelta(days=i)).isoformat(), 0) for i in range(28)) / 4)
        w = weight.get(k)
        if w and (w.get("latestWeight") or {}).get("weight"):
            r["kg"] = round(w["latestWeight"]["weight"] / 1000, 1)
        rows.append(r)
        d += dt.timedelta(days=1)

    # ---- record ----
    runs = [a for a in acts if a["g"] == "Corsa"]
    best = []
    for key, label, km in (("1000", "1 km", 1), ("1609", "1 miglio", 1.609), ("5000", "5 km", 5),
                           ("10000", "10 km", 10), ("21098", "Mezza", HALF_KM)):
        cands = [(a["splits"][key], a) for a in runs if a["splits"].get(key)]
        if not cands:
            continue
        t, a = min(cands, key=lambda x: x[0])
        cut = (TODAY - dt.timedelta(days=365)).isoformat()
        recent = [c for c in cands if c[1]["d"] >= cut]
        rt = min(recent, key=lambda x: x[0]) if recent else None
        best.append({"label": label, "km": km, "sec": t, "d": a["d"], "name": a["name"],
                     "year": rt[0] if rt else None, "yearD": rt[1]["d"] if rt else None})

    def slim(a):
        return {"d": a["d"], "name": a["name"], "km": r1(a["km"], 2), "sec": round(a["sec"]),
                "elev": round(a["elev"]), "load": round(a["load"]), "g": a["g"]}

    longest = [slim(a) for a in sorted(runs, key=lambda a: -a["km"])[:5]]
    biggest = [slim(a) for a in sorted(acts, key=lambda a: -a["load"])[:5]]
    climb = [slim(a) for a in sorted(runs, key=lambda a: -a["elev"])[:3]]
    run_weeks = sorted(((w, v["Corsa"]["km"]) for w, v in weeks.items()), key=lambda x: -x[1])[:3]
    months = {}
    for a in runs:
        months[a["d"][:7]] = months.get(a["d"][:7], 0) + a["km"]
    run_months = sorted(months.items(), key=lambda x: -x[1])[:3]

    totals = {"acts": len(acts), "runs": len(runs), "runKm": round(sum(a["km"] for a in runs)),
              "since": acts[0]["d"] if acts else None}

    fa = (profile.get("fitnessAge") or {})
    data = {
        "today": TODAY.isoformat(),
        "generated": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "lastPull": state.get("last_pull"),
        "race": {"name": RACE_NAME, "date": RACE_DATE.isoformat(), "planStart": PLAN_START.isoformat()},
        "weeks": week_rows,
        "compare": compare,
        "rows": rows,
        "best": best,
        "longest": longest,
        "biggest": biggest,
        "climb": climb,
        "runWeeks": [{"w": w, "km": round(k, 1)} for w, k in run_weeks],
        "runMonths": [{"m": m, "km": round(k, 1)} for m, k in run_months],
        "totals": totals,
        "fitnessAge": r1(fa.get("fitnessAge")),
        "age": fa.get("chronologicalAge"),
        "recent": [slim(a) for a in acts[-8:]][::-1],
    }

    with open(os.path.join(ROOT, "template.html"), encoding="utf-8") as f:
        html = f.read()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", payload)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("Dashboard creata: %s (%d KB)" % (OUT, os.path.getsize(OUT) // 1024))


if __name__ == "__main__":
    main()
