"""Deliver durable COM counters to RU independently of article requests."""
import time

import requests
from django.conf import settings
from django.core import signing
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections

from mirrors.view_counts import SIGNING_SALT, local_snapshots, reconcile_ru_views


def sync_views(session):
    for batch in local_snapshots():
        payload = {"region": "com", "views": [
            {"post_id": str(post_id), "count": count} for post_id, count in batch
        ]}
        body = signing.dumps(payload, key=settings.MIRROR_SIGNING_KEY, salt=SIGNING_SALT)
        # The existing SSH tunnel is private to the Compose network. No client
        # addresses, cookies or session identifiers leave COM.
        with session.post("http://ru_tunnel:8022/_mirror/views", data=body,
                headers={"Host": "subpolare.ru", "Content-Type": "text/plain"},
                timeout=(3, 10), allow_redirects=False) as response:
            if response.status_code != 200 or response.json().get("ok") is not True:
                raise ValueError("RU did not acknowledge the batch")
        # Never clear or decrement local counts: a lost acknowledgement simply
        # causes an idempotent retry, including after a worker restart.


class Command(BaseCommand):
    help = "Send COM view snapshots to RU every 15 seconds; on RU, reconcile local history once."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=15)

    def handle(self, *args, **options):
        if settings.SITE_REGION == "ru" and options["once"]:
            reconcile_ru_views()
            self.stdout.write("RU view history reconciled.")
            return
        if settings.SITE_REGION != "com":
            raise CommandError("Continuous synchronization runs on COM only; use --once on RU.")
        if not settings.MIRROR_SIGNING_KEY:
            raise CommandError("Set the shared MIRROR_SIGNING_KEY on both servers.")
        if options["interval"] < 1:
            raise CommandError("Interval must be positive.")
        with requests.Session() as session:
            session.trust_env = False
            failed = False
            while True:
                close_old_connections()
                try:
                    sync_views(session)
                except (requests.RequestException, DatabaseError, ValueError, AttributeError):
                    # Do not log payloads, signatures, connection strings or
                    # upstream error bodies. Counters remain in PostgreSQL.
                    if options["once"]:
                        raise CommandError("View synchronization failed; local counters retained.") from None
                    if not failed:
                        self.stderr.write("ALERT: view synchronization failed; local counters retained; retrying.")
                    failed = True
                else:
                    if failed or options["once"]:
                        self.stdout.write("View synchronization complete.")
                    failed = False
                    if options["once"]:
                        return
                finally:
                    close_old_connections()
                time.sleep(options["interval"])
