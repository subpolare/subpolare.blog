"""Explicit deployment operation; never run from an HTTP request."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

TABLES = ("posts", "clickers", "map_mapplace", "map_mapmarker")


class Command(BaseCommand):
    help = "Create/update the RU-only content publication and update notifications."

    def handle(self, *args, **options):
        if settings.SITE_REGION != "ru":
            raise CommandError("Only the RU source may publish content")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_publication WHERE pubname = 'blog_content'")
            operation = "ALTER" if cursor.fetchone() else "CREATE"
            clause = "SET TABLE" if operation == "ALTER" else "FOR TABLE"
            cursor.execute(f"{operation} PUBLICATION blog_content {clause} " + ", ".join(TABLES))
            cursor.execute("""
                CREATE OR REPLACE FUNCTION mirror_notify_content() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                    PERFORM pg_notify('mirror_content_changed', TG_TABLE_NAME);
                    RETURN NULL;
                END $$
            """)
            for table in TABLES:
                cursor.execute(f"DROP TRIGGER IF EXISTS mirror_content_change ON {table}")
                cursor.execute(f"CREATE TRIGGER mirror_content_change AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION mirror_notify_content()")
        self.stdout.write("Content publication ready; local counters, accounts and sessions are excluded.")
