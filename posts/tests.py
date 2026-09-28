import json
from datetime import datetime
from unittest.mock import Mock, patch

import requests
from django.contrib.auth.models import AnonymousUser
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Model
from django.http import Http404
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.template import Context
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from common.markdown.markdown import markdown_comment, markdown_text
from posts.editor import MAX_IMAGE_SIZE, preview_post, upload_post_image
from posts.forms import PostEditForm
from posts.models import Post
from posts.templatetags.posts import show_post as render_post
from posts.views import edit_post, show_post
from rss.feeds import FullFeed
from users.models import User


class HeaderAdminLinkTests(SimpleTestCase):
    def render_header(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return render_to_string("common/header.html", request=request)

    def test_superuser_gets_full_page_link_to_admin_posts(self):
        html = self.render_header(User(is_superuser=True, is_staff=True))
        self.assertIn(
            f'href="{reverse("admin:posts_post_changelist")}" '
            'class="button button-inverted header-menu-item" hx-boost="false"',
            html,
        )
        self.assertIn("🔏", html)

    def test_admin_link_is_hidden_from_visitors_members_and_staff(self):
        for user in (AnonymousUser(), User(), User(is_staff=True)):
            with self.subTest(user=type(user).__name__, is_staff=user.is_staff):
                html = self.render_header(user)
                self.assertNotIn(reverse("admin:posts_post_changelist"), html)
                self.assertNotIn("🔏", html)


class EditorTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User(is_superuser=True, is_staff=True)
        self.reader = User(is_superuser=False, is_staff=True)
        self.post = Post(
            type="blog", slug="editor-test", title="Title", text="Original",
            html_cache="Cached", lang="ru", data={}, is_visible=False,
            created_at=datetime(2020, 1, 1), updated_at=datetime(2020, 1, 1),
            published_at=datetime(2020, 1, 1), view_count=7,
        )
        self.post._state.adding = False
        self.edit_url = reverse("edit_post", args=[self.post.type, self.post.slug])
        self.preview_url = reverse("preview_post", args=[self.post.type, self.post.slug])
        self.upload_url = reverse("upload_post_image")

    def request(self, method, url, data=None, user=None):
        request = getattr(self.factory, method)(url, data or {})
        request.user = self.admin if user is None else user
        return request

    def dispatch(self, request):
        match = resolve(request.path)
        return match.func(request, **match.kwargs)

    def image(self, content=b"fake-image", content_type="image/png"):
        return SimpleUploadedFile("example.png", content, content_type=content_type)

    def test_non_admin_cannot_read_or_write_editor_endpoints(self):
        with patch("posts.editor.get_object_or_404") as lookup, patch("posts.editor.requests.post") as upload:
            for user in (AnonymousUser(), self.reader):
                for url in (self.edit_url, self.preview_url, self.upload_url):
                    for method in ("get", "post"):
                        with self.subTest(url=url, method=method, user=type(user).__name__):
                            response = self.dispatch(self.request(method, url, user=user))
                            self.assertEqual(response.status_code, 403)
                            self.assertNotIn(b"Original", response.content)
            lookup.assert_not_called()
            upload.assert_not_called()

    def test_preview_and_upload_require_post(self):
        for url in (self.preview_url, self.upload_url):
            self.assertEqual(self.dispatch(self.request("get", url)).status_code, 405)

    def test_all_editor_posts_require_csrf(self):
        middleware = CsrfViewMiddleware(lambda request: None)
        for url in (self.edit_url, self.preview_url, self.upload_url):
            request = self.request("post", url)
            match = resolve(url)
            self.assertEqual(middleware.process_view(request, match.func, (), match.kwargs).status_code, 403)
            request = self.request("post", url)
            request.META["HTTP_X_CSRFTOKEN"] = get_token(request)
            request.COOKIES["csrftoken"] = request.META["CSRF_COOKIE"]
            self.assertIsNone(middleware.process_view(request, match.func, (), match.kwargs))

    @override_settings(PEPIC_UPLOAD_CODE="test-credential-never-render")
    def test_form_assets_and_no_credential_in_html(self):
        with patch("posts.views.get_object_or_404", return_value=self.post):
            response = self.dispatch(self.request("get", self.edit_url))
        self.assertContains(response, "post-editor.js")
        self.assertContains(response, "post-editor.css")
        self.assertContains(response, "easymde.min.js")
        self.assertContains(response, self.preview_url)
        self.assertNotContains(response, "test-credential-never-render")
        self.assertNotContains(response, "simplemde.min.js")
        self.assertIn("no-store", response["Cache-Control"])
        for path in ("js/post-editor.js", "css/post-editor.css", "js/vendor/easymde/easymde.min.js",
                     "js/vendor/easymde/easymde.min.css", "js/vendor/inline-attachment/core.js",
                     "js/vendor/inline-attachment/codemirror4.js"):
            self.assertIsNotNone(finders.find(path), path)

    def preview(self, text):
        with patch("posts.editor.get_object_or_404", return_value=self.post) as lookup:
            response = self.dispatch(self.request("post", self.preview_url, {"text": text}))
        lookup.assert_called_once_with(Post, type="blog", slug="editor-test", lang="ru")
        return response

    def test_preview_uses_blog_plugins_without_mutating_post(self):
        text = "# Heading\n\n[[[.wide\n**Bold**\n]]]\n\n{{{\n![](https://example.test/a.png)\n}}}\n\n[? secret ?]\n\n% citation\n\n<div>raw html</div>"
        before = self.post.__dict__.copy()
        with patch.object(Post, "save") as save:
            response = self.preview(text)
        self.assertEqual(response.status_code, 200)
        self.assertIn(markdown_text(text), json.loads(response.content)["html"])
        self.assertEqual(before, self.post.__dict__)
        save.assert_not_called()
        self.assertIn("no-store", response["Cache-Control"])

    def test_preview_preserves_raw_html_and_post_styles(self):
        self.post.is_raw_html = True
        self.post.css = ".post { color: red; }"
        self.post.data = {"body_class": "custom-post", "background_color": "pink"}
        html = json.loads(self.preview("<div>**literal**</div>").content)["html"]
        self.assertIn("<div>**literal**</div>", html)
        self.assertIn(self.post.css, html)
        self.assertIn('class="custom-post"', html)
        self.assertIn("css/posts.css", html)
        self.assertIn("connect-src 'none'", html)
        self.assertIn("form-action 'none'", html)

    def test_preview_expands_legacy_blocks_without_comment_forms(self):
        html = json.loads(self.preview("[clicker 10]\n\n[commentable 20]").content)["html"]
        self.assertIn('class="clicker ', html)
        self.assertIn('id="block-20"', html)
        self.assertNotIn("[clicker", html)
        self.assertNotIn("<form", html)

    def test_preview_rejects_oversized_text_and_missing_post(self):
        self.assertEqual(self.preview("x" * 100001).status_code, 400)
        self.assertEqual(self.preview("").status_code, 200)
        with patch("posts.editor.get_object_or_404", side_effect=Http404):
            with self.assertRaises(Http404):
                self.dispatch(self.request("post", self.preview_url, {"text": "text"}))

    def test_save_keeps_markdown_and_invalidates_only_existing_cache_pipeline(self):
        text = "[[[\n**new text**\n]]]\n\n<div>raw HTML</div>"
        with patch("posts.views.get_object_or_404", return_value=self.post), patch.object(Model, "save") as save:
            response = self.dispatch(self.request("post", self.edit_url, {"title": "New", "text": text}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.post.text, text)
        self.assertIsNone(self.post.html_cache)
        self.assertFalse(self.post.is_visible)
        save.assert_called_once()

    def test_incomplete_and_failed_uploads_cannot_be_saved(self):
        for marker in ("![Загружаю файл... 1]()", "![Ошибка загрузки файла... 2]()"):
            form = PostEditForm({"title": "Title", "text": "Keep this\n" + marker}, instance=self.post)
            self.assertFalse(form.is_valid())
            self.assertIn("text", form.errors)

    def test_draft_preview_flag_is_not_public(self):
        with patch("posts.views.get_object_or_404", return_value=self.post), patch.object(Post.objects, "filter") as query:
            for user in (AnonymousUser(), self.reader):
                with self.assertRaises(Http404):
                    show_post(self.request("get", "/blog/editor-test/?preview=1", user=user), "blog", "editor-test")
            query.assert_not_called()

    @override_settings(DEBUG=False)
    def test_existing_post_cache_rss_and_comment_rendering_are_unchanged(self):
        context = Context({"post": self.post, "clickers": {}, "user_votes": set(), "cookies": {}, "comments": []})
        with patch.object(Post, "save") as save:
            self.assertEqual(render_post(context, self.post), "Cached")
            save.assert_not_called()
        self.assertEqual(FullFeed().item_description(self.post), "Cached")
        self.assertNotIn("<script>", markdown_comment("<script>alert(1)</script>"))

    def test_upload_validates_before_calling_pepic(self):
        with patch("posts.editor.requests.post") as upload:
            cases = ({}, {"media": self.image(content_type="text/html")}, {"media": self.image(b"")})
            for data in cases:
                self.assertIn(self.dispatch(self.request("post", self.upload_url, data)).status_code, (400, 413))
            with patch("posts.editor.MAX_IMAGE_SIZE", 2):
                self.assertEqual(self.dispatch(self.request("post", self.upload_url, {"media": self.image()})).status_code, 413)
            self.assertEqual(self.dispatch(self.request("post", self.upload_url, {"media": self.image()})).status_code, 503)
            upload.assert_not_called()
        self.assertLess(MAX_IMAGE_SIZE, 15 * 1024 * 1024)

    @override_settings(PEPIC_UPLOAD_URL="https://media.example.test/upload/multipart/", PEPIC_UPLOAD_CODE="fake-test-code")
    def test_upload_contract_and_secret_stays_server_side(self):
        upstream = Mock(status_code=200)
        upstream.json.return_value = {"uploaded": "https://media.example.test/image.png", "ignored": "private"}
        with patch("posts.editor.requests.post") as upload:
            upload.return_value.__enter__.return_value = upstream
            response = self.dispatch(self.request("post", self.upload_url, {"media": self.image(), "code": "browser-value-ignored"}))
        self.assertEqual(json.loads(response.content), {"uploaded": "https://media.example.test/image.png"})
        args, kwargs = upload.call_args
        self.assertEqual(args, ("https://media.example.test/upload/multipart/",))
        self.assertEqual(kwargs["data"], {"code": "fake-test-code"})
        self.assertEqual(kwargs["headers"], {"Accept": "application/json"})
        self.assertEqual(kwargs["files"]["media"][0], "example.png")
        self.assertEqual(kwargs["files"]["media"][2], "image/png")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (5, 45))
        self.assertIn("no-store", response["Cache-Control"])

    @override_settings(PEPIC_UPLOAD_URL="https://media.example.test/upload/multipart/", PEPIC_UPLOAD_CODE="fake-test-code")
    def test_upload_errors_are_safe_and_do_not_forward_upstream_body(self):
        responses = [None, [], {}, {"uploaded": 1}, {"uploaded": "javascript:alert(1)"},
                     {"uploaded": "https://example.test/a\n.png"}, {"uploaded": "https://example.test/a)bad.png"}]
        for body in responses:
            with self.subTest(body=body), patch("posts.editor.requests.post") as upload:
                upstream = upload.return_value.__enter__.return_value
                upstream.status_code = 200
                upstream.json.return_value = body
                self.assertEqual(self.dispatch(self.request("post", self.upload_url, {"media": self.image()})).status_code, 502)
        for status in (301, 403, 413, 500):
            with patch("posts.editor.requests.post") as upload:
                upstream = upload.return_value.__enter__.return_value
                upstream.status_code = status
                upstream.text = "fake-test-code"
                response = self.dispatch(self.request("post", self.upload_url, {"media": self.image()}))
                self.assertEqual(response.status_code, 502)
                self.assertNotIn(b"fake-test-code", response.content)
        for error in (requests.Timeout("private upstream body"), ValueError("invalid JSON")):
            with patch("posts.editor.requests.post", side_effect=error):
                response = self.dispatch(self.request("post", self.upload_url, {"media": self.image()}))
                self.assertEqual(response.status_code, 502)
                self.assertNotIn(b"private upstream body", response.content)

    @override_settings(PEPIC_UPLOAD_URL="http://media.example.test/upload/multipart/", PEPIC_UPLOAD_CODE="fake-test-code")
    def test_upload_rejects_plain_http_configuration(self):
        with patch("posts.editor.requests.post") as upload:
            response = self.dispatch(self.request("post", self.upload_url, {"media": self.image()}))
            self.assertEqual(response.status_code, 503)
            upload.assert_not_called()
