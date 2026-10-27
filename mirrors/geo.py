"""Local GeoIP lookup. Missing/stale inputs never make the site unavailable."""
import ipaddress
import json
from functools import lru_cache
from pathlib import Path
import time

import maxminddb
from django.conf import settings


@lru_cache(maxsize=2)
def reader(path, modified):
    return maxminddb.open_database(path)


def country(ip):
    try:
        path = Path(settings.MIRROR_RUNTIME) / "country.mmdb"
        data = reader(str(path), path.stat().st_mtime_ns).get(ip) or {}
        return data.get("country", {}).get("iso_code")
    except (OSError, ValueError, maxminddb.InvalidDatabaseError):
        return None


def target_available():
    try:
        data = json.loads((Path(settings.MIRROR_RUNTIME) / "peer.json").read_text())
        return data.get("healthy") is True and 0 <= time.time() - data["checked_at"] < 120
    except (OSError, ValueError, KeyError, TypeError):
        return False


@lru_cache(maxsize=2)
def crawler_networks(path, modified):
    return [ipaddress.ip_network(value) for value in json.loads(Path(path).read_text())]


def verified_crawler(ip):
    try:
        address = ipaddress.ip_address(ip)
        path = Path(settings.MIRROR_RUNTIME) / "crawlers.json"
        return any(address in network for network in crawler_networks(str(path), path.stat().st_mtime_ns))
    except (OSError, ValueError, TypeError):
        return False
