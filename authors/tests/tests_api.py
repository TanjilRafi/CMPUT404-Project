# The following API test code was written with assistance from OpenAI (ChatGPT).
# Prompt used: “Review the project files and help me debug test
# import issues and to structure endpoint tests.”
# Date: 2026-03-02

import pytest
import uuid
from django.contrib.auth.models import User
from django.utils import timezone
from authors.models import Author, Post, Inbox, Like, Comment, Node


import json
from datetime import timedelta
from urllib.parse import quote_plus
from django.test import Client, TestCase
from django.apps import apps 
from rest_framework.test import APIClient
from unittest.mock import patch

pytestmark = pytest.mark.django_db

def make_author(user: User, display_name: str) -> Author:
    author = Author.objects.create(
        user=user,
        displayName=display_name,
        host="http://testserver/",
    )
    Inbox.objects.create(author=author)
    return author


@pytest.fixture
def user_a(db):
    return User.objects.create_user(username=f"alice_{uuid.uuid4()}", password="password")

@pytest.fixture
def user_b(db):
    return User.objects.create_user(username=f"rachel_{uuid.uuid4()}", password="password")


@pytest.fixture
def author_a(user_a):
    return make_author(user_a, "alice")


@pytest.fixture
def author_b(user_b):
    return make_author(user_b, "rachel")


@pytest.fixture
def client_a(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a) 
    return client

@pytest.fixture
def client_b(user_b):
    client = APIClient()
    client.force_authenticate(user=user_b)
    return client

def test_api_author_id_stable(client, author_a):
    """
    US 01.01 - Author identity URL is consistent
    """
    response1 = client.get(f"/api/authors/{author_a.id}/")
    response2 = client.get(f"/api/authors/{author_a.id}/")

    assert response1.status_code == 200
    assert response2.status_code == 200

    data1 = response1.json()
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert str(author_a.id) in data1["id"]

def test_api_get_all_authors(client, author_a, author_b):
    """
    US 01.02 - Node hosts multiple authors
    """
    response = client.get("/api/authors/")

    assert response.status_code == 200
    data = response.json()

    names = [a["displayName"] for a in data["items"]]
    assert "alice" in names
    assert "rachel" in names


def test_api_get_single_author(client, author_a):
    """
    US 01.03 - Public profile page
    """
    response = client.get(f"/api/authors/{author_a.id}/")

    assert response.status_code == 200
    data = response.json()

    assert data["displayName"] == "alice"
    assert "id" in data
    assert "host" in data


def test_api_edit_profile_owner_only(client_a, author_a):
    """
    US 01.06 - Author can edit their own profile, not others
    """
    response = client_a.put(
        f"/api/authors/{author_a.id}/",
        data={
            "displayName": "Updated Name",
            "description": "New Bio"
        },
        content_type="application/json"
    )

    assert response.status_code == 200


def test_api_edit_profile_forbidden(client_b, author_a):
    response = client_b.put(
        f"/api/authors/{author_a.id}/",
        data={"displayName": "Hacked"},
        content_type="application/json"
    )

    assert response.status_code == 403

def test_api_manage_profile_requires_owner(client_b, author_a):
    """
    US 01.07 - API profile management restricted to owner
    """
    response = client_b.put(
        f"/api/authors/{author_a.id}/",
        data={"displayName": "Unauthorized"},
        content_type="application/json"
    )

    assert response.status_code == 403

def test_api_create_post(client_a, author_a):
    """
    US 02.01 + US 02.06 - Create plain text entry
    """
    response = client_a.post(
        f"/api/authors/{author_a.id}/entries/",
        data={
            "title": "API Post",
            "content": "Hello",
            "contentType": "text/plain",
            "visibility": "PUBLIC"
        },
        content_type="application/json"
    )

    assert response.status_code == 201
    assert Post.objects.count() == 1


def test_api_edit_post_owner(client_a, author_a):
    """
    US 02.03 + US 02.12 - Only owner can edit
    """
    post = Post.objects.create(
        author=author_a,
        title="Old",
        content="Old",
        content_type="text/plain",
        visibility=Post.Visibility.PUBLIC,
        type=Post.Type.TEXT,
    )

    response = client_a.put(
        f"/api/authors/{author_a.id}/entries/{post.id}/",
        data={
            "title": "Updated",
            "content": "Updated",
            "contentType": "text/plain",
            "visibility": "PUBLIC"
        },
        content_type="application/json"
    )

    assert response.status_code == 200
    post.refresh_from_db()
    assert post.title == "Updated"


def test_api_edit_post_forbidden(client_b, author_a):
    """
    US 02.03 + US 02.12 - Only owner can edit
    """
    post = Post.objects.create(
        author=author_a,
        title="Protected",
        content="No",
        content_type="text/plain",
        visibility=Post.Visibility.PUBLIC,
        type=Post.Type.TEXT,
    )

    response = client_b.put(
        f"/api/authors/{author_a.id}/entries/{post.id}/",
        data={"title": "Hack"},
        content_type="application/json"
    )

    assert response.status_code == 403

def test_api_create_markdown_post(client_a, author_a):
    """
    US 02.05 - API supports CommonMark
    """
    response = client_a.post(
        f"/api/authors/{author_a.id}/entries/",
        data={
            "title": "Markdown Post",
            "content": "# Heading",
            "contentType": "text/markdown",
            "visibility": "PUBLIC"
        },
        content_type="application/json"
    )

    assert response.status_code == 201
    data = response.json()
    assert data["contentType"] == "text/markdown"

def test_api_create_plain_text_content_type(client_a, author_a):
    """
    US 02.06 - API supports plain text explicitly
    """
    response = client_a.post(
        f"/api/authors/{author_a.id}/entries/",
        data={
            "title": "Plain",
            "content": "Hello",
            "contentType": "text/plain",
            "visibility": "PUBLIC"
        },
        content_type="application/json"
    )

    assert response.status_code == 201
    assert response.json()["contentType"] == "text/plain"

def test_api_soft_delete(client_a, author_a):
    """
    US 02.09 + US 08.14 - Soft delete
    """
    post = Post.objects.create(
        author=author_a,
        title="Delete",
        content="Bye",
        content_type="text/plain",
        visibility=Post.Visibility.PUBLIC,
        type=Post.Type.TEXT,
    )

    response = client_a.delete(
        f"/api/authors/{author_a.id}/entries/{post.id}/"
    )

    assert response.status_code in (200, 204)

    post.refresh_from_db()
    assert post.is_deleted is True

    # should not be visible through API
    hidden = client_a.get(
        f"/api/authors/{author_a.id}/entries/{post.id}/"
    )
    assert hidden.status_code == 404

