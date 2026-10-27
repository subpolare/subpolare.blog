"""End-to-end check against two disposable containers, never production."""
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import psycopg2

SOURCE, TARGET = "blog_validation_source", "blog_validation_target"
Path("/bootstrap").mkdir(exist_ok=True)
Path("/bootstrap/replication.password").write_text("replication-test-only")
Path("/bootstrap/application.password").write_text("application-test-only")
Path("/bootstrap/media.password").write_text("media-test-only")


def manage(host, region, *arguments):
    environment = {**os.environ, "DEBUG": "false", "SENTRY_DSN": "", "POSTGRES_HOST": host,
        "POSTGRES_DB": "subpolare_ru", "POSTGRES_USER": "maptest", "POSTGRES_PASSWORD": "validation-only", "SITE_REGION": region}
    subprocess.run([sys.executable, "manage.py", *arguments], env=environment, check=True)


def connect(host, user="maptest", password="validation-only"):
    connection = psycopg2.connect(host=host, dbname="subpolare_ru", user=user, password=password)
    connection.autocommit = True
    return connection


def scalar(connection, query, parameters=()):
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        row = cursor.fetchone()
        return row[0] if row else None


def eventually(test):
    for _ in range(60):
        if test():
            return
        time.sleep(1)
    raise AssertionError("Replication did not converge within 60 seconds")


manage(SOURCE, "ru", "migrate", "--noinput")
manage(TARGET, "com", "migrate", "--noinput")
manage(SOURCE, "ru", "configure_mirror_database", "--source")
manage(TARGET, "com", "configure_mirror_database", "--target")
source, target = connect(SOURCE), connect(TARGET)
eventually(lambda: scalar(target, "SELECT count(*) FROM pg_subscription_rel WHERE srsubstate != 'r'") == 0)
post_id = str(uuid.uuid4())
manage(SOURCE, "ru", "shell", "-c", "from posts.models import Post; from datetime import datetime; Post.objects.create(id='" + post_id + "', type='blog', slug='replication-check', title='Before', text='Test', author='test', created_at=datetime.utcnow())")
eventually(lambda: scalar(target, "SELECT title FROM posts WHERE id=%s", (post_id,)) == "Before")
reader = connect(TARGET, "blog_reader", "application-test-only")
with reader.cursor() as cursor:
    cursor.execute("INSERT INTO mirrors_localpostviews (post_id,count) VALUES (%s,17)", (post_id,))
    try:
        cursor.execute("UPDATE posts SET title='Forbidden' WHERE id=%s", (post_id,))
    except psycopg2.errors.InsufficientPrivilege:
        pass
    else:
        raise AssertionError("Mirror app may edit shared content")
with source.cursor() as cursor:
    cursor.execute("UPDATE posts SET title='After' WHERE id=%s", (post_id,))
eventually(lambda: scalar(target, "SELECT title FROM posts WHERE id=%s", (post_id,)) == "After")
assert scalar(target, "SELECT count FROM mirrors_localpostviews WHERE post_id=%s", (post_id,)) == 17
with source.cursor() as cursor:
    cursor.execute("DELETE FROM posts WHERE id=%s", (post_id,))
eventually(lambda: scalar(target, "SELECT title FROM posts WHERE id=%s", (post_id,)) is None)
assert not scalar(target, "SELECT has_table_privilege('blog_reader','posts','INSERT')")
assert not scalar(source, "SELECT has_table_privilege('blog_replicator','users','SELECT')")
assert not scalar(source, "SELECT has_table_privilege('blog_replicator','posts','UPDATE')")
print("PASS: replicated insert/update/delete; local counter retained; shared content and users protected.")
