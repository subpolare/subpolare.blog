from unittest.mock import patch

from django.contrib.auth.hashers import check_password, is_password_usable
from django.test import SimpleTestCase

from users.models import User


class UserAccountManagerTests(SimpleTestCase):
    def test_password_is_hashed_before_every_save(self):
        for method in ("create_user", "create_superuser"):
            for password in ("test-password", "", "пароль 🔐", "pbkdf2_sha256$1$salt$hash"):
                with self.subTest(method=method, password=password):
                    saved_passwords = []
                    with patch.object(User, "save", autospec=True) as save:
                        save.side_effect = lambda user: saved_passwords.append(user.password)
                        user = getattr(User.objects, method)(
                            "Reader", "Reader@EXAMPLE.TEST", password, city="Moscow"
                        )

                    self.assertEqual(len(saved_passwords), 1)
                    self.assertNotEqual(saved_passwords[0], password)
                    self.assertTrue(check_password(password, saved_passwords[0]))
                    self.assertFalse(check_password("wrong-password", saved_passwords[0]))
                    self.assertEqual(user.password, saved_passwords[0])
                    self.assertEqual(user.email, "Reader@example.test")
                    self.assertEqual(user.username, "Reader")
                    self.assertEqual(user.city, "Moscow")
                    self.assertEqual(user.is_staff, method == "create_superuser")
                    self.assertEqual(user.is_superuser, method == "create_superuser")

    def test_missing_password_is_unusable_before_every_save(self):
        for method, kwargs in (
            ("create_user", {}),
            ("create_user", {"password": None}),
            ("create_superuser", {"password": None}),
        ):
            with self.subTest(method=method, kwargs=kwargs):
                saved_passwords = []
                with patch.object(User, "save", autospec=True) as save:
                    save.side_effect = lambda user: saved_passwords.append(user.password)
                    user = getattr(User.objects, method)("Reader", "reader@example.test", **kwargs)

                self.assertEqual(len(saved_passwords), 1)
                self.assertFalse(is_password_usable(saved_passwords[0]))
                self.assertEqual(user.password, saved_passwords[0])

    def test_missing_email_is_rejected_without_saving(self):
        for method in ("create_user", "create_superuser"):
            with self.subTest(method=method), patch.object(User, "save") as save:
                with self.assertRaisesMessage(ValueError, "Email address is required!"):
                    getattr(User.objects, method)("Reader", "", "test-password")
                save.assert_not_called()

    def test_explicit_permission_flags_are_preserved(self):
        for method in ("create_user", "create_superuser"):
            for flag in (False, True):
                with self.subTest(method=method, flag=flag), patch.object(User, "save"):
                    user = getattr(User.objects, method)(
                        "Reader", "reader@example.test", None,
                        is_staff=flag, is_superuser=flag,
                    )
                    self.assertEqual(user.is_staff, flag)
                    self.assertEqual(user.is_superuser, flag)
