import hashlib
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import urlsplit

from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import SimpleTestCase, override_settings
from PIL import Image
import requests

from common.image_previews import prepare_previews, PreviewPreparationError
from common.images import preview_sources, storage_path
from posts.management.commands.warm_homepage_previews import Command
from posts.models import Post


class AutomaticPreviewTests(SimpleTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        override = override_settings(
            PEPIC_STORAGE_ROOT=self.temp.name,
            PEPIC_MEDIA_ORIGIN="https://media.example.test",
        )
        override.enable()
        self.addCleanup(override.disable)
        self.name = "a" * 64 + ".jpg"
        self.url = "https://media.example.test/" + self.name
        self.write_image(self.name, "orig", (900, 1800))
        self.session = Mock()
        self.session.get.side_effect = self.generate_preview
        self.command = Command(stdout=StringIO(), stderr=StringIO())

    def write_image(self, name, directory, size):
        path = storage_path(name, directory)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color=(40, 80, 120)).save(path)
        return path

    def generate_preview(self, url, **kwargs):
        length, name = urlsplit(url).path.strip("/").split("/")
        with Image.open(storage_path(name)) as source:
            source.thumbnail((int(length), int(length)))
            self.write_image(name, f"resize/{length}", source.size)
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.iter_content.return_value = [b"image"]
        return response

    def run_pass(self, posts):
        with patch.object(Post.objects, "filter") as query:
            query.return_value.only.return_value = posts
            failed = self.command.prepare_covers(self.session)
        query.assert_called_once_with(is_visible_on_home_page=True)
        query.return_value.only.assert_called_once_with("image", "og_image")
        return failed

    def test_new_cover_generates_three_previews_and_preserves_original(self):
        original = storage_path(self.name).read_bytes()
        self.assertEqual(prepare_previews(self.url, self.session), 3)
        self.assertEqual(self.session.get.call_count, 3)
        self.assertIn("?v=1 240w", preview_sources(self.url))
        self.assertIn("?v=1 720w", preview_sources(self.url))
        self.assertEqual(hashlib.sha256(storage_path(self.name).read_bytes()).digest(),
                         hashlib.sha256(original).digest())
        for call in self.session.get.call_args_list:
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertEqual(call.kwargs["timeout"], (5, 20))

    def test_ready_previews_are_not_downloaded_or_replaced_on_next_pass(self):
        prepare_previews(self.url, self.session)
        paths = [storage_path(self.name, f"resize/{size}") for size in (480, 960, 1440)]
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
        self.session.reset_mock()
        self.assertEqual(prepare_previews(self.url, self.session), 0)
        self.session.get.assert_not_called()
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths])

    def test_partial_failure_retries_only_missing_sizes(self):
        def interrupted(url, **kwargs):
            if "/960/" in url:
                raise requests.Timeout("temporary outage")
            return self.generate_preview(url, **kwargs)
        self.session.get.side_effect = interrupted
        self.assertTrue(self.run_pass([Post(image=self.url)]))
        self.assertIn("/480/", preview_sources(self.url))
        self.assertNotIn("/960/", preview_sources(self.url))
        self.session.reset_mock()
        self.session.get.side_effect = self.generate_preview
        self.assertFalse(self.run_pass([Post(image=self.url)]))
        self.assertEqual(self.session.get.call_count, 2)
        self.assertNotIn("/480/", self.session.get.call_args_list[0].args[0])

    def test_new_draft_and_changed_cover_are_detected_on_subsequent_passes(self):
        self.assertFalse(self.run_pass([]))
        post = Post(image=self.url, is_visible=False, lang="en")
        self.assertFalse(self.run_pass([post]))
        second = "b" * 64 + ".jpg"
        self.write_image(second, "orig", (1800, 1200))
        post.image = "https://media.example.test/" + second
        self.session.reset_mock()
        self.assertFalse(self.run_pass([post]))
        self.assertEqual(self.session.get.call_count, 3)
        self.assertTrue(all(second in c.args[0] for c in self.session.get.call_args_list))
        self.assertIn("1440w", preview_sources(post.image))

    def test_video_fallback_and_duplicate_covers_are_prepared_once(self):
        self.assertFalse(self.run_pass([
            Post(image="https://media.example.test/video.mp4", og_image=self.url),
            Post(image=self.url),
            Post(og_image=self.url),
        ]))
        self.assertEqual(self.session.get.call_count, 3)

    def test_failed_cover_does_not_stop_other_covers(self):
        missing = self.url.replace("a" * 64, "0" * 64)
        self.assertTrue(self.run_pass([Post(image=missing), Post(image=self.url)]))
        self.assertEqual(self.session.get.call_count, 3)
        self.assertIn("will be retried", self.command.stderr._out.getvalue())

    def test_external_empty_and_unsafe_urls_are_never_requested(self):
        for url in (None, "", "https://external.test/" + self.name,
                    "https://media.example.test/../../secret.jpg",
                    "https://media.example.test/480/" + self.name):
            self.assertEqual(prepare_previews(url, self.session), 0)
        self.session.get.assert_not_called()

    def test_small_original_is_not_upscaled(self):
        self.write_image(self.name, "orig", (600, 400))
        self.assertEqual(prepare_previews(self.url, self.session), 1)
        self.assertIn("/480/", self.session.get.call_args.args[0])

    def test_http_failure_or_missing_output_is_not_reported_as_ready(self):
        for status in (200, 302, 500):
            with self.subTest(status=status):
                response = MagicMock()
                response.__enter__.return_value = response
                response.status_code = status
                response.iter_content.return_value = []
                self.session.get.side_effect = None
                self.session.get.return_value = response
                with self.assertRaises(PreviewPreparationError):
                    prepare_previews(self.url, self.session)
                self.assertNotIn("/480/", preview_sources(self.url))

    def test_worker_recovers_from_database_failure_and_waits_an_hour(self):
        with patch.object(self.command, "prepare_covers",
                          side_effect=[OperationalError("offline"), False]) as prepare, \
                patch("posts.management.commands.warm_homepage_previews.close_old_connections"), \
                patch("posts.management.commands.warm_homepage_previews.time.sleep",
                      side_effect=[None, KeyboardInterrupt]) as sleep:
            with self.assertRaises(KeyboardInterrupt):
                self.command.handle(once=False, interval=3600)
        self.assertEqual(prepare.call_count, 2)
        self.assertEqual([call.args for call in sleep.call_args_list], [(3600,), (3600,)])
        self.assertIn("will retry", self.command.stderr._out.getvalue())
        parser = self.command.create_parser("manage.py", "warm_homepage_previews")
        self.assertEqual(parser.parse_args([]).interval, 3600)

    def test_once_exits_with_failure_instead_of_silently_succeeding(self):
        with patch.object(self.command, "prepare_covers", return_value=True), \
                patch("posts.management.commands.warm_homepage_previews.close_old_connections"):
            with self.assertRaisesMessage(CommandError, "Some previews"):
                self.command.handle(once=True, interval=3600)

    def test_missing_mount_stops_worker_before_any_requests(self):
        with override_settings(PEPIC_STORAGE_ROOT=""), \
                patch.object(self.command, "prepare_covers") as prepare:
            with self.assertRaisesMessage(CommandError, "Mount Pepic"):
                self.command.handle(once=True, interval=3600)
            prepare.assert_not_called()
