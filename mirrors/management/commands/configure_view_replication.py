"""Add view totals to an existing mirror without reconfiguring credentials."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from mirrors.view_counts import reconcile_ru_views


class Command(BaseCommand):
    help = "Explicit owner-only deployment step: publish/subscribe to RU view totals."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            if settings.SITE_REGION == "ru":
                cursor.execute("SELECT 1 FROM pg_publication WHERE pubname = 'blog_content'")
                if not cursor.fetchone():
                    raise CommandError("Bootstrap the content mirror first.")
                # Also catches views written by the old app during migration.
                reconcile_ru_views()
                cursor.execute("GRANT SELECT ON mirrors_postviewtotals TO blog_replicator")
                cursor.execute("""
                    SELECT 1 FROM pg_publication_tables
                    WHERE pubname = 'blog_content' AND schemaname = 'public'
                      AND tablename = 'mirrors_postviewtotals'
                """)
                if not cursor.fetchone():
                    cursor.execute("ALTER PUBLICATION blog_content ADD TABLE mirrors_postviewtotals")
            elif settings.SITE_REGION == "com":
                cursor.execute("SELECT 1 FROM pg_subscription WHERE subname = 'blog_content_from_ru'")
                if not cursor.fetchone():
                    raise CommandError("Bootstrap the content mirror first.")
                cursor.execute("GRANT SELECT ON mirrors_postviewtotals TO blog_reader")
                cursor.execute("""
                    SELECT 1 FROM pg_subscription_rel r
                    JOIN pg_subscription s ON s.oid = r.srsubid
                    WHERE s.subname = 'blog_content_from_ru'
                      AND r.srrelid = 'mirrors_postviewtotals'::regclass
                """)
                if not cursor.fetchone():
                    cursor.execute("SELECT EXISTS(SELECT 1 FROM mirrors_postviewtotals)")
                    if cursor.fetchone()[0]:
                        raise CommandError("Target totals must be empty for initial replication; refusing to overwrite.")
                    cursor.execute("ALTER SUBSCRIPTION blog_content_from_ru REFRESH PUBLICATION WITH (copy_data = true)")
                    cursor.execute("""
                        SELECT 1 FROM pg_subscription_rel r
                        JOIN pg_subscription s ON s.oid = r.srsubid
                        WHERE s.subname = 'blog_content_from_ru'
                          AND r.srrelid = 'mirrors_postviewtotals'::regclass
                    """)
                    if not cursor.fetchone():
                        raise CommandError("RU has not published view totals; configure RU first.")
            else:
                raise CommandError("Unknown site region.")
        self.stdout.write("View totals replication configured.")
