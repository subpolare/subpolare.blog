"""Run with a disposable PostgreSQL via subpolare.integration_test_settings."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from clickers.models import Clicker
from posts.models import Post


class RetiredCommentsMigrationTests(TransactionTestCase):
    def test_removes_comments_and_their_votes_but_preserves_block_clickers(self):
        previous = [
            ("comments", "0005_alter_comment_options"),
            ("clickers", "0003_alter_clicker_block_alter_clicker_comment"),
            ("posts", "0005_post_reading_time"),
        ]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            now = timezone.now()
            post = apps.get_model("posts", "Post").objects.create(
                type="blog", slug="retirement", text="[clicker Useful]", lang="ru",
                created_at=now, published_at=now, updated_at=now,
            )
            comment = apps.get_model("comments", "Comment").objects.create(
                post=post, text="Old comment", created_at=now, updated_at=now,
            )
            OldClicker = apps.get_model("clickers", "Clicker")
            OldClicker.objects.create(post=post, comment=comment, block=str(comment.pk), ipaddress="127.0.0.1", useragent="test")
            block_vote = OldClicker.objects.create(post=post, block="Useful", ipaddress="127.0.0.1", useragent="test")
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            self.assertNotIn("comments", connection.introspection.table_names())
            self.assertEqual(list(Clicker.objects.values_list("pk", flat=True)), [block_vote.pk])
            self.assertEqual(Post.objects.get(pk=post.pk).text, "[clicker Useful]")
            for path in ("/comments/create/", f"/comments/{comment.pk}/delete/", f"/clickers/comments/{comment.pk}/"):
                self.assertEqual(self.client.post(path, {}, follow=True).status_code, 404)
            response = self.client.post("/clickers/blocks/retirement/Useful/", REMOTE_ADDR="127.0.0.2")
            self.assertContains(response, 'class="clicker ')
            self.assertEqual(Clicker.objects.filter(post_id=post.pk, block="Useful").count(), 2)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
