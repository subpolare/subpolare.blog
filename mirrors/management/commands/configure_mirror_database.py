"""One-time bootstrap, invoked explicitly using the database owner credentials."""
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg2 import sql
from psycopg2.extensions import make_dsn

from mirrors.management.commands.prepare_mirror_publication import TABLES


class Command(BaseCommand):
    help = "Bootstrap restricted replication/application roles from mounted secret files."

    def add_arguments(self, parser):
        parser.add_argument("--source", action="store_true")
        parser.add_argument("--target", action="store_true")

    def handle(self, *args, **options):
        if options["source"] == options["target"]:
            raise CommandError("Choose --source or --target")
        password = Path("/bootstrap/replication.password").read_text().strip()
        if options["source"]:
            if settings.SITE_REGION != "ru":
                raise CommandError("Wrong region")
            call_command("prepare_mirror_publication")
            with connection.cursor() as cursor:
                media_password = Path("/bootstrap/media.password").read_text().strip()
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='blog_media_worker'")
                if not cursor.fetchone():
                    cursor.execute("CREATE ROLE blog_media_worker LOGIN")
                cursor.execute(sql.SQL("ALTER ROLE blog_media_worker PASSWORD {}").format(sql.Literal(media_password)))
                cursor.execute("GRANT CONNECT ON DATABASE subpolare_ru TO blog_media_worker")
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='blog_replicator'")
                if not cursor.fetchone():
                    cursor.execute("CREATE ROLE blog_replicator LOGIN REPLICATION")
                cursor.execute(sql.SQL("ALTER ROLE blog_replicator PASSWORD {}").format(sql.Literal(password)))
                cursor.execute("GRANT CONNECT ON DATABASE subpolare_ru TO blog_replicator")
                cursor.execute("GRANT USAGE ON SCHEMA public TO blog_replicator")
                for table in TABLES:
                    cursor.execute(sql.SQL("GRANT SELECT ON {} TO blog_replicator").format(sql.Identifier(table)))
        else:
            if settings.SITE_REGION != "com":
                raise CommandError("Wrong region")
            app_password = Path("/bootstrap/application.password").read_text().strip()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='blog_reader'")
                if not cursor.fetchone():
                    cursor.execute("CREATE ROLE blog_reader LOGIN")
                cursor.execute(sql.SQL("ALTER ROLE blog_reader PASSWORD {}").format(sql.Literal(app_password)))
                cursor.execute("GRANT CONNECT ON DATABASE subpolare_ru TO blog_reader")
                cursor.execute("GRANT USAGE ON SCHEMA public TO blog_reader")
                cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO blog_reader")
                cursor.execute("GRANT INSERT, UPDATE, DELETE ON mirrors_localpostviews, django_session TO blog_reader")
                cursor.execute("SELECT 1 FROM pg_subscription WHERE subname='blog_content_from_ru'")
                if not cursor.fetchone():
                    # Migration 0003 seeds map places; initial replication must
                    # start with empty content tables on this newly created DB.
                    cursor.execute("SELECT count(*) FROM posts")
                    if cursor.fetchone()[0]:
                        raise CommandError("Target contains posts; refusing initial subscription")
                    cursor.execute("DELETE FROM map_mapplace")
                    dsn = make_dsn(host="ru_tunnel", port=5432, dbname="subpolare_ru", user="blog_replicator", password=password)
                    cursor.execute(sql.SQL("CREATE SUBSCRIPTION blog_content_from_ru CONNECTION {} PUBLICATION blog_content WITH (slot_name='blog_netcup', copy_data=true)").format(sql.Literal(dsn)))
        self.stdout.write("Restricted database access configured.")