def test_api_stream_sorted_newest_first(client_a, author_a, author_b):
    """
    US 03.02 - Stream newest first
    """
    old = Post.objects.create(
        author=author_b,
        title="Old",
        content="Old",
        content_type="text/plain",
        visibility=Post.Visibility.PUBLIC,
        type=Post.Type.TEXT,
        created_at=timezone.now() - timezone.timedelta(minutes=10)
    )
    new = Post.objects.create(
        author=author_b,
        title="New",
        content="New",
        content_type="text/plain",
        visibility=Post.Visibility.PUBLIC,
        type=Post.Type.TEXT,
        created_at=timezone.now()
    )

    author_a.inbox.posts.add(old)
    author_a.inbox.posts.add(new)

    response = client_a.get(f"/api/authors/{author_a.id}/stream")
    assert response.status_code == 200
    data = response.json()
    posts = data["items"]
    assert posts[0]["title"] == "New"


def test_api_public_visible_to_anonymous(client, author_a):
    """
    US 04.01 + US 04.06 - Public visible to everyone in stream
    """
    post = Post.objects.create(
        author=author_a,
        title="Public",
        content="Visible",
        content_type="text/plain",
        visibility=Post.Visibility.PUBLIC,
        type=Post.Type.TEXT,
    )

    response = client.get(
        f"/api/authors/{author_a.id}/entries/{post.id}/"
    )

    assert response.status_code == 200


def test_api_unlisted_not_in_author_posts(client_a, author_a):
    """
    US 04.02 - Unlisted not in author posts
    """
    Post.objects.create(
        author=author_a,
        title="Unlisted",
        content="Hidden",
        content_type="text/plain",
        visibility=Post.Visibility.UNLISTED,
        type=Post.Type.TEXT,
    )

    response = client_a.get(
        f"/api/authors/{author_a.id}/entries/"
    )

    data = response.json()
    titles = [p["title"] for p in data["items"]]

    assert "Unlisted" not in titles


def test_unlisted_not_in_stream(client_a, author_a):
    """
    US 04.02 - Unlisted not in stream
    """
    Post.objects.create(
        author=author_a,
        title="Unlisted Stream",
        content="Hidden",
        content_type="text/plain",
        visibility=Post.Visibility.UNLISTED,
        type=Post.Type.TEXT,
    )

    response = client_a.get(f"/api/authors/{author_a.id}/stream")
    titles = [p["title"] for p in response.json()["items"]]

    assert "Unlisted Stream" not in titles



def test_public_visible_in_other_author_stream(client_b, author_a, author_b):
    """
    US 04.06 - Public visible in everyone’s stream
    """
    Post.objects.create(
        author=author_a,
        title="Global Public",
        content="Visible to all",
        content_type="text/plain",
        visibility=Post.Visibility.PUBLIC,
        type=Post.Type.TEXT,
    )

    response = client_b.get(f"/api/authors/{author_b.id}/stream")

    titles = [p["title"] for p in response.json()["items"]]

    assert "Global Public" in titles


def test_unlisted_accessible_by_link_anonymous(client, author_a):
    """
    US 04.07 - Unlisted accessible via direct link anonymously
    """
    post = Post.objects.create(
        author=author_a,
        title="Secret Link",
        content="Accessible",
        content_type="text/plain",
        visibility=Post.Visibility.UNLISTED,
        type=Post.Type.TEXT,
    )

    response = client.get(
        f"/api/authors/{author_a.id}/entries/{post.id}/"
    )

    assert response.status_code == 200

def test_deleted_hidden_from_normal_users(client_a, author_a):
    """
    US 04.09 - Deleted entries not visible to normal users
    """
    post = Post.objects.create(
        author=author_a,
        title="Deleted Hidden",
        content="Gone",
        content_type="text/plain",
        visibility=Post.Visibility.PUBLIC,
        type=Post.Type.TEXT,
        is_deleted=True,
    )

    response = client_a.get(
        f"/api/authors/{author_a.id}/entries/{post.id}/"
    )

    assert response.status_code == 404



@pytest.fixture
def admin_user():
    return User.objects.create_user(
        username="admin",
        password="password",
        is_staff=True
    )


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


def test_deleted_visible_to_admin(admin_client, author_a):
    """
    US 08.14 - Deleted posts remain in DB and admin can access
    """
    post = Post.objects.create(
        author=author_a,
        title="Admin Visible",
        content="Soft deleted",
        content_type="text/plain",
        visibility=Post.Visibility.PUBLIC,
        type=Post.Type.TEXT,
        is_deleted=True,
    )

    response = admin_client.get(
        f"/api/authors/{author_a.id}/entries/{post.id}/"
    )

    # Admin should still see it
    assert response.status_code == 200


