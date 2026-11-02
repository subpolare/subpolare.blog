from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from django.core import signing
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.template import Context
from django.http import HttpResponse

from mirrors.models import LocalPostViews, MirrorViewBaseline, PostViewTotals
from mirrors.view_counts import SIGNING_SALT, local_snapshots, merge_totals, record_view, reconcile_ru_views
from posts.models import Post
from posts.templatetags.posts import show_post


class MirrorPersistenceTests(TestCase):
    def setUp(self):
        self.post = Post.objects.create(type="blog", slug="mirror-test", title="Mirror", text="Text",
            author="test", created_at=datetime.utcnow(), view_count=27)

    def test_local_counter_is_not_overwritten_by_content_update(self):
        LocalPostViews.objects.create(post_id=self.post.pk, count=12)
        PostViewTotals.objects.create(post_id=self.post.pk, ru_count=12, com_count=5)
        Post.objects.filter(pk=self.post.pk).update(title="Changed", view_count=99)
        self.post.refresh_from_db()
        self.assertEqual(self.post.local_view_count, 12)
        self.assertEqual(self.post.total_view_count, 17)

    def test_read_increments_local_counter_without_updating_replicated_post(self):
        with patch("posts.views.render_post", return_value=HttpResponse("ok")):
            self.client.get(self.post.get_absolute_url())
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 27)
        self.assertEqual(self.post.local_view_count, 1)
        self.assertEqual(self.post.total_view_count, 1)

    @override_settings(SITE_REGION="com")
    def test_rendering_on_mirror_does_not_write_content_cache(self):
        show_post(Context({"clickers": {}, "user_votes": set()}), self.post)
        self.post.refresh_from_db()
        self.assertIsNone(self.post.html_cache)

    @override_settings(SITE_REGION="com")
    def test_direct_reaction_write_to_mirror_is_rejected(self):
        response = self.client.post("/clickers/blocks/mirror-test/hello/")
        self.assertEqual(response.status_code, 503)


@override_settings(SITE_REGION="ru", MIRROR_SIGNING_KEY="views-test-key")
class ViewSyncPersistenceTests(TestCase):
    def setUp(self):
        self.post = Post.objects.create(type="blog", slug="count-test", title="Count", text="Text",
            author="test", created_at=datetime.utcnow(), view_count=100)
        LocalPostViews.objects.create(post_id=self.post.pk, count=120)
        reconcile_ru_views()

    def send(self, count, post_id=None):
        token = signing.dumps({"region": "com", "views": [
            {"post_id": str(post_id or self.post.pk), "count": count}
        ]}, key="views-test-key", salt=SIGNING_SALT)
        return Client(enforce_csrf_checks=True).post("/_mirror/views", data=token, content_type="text/plain")

    def test_historical_counts_and_retry_after_lost_ack_are_counted_once(self):
        for count, expected in ((17, 137), (17, 137), (12, 137), (20, 140)):
            self.assertEqual(self.send(count).status_code, 200)
            self.assertEqual(self.post.total_view_count, expected)
        self.assertEqual(self.post.local_view_count, 120)

    def test_ru_reads_and_com_deliveries_preserve_each_other(self):
        self.send(17)
        record_view(self.post.pk)
        self.send(18)
        record_view(self.post.pk)
        self.assertEqual(self.post.total_view_count, 140)
        self.assertEqual(self.post.local_view_count, 122)
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 100)
        self.assertEqual(PostViewTotals.objects.get(pk=self.post.pk).com_count, 18)

    @override_settings(SITE_REGION="com")
    def test_com_read_during_outage_only_changes_durable_local_count(self):
        with patch("posts.views.render_post", return_value=HttpResponse("readable")):
            self.assertContains(self.client.get(self.post.get_absolute_url()), "readable")
        self.assertEqual(self.post.local_view_count, 121)
        self.assertEqual(self.post.total_view_count, 120)
        with self.assertRaises(ValueError):
            merge_totals([(self.post.pk, 999, 999)])

    def test_deleted_post_snapshot_does_not_create_total(self):
        unknown = uuid4()
        self.assertEqual(self.send(15, unknown).status_code, 200)
        self.assertFalse(PostViewTotals.objects.filter(pk=unknown).exists())

    def test_snapshot_pagination_is_complete(self):
        LocalPostViews.objects.bulk_create([LocalPostViews(post_id=uuid4(), count=2) for _ in range(6)])
        with patch("mirrors.view_counts.BATCH_SIZE", 2):
            batches = list(local_snapshots())
        self.assertEqual([len(batch) for batch in batches], [2, 2, 2, 1])
        self.assertEqual(len({post_id for batch in batches for post_id, _ in batch}), 7)

    @override_settings(SITE_REGION="com")
    def test_only_views_after_baseline_are_sent_and_local_history_is_preserved(self):
        MirrorViewBaseline.objects.create(post_id=self.post.pk, count=120)
        self.assertEqual(list(local_snapshots()), [[(self.post.pk, 0)]])
        record_view(self.post.pk)
        self.assertEqual(list(local_snapshots()), [[(self.post.pk, 1)]])
        self.assertEqual(self.post.local_view_count, 121)
        self.assertEqual(MirrorViewBaseline.objects.get(pk=self.post.pk).count, 120)
        self.assertEqual(self.post.total_view_count, 120)

    @override_settings(SITE_REGION="com")
    def test_new_com_posts_have_zero_baseline(self):
        post_id = uuid4()
        record_view(post_id)
        self.assertEqual(dict(row for batch in local_snapshots() for row in batch)[post_id], 1)


