#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_delivery_data.py — delivery-zone dataset for Vlad iLiver (zbi.mir-betona33.ru).
Generates compact GeoJSON-like JSON: public/delivery/vladimir.json

Data sources: OpenStreetMap via Overpass (mirrors) + local shapely processing.
Layers: city boundary (relation 1991003), roads (primary/secondary/tertiary),
water, greens, delivery rings (5/10/20/35/60 km), neighbour cities w/ distances.

Usage:
  python gen_delivery_data.py [--preview out.png]

Output file: public/delivery/vladimir.json (gzip target <= 60 KB)
"""
import os
import sys
import time
import math
import json
import gzip
import argparse
import requests

UA = "zbi-delivery-gen/1.0 (+https://zbi.mir-betona33.ru)"
PROXIES = {"http": "http://127.0.0.1:3067", "https": "http://127.0.0.1:3067"}
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

from shapely.geometry import LineString, Polygon, MultiPolygon, Point
from shapely.ops import unary_union, polygonize

# ----------------------------------------------------------------------------- config
CENTER_LAT, CENTER_LON = 56.1288899, 40.4075203
CENTER = (CENTER_LAT, CENTER_LON)
BOUNDARY_REL = 1991003

# bbox for roads/water/greens fetch: ~9 km around center
# Overpass bbox order is (south, west, north, east) == (lat_min, lon_min, lat_max, lon_max)
DLAT9 = 9000.0 / 111320.0
DLON9 = 9000.0 / (111320.0 * math.cos(math.radians(CENTER_LAT)))
BBOX_STR = "%.5f,%.5f,%.5f,%.5f" % (CENTER_LAT - DLAT9, CENTER_LON - DLON9,
                                    CENTER_LAT + DLAT9, CENTER_LON + DLON9)

ROAD_TYPES = ("primary", "secondary", "tertiary")
RING_KM = (5, 10, 20, 35, 60)
RING_PTS = 72

SIMPLIFY = {  # degrees
    "boundary": 0.0004,
    "road": 0.0002,
    "water": 0.0004,
    "green": 0.0005,
}

MIN_AREA = {  # deg^2
    "water": 1e-7,     # ~0.0007 km2 — keep all ponds, drop degenerate
    "green": 0.000001,  # ~0.007 km2 — keep green areas > 0.7 ha
}

CITIES = [  # name, lat, lon (OSM coords used by gen_maps.py)
    ("Радужный", 55.9966, 40.3130),
    ("Суздаль", 56.4252, 40.4477),
    ("Судогда", 55.9482, 40.8623),
    ("Гусь-Хрустальный", 55.6195, 40.6594),
    ("Юрьев-Польский", 56.4977, 39.6793),
    ("Ковров", 56.3563, 41.3163),
    ("Иваново", 56.9997, 40.9731),
]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.normpath(os.path.join(HERE, "..", "public", "delivery", "vladimir.json"))
BOUNDARY_CACHE = os.path.join(HERE, "osm_cache", "boundary_rel_%d.json" % BOUNDARY_REL)
CACHE_MAX_AGE = 3600 * 24 * 60  # 60 days


# ----------------------------------------------------------------------------- io
def op(query, timeout=180, max_tries=3):
    """Run Overpass query with mirror fallback through Karing proxy."""
    last = None
    for attempt in range(max_tries):
        for mirror in MIRRORS:
            try:
                r = requests.post(
                    mirror, data={"data": query},
                    headers={"User-Agent": UA, "Accept": "*/*"},
                    proxies=PROXIES, timeout=timeout,
                )
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last = e
                print("    ! %s: %s %s" % (mirror.split("//")[1].split("/")[0],
                                           type(e).__name__, str(e)[:90]), flush=True)
        time.sleep(2)
    raise RuntimeError("Overpass failed for query: %s" % last)


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    R = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def r6(v):
    return round(v, 6)


def round_coords(seq):
    """seq: list of (lon, lat) → rounded [lon, lat]"""
    return [[r6(x), r6(y)] for x, y in seq]


def simplify_and_round(geom, tol):
    g = geom.simplify(tol, preserve_topology=True)
    return g


# ----------------------------------------------------------------------------- fetch
def boundary_from_overpass_json(d):
    """Build largest polygon from Overpass rel+way(r) out geom response."""
    ways = [w for w in d["elements"] if w["type"] == "way" and len(w.get("geometry", [])) >= 2]
    lines = [LineString([(p["lon"], p["lat"]) for p in w["geometry"]]) for w in ways]
    print("    boundary ways:", len(ways), flush=True)
    merged = unary_union(lines)
    polys = [p for p in polygonize(merged) if not p.is_empty]
    if not polys:
        raise RuntimeError("polygonize gave no polygon")
    largest = max(polys, key=lambda p: p.area)
    return largest


def fetch_boundary():
    print("[1/5] boundary: relation %d ..." % BOUNDARY_REL, flush=True)
    # 1) local cache (relation 1991003 raw OSM response from a previous successful fetch)
    if os.path.exists(BOUNDARY_CACHE):
        age = time.time() - os.path.getmtime(BOUNDARY_CACHE)
        if age < CACHE_MAX_AGE:
            with open(BOUNDARY_CACHE, "r", encoding="utf-8") as f:
                d = json.load(f)
            print("    from cache (%d s old)" % age, flush=True)
            return boundary_from_overpass_json(d)
    # 2) Overpass
    try:
        q = "[out:json][timeout:180][maxsize:1073741824];rel(%d);out tags;rel(%d);way(r);out geom;" % (BOUNDARY_REL, BOUNDARY_REL)
        d = op(q)
        os.makedirs(os.path.dirname(BOUNDARY_CACHE), exist_ok=True)
        with open(BOUNDARY_CACHE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        return boundary_from_overpass_json(d)
    except Exception as e:
        print("    boundary overpass failed: %s — trying Nominatim fallback via osmnx" % e, flush=True)
        try:
            import osmnx as ox
            ox.settings.http_user_agent = UA
            ox.settings.requests_kwargs = {"proxies": PROXIES}
            gdf = ox.geocode_to_gdf("Владимир, Владимирская область, Россия")
            boundary = gdf.geometry.iloc[0]
            if boundary.geom_type == "MultiPolygon":
                boundary = max(list(boundary.geoms), key=lambda p: p.area)
            print("    nominatim area km2: %.1f bounds: %s" % (
                boundary.area * 111.32 * 62.06,
                [round(v, 4) for v in boundary.bounds],
            ), flush=True)
            return boundary
        except Exception as e2:
            print("    nominatim fallback failed: %r" % e2, flush=True)
            raise


def fetch_features():
    print("[2/5] roads/water/greens: bbox %s ..." % BBOX_STR, flush=True)
    q = (
        '[out:json][timeout:240][maxsize:1073741824];('
        'way["highway"~"^(primary|secondary|tertiary)$"](%s);'
        'way["natural"="water"](%s);'
        'way["waterway"="riverbank"](%s);'
        'way["waterway"="river"](%s);'
        'way["landuse"~"^(grass|forest|meadow|village_green|recreation_ground|orchard)$"](%s);'
        'way["leisure"~"^(park|garden|nature_reserve|playground)$"](%s);'
        'way["natural"~"^(wood|scrub)$"](%s);'
        ');out geom;'
    ) % (BBOX_STR, BBOX_STR, BBOX_STR, BBOX_STR, BBOX_STR, BBOX_STR, BBOX_STR)
    d = op(q)
    els = d.get("elements", [])
    roads, water, waterways, greens = [], [], [], []
    for w in els:
        if w["type"] != "way":
            continue
        geom = w.get("geometry")
        if not geom or len(geom) < 2:
            continue
        tags = w.get("tags", {})
        hw = tags.get("highway", "")
        if hw in ROAD_TYPES:
            roads.append((hw, [(p["lon"], p["lat"]) for p in geom]))
            continue
        nat = tags.get("natural", "")
        ww = tags.get("waterway", "")
        lu = tags.get("landuse", "")
        le = tags.get("leisure", "")
        if nat == "water" or ww == "riverbank":
            water.append([(p["lon"], p["lat"]) for p in geom])
        elif ww == "river":
            waterways.append([(p["lon"], p["lat"]) for p in geom])
        elif (lu in ("grass", "forest", "meadow", "village_green", "recreation_ground", "orchard")
              or le in ("park", "garden", "nature_reserve", "playground")
              or nat in ("wood", "scrub")):
            greens.append([(p["lon"], p["lat"]) for p in geom])
    print("    fetched -> roads:%d water:%d waterways:%d greens:%d" % (
        len(roads), len(water), len(waterways), len(greens)), flush=True)
    return roads, water, waterways, greens


# ----------------------------------------------------------------------------- process
def to_poly(ring):
    return Polygon(ring)


def process_roads(roads, clip_circle):
    out = []
    for typ, coords in roads:
        line = LineString(coords)
        line = line.intersection(clip_circle)
        geoms = line.geoms if hasattr(line, "geoms") else [line]
        for g in geoms:
            if g.is_empty or g.length < 1e-6:
                continue
            g = simplify_and_round(g, SIMPLIFY["road"])
            if g.is_empty or g.geom_type not in ("LineString", "MultiLineString"):
                continue
            parts = g.geoms if g.geom_type == "MultiLineString" else [g]
            for p in parts:
                c = round_coords(p.coords)
                if len(c) >= 2:
                    out.append({"t": typ[0], "c": c})
    return out


def process_polys(rows, clip, tol, min_area):
    """rows: list of coordinate rings; clip: polygon; returns rounded rings."""
    out = []
    for ring in rows:
        p = Polygon(ring)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty:
            continue
        p = p.intersection(clip)
        if p.is_empty:
            continue
        if isinstance(p, (Polygon, MultiPolygon)):
            polys = list(p.geoms) if p.geom_type == "MultiPolygon" else [p]
        else:
            polys = []
        for pp in polys:
            if pp.area < min_area:
                continue
            pp = pp.simplify(tol, preserve_topology=True)
            if pp.geom_type != "Polygon" or pp.area < min_area:
                continue
            out.append(round_coords(list(pp.exterior.coords)))
    return out


def process_lines(rows, clip, tol):
    out = []
    for coords in rows:
        line = LineString(coords)
        line = line.intersection(clip)
        geoms = line.geoms if hasattr(line, "geoms") else [line]
        for g in geoms:
            if g.is_empty or g.length < 1e-6:
                continue
            g = simplify_and_round(g, tol)
            parts = g.geoms if g.geom_type == "MultiLineString" else [g]
            for p in parts:
                if p.geom_type != "LineString":
                    continue
                c = round_coords(p.coords)
                if len(c) >= 2:
                    out.append(c)
    return out


def ring_points(lat, lon, radius_km, n=RING_PTS):
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((lon + dlon * math.cos(a), lat + dlat * math.sin(a)))
    return pts


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", help="write a debug PNG preview to this path")
    args = ap.parse_args()

    t0 = time.time()
    boundary = None
    try:
        boundary = fetch_boundary()
    except Exception as e:
        print("    boundary fetch failed entirely: %s" % e, flush=True)
        raise
    print("    polygon area km2: %.1f  bounds: %s" % (
        boundary.area * 111.32 * 62.06,
        [round(v, 4) for v in boundary.bounds],
    ), flush=True)

    # roads/water/greens
    roads_raw, water_raw, waterways_raw, greens_raw = fetch_features()

    # clip circle around center: physical 8 km (degree-corrected)
    clip_circle = Polygon(ring_points(CENTER_LAT, CENTER_LON, 8.0))
    roads = process_roads(roads_raw, clip_circle)
    print("    roads kept: %d" % len(roads), flush=True)

    water = process_polys(water_raw, boundary, SIMPLIFY["water"], MIN_AREA["water"])
    waterways = process_lines(waterways_raw, boundary, SIMPLIFY["water"])
    greens = process_polys(greens_raw, boundary, SIMPLIFY["green"], MIN_AREA["green"])
    print("    water:%d waterways:%d greens:%d" % (len(water), len(waterways), len(greens)), flush=True)

    # rings
    rings = []
    for km in RING_KM:
        pts = ring_points(CENTER_LAT, CENTER_LON, km)
        rings.append({"km": km, "c": round_coords(pts)})

    # cities
    cities = []
    for name, lat, lon in CITIES:
        cities.append({
            "n": name,
            "km": round(haversine_km(CENTER_LAT, CENTER_LON, lat, lon)),
            "lat": r6(lat),
            "lon": r6(lon),
        })
    cities.sort(key=lambda c: c["km"])
    print("    cities:", ", ".join("%s=%dkm" % (c["n"], c["km"]) for c in cities), flush=True)

    # boundary rings (simplify, largest polygon)
    b = boundary.simplify(SIMPLIFY["boundary"], preserve_topology=True)
    if b.geom_type == "MultiPolygon":
        b = max(list(b.geoms), key=lambda p: p.area)
    boundary_rings = [round_coords(list(b.exterior.coords))]

    data = {
        "center": [r6(CENTER_LAT), r6(CENTER_LON)],
        "boundary": boundary_rings,
        "roads": roads,
        "water": water,
        "waterways": waterways,
        "greens": greens,
        "rings": rings,
        "cities": cities,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(OUT_PATH, "wb") as f:
        f.write(raw)
    gz = gzip.compress(raw, mtime=0)

    pts = {
        "boundary": sum(len(r) for r in boundary_rings),
        "roads": sum(len(r["c"]) for r in roads),
        "water": sum(len(r) for r in water),
        "waterways": sum(len(r) for r in waterways),
        "greens": sum(len(r) for r in greens),
        "rings": sum(len(r["c"]) for r in rings),
    }
    print("=" * 60, flush=True)
    print("WROTE %s" % OUT_PATH, flush=True)
    print("raw  : %6.1f KB" % (len(raw) / 1024), flush=True)
    print("gzip : %6.1f KB" % (len(gz) / 1024), flush=True)
    print("points:", pts, flush=True)
    print("elapsed %.1f s" % (time.time() - t0), flush=True)

    if args.preview:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 8))
            xs, ys = [], []
            for ring in boundary_rings:
                xx = [p[0] for p in ring]; yy = [p[1] for p in ring]
                ax.fill(xx, yy, fc="#faf6ee", ec="#e0662f", lw=1.5)
                xs += xx; ys += yy
            for g in greens:
                xx = [p[0] for p in g]; yy = [p[1] for p in g]
                ax.fill(xx, yy, fc="#cfe0b8", ec="none")
            for w in water:
                xx = [p[0] for p in w]; yy = [p[1] for p in w]
                ax.fill(xx, yy, fc="#9ec3e6", ec="none")
            for wl in waterways:
                xx = [p[0] for p in wl]; yy = [p[1] for p in wl]
                ax.plot(xx, yy, color="#9ec3e6", lw=2.5)
            for r in roads:
                xx = [p[0] for p in r["c"]]; yy = [p[1] for p in r["c"]]
                ax.plot(xx, yy, color="#888", lw=1.2 if r["t"] != "p" else 2.2)
            for r in rings:
                xx = [p[0] for p in r["c"]]; yy = [p[1] for p in r["c"]]
                ax.plot(xx, yy, ls="--", color="#c98a5f", lw=1)
            ax.plot(CENTER_LON, CENTER_LAT, "o", color="#E44D24", ms=8)
            for c in cities:
                ax.plot(c["lon"], c["lat"], "o", color="#555", ms=4)
                ax.annotate("%s %dкм" % (c["n"], c["km"]), (c["lon"], c["lat"]), fontsize=7)
            ax.set_aspect(1 / math.cos(math.radians(CENTER_LAT)))
            ax.set_title("delivery preview vladimir")
            fig.savefig(args.preview, dpi=110)
            print("preview saved:", args.preview, flush=True)
        except Exception as e:
            print("preview failed:", e, flush=True)


if __name__ == "__main__":
    main()