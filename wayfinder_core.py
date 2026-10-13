
from __future__ import annotations
import csv, os, sqlite3, urllib.parse, json
from pathlib import Path
from typing import Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "wayfinder.db"

def load_csv(name: str) -> List[dict]:
    with (DATA_DIR / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def load_personas() -> List[dict]:
    rows = load_csv("personas.csv")
    for r in rows:
        for k in ["safety","cost","speed","entertainment","risk_tolerance"]:
            r[k] = int(r[k])
    return rows

def load_places() -> List[dict]:
    return load_csv("places.csv")

def split_categories(value: str) -> List[str]:
    return [x.strip() for x in (value or "").split("|") if x.strip()]

def init_db(path: Path = DB_PATH) -> None:
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS journey (
        journey_id INTEGER PRIMARY KEY AUTOINCREMENT,
        persona_id TEXT NOT NULL,
        origin TEXT NOT NULL,
        destination TEXT NOT NULL,
        event TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS decision (
        decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
        journey_id INTEGER NOT NULL,
        stop_order INTEGER NOT NULL,
        place_id TEXT NOT NULL,
        evidence TEXT,
        uncertainty TEXT,
        choice_reason TEXT,
        consequence TEXT,
        confidence REAL,
        FOREIGN KEY(journey_id) REFERENCES journey(journey_id)
    );
    CREATE TABLE IF NOT EXISTS memory (
        memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
        persona_id TEXT NOT NULL,
        place_id TEXT NOT NULL,
        rating INTEGER NOT NULL,
        cost_impression TEXT,
        friendliness TEXT,
        note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS contribution (
        contribution_id INTEGER PRIMARY KEY AUTOINCREMENT,
        persona_id TEXT NOT NULL,
        claim TEXT NOT NULL,
        evidence TEXT,
        confidence REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    con.commit()
    con.close()

def add_memory(persona_id: str, place_id: str, rating: int, note: str = "",
               cost_impression: str = "", friendliness: str = "", path: Path = DB_PATH) -> None:
    init_db(path)
    con = sqlite3.connect(path)
    con.execute(
        "INSERT INTO memory(persona_id, place_id, rating, cost_impression, friendliness, note) VALUES(?,?,?,?,?,?)",
        (persona_id, place_id, int(rating), cost_impression, friendliness, note),
    )
    con.commit(); con.close()

def memory_score(persona_id: str, place_id: str, path: Path = DB_PATH) -> float:
    init_db(path)
    con = sqlite3.connect(path)
    row = con.execute(
        "SELECT AVG(rating) FROM memory WHERE persona_id=? AND place_id=?",
        (persona_id, place_id),
    ).fetchone()
    con.close()
    if not row or row[0] is None:
        return 0.0
    # centered around 3: positive experience adds points, negative subtracts
    return (float(row[0]) - 3.0) * 1.5

def place_score(persona: dict, place: dict, path: Path = DB_PATH) -> float:
    preferred = split_categories(persona.get("preferred_categories",""))
    avoided = split_categories(persona.get("avoid_categories",""))
    cat = place["category"]
    if cat in avoided:
        return -999.0
    score = 1.0
    if cat in preferred:
        # Earlier in the preference string means slightly stronger preference.
        score += max(0.5, 4.0 - preferred.index(cat) * 0.35)
    if cat in {"Tavern","Night Club","Bar","Liquor Store"}:
        score += (persona["entertainment"] - 3) * 0.8
        score += (persona["risk_tolerance"] - 3) * 0.35
    if cat in {"Service Station","Drug Store","Garage","Hotel","Lodging"}:
        score += (persona["safety"] - 3) * 0.35
    score += memory_score(persona["persona_id"], place["place_id"], path)
    return score

def choose_route(persona: dict, origin_id: str = "CHI001", destination_id: str = "CHI006",
                 intermediate_count: int = 3, path: Path = DB_PATH) -> List[dict]:
    places = load_places()
    by_id = {p["place_id"]: p for p in places}
    origin = by_id[origin_id]; dest = by_id[destination_id]
    candidates = [p for p in places if p["place_id"] not in {origin_id, destination_id}]
    ranked = sorted(candidates, key=lambda p: (place_score(persona,p,path), p["place_id"]), reverse=True)

    selected = []
    # Scenario-specific diversity rules for a useful prototype.
    if persona["persona_id"] == "P001":
        # Family: practical mix, no nightlife.
        for wanted in ["Drug Store", "Garage", "Service Station"]:
            p = next((x for x in ranked if x["category"] == wanted and x not in selected), None)
            if p:
                selected.append(p)
    elif persona["persona_id"] == "P002":
        # Woman, 19: practical/safety-focused prototype with service support and no nightlife.
        service_stops = [p for p in ranked if p["category"] == "Service Station"]
        if service_stops:
            selected.append(service_stops[0])
        drug = next((p for p in ranked if p["category"] == "Drug Store" and p not in selected), None)
        if drug:
            selected.append(drug)
        if len(service_stops) > 1 and service_stops[1] not in selected:
            selected.append(service_stops[1])
    elif persona["persona_id"] == "P003":
        # Man, 27: make flexible nightlife choice visible.
        nightlife = [p for p in ranked if p["category"] in {"Tavern","Night Club"}]
        selected.extend(nightlife[:3])

    for p in ranked:
        if p not in selected and len(selected) < intermediate_count:
            selected.append(p)
    return [origin] + selected[:intermediate_count] + [dest]

def google_maps_link(route: List[dict]) -> str:
    origin = route[0]["routing_address"]
    destination = route[-1]["routing_address"]
    waypoints = "|".join(p["routing_address"] for p in route[1:-1])
    params = {"api":"1","origin":origin,"destination":destination,"travelmode":"driving"}
    if waypoints:
        params["waypoints"] = waypoints
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params)

def event_effect(event: str, route: List[dict]) -> Tuple[str,str]:
    event = event or "No dynamic event"
    if event == "No dynamic event":
        return ("Normal journey", "No simulated condition changed the route.")
    if event == "Gas becomes scarce":
        if any(p["category"]=="Service Station" for p in route):
            return ("Adapted successfully", "A service-station stop reduced uncertainty after gas became scarce.")
        return ("Higher uncertainty", "Gas became scarce and the route had no service-station stop.")
    if event == "Lodging becomes unavailable":
        return ("Replan required", "The destination/lodging condition changed, requiring a new decision.")
    if event == "Trusted source warning":
        return ("Evidence conflict", "A trusted contact contributed new information that should be weighed against the original source.")
    if event == "Road delay":
        return ("Delay", "Travel time increased, so speed and remaining resources become more important.")
    return ("Condition observed", event)

def decision_rows(persona: dict, route: List[dict], event: str, path: Path = DB_PATH) -> List[dict]:
    rows = []
    outcome, event_note = event_effect(event, route)
    for idx, p in enumerate(route[1:-1], start=1):
        score = place_score(persona, p, path)
        confidence = min(0.95, max(0.50, 0.62 + score * 0.035))
        rows.append({
            "Decision": f"Stop {idx}",
            "Evidence": p["evidence"],
            "Uncertainty": "Historical listing does not guarantee current availability, suitability, or surrounding-area conditions.",
            "Choice": p["name"],
            "Why": f"{p['category']} aligns with this persona's configured preferences and prior memory score.",
            "Consequence": event_note if idx == 1 and event != "No dynamic event" else "Stop retained in the journey plan.",
            "Confidence": round(confidence, 2),
            "Outcome": outcome if idx == 1 else "Planned",
        })
    return rows

def save_journey(persona: dict, route: List[dict], event: str, decisions: List[dict], path: Path = DB_PATH) -> int:
    init_db(path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("INSERT INTO journey(persona_id, origin, destination, event) VALUES(?,?,?,?)",
                (persona["persona_id"], route[0]["name"], route[-1]["name"], event))
    jid = cur.lastrowid
    for i, (p, d) in enumerate(zip(route[1:-1], decisions), start=1):
        cur.execute("""INSERT INTO decision(journey_id, stop_order, place_id, evidence, uncertainty,
                     choice_reason, consequence, confidence) VALUES(?,?,?,?,?,?,?,?)""",
                    (jid, i, p["place_id"], d["Evidence"], d["Uncertainty"], d["Why"], d["Consequence"], d["Confidence"]))
    con.commit(); con.close()
    return int(jid)

def memory_summary(persona_id: str, path: Path = DB_PATH) -> List[dict]:
    init_db(path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT place_id, ROUND(AVG(rating),2) AS avg_rating, COUNT(*) AS experiences,
               MAX(note) AS latest_note
        FROM memory WHERE persona_id=? GROUP BY place_id ORDER BY avg_rating DESC, experiences DESC
    """, (persona_id,)).fetchall()
    con.close()
    place_names = {p["place_id"]:p["name"] for p in load_places()}
    return [{"Place":place_names.get(r["place_id"],r["place_id"]),
             "Average rating":r["avg_rating"],"Experiences":r["experiences"],
             "Latest note":r["latest_note"] or ""} for r in rows]

def simulated_persona_conversation(route: List[dict]) -> List[dict]:
    names = " → ".join(p["name"] for p in route)
    return [
        {"speaker":"Family of 4","message":f"I would judge this journey by practical stops, low uncertainty, and whether the route works for everyone traveling together. Proposed path: {names}"},
        {"speaker":"Woman, 19","message":"I would prioritize a service stop, reliable information, and fewer unnecessary stops. I would avoid nightlife in my current persona settings."},
        {"speaker":"Man, 27","message":"I am more flexible about restaurants and nightlife, but I still want the system to explain why each stop was recommended and remember what worked last time."},
    ]

def openai_persona_conversation(route: List[dict], api_key: str | None = None, model: str | None = None) -> str | None:
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = model or os.getenv("OPENAI_MODEL", "gpt-6-astra")
        route_text = " -> ".join(f"{p['name']} ({p['category']})" for p in route)
        prompt = f"""
You are simulating a WAYFINDER design review among exactly three configured prototype personas:
1) Family of 4: practical family stops; avoids nightlife.
2) Woman, age 19, traveling alone: safety-focused prototype; practical stops; avoids nightlife. Do NOT claim any place is proven safe.
3) Man, age 27, traveling alone: more flexible, may include restaurant/tavern/nightclub stops.

Route being discussed:
{route_text}

Write a concise conversation of 6-9 turns. Each persona must explain preferences, uncertainty, and how a previous positive/negative experience could change a future choice.
Do not invent facts about historical safety or current business availability.
"""
        response = client.responses.create(model=model, input=prompt)
        return response.output_text
    except Exception as e:
        return f"OpenAI mode could not run: {e}"

def mapbox_geocode(address: str, token: str) -> Tuple[float,float] | None:
    import requests
    r = requests.get(
        "https://api.mapbox.com/search/geocode/v6/forward",
        params={"q":address, "country":"us", "limit":1, "access_token":token},
        timeout=20,
    )
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        return None
    lon, lat = features[0]["geometry"]["coordinates"][:2]
    return float(lon), float(lat)

def mapbox_route_geometry(route: List[dict], token: str) -> dict | None:
    import requests
    coords = []
    for p in route:
        c = mapbox_geocode(p["routing_address"], token)
        if not c:
            return None
        coords.append(c)
    coord_text = ";".join(f"{lon},{lat}" for lon,lat in coords)
    url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coord_text}"
    r = requests.get(url, params={
        "geometries":"geojson","overview":"full","steps":"false",
        "access_token":token
    }, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("routes"):
        return None
    rt = data["routes"][0]
    return {"coordinates":rt["geometry"]["coordinates"],
            "distance_m":rt.get("distance"), "duration_s":rt.get("duration"),
            "waypoints":coords}

def build_counterfactual(persona: dict, change: str) -> dict:
    p = dict(persona)
    if change == "Higher safety priority":
        p["safety"] = 5; p["risk_tolerance"] = 1
    elif change == "Higher entertainment priority":
        p["entertainment"] = 5; p["risk_tolerance"] = max(3, p["risk_tolerance"])
    elif change == "Higher speed priority":
        p["speed"] = 5
    return p
