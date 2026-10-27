"""Push owned media after filesystem/DB events, with reconciliation on restart."""
import os
import fcntl
from pathlib import Path
import select
import subprocess
import time

import psycopg2
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SSH = "ssh -i /mirror-secrets/media_sync -o UserKnownHostsFile=/mirror-secrets/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=10"
SOURCES = (("/pepic-media/", "uploads/"), ("/legacy-images/", "legacy/images/"), ("/legacy-videos/", "legacy/videos/"))


def synchronize():
    with open("/tmp/blog-media-sync.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _synchronize()


def _synchronize():
    for source, target in SOURCES:
        subprocess.run([
            "rsync", "-rt", "--safe-links", "--no-perms", "--omit-dir-times",
            "--timeout=90", "--exclude=.mirror-synced", "-e", SSH,
            source, "subpolare@5.181.51.194:" + target,
        ], check=True, timeout=600)
    marker = Path("/tmp/.mirror-synced")
    marker.write_text(str(int(time.time())))
    subprocess.run(["rsync", "-t", "--timeout=30", "-e", SSH, str(marker),
                    "subpolare@5.181.51.194:uploads/"], check=True, timeout=60)


class Command(BaseCommand):
    help = "Synchronize media after writes and every 60 seconds; never delete destination files."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if settings.SITE_REGION != "ru":
            raise CommandError("Media source must be RU")
        if options["once"]:
            synchronize()
            return
        database = settings.DATABASES["default"]
        while True:
            watcher = connection = None
            try:
                connection = psycopg2.connect(dbname=database["NAME"], user=database["USER"],
                    password=database["PASSWORD"], host=database["HOST"], port=database["PORT"], connect_timeout=10)
                connection.autocommit = True
                with connection.cursor() as cursor:
                    cursor.execute("LISTEN mirror_content_changed")
                watcher = subprocess.Popen(["inotifywait", "-m", "-r", "-q", "-e", "close_write,moved_to,create,delete",
                    "--format", "%w%f", *[source for source, _ in SOURCES]], stdout=subprocess.PIPE)
                os.set_blocking(watcher.stdout.fileno(), False)
                while watcher.poll() is None:
                    synchronize()
                    self.stdout.write("Media synchronized successfully.")
                    ready, _, _ = select.select([connection, watcher.stdout], [], [], 60)
                    if connection in ready:
                        connection.poll()
                        connection.notifies.clear()
                    if watcher.stdout in ready:
                        os.read(watcher.stdout.fileno(), 1048576)
                    # Coalesce multi-file uploads; the 60-second reconciliation
                    # also recovers missed events / inotify queue overflows.
                    time.sleep(2)
            except (psycopg2.Error, OSError, subprocess.SubprocessError):
                self.stderr.write("Media synchronization interrupted; retrying in 15 seconds.")
                time.sleep(15)
            finally:
                if watcher:
                    watcher.terminate()
                    watcher.wait(timeout=10)
                if connection:
                    connection.close()