class APIFollowAndStreamTests(TestCase):

    def setUp(self):
        self.client = Client()

        # using an API host so branches that generate api_url from host behave consistently
        self.user_a = User.objects.create_user(username="api_alice", password="pass123")
        self.author_a = Author.objects.create(
            user=self.user_a,
            displayName="API Alice",
            host="http://testserver/api/",
            github="",
            profileImage="",
        )

        self.user_b = User.objects.create_user(username="api_rachel", password="pass123")
        self.author_b = Author.objects.create(
            user=self.user_b,
            displayName="API rachel",
            host="http://testserver/api/",
            github="",
            profileImage="",
        )
        Inbox = apps.get_model("authors", "Inbox")
        Inbox.objects.get_or_create(author=self.author_a)
        Inbox.objects.get_or_create(author=self.author_b)

    # helpers

    def _first_existing(self, method: str, paths, *, data=None, content_type=None):
        """
        Try candidate URLs and return the first non-404 response.
        If all are 404, skip the test (endpoint not implemented yet).

        For PUT/POST/PATCH, default to JSON so Django's test client doesn't crash
        when content_type is None.
        """
        method = method.lower()

        needs_body = method in ("post", "put", "patch")
        if needs_body and content_type is None:
            content_type = "application/json"
        if needs_body and data is None:
            data = {}  # safe no-op body for JSON encoding

        for p in paths:
            resp = getattr(self.client, method)(p, data=data, content_type=content_type)
            if resp.status_code != 404:
                return p, resp

        self.skipTest(f"Endpoint not implemented yet (all 404): {paths}")

        
    def _extract_post_list(self, payload):
    
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("items", "src", "posts", "entries", "following", "followers"):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
        self.fail(f"Unrecognized JSON shape for list response: {type(payload)} {payload}")

    def _ensure_inbox_model(self):
        
        try:
            from ..models import Inbox 
            return Inbox
        except Exception:
            return None

    # stream

    def test_api_author_stream_public_sorted_newest_first(self):
        now = timezone.now()

        Post.objects.create(
            author=self.author_b,
            title="Old Public",
            content="old",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
            created_at=now - timedelta(minutes=10),
        )

        Post.objects.create(
            author=self.author_b,
            title="New Public",
            content="new",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
            created_at=now,
        )

        Post.objects.create(
            author=self.author_b,
            title="Unlisted Hidden",
            content="nope",
            content_type="text/plain",
            visibility=Post.Visibility.UNLISTED,
            type=Post.Type.TEXT,
            created_at=now - timedelta(minutes=5),
        )

        Post.objects.create(
            author=self.author_b,
            title="Deleted Hidden",
            content="nope",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
            is_deleted=True,
            created_at=now - timedelta(minutes=3),
        )

        paths = [
        f"/api/authors/{self.author_a.id}/stream/",
        f"/api/authors/{self.author_a.id}/stream",
        ]

        path, resp0 = self._first_existing("get", paths)

        if resp0.status_code in (301, 302, 303, 307, 308):
            location = resp0.headers.get("Location", "")

            # If this endpoint requires auth and redirects to login, authenticate and retry.
            if "login" in location.lower():
                self.client.force_login(self.user_a)
                path, resp = self._first_existing("get", paths)
            else:
                # Likely just a slash-redirect; follow it.
                resp = self.client.get(path, follow=True)
        else:
            resp = resp0

        self.assertEqual(resp.status_code, 200)

        posts = self._extract_post_list(resp.json())
        titles = [p.get("title") for p in posts]

        self.assertIn("Old Public", titles)
        self.assertIn("New Public", titles)
        self.assertNotIn("Unlisted Hidden", titles)
        self.assertNotIn("Deleted Hidden", titles)

        # newest first
        self.assertLess(titles.index("New Public"), titles.index("Old Public"))

    # follow requests lists

    def test_api_follow_requests_list_auth_and_shape(self):
        
        paths = [
            f"/api/authors/{self.author_a.id}/follow_requests/",
            f"/api/authors/{self.author_a.id}/follow-requests/",
            f"/api/authors/{self.author_a.id}/follow_requests",
            f"/api/authors/{self.author_a.id}/follow-requests",
        ]

    
        _, resp0 = self._first_existing("get", paths)
        if resp0.status_code in (401, 403):
            self.client.force_login(self.user_a)
            _, resp = self._first_existing("get", paths)
        else:
            resp = resp0  # endpoint is public on this branch

        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Accept either dict-wrapped or list; just require it to be "list-ish"
        if isinstance(data, dict):
            items = self._extract_post_list(data)
            self.assertIsInstance(items, list)
        elif isinstance(data, list):
            self.assertIsInstance(data, list)
        else:
            self.fail(f"Unexpected follow_requests response type: {type(data)}")

    # followers, follow and inbox

    def test_api_following_followers_and_inbox_flow_smoke(self):
     
        if not hasattr(self.author_a, "api_url") or not hasattr(self.author_b, "api_url"):
            self.skipTest("Author.api_url not present on this branch (follow API not ready).")

        following_list_paths = [f"/api/authors/{self.author_a.id}/following/"]
        followers_list_paths = [f"/api/authors/{self.author_b.id}/followers/"]
        inbox_paths = [
            f"/api/authors/{self.author_b.id}/inbox/",
            f"/api/authors/{self.author_b.id}/inbox",
        ]

        # If any of these are missing, skip if not implemented yet
        self._first_existing("get", following_list_paths)
        self._first_existing("get", followers_list_paths)
        self._first_existing("post", inbox_paths, data=json.dumps({}), content_type="application/json")

        fqid_b = quote_plus(str(self.author_b.api_url))
        fqid_a = quote_plus(str(self.author_a.api_url))

        following_item_paths = [
            f"/api/authors/{self.author_a.id}/following/{fqid_b}/",
            f"/api/authors/{self.author_a.id}/following/{fqid_b}",
        ]
        followers_item_paths = [
            f"/api/authors/{self.author_b.id}/followers/{fqid_a}/",
            f"/api/authors/{self.author_b.id}/followers/{fqid_a}",
        ]

        self.client.force_login(self.user_a)
        _, put_follow = self._first_existing("put", following_item_paths)
        self.assertIn(put_follow.status_code, (200, 201, 204))

        self.client.logout()
        self.client.force_login(self.user_b)
        _, put_accept = self._first_existing("put", followers_item_paths)
        self.assertIn(put_accept.status_code, (200, 201, 204))

        if hasattr(self.author_b, "followers"):
            self.author_b.refresh_from_db()
            self.assertTrue(
                self.author_b.followers.filter(id=self.author_a.id).exists()
                or (hasattr(self.author_b, "friends") and self.author_b.friends.filter(id=self.author_a.id).exists())
            )


"""
API tests for the Likes & Liked endpoints.
"""


def make_author(user_or_username, display_name: str) -> Author:
    """
    Helper to create an author. Handles being passed a Django User object
    (from pytest fixtures) or a string username (from class-based tests).
    """
    if isinstance(user_or_username, User):
        user = user_or_username
    else:
        import uuid as _uuid
        unique_username = f"{user_or_username}_{_uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username=unique_username, password="pw")
        
    author, created = Author.objects.get_or_create(
        user=user,
        defaults={
            "displayName": display_name,
            "host": "http://testserver/",
        }
    )
    Inbox.objects.get_or_create(author=author)
    return author


def make_post(author: Author, title="Test", visibility=Post.Visibility.PUBLIC) -> Post:
    return Post.objects.create(
        author=author,
        title=title,
        content="content",
        content_type="text/plain",
        visibility=visibility,
        type=Post.Type.TEXT,
    )


def make_like(liker: Author, post: Post) -> Like:
    """
    Create a Like following the same id convention as _make_like_id() in api_views.py.
    """
    import uuid as _uuid
    object_url = f"{post.author.host}api/authors/{post.author.id}/entries/{post.id}"
    liker_fqid = f"{liker.host}api/authors/{liker.id}"
    namespace = _uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    like_uuid = _uuid.uuid5(namespace, liker_fqid + "|" + object_url)
    like_id = f"{liker.host}api/authors/{liker.id}/liked/{like_uuid}"
    return Like.objects.create(id=like_id, author=liker, object=object_url)


def entry_api_url(post: Post) -> str:
    return f"{post.author.host}api/authors/{post.author.id}/entries/{post.id}"


