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
SOURCES = {
    "ne_110m_lakes.geojson": (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/ne_110m_lakes.geojson", "eb02ecc86c82004fccbf979058bfabbbd6c2d07968c7844d38eb1c9152d2ffc9"),
    "ne_110m_rivers_lake_centerlines.geojson": (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/ne_110m_rivers_lake_centerlines.geojson", "55aa4497405afc07cdc931b7fbe062c4d6693ba2a550c0d24899953f5d507c8d"),
    "ne_110m_land.geojson": (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/ne_110m_land.geojson", "9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9"),
    "ne_110m_populated_places.geojson": (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/ne_110m_populated_places.geojson", "a86028b083182b68c7620fc6e1a8a47ee547cb9cd2fb62ccbb78bea786440899"),
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


def prepare(directory):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, source_name in (("land", "land"), ("lakes", "lakes"), ("rivers", "rivers_lake_centerlines")):
        collection = json.loads(source(f"ne_110m_{source_name}.geojson", directory))
        write_json(f"{name}.json", {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": {
                "type": feature["geometry"]["type"],
                "coordinates": round_coordinates(feature["geometry"]["coordinates"]),
            }} for feature in collection["features"]
        ]})
    places = json.loads(source("ne_110m_populated_places.geojson", directory))
    cities = []
    for feature in places["features"]:
        props = feature["properties"]
        cities.append({
            "coordinates": round_coordinates(feature["geometry"]["coordinates"]),
            "ru": props.get("NAME_RU") or props["NAME"],
            "en": props.get("NAME_EN") or props["NAME"],
            "rank": props["SCALERANK"], "population": props["POP_MAX"],
        })
    write_json("cities.json", sorted(cities, key=lambda city: (city["rank"], -city["population"], city["en"])))
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
    print(f"TOTAL: {total:,} bytes gzip (budget 200,000)")
    if total > 200_000:
        raise ValueError("Map asset budget exceeded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--pack-only", action="store_true")
    args = parser.parse_args()
    if not args.pack_only:
        prepare(args.source_dir)
    pack()
