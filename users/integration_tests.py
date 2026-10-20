"""Run explicitly with subpolare.integration_test_settings and disposable PostgreSQL."""
from django.contrib.auth.hashers import check_password, is_password_usable
from django.db.models.signals import post_save
from django.test import TestCase
from django.urls import reverse

from users.models import User


class UserPasswordPersistenceTests(TestCase):
    def test_existing_superuser_keeps_password_permissions_and_admin_access(self):
        existing = User(
            username="Existing admin", email="existing-admin@example.test",
            is_staff=True, is_superuser=True,
        )
        existing.set_password("existing-admin-password")
        existing.save()
        original_hash = existing.password

        for method in ("create_user", "create_superuser"):
            getattr(User.objects, method)(
                "New user", f"new-{method}@example.test", "new-password"
            )

        existing.refresh_from_db()
        self.assertEqual(existing.password, original_hash)
        self.assertTrue(existing.is_staff)
        self.assertTrue(existing.is_superuser)
        self.assertTrue(self.client.login(
            email=existing.email, password="existing-admin-password"
        ))
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        existing.refresh_from_db()
        self.assertEqual(existing.password, original_hash)

    def test_every_database_write_contains_a_hash_or_unusable_password(self):
        for method in ("create_user", "create_superuser"):
            for index, password in enumerate(("test-password", "", "пароль 🔐", None)):
                with self.subTest(method=method, password=password):
                    saved_passwords = []

                    def record_password(sender, instance, using, **kwargs):
                        saved_passwords.append(
                            User.objects.using(using).get(pk=instance.pk).password
                        )

                    post_save.connect(record_password, sender=User)
                    try:
                        user = getattr(User.objects, method)(
                            "Reader", f"{method}-{index}@EXAMPLE.TEST", password
                        )
                    finally:
                        post_save.disconnect(record_password, sender=User)

                    user.refresh_from_db()
                    self.assertEqual(saved_passwords, [user.password])
                    if password is None:
                        self.assertFalse(is_password_usable(user.password))
                    else:
                        self.assertNotEqual(user.password, password)
                        self.assertTrue(check_password(password, user.password))
                        self.assertTrue(user.check_password(password))
                        self.assertFalse(user.check_password("wrong-password"))
                    self.assertEqual(user.email, f"{method}-{index}@example.test")
                    self.assertEqual(user.is_staff, method == "create_superuser")
                    self.assertEqual(user.is_superuser, method == "create_superuser")