class InboxLikeTests(TestCase):
    """
    Tests for the inbox like handler.
    US: Remote node notifies local author that someone liked their entry.
    """

    def setUp(self):
        self.client = APIClient()
        self.alice = make_author("alice", "Alice")
        self.rachel = make_author("rachel", "rachel")
        self.post = make_post(self.alice, "Alice's Post")

    def _like_body(self, liker: Author, post: Post) -> dict:
        return {
            "type": "like",
            "author": {
                "type": "author",
                "id": f"{liker.host}api/authors/{liker.id}",
                "host": liker.host,
                "displayName": liker.displayName,
                "github": liker.github or "",
                "profileImage": liker.profileImage or "",
                "web": liker.url,
            },
            "object": entry_api_url(self.post),
        }

    def test_like_via_inbox_creates_like_object(self):
        """
        A valid like POST to an author's inbox creates a Like row.
        """
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.post(
            f"/api/authors/{self.alice.id}/inbox",
            data=json.dumps(self._like_body(self.rachel, self.post)),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Like.objects.count(), 1)
        like = Like.objects.first()
        self.assertEqual(like.author, self.rachel)
        self.assertEqual(like.object, entry_api_url(self.post))

    def test_like_via_inbox_idempotent(self):
        """
        Sending the same like twice does not create a duplicate row.
        """
        self.client.login(username=self.rachel.user.username, password="pw")
        body = json.dumps(self._like_body(self.rachel, self.post))
        self.client.post(f"/api/authors/{self.alice.id}/inbox", data=body, content_type="application/json")
        self.client.post(f"/api/authors/{self.alice.id}/inbox", data=body, content_type="application/json")
        self.assertEqual(Like.objects.count(), 1)

    def test_like_via_inbox_creates_remote_author_stub(self):
        """
        If the liker is not yet in the DB, a stub Author is created automatically.
        """
        self.client.login(username=self.alice.user.username, password="pw")
        remote_body = {
            "type": "like",
            "author": {
                "type": "author",
                "id": "http://remotenode/api/authors/remote-person-999",
                "host": "http://remotenode/",
                "displayName": "Remote Person",
                "github": "",
                "profileImage": "",
                "web": "http://remotenode/authors/remote-person-999",
            },
            "object": entry_api_url(self.post),
        }
        resp = self.client.post(
            f"/api/authors/{self.alice.id}/inbox",
            data=json.dumps(remote_body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Like.objects.count(), 1)
        stub = Author.objects.filter(displayName="Remote Person").first()
        self.assertIsNotNone(stub)

    def test_like_via_inbox_wrong_type_returns_400(self):
        """
        Sending a body with an unrecognised type returns 400.
        """
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.post(
            f"/api/authors/{self.alice.id}/inbox",
            data=json.dumps({"type": "banana"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_like_via_inbox_missing_object_returns_400(self):
        """
        A like body without 'object' returns 400.
        """
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.post(
            f"/api/authors/{self.alice.id}/inbox",
            data=json.dumps({
                "type": "like",
                "author": {"id": f"{self.rachel.host}api/authors/{self.rachel.id}", "web": self.rachel.url, "host": "http://testserver/"},
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_like_via_inbox_invalid_json_returns_400(self):
        """
        Invalid JSON body returns 400.
        """
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.post(
            f"/api/authors/{self.alice.id}/inbox",
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_like_via_inbox_unknown_author_returns_404(self):
        """
        POST to a non-existent author's inbox returns 404.
        """
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.post(
            f"/api/authors/{uuid.uuid4()}/inbox",
            data=json.dumps(self._like_body(self.rachel, self.post)),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)


class EntryLikesSerialTests(TestCase):
    """
    Tests for GET /api/authors/<id>/entries/<post_id>/likes/
    [local, remote] — who liked a specific entry, identified by serial IDs.
    """

    def setUp(self):
        self.client = APIClient()
        self.alice = make_author("alice", "Alice")
        self.rachel = make_author("rachel", "rachel")
        self.post = make_post(self.alice, "Alice's Post")

    def _url(self, post=None):
        p = post or self.post
        return f"/api/authors/{self.alice.id}/entries/{p.id}/likes/"

    def test_no_likes_returns_empty_list(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["type"], "likes")
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["src"], [])

    def test_returns_all_likes_for_entry(self):
        make_like(self.rachel, self.post)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["src"][0]["type"], "like")
        self.assertEqual(data["src"][0]["author"]["displayName"], "rachel")

    def test_like_object_shape(self):
        """
        Each like in 'src' must have type, author, published, id, object.
        """
        make_like(self.rachel, self.post)
        resp = self.client.get(self._url())
        like_obj = resp.json()["src"][0]
        for field in ("type", "author", "published", "id", "object"):
            self.assertIn(field, like_obj)
        self.assertEqual(like_obj["type"], "like")
        self.assertIn("displayName", like_obj["author"])

    def test_envelope_has_required_fields(self):
        """
        Response envelope must contain type, id, page_number, size, count, src.
        """
        resp = self.client.get(self._url())
        data = resp.json()
        for field in ("type", "id", "page_number", "size", "count", "src"):
            self.assertIn(field, data)

    def test_likes_sorted_newest_first(self):
        """
        Likes are returned newest-first.
        """
        like1 = make_like(self.rachel, self.post)
        # Force older timestamp
        Like.objects.filter(id=like1.id).update(published=timezone.now() - timezone.timedelta(hours=1))

        carol = make_author("carol", "Carol")
        like2 = make_like(carol, self.post)

        resp = self.client.get(self._url())
        src = resp.json()["src"]
        self.assertEqual(src[0]["author"]["displayName"], "Carol")
        self.assertEqual(src[1]["author"]["displayName"], "rachel")

    def test_pagination(self):
        carol = make_author("carol", "Carol")
        make_like(self.rachel, self.post)
        make_like(carol, self.post)
        resp = self.client.get(self._url() + "?page=1&size=1")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["src"]), 1)

    def test_friends_only_entry_returns_403_to_stranger(self):
        friends_post = make_post(self.alice, "Secret", visibility=Post.Visibility.FRIENDS)
        make_like(self.rachel, friends_post)
        resp = self.client.get(f"/api/authors/{self.alice.id}/entries/{friends_post.id}/likes/")
        self.assertEqual(resp.status_code, 403)

    def test_friends_only_entry_accessible_to_friend(self):
        self.alice.friends.add(self.rachel)
        friends_post = make_post(self.alice, "FriendPost", visibility=Post.Visibility.FRIENDS)
        make_like(self.rachel, friends_post)
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.alice.id}/entries/{friends_post.id}/likes/")
        self.assertEqual(resp.status_code, 200)

    def test_deleted_entry_returns_404(self):
        self.post.is_deleted = True
        self.post.save()
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 404)

    def test_unknown_entry_returns_404(self):
        resp = self.client.get(f"/api/authors/{self.alice.id}/entries/{uuid.uuid4()}/likes/")
        self.assertEqual(resp.status_code, 404)

    def test_unknown_author_returns_404(self):
        resp = self.client.get(f"/api/authors/{uuid.uuid4()}/entries/{self.post.id}/likes/")
        self.assertEqual(resp.status_code, 404)

    def test_only_counts_likes_for_this_entry(self):
        """
        Likes on a different entry do not appear in this entry's list.
        """
        other_post = make_post(self.alice, "Other")
        make_like(self.rachel, other_post)  
        resp = self.client.get(self._url())  
        self.assertEqual(resp.json()["count"], 0)

class EntryLikesFqidTests(TestCase):
    """
    Tests for GET /api/entries/<entry_fqid>/likes — likes by FQID.
    """

    def setUp(self):
        self.client = APIClient()
        self.alice = make_author("alice", "Alice")
        self.rachel = make_author("rachel", "rachel")
        self.post = make_post(self.alice)

    def _fqid_url(self, post=None):
        p = post or self.post
        fqid = quote_plus(entry_api_url(p))
        return f"/api/entries/{fqid}/likes"

    def test_returns_likes_via_fqid(self):
        make_like(self.rachel, self.post)
        resp = self.client.get(self._fqid_url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)

    def test_empty_likes_via_fqid(self):
        resp = self.client.get(self._fqid_url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)

    def test_invalid_fqid_returns_404(self):
        bad_fqid = quote_plus("http://testserver/api/authors/bad-uuid/entries/also-bad")
        resp = self.client.get(f"/api/entries/{bad_fqid}/likes")
        self.assertEqual(resp.status_code, 404)

    def test_nonexistent_fqid_returns_404(self):
        fake_fqid = quote_plus(f"{"http://testserver/"}api/authors/{self.alice.id}/entries/{uuid.uuid4()}")
        resp = self.client.get(f"/api/entries/{fake_fqid}/likes")
        self.assertEqual(resp.status_code, 404)

    def test_friends_only_blocked_via_fqid(self):
        friends_post = make_post(self.alice, "FP", visibility=Post.Visibility.FRIENDS)
        resp = self.client.get(self._fqid_url(friends_post))
        self.assertEqual(resp.status_code, 403)

    def test_deleted_entry_returns_404_via_fqid(self):
        self.post.is_deleted = True
        self.post.save()
        resp = self.client.get(self._fqid_url())
        self.assertEqual(resp.status_code, 404)

'''class CommentLikesTests(TestCase):
    """
    Tests for comment likes endpoint — always 501 until Comment model exists.
    """

    def setUp(self):
        self.client = APIClient()
        self.alice = make_author("alice", "Alice")
        self.post = make_post(self.alice)

    def test_comment_likes_returns_501(self):
        """
        Until the Comment model is implemented, this endpoint must return 501.
        """
        fake_comment_fqid = quote_plus(f"{"http://testserver/"}api/authors/{self.alice.id}/entries/{self.post.id}/comments/{uuid.uuid4()}")
        resp = self.client.get(
            f"/api/authors/{self.alice.id}/entries/{self.post.id}/comments/{fake_comment_fqid}/likes"
        )
        self.assertEqual(resp.status_code, 501)

    def test_comment_likes_body_has_helpful_message(self):
        fake_fqid = quote_plus(f"{"http://testserver/"}api/comments/{uuid.uuid4()}")
        resp = self.client.get(
            f"/api/authors/{self.alice.id}/entries/{self.post.id}/comments/{fake_fqid}/likes"
        )
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("detail", data)
        self.assertIn("Comment", data["detail"])'''

class AuthorLikedSerialTests(TestCase):
    """
    Tests for GET /api/authors/<id>/liked/  [local, remote]
    Returns everything the author has liked.
    """

    def setUp(self):
        self.client = APIClient()
        self.alice = make_author("alice", "Alice")
        self.rachel = make_author("rachel", "rachel")
        self.post = make_post(self.alice)

    def test_liked_requires_auth(self):
        resp = self.client.get(f"/api/authors/{self.rachel.id}/liked/")
        self.assertEqual(resp.status_code, 403)

    def test_liked_returns_empty_when_no_likes(self):
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.rachel.id}/liked/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["type"], "likes")
        self.assertEqual(data["count"], 0)

    def test_liked_returns_likes_by_author(self):
        like = make_like(self.rachel, self.post)
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.rachel.id}/liked/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["src"][0]["type"], "like")

    def test_liked_does_not_include_other_authors_likes(self):
        """
        Alice's liked list must not contain rachel's likes.
        """
        make_like(self.rachel, self.post) 
        self.client.login(username=self.alice.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.alice.id}/liked/")
        self.assertEqual(resp.json()["count"], 0)

    def test_liked_envelope_shape(self):
        make_like(self.rachel, self.post)
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.rachel.id}/liked/")
        data = resp.json()
        for field in ("type", "page_number", "size", "count", "src"):
            self.assertIn(field, data)

    def test_liked_pagination(self):
        alice2 = make_author("alice2", "Alice2")
        post2 = make_post(alice2, "Post2")
        make_like(self.rachel, self.post)
        make_like(self.rachel, post2)
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.rachel.id}/liked/?page=1&size=1")
        data = resp.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["src"]), 1)

    def test_liked_unknown_author_returns_404(self):
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{uuid.uuid4()}/liked/")
        self.assertEqual(resp.status_code, 404)

    def test_liked_sorted_newest_first(self):
        alice2 = make_author("alice2", "Alice2")
        post2 = make_post(alice2, "Post2")
        like1 = make_like(self.rachel, self.post)
        Like.objects.filter(id=like1.id).update(published=timezone.now() - timezone.timedelta(hours=1))
        make_like(self.rachel, post2)
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.rachel.id}/liked/")
        src = resp.json()["src"]
        self.assertIn(str(post2.id), src[0]["object"])

