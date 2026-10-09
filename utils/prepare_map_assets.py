"""Rebuild local map data/vendor assets and deterministic gzip siblings.

poetry run python utils/prepare_map_assets.py [--source-dir /path/to/downloads]
poetry run python utils/prepare_map_assets.py --pack-only  # after JS/CSS edits
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "frontend/static/map"
REVISION = "ca96624a56bd078437bca8184e78163e5039ad19"
GEOMETRY_TOLERANCE = 0.05  # degrees; roughly 5.6 km at the equator
ASSET_BUDGET = 325_000
MAX_RIVER_RANK = 2  # Only the largest rivers; keep their lake centerline segments.
# Tiny ocean islands look like stray dots at the site's overview scale.
# Keep these places searchable in the editor, but omit their background dots.
HIDDEN_CITY_DOTS = {
    (179.217, -8.517),  # Funafuti
    (144.75, 13.47),  # Hagåtña
    (171.38, 7.103),  # Majuro
    (73.509, 4.172),  # Malé
    (134.627, 7.487),  # Melekeok
    (158.15, 6.917),  # Palikir
    (-149.567, -17.533),  # Papeete
    (173.018, 1.338),  # South Tarawa
    (55.45, -4.617),  # Victoria, Seychelles
    (-171.769, -13.836),  # Apia
    (-175.221, -21.139),  # Nuku'alofa
    (-170.707, -14.277),  # Pago Pago
}
SOURCES = {
    "ne_10m_populated_places_simple.geojson": (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/ne_10m_populated_places_simple.geojson", "fd3fa867a320cbd5c5b6bb5bc550afeec2939fb2cef688e508007282a55ac42f"),
    "ne_50m_lakes.geojson": (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/ne_50m_lakes.geojson", "d350b75978b26fe839b797c2c529b2fb8f47fb3983c03f4964e36d5df9378a52"),
    "ne_50m_rivers_lake_centerlines.geojson": (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/ne_50m_rivers_lake_centerlines.geojson", "f286e0ce978fde999ca2d7a78c764be08542e19b63cded52b05c12d5173ccc51"),
    "ne_50m_land.geojson": (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/ne_50m_land.geojson", "e874b27a51d146452be360cafb3cc50c86001074a67d534113e6534682f9826b"),
    "ne_50m_populated_places.geojson": (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/ne_50m_populated_places.geojson", "da4662b7bbfeb897d02f228c5839131dce27acff5717630f91ccff4f67828ee7"),
    "leaflet-1.9.4.tgz": ("https://registry.npmjs.org/leaflet/-/leaflet-1.9.4.tgz", "84c65a256e50657896f54c33bd857b6849ebe94c817803be818bf32a3dde0b77"),
}


def source(name, directory):
    url, digest = SOURCES[name]
    if directory:
        data = (directory / name).read_bytes()
    else:
        with urlopen(url, timeout=30) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Source checksum mismatch: {name}")
    return data


def write_json(name, data):
    (OUTPUT / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")


def round_coordinates(value):
    return [round_coordinates(item) for item in value] if isinstance(value, list) else round(value, 3)


def simplify_line(points, tolerance):
    """Douglas–Peucker simplification, retaining endpoints and detailed bends."""
    if len(points) <= 2:
        return points
    first, last = points[0], points[-1]
    dx, dy = last[0] - first[0], last[1] - first[1]
    length = dx * dx + dy * dy
    farthest, split = 0, 0
    for index, point in enumerate(points[1:-1], 1):
        fraction = max(0, min(1, ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / length)) if length else 0
        distance = (point[0] - first[0] - fraction * dx) ** 2 + (point[1] - first[1] - fraction * dy) ** 2
        if distance > farthest:
            farthest, split = distance, index
    if farthest > tolerance * tolerance:
        return simplify_line(points[:split + 1], tolerance)[:-1] + simplify_line(points[split:], tolerance)
    return [first, last]


def simplify_coordinates(coordinates):
    if not coordinates:
        return []
    if isinstance(coordinates[0][0], (int, float)):
        simplified = simplify_line(coordinates, GEOMETRY_TOLERANCE)
        # Preserve tiny islands/lakes rather than collapsing their closed rings.
        if coordinates[0] == coordinates[-1] and len(simplified) < 4:
            simplified = coordinates
        return round_coordinates(simplified)
    return [simplify_coordinates(part) for part in coordinates]


def without_antarctica(geometry):
    """Omit Antarctic polygons and islands south of 60°S."""
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    polygons = [polygon for polygon in polygons if any(point[1] >= -60 for point in polygon[0])]
    return {"type": geometry["type"], "coordinates": (
        polygons[0] if polygons else []
    ) if geometry["type"] == "Polygon" else polygons}


def prepare(directory):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, source_name in (("land", "land"), ("lakes", "lakes"), ("rivers", "rivers_lake_centerlines")):
        collection = json.loads(source(f"ne_50m_{source_name}.geojson", directory))
        if name == "land":
            for feature in collection["features"]:
                feature["geometry"] = without_antarctica(feature["geometry"])
        write_json(f"{name}.json", {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": {
                "type": feature["geometry"]["type"],
                "coordinates": simplify_coordinates(feature["geometry"]["coordinates"]),
            }} for feature in collection["features"] if feature["geometry"]["coordinates"]
            and (name != "rivers" or feature["properties"]["scalerank"] <= MAX_RIVER_RANK)
        ]})
    prepare_cities(directory)
    vendor = OUTPUT / "leaflet-1.9.4"
    vendor.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(source("leaflet-1.9.4.tgz", directory))) as archive:
        # Extract only the required files, with explicit safe target paths.
        for src, dest in (("package/dist/leaflet.js", "leaflet.js"), ("package/dist/leaflet.css", "leaflet.css"), ("package/LICENSE", "LICENSE")):
            (vendor / dest).write_bytes(archive.extractfile(src).read())
    from PIL import Image, ImageDraw
    placeholder = Image.new("RGB", (128, 128), "#bcc0c2")
    draw = ImageDraw.Draw(placeholder)
    draw.ellipse((42, 42, 86, 86), fill="#e5e7e8")
    placeholder.save(ROOT / "map/placeholder.webp", format="WEBP", quality=70, method=6)


def prepare_cities(directory):
    places = json.loads(source("ne_50m_populated_places.geojson", directory))
    cities = []
    for feature in places["features"]:
        props = feature["properties"]
        cities.append({
            "coordinates": round_coordinates(feature["geometry"]["coordinates"]),
            "ru": props.get("NAME_RU") or props["NAME"],
            "en": props.get("NAME_EN") or props["NAME"],
            "rank": props["SCALERANK"], "population": props["POP_MAX"],
            **({"hidden": True} if tuple(round_coordinates(feature["geometry"]["coordinates"])) in HIDDEN_CITY_DOTS else {}),
        })
    cities.sort(key=lambda city: (city["rank"], -city["population"], city["en"]))
    # Add only coordinate pairs for smaller towns; no new geometry or browser requests.
    detailed = json.loads(source("ne_10m_populated_places_simple.geojson", directory))
    candidates = sorted(detailed["features"], key=lambda feature: (
        feature["properties"]["scalerank"], -feature["properties"]["pop_max"],
        feature["properties"]["name"],
    ))
    remaining = sum(not city.get("hidden") for city in cities)
    for feature in candidates:
        if not 1000 <= feature["properties"]["pop_max"] <= 150000:
            continue
        coordinates = round_coordinates(feature["geometry"]["coordinates"])
        if coordinates[1] < -60:
            continue
        # Exclude duplicate towns, suburbs and previously hidden island capitals.
        if any(abs(coordinates[1] - city["coordinates"][1]) < 0.15 and
               abs((coordinates[0] - city["coordinates"][0] + 180) % 360 - 180) < 0.15
               for city in cities):
            continue
        cities.append({"coordinates": coordinates, "secondary": True})
        remaining -= 1
        if not remaining:
            break
    if remaining:
        raise ValueError("Not enough additional towns to double the visible city dots")
    write_json("cities.json", cities)


def pack():
    files = sorted(path for path in OUTPUT.rglob("*") if path.suffix in {".js", ".css", ".json"} and path.name != "manifest.json")
    digest = hashlib.sha256()
    total = 0
    for path in files:
        data = path.read_bytes()
        digest.update(str(path.relative_to(OUTPUT)).encode() + b"\0" + data)
        # GzipFile fixes the OS header byte across Python 3.12/3.14 as well.
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", compresslevel=9, mtime=0) as archive:
            archive.write(data)
        compressed = buffer.getvalue()
        path.with_name(path.name + ".gz").write_bytes(compressed)
        total += len(compressed)
        print(f"{path.relative_to(OUTPUT)}: {len(data):,} bytes; gzip {len(compressed):,}")
    write_json("manifest.json", {"version": digest.hexdigest()[:16], "gzip_bytes": total, "natural_earth_revision": REVISION})
    print(f"TOTAL: {total:,} bytes gzip (budget {ASSET_BUDGET:,})")
    if total > ASSET_BUDGET:
        raise ValueError("Map asset budget exceeded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--pack-only", action="store_true")
    parser.add_argument("--cities-only", action="store_true", help="Refresh city coordinates without rebuilding geography/vendor assets")
    args = parser.parse_args()
    if args.cities_only:
        prepare_cities(args.source_dir)
    elif not args.pack_only:
        prepare(args.source_dir)
    pack()