@override_settings(SITE_REGION="ru")
class ConcurrentViewsTests(TransactionTestCase):
    def test_simultaneous_ru_reads_and_reordered_com_snapshots_do_not_lose_views(self):
        post_id = uuid4()

        def read_or_sync(index):
            try:
                record_view(post_id)
                merge_totals([(post_id, 0, index + 1)])
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(read_or_sync, range(30)))
        total = PostViewTotals.objects.get(pk=post_id)
        self.assertEqual((total.ru_count, total.com_count), (30, 30))
        self.assertEqual(LocalPostViews.objects.get(pk=post_id).count, 30)


class ViewMigrationTests(TransactionTestCase):
    def test_history_is_seeded_only_on_ru_and_com_keeps_local_views(self):
        previous = [("mirrors", "0001_local_views")]
        current = [("mirrors", "0002_postviewtotals")]
        for region in ("ru", "com"):
            with self.subTest(region=region), override_settings(SITE_REGION=region):
                executor = MigrationExecutor(connection)
                executor.migrate(previous)
                try:
                    old = executor.loader.project_state(previous).apps.get_model("mirrors", "LocalPostViews")
                    old.objects.all().delete()
                    post_id = uuid4()
                    old.objects.create(post_id=post_id, count=12345)
                    executor = MigrationExecutor(connection)
                    executor.migrate(current)
                    self.assertEqual(LocalPostViews.objects.get(pk=post_id).count, 12345)
                    if region == "ru":
                        row = PostViewTotals.objects.get(pk=post_id)
                        self.assertEqual((row.ru_count, row.com_count), (12345, 0))
                    else:
                        self.assertFalse(PostViewTotals.objects.exists())
                finally:
                    executor = MigrationExecutor(connection)
                    executor.migrate(executor.loader.graph.leaf_nodes())


class ViewBaselineMigrationTests(TransactionTestCase):
    def test_com_history_is_excluded_without_changing_ru_total(self):
        previous = [("mirrors", "0002_postviewtotals")]
        current = [("mirrors", "0003_mirrorviewbaseline")]
        for region in ("ru", "com"):
            with self.subTest(region=region), override_settings(SITE_REGION=region):
                executor = MigrationExecutor(connection)
                executor.migrate(previous)
                try:
                    LocalPostViews.objects.all().delete()
                    PostViewTotals.objects.all().delete()
                    post_id = uuid4()
                    LocalPostViews.objects.create(post_id=post_id, count=325)
                    PostViewTotals.objects.create(post_id=post_id, ru_count=4040)
                    MigrationExecutor(connection).migrate(current)
                    total = PostViewTotals.objects.get(pk=post_id)
                    self.assertEqual((total.ru_count, total.com_count), (4040, 0))
                    self.assertEqual(LocalPostViews.objects.get(pk=post_id).count, 325)
                    if region == "com":
                        self.assertEqual(MirrorViewBaseline.objects.get(pk=post_id).count, 325)
                        self.assertEqual(list(local_snapshots()), [[(post_id, 0)]])
                        record_view(post_id)
                        self.assertEqual(list(local_snapshots()), [[(post_id, 1)]])
                    else:
                        self.assertFalse(MirrorViewBaseline.objects.exists())
                        self.assertEqual(list(local_snapshots()), [[(post_id, 325)]])
                finally:
                    executor = MigrationExecutor(connection)
                    executor.migrate(executor.loader.graph.leaf_nodes())

    @override_settings(SITE_REGION="com")
    def test_refuses_to_rebase_com_views_already_accepted_by_ru(self):
        previous = [("mirrors", "0002_postviewtotals")]
        current = [("mirrors", "0003_mirrorviewbaseline")]
        MigrationExecutor(connection).migrate(previous)
        try:
            PostViewTotals.objects.create(post_id=uuid4(), ru_count=4040, com_count=325)
            with self.assertRaisesMessage(RuntimeError, "COM views already accepted by RU"):
                MigrationExecutor(connection).migrate(current)
        finally:
            PostViewTotals.objects.all().delete()
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
