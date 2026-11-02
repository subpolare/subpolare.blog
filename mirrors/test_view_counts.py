from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.core import signing
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings

from mirrors.view_counts import BATCH_SIZE, MAX_BODY_SIZE, MAX_COUNT, SIGNING_SALT


@override_settings(SITE_REGION="ru", MIRROR_SIGNING_KEY="views-test-key")
class ViewIngestionTests(SimpleTestCase):
    def payload(self, **changes):
        return {"region": "com", "views": [{"post_id": str(uuid4()), "count": 5}], **changes}

    def send(self, payload, key="views-test-key", salt=SIGNING_SALT):
        token = signing.dumps(payload, key=key, salt=salt)
        return self.client.post("/_mirror/views", data=token, content_type="text/plain")

    def test_rejects_unsigned_wrong_key_and_navigation_signatures(self):
        self.assertEqual(self.client.post("/_mirror/views", data="unsigned", content_type="text/plain").status_code, 403)
        self.assertEqual(self.send(self.payload(), key="other-key").status_code, 403)
        self.assertEqual(self.send(self.payload(), salt="mirror-hop").status_code, 403)

    def test_expired_signature_is_rejected(self):
        with patch("django.core.signing.time.time", return_value=1):
            token = signing.dumps(self.payload(), key="views-test-key", salt=SIGNING_SALT)
        self.assertEqual(self.client.post("/_mirror/views", data=token, content_type="text/plain").status_code, 403)

    @override_settings(SITE_REGION="com")
    def test_com_cannot_receive_or_change_canonical_counts(self):
        self.assertEqual(self.send(self.payload()).status_code, 403)

    @override_settings(MIRROR_SIGNING_KEY="")
    def test_missing_key_disables_ingestion(self):
        self.assertEqual(self.send(self.payload()).status_code, 503)

    def test_only_post_is_supported(self):
        self.assertEqual(self.client.get("/_mirror/views").status_code, 405)

    def test_oversized_body_is_rejected(self):
        response = self.client.post("/_mirror/views", data="x" * (MAX_BODY_SIZE + 1), content_type="text/plain")
        self.assertEqual(response.status_code, 413)

    def test_invalid_batches_never_touch_database(self):
        row = {"post_id": str(uuid4()), "count": 5}
        invalid = [None, [], {}, self.payload(region="ru"), self.payload(views=[]),
            self.payload(views="wrong"), self.payload(views=[row, row]),
            self.payload(views=[row] * (BATCH_SIZE + 1)),
            self.payload(views=[None]), self.payload(views=[{}]),
            self.payload(views=[{**row, "post_id": "invalid"}]),
            self.payload(views=[{**row, "post_id": 10}])]
        invalid.extend(self.payload(views=[{**row, "count": value}])
            for value in (-1, MAX_COUNT + 1, True, 1.5, "5", None))
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.send(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn("no-store", response["Cache-Control"])


@override_settings(SITE_REGION="com", MIRROR_SIGNING_KEY="views-test-key")
class ViewWorkerTests(SimpleTestCase):
    def test_batches_are_signed_and_sent_only_through_private_tunnel(self):
        from mirrors.management.commands.mirror_views_sync import sync_views
        batches = [[(uuid4(), 17)], [(uuid4(), 3)]]
        session = Mock()
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True}
        session.post.return_value.__enter__ = Mock(return_value=response)
        session.post.return_value.__exit__ = Mock(return_value=False)
        with patch("mirrors.management.commands.mirror_views_sync.local_snapshots", return_value=iter(batches)):
            sync_views(session)
        self.assertEqual(session.post.call_count, 2)
        for call, batch in zip(session.post.call_args_list, batches):
            self.assertEqual(call.args, ("http://ru_tunnel:8022/_mirror/views",))
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertEqual(call.kwargs["timeout"], (3, 10))
            self.assertEqual(call.kwargs["headers"]["Host"], "subpolare.ru")
            self.assertEqual(signing.loads(call.kwargs["data"], key="views-test-key", salt=SIGNING_SALT),
                {"region": "com", "views": [{"post_id": str(batch[0][0]), "count": batch[0][1]}]})

    def test_once_fails_safely_without_printing_credentials(self):
        with patch("mirrors.management.commands.mirror_views_sync.sync_views", side_effect=requests.Timeout("secret")), \
                self.assertRaisesMessage(CommandError, "View synchronization failed; local counters retained."):
            call_command("mirror_views_sync", once=True)

    def test_continuous_worker_retries_and_reports_recovery(self):
        output = Mock()
        errors = Mock()
        with patch("mirrors.management.commands.mirror_views_sync.sync_views", side_effect=[requests.Timeout(), None]) as sync, \
                patch("mirrors.management.commands.mirror_views_sync.time.sleep", side_effect=[None, KeyboardInterrupt]), \
                self.assertRaises(KeyboardInterrupt):
            call_command("mirror_views_sync", stdout=output, stderr=errors)
        self.assertEqual(sync.call_count, 2)
        self.assertIn("local counters retained", errors.write.call_args.args[0])
        self.assertIn("complete", output.write.call_args.args[0])

    @override_settings(SITE_REGION="ru")
    def test_ru_command_reconciles_local_history_without_network(self):
        with patch("mirrors.management.commands.mirror_views_sync.reconcile_ru_views") as reconcile, \
                patch("mirrors.management.commands.mirror_views_sync.requests.Session") as session:
            call_command("mirror_views_sync", once=True, stdout=Mock())
        reconcile.assert_called_once()
        session.assert_not_called()

    def test_missing_key_or_invalid_interval_is_rejected(self):
        with override_settings(MIRROR_SIGNING_KEY=""), self.assertRaises(CommandError):
            call_command("mirror_views_sync", once=True)
        with self.assertRaises(CommandError):
            call_command("mirror_views_sync", interval=0)
