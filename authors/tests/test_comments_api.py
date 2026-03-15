import json
from urllib.parse import quote_plus

import pytest
from django.contrib.auth.models import User
from django.test import Client, TestCase

from authors.models import Author, Post, Inbox, Comment

pytestmark = pytest.mark.django_db


def make_author(user: User, display_name: str) -> Author:
    author = Author.objects.create(
        user=user,
        displayName=display_name,
        host="http://testserver/api/",
    )
    Inbox.objects.get_or_create(author=author)
    return author


class APICommentsAndCommentedTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user_a = User.objects.create_user(username="alice_comments", password="pass123")
        self.user_b = User.objects.create_user(username="bob_comments", password="pass123")

        self.author_a = make_author(self.user_a, "Alice Comments")
        self.author_b = make_author(self.user_b, "Bob Comments")

        self.post_a = Post.objects.create(
            author=self.author_a,
            title="Post for Comments API",
            content="Hello world",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
        )

        self.comment_by_b = Comment.objects.create(
            author=self.author_b,
            post=self.post_a,
            content="Nice post!",
            contentType="text/plain",
        )

        self.comment_fqid = f"http://testserver/api/authors/{self.author_b.id}/commented/{self.comment_by_b.id}"
        self.encoded_comment_fqid = quote_plus(self.comment_fqid)

        self.entry_fqid = f"http://testserver/api/authors/{self.author_a.id}/entries/{self.post_a.id}"
        self.encoded_entry_fqid = quote_plus(self.entry_fqid)

    def _first_non_404_get(self, paths, *, auth_user=None):
        if auth_user:
            self.client.force_login(auth_user)
        try:
            tried = []
            for p in paths:
                resp = self.client.get(p)
                tried.append((p, resp.status_code))
                if resp.status_code != 404:
                    return p, resp
            self.fail(f"All candidate endpoints returned 404. Tried: {tried}")
        finally:
            if auth_user:
                self.client.logout()

    def _extract_list(self, payload):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("items", "src", "comments", "entries", "posts"):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
        self.fail(f"Unrecognized list payload shape: {type(payload)} {payload}")

    def _assert_is_comment_object(self, obj):
        self.assertIsInstance(obj, dict)
        self.assertEqual(obj.get("type"), "comment")
        self.assertTrue(any(k in obj for k in ("id",)))
        self.assertTrue(any(k in obj for k in ("comment", "content")))
        self.assertIn("author", obj)
        self.assertIn("published", obj)
        self.assertIn("contentType", obj)
        self.assertTrue(any(k in obj for k in ("entry", "post")))

    def test_comments_api_get_comments_on_entry_by_serial(self):
        paths = [
            f"/api/authors/{self.author_a.id}/entries/{self.post_a.id}/comments/",
            f"/api/authors/{self.author_a.id}/entries/{self.post_a.id}/comments",
        ]
        _, resp = self._first_non_404_get(paths, auth_user=self.user_a)

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        items = self._extract_list(payload)
        self.assertGreaterEqual(len(items), 1)

        joined = json.dumps(items)
        self.assertIn("Nice post!", joined)
        self.assertIn(str(self.comment_by_b.id), joined)

        first = items[0]
        if isinstance(first, dict) and first.get("type") == "comment":
            self._assert_is_comment_object(first)

    def test_comments_api_get_comments_on_entry_by_fqid(self):
        paths = [
            f"/api/entries/{self.encoded_entry_fqid}/comments/",
            f"/api/entries/{self.encoded_entry_fqid}/comments",
        ]
        _, resp = self._first_non_404_get(paths, auth_user=self.user_a)

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        items = self._extract_list(payload)
        self.assertGreaterEqual(len(items), 1)

        joined = json.dumps(items)
        self.assertIn("Nice post!", joined)

    def test_comments_api_get_single_comment_by_remote_comment_fqid(self):
        paths = [
            f"/api/authors/{self.author_a.id}/entries/{self.post_a.id}/comments/{self.encoded_comment_fqid}/",
            f"/api/authors/{self.author_a.id}/entries/{self.post_a.id}/comments/{self.encoded_comment_fqid}",
        ]
        _, resp = self._first_non_404_get(paths, auth_user=self.user_a)

        self.assertEqual(resp.status_code, 200)
        obj = resp.json()
        self._assert_is_comment_object(obj)

        blob = json.dumps(obj)
        self.assertIn("Nice post!", blob)
        self.assertIn(str(self.comment_by_b.id), blob)

    def test_commented_api_get_list_of_comments_by_author_serial(self):
        paths = [
            f"/api/authors/{self.author_b.id}/commented/",
            f"/api/authors/{self.author_b.id}/commented",
        ]
        _, resp = self._first_non_404_get(paths, auth_user=self.user_b)

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        items = self._extract_list(payload)
        self.assertGreaterEqual(len(items), 1)

        joined = json.dumps(items)
        self.assertIn("Nice post!", joined)
        self.assertIn(str(self.comment_by_b.id), joined)

    def test_commented_api_get_single_comment_by_comment_serial(self):
        paths = [
            f"/api/authors/{self.author_b.id}/commented/{self.comment_by_b.id}/",
            f"/api/authors/{self.author_b.id}/commented/{self.comment_by_b.id}",
        ]
        _, resp = self._first_non_404_get(paths, auth_user=self.user_b)

        self.assertEqual(resp.status_code, 200)
        obj = resp.json()
        self._assert_is_comment_object(obj)

        blob = json.dumps(obj)
        self.assertIn("Nice post!", blob)
        self.assertIn(str(self.comment_by_b.id), blob)

    def test_commented_api_get_single_comment_by_comment_fqid(self):
        paths = [
            f"/api/commented/{self.encoded_comment_fqid}/",
            f"/api/commented/{self.encoded_comment_fqid}",
        ]
        _, resp = self._first_non_404_get(paths, auth_user=self.user_b)

        self.assertEqual(resp.status_code, 200)
        obj = resp.json()
        self._assert_is_comment_object(obj)

        blob = json.dumps(obj)
        self.assertIn("Nice post!", blob)
        self.assertIn(str(self.comment_by_b.id), blob)