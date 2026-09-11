#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_delivery_data.py — delivery-zone datasets for zbi.mir-betona33.ru.
Generates compact GeoJSON-like JSON per city:
  public/delivery/{slug}.json   (slug: vladimir, sudogda, suzdal, raduzhny,
                                 kovrov, gus-khrustalny, yuryev-polsky)

Data sources: OpenStreetMap via Overpass (mirrors) + local shapely processing.
Layers per JSON:
  center   [lat, lon]         — OSM place=city/town node
  boundary [ring of [lon,lat]]— largest polygon of the town boundary relation
                                (for towns w/o admin polygon: built-up footprint)
  roads    [{t: p|s|t, c}]    — primary/secondary/tertiary, clipped to ~8 km circle
  water    [rings]            — water polygons (within boundary for vladimir, else belt)
  waterways[rings]            — river lines
  greens   [rings]            — parks/forest/meadow/...
  rings    [{km, c}]          — 5/10/20/35/60 km around center
  cities   [{n, km, lat, lon}]— other cities of the area (no Ivanovo), km from center

Usage:
  python gen_delivery_data.py                 # all 7 cities
  python gen_delivery_data.py --city suzdal   # single city
  python gen_delivery_data.py --city suzdal --preview previews/delivery

Gzip target: <= 60 KB per city (adaptive simplification loop).
Boundary raw responses are cached in scripts/osm_cache/ (60 days).
"""
import os
import sys
import time
import math
import json
import gzip
import argparse
import requests

from shapely.geometry import LineString, Polygon, MultiPolygon
from shapely.ops import unary_union, polygonize

UA = "zbi-delivery-gen/1.0 (+https://zbi.mir-betona33.ru)"
MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


# ----------------------------------------------------------------------------- config
# badge list for `cities` layer — the 7 cities of the delivery area (no Ivanovo).
# Coordinates: OSM place=city/town nodes (fetched via Overpass node(id:...);out;).
CITIES = [  # name, lat, lon
    ("Владимир", 56.1288899, 40.4075203),
    ("Судогда", 55.951570, 40.858689),
    ("Суздаль", 56.419391, 40.448789),
    ("Радужный", 55.993959, 40.329441),
    ("Ковров", 56.374371, 41.311644),
    ("Гусь-Хрустальный", 55.614997, 40.670867),
    ("Юрьев-Польский", 56.497195, 39.678640),
]

# per-city config:
#   rel  — OSM boundary relation (place=city/town, or admin relation covering the town)
#   builtup — if True, build the boundary from landuse=residential footprint (Юрьев-Польский)
#   clip — "boundary": water/greens/waterways inside town boundary (vladimir, keeps approved look)
#          "belt":     water/greens/waterways inside ~8 km circle from center (new cities)
CITY_CFG = {
    "vladimir":       {"name": "Владимир",         "rel": 1991003, "lat": 56.1288899, "lon": 40.4075203, "clip": "boundary", "builtup": False},
    "sudogda":        {"name": "Судогда",          "rel": 5713779, "lat": 55.951570,  "lon": 40.858689,  "clip": "belt",    "builtup": False},
    "suzdal":         {"name": "Суздаль",          "rel": 1390203, "lat": 56.419391,  "lon": 40.448789,  "clip": "belt",    "builtup": False},
    "raduzhny":       {"name": "Радужный",         "rel": 3441002, "lat": 55.993959,  "lon": 40.329441,  "clip": "belt",    "builtup": False},
    "kovrov":         {"name": "Ковров",           "rel": 2350024, "lat": 56.374371,  "lon": 41.311644,  "clip": "belt",    "builtup": False},
    "gus-khrustalny": {"name": "Гусь-Хрустальный", "rel": 1582363, "lat": 55.614997,  "lon": 40.670867,  "clip": "belt",    "builtup": False},
    "yuryev-polsky":  {"name": "Юрьев-Польский",   "rel": None,    "lat": 56.497195,  "lon": 39.678640,  "clip": "belt",    "builtup": True},
}

ROAD_TYPES = ("primary", "secondary", "tertiary")
RING_KM = (5, 10, 20, 35, 60)
RING_PTS = 72

SIMPLIFY = {  # degrees (multiplied by 1.3^attempt when gzip overshoots 60 KB)
    "boundary": 0.0004,
    "road": 0.0002,
    "water": 0.0004,
    "green": 0.0005,
}

MIN_AREA = {  # deg^2
    "water": 1e-7,
    "green": 0.000001,
}

GZ_TARGET = 60 * 1024  # bytes
BELT_KM = 8.0           # local data belt for new cities
FETCH_KM = 9.0          # overpass bbox half-size

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "public", "delivery"))
CACHE_DIR = os.path.join(HERE, "osm_cache")
CACHE_MAX_AGE = 3600 * 24 * 60  # 60 days


# ----------------------------------------------------------------------------- io
def op(query, timeout=300, max_tries=3):
    """Run Overpass query with mirror fallback (direct POST, no proxy needed)."""
    last = None
    for attempt in range(max_tries):
        for mirror in MIRRORS:
            try:
                r = requests.post(
                    mirror, data={"data": query},
                    headers={"User-Agent": UA, "Accept": "*/*"},
                    timeout=timeout,
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


def ring_points(lat, lon, radius_km, n=RING_PTS):
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((lon + dlon * math.cos(a), lat + dlat * math.sin(a)))
    return pts


def load_json(fn):
    with open(fn, "r", encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------------- fetchers
def _polygon_from_ways(ways):
    """ways: list of way dicts with geometry list; returns largest polygon."""
    lines = [LineString([(p["lon"], p["lat"]) for p in w["geometry"]])
             for w in ways if len(w.get("geometry", [])) >= 2]
    if not lines:
        raise RuntimeError("no usable ways")
    merged = unary_union(lines)
    polys = [p for p in polygonize(merged) if not p.is_empty]
    if not polys:
        raise RuntimeError("polygonize gave no polygon")
    return max(polys, key=lambda p: p.area)


def _cached_or_fetch(cache_path, query):
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < CACHE_MAX_AGE:
            print("    from cache (%d s old)" % age, flush=True)
            return load_json(cache_path)
    print("    overpass fetch ...", flush=True)
    d = op(query)
    # NEVER cache a storm-truncated empty response: Overpass sometimes returns a
    # well-formed 200 with elements:[] when the mirror died mid-query. Persisting
    # that poisons the cache -> permanently empty layer even after the storm passes.
    # Refuse to write it (and refuse to memoize) so the next run retries the fetch.
    if not d.get("elements"):
        raise RuntimeError("empty Overpass response (elements=[]) for cache %s — not caching, storm guard" % cache_path)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    return d


def fetch_boundary(rel):
    """Boundary polygon from a relation id (place=city/town multipolygon)."""
    cx = os.path.join(CACHE_DIR, "boundary_rel_%d.json" % rel)
    q = "[out:json][timeout:180][maxsize:1073741824];rel(%d);out tags;rel(%d);way(r);out geom;" % (rel, rel)
    d = _cached_or_fetch(cx, q)
    return _polygon_from_ways(d["elements"])


def fetch_builtup_boundary(slug, lat, lon):
    """Synthetic town boundary from landuse=residential etc. (no admin polygon on OSM)."""
    cx = os.path.join(CACHE_DIR, "boundary_builtup_%s.json" % slug)
    q = (
        '[out:json][timeout:180][maxsize:1073741824];('
        'around:10000,%.5f,%.5f'
        ) % (lat, lon)
    q = (
        '[out:json][timeout:180][maxsize:1073741824];('
        'way["landuse"~"^(residential|industrial|commercial|retail|allotments|construction|brownfield)$"](around:10000,%.5f,%.5f);'
        ');out geom;' % (lat, lon)
    )
    d = _cached_or_fetch(cx, q)
    ways = [w for w in d.get("elements", [])
            if w["type"] == "way" and len(w.get("geometry", [])) >= 2]
    print("    builtup ways:", len(ways), flush=True)
    if not ways:
        raise RuntimeError("no builtup ways for %s" % slug)
    polys = [Polygon([(p["lon"], p["lat"]) for p in w["geometry"]]) for w in ways]
    polys = [p if p.is_valid else p.buffer(0) for p in polys]
    merged = unary_union([p for p in polys if not p.is_empty])
    if merged.is_empty:
        raise RuntimeError("builtup union empty for %s" % slug)
    merged = merged.buffer(0.00025, join_style=2)  # ~25 m smoothing
    if isinstance(merged, MultiPolygon):
        merged = max(list(merged.geoms), key=lambda p: p.area)
    return merged


def _bbox_str(lat, lon):
    dlat9 = FETCH_KM * 1000.0 / 111320.0
    dlon9 = FETCH_KM * 1000.0 / (111320.0 * math.cos(math.radians(lat)))
    return "%.5f,%.5f,%.5f,%.5f" % (lat - dlat9, lon - dlon9, lat + dlat9, lon + dlon9)


def fetch_features(slug, lat, lon):
    """roads/water/greens from a ~9 km bbox around the center.

    Split into 3 smaller Overpass requests (roads / water / greens) so each
    stays well under server limits; raw responses cached per city so a rerun
    (e.g. different simplification) does not hit Overpass again.
    """
    bbox = _bbox_str(lat, lon)
    print("    bbox %s ..." % bbox, flush=True)

    QUERIES = [
        ("roads", '[out:json][timeout:300][maxsize:1073741824];'
                  'way["highway"~"^(primary|secondary|tertiary)$"](%s);out geom;' % bbox),
        ("water", '[out:json][timeout:300][maxsize:1073741824];'
                  'way["natural"="water"](%s);'
                  'way["waterway"="riverbank"](%s);'
                  'way["waterway"="river"](%s);out geom;' % (bbox, bbox, bbox)),
        ("greens", '[out:json][timeout:300][maxsize:1073741824];'
                   'way["landuse"~"^(grass|forest|meadow|village_green|recreation_ground|orchard)$"](%s);'
                   'way["leisure"~"^(park|garden|nature_reserve|playground)$"](%s);'
                   'way["natural"~"^(wood|scrub)$"](%s);out geom;' % (bbox, bbox, bbox)),
    ]
    raw = {}
    for part, q in QUERIES:
        cx = os.path.join(CACHE_DIR, "features_%s_%s.json" % (slug, part))
        raw[part] = _cached_or_fetch(cx, q)
        print("    %s fetch done" % part, flush=True)

    roads, water, waterways, greens = [], [], [], []
    for part, d in raw.items():
        for w in d.get("elements", []):
            if w["type"] != "way":
                continue
            geom = w.get("geometry")
            if not geom or len(geom) < 2:
                continue
            tags = w.get("tags", {})
            coords = [(p["lon"], p["lat"]) for p in geom]
            if part == "roads":
                hw = tags.get("highway", "")
                if hw in ROAD_TYPES:
                    roads.append((hw, coords))
            elif part == "water":
                nat = tags.get("natural", "")
                ww = tags.get("waterway", "")
                if nat == "water" or ww == "riverbank":
                    water.append(coords)
                elif ww == "river":
                    waterways.append(coords)
            else:  # greens
                lu = tags.get("landuse", "")
                le = tags.get("leisure", "")
                nat = tags.get("natural", "")
                if (lu in ("grass", "forest", "meadow", "village_green", "recreation_ground", "orchard")
                        or le in ("park", "garden", "nature_reserve", "playground")
                        or nat in ("wood", "scrub")):
                    greens.append(coords)
    print("    fetched -> roads:%d water:%d waterways:%d greens:%d" % (
        len(roads), len(water), len(waterways), len(greens)), flush=True)
    return roads, water, waterways, greens


# ----------------------------------------------------------------------------- process
def process_roads(roads, clip_poly, tol):
    out = []
    for typ, coords in roads:
        line = LineString(coords)
        line = line.intersection(clip_poly)
        geoms = line.geoms if hasattr(line, "geoms") else [line]
        for g in geoms:
            if g.is_empty or g.length < 1e-6:
                continue
            g = g.simplify(tol, preserve_topology=True)
            if g.is_empty or g.geom_type not in ("LineString", "MultiLineString"):
                continue
            parts = g.geoms if g.geom_type == "MultiLineString" else [g]
            for p in parts:
                c = round_coords(p.coords)
                if len(c) >= 2:
                    out.append({"t": typ[0], "c": c})
    return out


def process_polys(rows, clip_poly, tol, min_area):
    out = []
    for ring in rows:
        p = Polygon(ring)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty:
            continue
        p = p.intersection(clip_poly)
        if p.is_empty:
            continue
        polys = list(p.geoms) if p.geom_type == "MultiPolygon" else [p]
        for pp in polys:
            if pp.area < min_area:
                continue
            pp = pp.simplify(tol, preserve_topology=True)
            if pp.geom_type != "Polygon" or pp.area < min_area:
                continue
            out.append(round_coords(list(pp.exterior.coords)))
    return out


def process_lines(rows, clip_poly, tol):
    out = []
    for coords in rows:
        line = LineString(coords)
        line = line.intersection(clip_poly)
        geoms = line.geoms if hasattr(line, "geoms") else [line]
        for g in geoms:
            if g.is_empty or g.length < 1e-6:
                continue
            g = g.simplify(tol, preserve_topology=True)
            parts = g.geoms if g.geom_type == "MultiLineString" else [g]
            for p in parts:
                if p.geom_type != "LineString":
                    continue
                c = round_coords(p.coords)
                if len(c) >= 2:
                    out.append(c)
    return out


def build_city(slug, cfg, fetches, tol_mult):
    """Run full pipeline for one city with tolerance multiplier tol_mult."""
    lat, lon = cfg["lat"], cfg["lon"]
    boundary = fetches["boundary"]
    roads_raw, water_raw, waterways_raw, greens_raw = fetches["features"]

    # clip polygon for water/greens/waterways
    belt_poly = Polygon(ring_points(lat, lon, BELT_KM))
    clip_poly = belt_poly if cfg["clip"] == "belt" else boundary

    # roads — clipped to the physical 8 km circle (like vladimir)
    roads = process_roads(roads_raw, belt_poly, SIMPLIFY["road"] * tol_mult)
    water = process_polys(water_raw, clip_poly, SIMPLIFY["water"] * tol_mult, MIN_AREA["water"])
    waterways = process_lines(waterways_raw, clip_poly, SIMPLIFY["water"] * tol_mult)
    greens = process_polys(greens_raw, clip_poly, SIMPLIFY["green"] * tol_mult, MIN_AREA["green"])

    # rings
    rings = [{"km": km, "c": round_coords(ring_points(lat, lon, km))} for km in RING_KM]

    # cities (badges): the other 6 cities of the area, km from this city's center
    cities = []
    for name, clat, clon in CITIES:
        if abs(clat - lat) < 1e-6 and abs(clon - lon) < 1e-6:
            continue
        cities.append({
            "n": name,
            "km": round(haversine_km(lat, lon, clat, clon)),
            "lat": r6(clat),
            "lon": r6(clon),
        })
    cities.sort(key=lambda c: c["km"])

    # boundary ring (simplify, largest polygon)
    b = boundary.simplify(SIMPLIFY["boundary"] * tol_mult, preserve_topology=True)
    if b.geom_type == "MultiPolygon":
        b = max(list(b.geoms), key=lambda p: p.area)
    if b.geom_type != "Polygon":
        raise RuntimeError("boundary not polygon for %s" % slug)
    boundary_rings = [round_coords(list(b.exterior.coords))]

    data = {
        "center": [r6(lat), r6(lon)],
        "boundary": boundary_rings,
        "roads": roads,
        "water": water,
        "waterways": waterways,
        "greens": greens,
        "rings": rings,
        "cities": cities,
    }
    stats = {
        "boundary": sum(len(r) for r in boundary_rings),
        "roads": sum(len(r["c"]) for r in roads),
        "water": sum(len(r) for r in water),
        "waterways": sum(len(r) for r in waterways),
        "greens": sum(len(r) for r in greens),
        "rings": sum(len(r["c"]) for r in rings),
    }
    return data, stats


def write_output(slug, data, stats, preview_prefix):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "%s.json" % slug)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as f:
        f.write(raw)
    gz = gzip.compress(raw, mtime=0)
    print("WROTE %s" % path, flush=True)
    print("raw  : %6.1f KB  gzip: %6.1f KB" % (len(raw) / 1024, len(gz) / 1024), flush=True)
    print("points:", stats, flush=True)

    if preview_prefix:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 8))
            lat, lon = data["center"]
            xs, ys = [], []
            for ring in data["boundary"]:
                xx = [p[0] for p in ring]; yy = [p[1] for p in ring]
                ax.fill(xx, yy, fc="#faf6ee", ec="#e0662f", lw=1.5)
                xs += xx; ys += yy
            for g in data["greens"]:
                xx = [p[0] for p in g]; yy = [p[1] for p in g]
                ax.fill(xx, yy, fc="#cfe0b8", ec="none")
            for w in data["water"]:
                xx = [p[0] for p in w]; yy = [p[1] for p in w]
                ax.fill(xx, yy, fc="#9ec3e6", ec="none")
            for wl in data["waterways"]:
                xx = [p[0] for p in wl]; yy = [p[1] for p in wl]
                ax.plot(xx, yy, color="#9ec3e6", lw=2.5)
            for r in data["roads"]:
                xx = [p[0] for p in r["c"]]; yy = [p[1] for p in r["c"]]
                ax.plot(xx, yy, color="#888", lw=1.2 if r["t"] != "p" else 2.2)
            for r in data["rings"]:
                xx = [p[0] for p in r["c"]]; yy = [p[1] for p in r["c"]]
                ax.plot(xx, yy, ls="--", color="#c98a5f", lw=1)
            ax.plot(lon, lat, "o", color="#E44D24", ms=8)
            for c in data["cities"]:
                ax.plot(c["lon"], c["lat"], "o", color="#555", ms=4)
                ax.annotate("%s %dкм" % (c["n"], c["km"]), (c["lon"], c["lat"]), fontsize=7)
            ax.set_aspect(1 / math.cos(math.radians(lat)))
            ax.set_title("delivery preview %s" % slug)
            pv = "%s.%s.png" % (preview_prefix, slug)
            fig.savefig(pv, dpi=110)
            plt.close(fig)
            print("preview saved:", pv, flush=True)
        except Exception as e:
            print("preview failed:", e, flush=True)

    return len(gz)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", help="slug to build (default: all)")
    ap.add_argument("--preview", help="prefix for debug PNG previews")
    args = ap.parse_args()

    slugs = [args.city] if args.city else list(CITY_CFG.keys())
    if args.city and args.city not in CITY_CFG:
        print("unknown city slug: %s (known: %s)" % (args.city, ", ".join(CITY_CFG)))
        sys.exit(1)

    t_start = time.time()
    for slug in slugs:
        cfg = CITY_CFG[slug]
        lat, lon = cfg["lat"], cfg["lon"]
        print("=" * 60, flush=True)
        print("BUILD %s (%s)  center %.5f, %.5f" % (slug, cfg["name"], lat, lon), flush=True)

        # fetch once (boundary + local features), reused across simplification attempts
        try:
            if cfg["builtup"]:
                boundary = fetch_builtup_boundary(slug, lat, lon)
            else:
                boundary = fetch_boundary(cfg["rel"])
        except Exception as e:
            print("    BOUNDARY FAILED for %s: %s — skipping" % (slug, e), flush=True)
            continue
        print("    boundary area km2: %.1f  bounds: %s" % (
            boundary.area * 111.32 * 62.06,
            [round(v, 4) for v in boundary.bounds],
        ), flush=True)

        try:
            features = fetch_features(slug, lat, lon)
        except Exception as e:
            print("    FEATURES FAILED for %s: %s — skipping" % (slug, e), flush=True)
            continue

        fetches = {"boundary": boundary, "features": features}

        # adaptive simplification: bump tolerance until gzip <= 60 KB (max 6 bumps)
        tol_mult = 1.0
        data = stats = None
        for attempt in range(6):
            data, stats = build_city(slug, cfg, fetches, tol_mult)
            raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            gz_len = len(gzip.compress(raw, mtime=0))
            print("    attempt %d: tol x%.2f  raw %.1f KB  gzip %.1f KB  (target <= %.0f KB)" % (
                attempt + 1, tol_mult, len(raw) / 1024, gz_len / 1024, GZ_TARGET / 1024), flush=True)
            if gz_len <= GZ_TARGET:
                break
            tol_mult *= 1.3
        else:
            print("    WARN: %s could not meet gzip target within 6 attempts" % slug, flush=True)

        write_output(slug, data, stats, args.preview)
        print("elapsed %.1f s" % (time.time() - t_start), flush=True)

    print("=" * 60, flush=True)
    print("DONE in %.1f s" % (time.time() - t_start), flush=True)


if __name__ == "__main__":
    main()