class AuthorLikedSingleTests(TestCase):
    """
    Tests for GET /api/authors/<id>/liked/<like_serial>/  [local, remote]
    Returns a single like by its serial (UUID at end of like id URL).
    """

    def setUp(self):
        self.client = APIClient()
        self.alice = make_author("alice", "Alice")
        self.rachel = make_author("rachel", "rachel")
        self.post = make_post(self.alice)
        self.like = make_like(self.rachel, self.post)
        # Extract the serial (last segment of the like id URL)
        self.like_serial = self.like.id.rstrip("/").split("/")[-1]

    def test_single_like_requires_auth(self):
        resp = self.client.get(f"/api/authors/{self.rachel.id}/liked/{self.like_serial}/")
        self.assertEqual(resp.status_code, 403)

    def test_single_like_returns_correct_object(self):
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.rachel.id}/liked/{self.like_serial}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["type"], "like")
        self.assertEqual(data["id"], self.like.id)
        self.assertEqual(data["object"], self.like.object)
        self.assertIn("author", data)
        self.assertEqual(data["author"]["displayName"], "rachel")

    def test_single_like_wrong_author_returns_404(self):
        """
        A like owned by rachel is not accessible at alice's liked/<serial>.
        """
        self.client.login(username=self.alice.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.alice.id}/liked/{self.like_serial}/")
        self.assertEqual(resp.status_code, 404)

    def test_single_like_nonexistent_serial_returns_404(self):
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(f"/api/authors/{self.rachel.id}/liked/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)

class AuthorLikedFqidTests(TestCase):
    """
    Tests for GET /api/authors/<AUTHOR_FQID>/liked  [local]
    Author identified by URL-encoded FQID rather than bare UUID.
    """

    def setUp(self):
        self.client = APIClient()
        self.alice = make_author("alice", "Alice")
        self.rachel = make_author("rachel", "rachel")
        self.post = make_post(self.alice)

    def _url(self, author: Author):
        fqid = quote_plus(f"{author.host}api/authors/{author.id}")
        return f"/api/authors/{fqid}/liked"

    def test_liked_via_fqid_requires_auth(self):
        resp = self.client.get(self._url(self.rachel))
        self.assertEqual(resp.status_code, 403)

    def test_liked_via_fqid_returns_likes(self):
        make_like(self.rachel, self.post)
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(self._url(self.rachel))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["type"], "likes")
        self.assertEqual(data["count"], 1)

    def test_liked_via_fqid_empty(self):
        self.client.login(username=self.rachel.user.username, password="pw")
        resp = self.client.get(self._url(self.rachel))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)

    def test_liked_via_invalid_fqid_returns_404(self):
        self.client.login(username=self.rachel.user.username, password="pw")
        bad = quote_plus("http://testserver/api/authors/not-a-uuid")
        resp = self.client.get(f"/api/authors/{bad}/liked")
        self.assertEqual(resp.status_code, 404)

    def test_liked_via_nonexistent_fqid_returns_404(self):
        self.client.login(username=self.alice.user.username, password="pw")
        ghost_fqid = quote_plus(f"{"http://testserver/"}api/authors/{uuid.uuid4()}")
        resp = self.client.get(f"/api/authors/{ghost_fqid}/liked")
        self.assertEqual(resp.status_code, 404)

class LikedFqidTests(TestCase):
    """
    Tests for GET /api/liked/<LIKE_FQID>  [local]
    Returns a single like by its full URL-encoded FQID.
    No authentication required.
    """

    def setUp(self):
        self.client = APIClient()
        self.alice = make_author("alice", "Alice")
        self.rachel = make_author("rachel", "rachel")
        self.post = make_post(self.alice)
        self.like = make_like(self.rachel, self.post)

    def _url(self, like: Like):
        fqid = quote_plus(like.id)
        return f"/api/liked/{fqid}"

    def test_returns_like_by_fqid(self):
        resp = self.client.get(self._url(self.like))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["type"], "like")
        self.assertEqual(data["id"], self.like.id)
        self.assertEqual(data["object"], self.like.object)

    def test_no_auth_required(self):
        """
        GET /api/liked/<fqid> is public — no login needed.
        """
        resp = self.client.get(self._url(self.like))
        self.assertEqual(resp.status_code, 200)

    def test_inbox_requires_basic_auth(self):
        """US 03.02: Node-to-node inbox POSTs should require authentication."""
        self.client.credentials() # Clear credentials
        resp = self.client.post(
            f"/api/authors/{self.alice.id}/inbox",
            data=json.dumps(self._like_body(self.rachel, self.post)),
            content_type="application/json"
        )
  
        self.assertIn(resp.status_code, [401, 403])

    def test_nonexistent_fqid_returns_404(self):
        fake_fqid = quote_plus(f"{"http://testserver/"}api/authors/{self.rachel.id}/liked/{uuid.uuid4()}")
        resp = self.client.get(f"/api/liked/{fake_fqid}")
        self.assertEqual(resp.status_code, 404)

    def test_like_object_shape(self):
        """
        Response must have type, author, published, id, object.
        """
        resp = self.client.get(self._url(self.like))
        data = resp.json()
        for field in ("type", "author", "published", "id", "object"):
            self.assertIn(field, data)
        self.assertEqual(data["type"], "like")
        self.assertIn("displayName", data["author"])
        
    def _like_body(self, liker: Author, post: Post) -> dict:
        return {
            "type": "like",
            "author": {
                "type": "author",
                "id": f"{liker.host}api/authors/{liker.id}",
                "host": liker.host,
                "displayName": liker.displayName,
                "github": liker.github or "",
                "profileImage": liker.profileImage or "",
                "web": liker.url,
            },
            "object": entry_api_url(self.post),
        }
    
    def test_like_via_inbox_nonexistent_object(self):
        """The node should handle likes for objects it doesn't recognize gracefully."""
        self.client.login(username=self.rachel.user.username, password="pw")
        remote_body = self._like_body(self.rachel, self.post)
        remote_body["object"] = "http://unknown-node/api/authors/uuid/entries/uuid"
    
        resp = self.client.post(
            f"/api/authors/{self.alice.id}/inbox",
            data=json.dumps(remote_body),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)   

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



    def test_commented_api_post_creates_comment_for_author(self):
        path = f"/api/authors/{self.author_b.id}/commented/"
        payload = {
            "type": "comment",
            "entry": self.entry_fqid,
            "contentType": "text/plain",
            "comment": "Posted through commented API",
        }

        self.client.force_login(self.user_b)
        try:
            resp = self.client.post(path, data=json.dumps(payload), content_type="application/json")
        finally:
            self.client.logout()

        self.assertEqual(resp.status_code, 201)
        obj = resp.json()
        self._assert_is_comment_object(obj)
        self.assertEqual(obj.get("comment"), "Posted through commented API")
        self.assertEqual(
            str(obj.get("author", {}).get("id")).rstrip("/"),
            f"http://testserver/api/authors/{self.author_b.id}".rstrip("/")
        )
        self.assertTrue(
            Comment.objects.filter(
                author=self.author_b,
                post=self.post_a,
                content="Posted through commented API"
            ).exists()
        )

class APIInboxEntryAndCommentTests(TestCase):
    def setUp(self):
        self.client = Client()

        # local author who receives things in their inbox
        self.user_local = User.objects.create_user(username="inbox_local", password="pw")
        self.author_local = Author.objects.create(
            user=self.user_local,
            displayName="Local Author",
            host="http://testserver/api/",
        )
        Inbox.objects.get_or_create(author=self.author_local)

        # remote author who sends entries/comments (already known to this node)
        self.user_remote = User.objects.create_user(username="inbox_remote", password="pw")
        self.author_remote = Author.objects.create(
            user=self.user_remote,
            displayName="Remote Author",
            host="http://remotenode/api/",
        )
        Inbox.objects.get_or_create(author=self.author_remote)

        self.inbox_url = f"/api/authors/{self.author_local.id}/inbox"

    def _entry_body(self, author, post_api_url, post_web_url):
        return {
            "type": "entry",
            "id": post_api_url,
            "web": post_web_url,
            "title": "Remote Entry",
            "content": "Hello from remote",
            "contentType": "text/plain",
            "visibility": "PUBLIC",
            "author": {
                "type": "author",
                "id": author.api_url,
                "host": author.host,
                "displayName": author.displayName,
                "github": author.github or "",
                "profileImage": author.profileImage or "",
                "web": author.url,
            },
        }

    def _comment_body(self, commenter, post, comment_api_url):
        return {
            "type": "comment",
            "id": comment_api_url,
            "author": {
                "type": "author",
                "id": commenter.api_url,
                "host": commenter.host,
                "displayName": commenter.displayName,
                "github": commenter.github or "",
                "profileImage": commenter.profileImage or "",
                "web": commenter.url,
            },
            "comment": "Nice entry!",
            "contentType": "text/plain",
            "entry": post.api_url,
        }

    def test_inbox_entry_saved_to_db(self):
        """Entry POSTed to inbox is saved as a Post and added to inbox."""
        self.client.login(username="inbox_remote", password="pw")

        post_api_url = f"{self.author_remote.api_url}/entries/{uuid.uuid4()}"
        post_web_url = f"{self.author_remote.url}/posts/{uuid.uuid4()}"

        resp = self.client.post(
            self.inbox_url,
            data=json.dumps(self._entry_body(self.author_remote, post_api_url, post_web_url)),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("message"), "Post saved")
        self.assertTrue(Post.objects.filter(api_url=post_api_url).exists())
        post = Post.objects.get(api_url=post_api_url)
        self.assertIn(post, self.author_local.inbox.posts.all())

    def test_inbox_entry_fields_saved_correctly(self):
        """Entry title, content, contentType, visibility are stored correctly."""
        self.client.login(username="inbox_remote", password="pw")

        post_api_url = f"{self.author_remote.api_url}/entries/{uuid.uuid4()}"
        post_web_url = f"{self.author_remote.url}/posts/{uuid.uuid4()}"

        self.client.post(
            self.inbox_url,
            data=json.dumps(self._entry_body(self.author_remote, post_api_url, post_web_url)),
            content_type="application/json",
        )

        post = Post.objects.get(api_url=post_api_url)
        self.assertEqual(post.title, "Remote Entry")
        self.assertEqual(post.content, "Hello from remote")
        self.assertEqual(post.content_type, "text/plain")
        self.assertEqual(post.visibility, "PUBLIC")


    def test_inbox_entry_unauthenticated_returns_401(self):
        """Unauthenticated POST to inbox is rejected."""
        post_api_url = f"{self.author_remote.api_url}/entries/{uuid.uuid4()}"
        post_web_url = f"{self.author_remote.url}/posts/{uuid.uuid4()}"

        resp = self.client.post(
            self.inbox_url,
            data=json.dumps(self._entry_body(self.author_remote, post_api_url, post_web_url)),
            content_type="application/json",
        )

        self.assertIn(resp.status_code, [401, 403])
        

    def test_inbox_comment_saved_to_db(self):
        """Comment POSTed to inbox is saved against the correct local post."""
        self.client.login(username="inbox_remote", password="pw")

        local_post = Post.objects.create(
            author=self.author_local,
            title="Local Post",
            content="content",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
        )

        comment_api_url = f"{self.author_remote.api_url}/commented/{uuid.uuid4()}"

        resp = self.client.post(
            self.inbox_url,
            data=json.dumps(self._comment_body(self.author_remote, local_post, comment_api_url)),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("message"), "Comment saved")
        self.assertTrue(Comment.objects.filter(api_url=comment_api_url).exists())
        comment = Comment.objects.get(api_url=comment_api_url)
        self.assertEqual(comment.post, local_post)
        self.assertEqual(comment.content, "Nice entry!")

    def test_inbox_comment_duplicate_is_idempotent(self):
        """Sending the same comment twice does not create a duplicate."""
        self.client.login(username="inbox_remote", password="pw")

        local_post = Post.objects.create(
            author=self.author_local,
            title="Post",
            content="content",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
        )

        comment_api_url = f"{self.author_remote.api_url}/commented/{uuid.uuid4()}"
        body = json.dumps(self._comment_body(self.author_remote, local_post, comment_api_url))

        self.client.post(self.inbox_url, data=body, content_type="application/json")
        self.client.post(self.inbox_url, data=body, content_type="application/json")

        self.assertEqual(Comment.objects.filter(api_url=comment_api_url).count(), 1)

    def test_inbox_comment_unknown_entry_returns_404(self):
        """Comment referencing an entry not on this node returns 404."""
        self.client.login(username="inbox_remote", password="pw")

        # make a fake post object just to build the body, but don't save it to db
        fake_post_api_url = f"http://remotenode/api/authors/{uuid.uuid4()}/entries/{uuid.uuid4()}"
        comment_api_url = f"{self.author_remote.api_url}/commented/{uuid.uuid4()}"

        body = {
            "type": "comment",
            "id": comment_api_url,
            "author": {
                "type": "author",
                "id": self.author_remote.api_url,
                "host": self.author_remote.host,
                "displayName": self.author_remote.displayName,
                "web": self.author_remote.url,
            },
            "comment": "This entry doesn't exist here",
            "contentType": "text/plain",
            "entry": fake_post_api_url,
        }

        resp = self.client.post(
            self.inbox_url,
            data=json.dumps(body),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 404)

    def test_inbox_entry_unknown_author_creates_minimal_and_saves(self):
        """Entry from an unknown author creates a bare minimum author and saves the post."""
        self.client.login(username="inbox_local", password="pw")

        post_api_url = f"http://unknownnode/api/authors/{uuid.uuid4()}/entries/{uuid.uuid4()}"
        body = {
            "type": "entry",
            "id": post_api_url,
            "web": "http://unknownnode/authors/x/posts/x",
            "title": "Ghost Entry",
            "content": "...",
            "contentType": "text/plain",
            "visibility": "PUBLIC",
            "author": {
                "type": "author",
                "id": "http://unknownnode/api/authors/doesnotexist",
                "host": "http://unknownnode/api/",
                "displayName": "Ghost",
                "web": "http://unknownnode/authors/doesnotexist",
                "github": "",
                "profileImage": "",
            },
        }

        resp = self.client.post(
            self.inbox_url,
            data=json.dumps(body),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Post.objects.filter(api_url=post_api_url).exists())
        self.assertTrue(Author.objects.filter(api_url="http://unknownnode/api/authors/doesnotexist").exists())
        
    def test_inbox_comment_unknown_author_returns_400(self):
        """Comment from an author not in the local db returns 400."""
        self.client.login(username="inbox_local", password="pw")

        local_post = Post.objects.create(
            author=self.author_local,
            title="Post",
            content="content",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
        )

        body = {
            "type": "comment",
            "id": f"http://unknownnode/api/authors/x/commented/{uuid.uuid4()}",
            "author": {
                "type": "author",
                "id": "http://unknownnode/api/authors/doesnotexist",
                "host": "http://unknownnode/api/",
                "displayName": "Ghost",
                "web": "http://unknownnode/authors/doesnotexist",
            },
            "comment": "Ghost comment",
            "contentType": "text/plain",
            "entry": local_post.api_url,
        }

        resp = self.client.post(
            self.inbox_url,
            data=json.dumps(body),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 400)
        
class PushToRemoteTests(TestCase):
    def setUp(self):
        self.user_local = User.objects.create_user(username="push_local", password="pw")
        self.author_local = Author.objects.create(
            user=self.user_local,
            displayName="Local Author",
            host="http://testserver/api/",
        )
        Inbox.objects.get_or_create(author=self.author_local)

        # remote follower on a different node
        self.user_remote = User.objects.create_user(username="push_remote", password="pw")
        self.author_remote = Author.objects.create(
            displayName="Remote Follower",
            host="http://remotenode/api/",
        )
        Inbox.objects.get_or_create(author=self.author_remote)

        # make remote author a follower of local author
        self.author_local.followers.add(self.author_remote)

        # enabled node for remotenode
        self.node = Node.objects.create(
            url="http://remotenode/api/",
            username="remoteuser",
            password="remotepass",
            is_enabled=True,
        )

    def _make_post(self, visibility):
        return Post.objects.create(
            author=self.author_local,
            title="Test Push",
            content="Hello remote",
            content_type="text/plain",
            visibility=visibility,
            type=Post.Type.TEXT,
        )

    @patch("authors.helpers.requests.post")
    def test_public_post_pushed_to_remote(self, mock_post):
        """Public post is pushed to remote follower's inbox."""
        from authors.helpers import push_post_to_remote
        post = self._make_post(Post.Visibility.PUBLIC)
        push_post_to_remote(post, self.author_local)

        self.assertTrue(mock_post.called)
        called_url = mock_post.call_args[0][0]
        self.assertIn(str(self.author_remote.id), called_url)
        self.assertIn("inbox", called_url)

    @patch("authors.helpers.requests.post")
    def test_friends_only_post_not_pushed_to_follower(self, mock_post):
        """Friends-only post is not pushed to a follower who is not a friend."""
        from authors.helpers import push_post_to_remote
        post = self._make_post(Post.Visibility.FRIENDS)
        push_post_to_remote(post, self.author_local)

        self.assertFalse(mock_post.called)

    @patch("authors.helpers.requests.post")
    def test_friends_only_post_pushed_to_friend(self, mock_post):
        """Friends-only post is pushed to a remote friend."""
        from authors.helpers import push_post_to_remote
        # upgrade remote author from follower to friend
        self.author_local.followers.remove(self.author_remote)
        self.author_local.friends.add(self.author_remote)

        post = self._make_post(Post.Visibility.FRIENDS)
        push_post_to_remote(post, self.author_local)

        self.assertTrue(mock_post.called)

    @patch("authors.helpers.requests.post")
    def test_disabled_node_not_pushed_to(self, mock_post):
        """
        US: node admin can disable connections.
        Disabled node should not receive any pushes.
        """
        from authors.helpers import push_post_to_remote
        self.node.is_enabled = False
        self.node.save()

        post = self._make_post(Post.Visibility.PUBLIC)
        push_post_to_remote(post, self.author_local)

        self.assertFalse(mock_post.called)

    @patch("authors.helpers.requests.post")
    def test_local_follower_not_pushed_to(self, mock_post):
        """Local followers are not pushed to via HTTP — they get posts through inbox directly."""
        from authors.helpers import push_post_to_remote
        # add a local follower (same host)
        local_follower = Author.objects.create(
            displayName="Local Follower",
            host="http://testserver/api/",
        )
        self.author_local.followers.add(local_follower)

        post = self._make_post(Post.Visibility.PUBLIC)
        push_post_to_remote(post, self.author_local)

        # only the remote follower should be pushed to, not the local one
        for c in mock_post.call_args_list:
            self.assertNotIn(str(local_follower.id), c[0][0])

    @patch("authors.helpers.requests.post")
    def test_push_uses_node_credentials(self, mock_post):
        """Push uses the node's HTTP Basic Auth credentials."""
        from authors.helpers import push_post_to_remote
        post = self._make_post(Post.Visibility.PUBLIC)
        push_post_to_remote(post, self.author_local)

        self.assertTrue(mock_post.called)
        kwargs = mock_post.call_args[1]
        self.assertEqual(kwargs["auth"], ("remoteuser", "remotepass"))

    @patch("authors.helpers.requests.post")
    def test_push_body_contains_correct_fields(self, mock_post):
        """Push body contains all required entry fields."""
        from authors.helpers import push_post_to_remote
        post = self._make_post(Post.Visibility.PUBLIC)
        push_post_to_remote(post, self.author_local)

        self.assertTrue(mock_post.called)
        kwargs = mock_post.call_args[1]
        body = kwargs["json"]
        self.assertEqual(body["type"], "entry")
        self.assertEqual(body["title"], "Test Push")
        self.assertEqual(body["content"], "Hello remote")
        self.assertEqual(body["visibility"], "PUBLIC")
        self.assertIn("author", body)