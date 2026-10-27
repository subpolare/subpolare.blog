"""Refresh local country/crawler databases and probe the other mirror."""
import gzip
import ipaddress
import json
import os
from pathlib import Path
import time
from threading import Thread

import maxminddb
import requests
from django.conf import settings
from django.core.management.base import BaseCommand


def atomic_write(path, data):
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def refresh_geo(directory):
    # Country data: DB-IP Lite (https://db-ip.com), CC BY 4.0.
    from datetime import datetime, timedelta, timezone
    for offset in (0, 1):
        month = (datetime.now(timezone.utc).replace(day=1) - timedelta(days=offset)).strftime("%Y-%m")
        response = requests.get(f"https://download.db-ip.com/free/dbip-country-lite-{month}.mmdb.gz", timeout=(10, 90))
        if response.status_code == 404:
            continue
        response.raise_for_status()
        data = gzip.decompress(response.content)
        candidate = directory / "country.download.mmdb"
        candidate.write_bytes(data)
        with maxminddb.open_database(str(candidate)) as database:
            if not database.get("8.8.8.8"):
                raise ValueError("Empty country database")
        os.replace(candidate, directory / "country.mmdb")
        return
    raise ValueError("No recent country database available")


def refresh_crawlers(directory):
    networks = []
    for url in (
        "https://developers.google.com/static/search/apis/ipranges/googlebot.json",
        "https://www.bing.com/toolbox/bingbot.json",
    ):
        response = requests.get(url, timeout=(10, 30))
        response.raise_for_status()
        for prefix in response.json()["prefixes"]:
            value = prefix.get("ipv4Prefix") or prefix.get("ipv6Prefix")
            networks.append(str(ipaddress.ip_network(value)))
    atomic_write(directory / "crawlers.json", json.dumps(networks).encode())


def refresh_databases(directory, stderr):
    for name, update in (("country.mmdb", refresh_geo), ("crawlers.json", refresh_crawlers)):
        path = directory / name
        try:
            if not path.exists() or time.time() - path.stat().st_mtime > 86400:
                update(directory)
        except (requests.RequestException, OSError, ValueError, KeyError, maxminddb.InvalidDatabaseError):
            stderr.write(f"Could not refresh {name}; keeping previous data.")


class Command(BaseCommand):
    help = "Refresh GeoIP daily and check peer health every 30 seconds."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        directory = Path(settings.MIRROR_RUNTIME)
        directory.mkdir(parents=True, exist_ok=True)
        peer = "subpolare.ru" if settings.SITE_REGION == "com" else "subpolare.com"
        refresh = None
        previous_local_ready = None
        while True:
            # Slow provider downloads must not stall health monitoring.
            if refresh is None or not refresh.is_alive():
                refresh = Thread(target=refresh_databases, args=(directory, self.stderr), daemon=True)
                refresh.start()
            healthy = False
            try:
                response = requests.get(f"https://{peer}/_mirror/health", timeout=(3, 5), allow_redirects=False)
                healthy = response.status_code == 200 and response.json().get("ready") is True
            except (requests.RequestException, ValueError):
                pass
            atomic_write(directory / "peer.json", json.dumps({"checked_at": time.time(), "healthy": healthy}).encode())
            local_ready = False
            try:
                response = requests.get("http://blog_app:8022/_mirror/health",
                    headers={"Host": "subpolare." + settings.SITE_REGION}, timeout=(3, 5))
                local_ready = response.status_code == 200 and response.json().get("ready") is True
            except (requests.RequestException, ValueError):
                pass
            if local_ready != previous_local_ready:
                self.stderr.write("Mirror freshness recovered." if local_ready else
                    "ALERT: mirror not ready; check replication and media synchronization.")
                previous_local_ready = local_ready
            atomic_write(directory / "local.json", json.dumps({"checked_at": time.time(), "ready": local_ready}).encode())
            if options["once"]:
                refresh.join()
                return
            time.sleep(30)
