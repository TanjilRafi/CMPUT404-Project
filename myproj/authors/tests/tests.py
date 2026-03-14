# The following API test code was written with assistance from OpenAI (ChatGPT).
# Prompt used: “Review the project files and help me debug test
# import issues and to structure endpoint tests.”
# Date: 2026-03-02


from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from authors.models import Author, Post, Inbox

import base64

from datetime import timedelta
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework.test import APIClient  
from django.apps import apps

def make_author(user: User, display_name: str) -> Author:
    """
    Creates an Author + Inbox for a given User.
    """
    author = Author.objects.create(
        user=user,
        displayName=display_name,
        host="http://testserver/",
    )
    Inbox.objects.create(author=author)
    return author


class IdentityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="alice", password="password")
        self.author = make_author(self.user, "alice")

    def test_author_identity_url_stable(self):
        """US 01.01 - consistent identity """
        url_before = reverse("author_profile", args=[self.author.id])

        self.author.displayName = "Alice Updated"
        self.author.save()

        url_after = reverse("author_profile", args=[self.author.id])
        self.assertEqual(url_before, url_after)

    def test_multiple_authors_supported(self):
        """US 01.02 - node can host multiple authors"""
        user2 = User.objects.create_user(username="rachel", password="password")
        make_author(user2, "rachel")

        resp = self.client.get(reverse("authors_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice")
        self.assertContains(resp, "rachel")

class ProfileEditTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username="alice", password="password")
        self.user2 = User.objects.create_user(username="rachel", password="password")
        self.author1 = make_author(self.user1, "alice")
        self.author2 = make_author(self.user2, "rachel")

    def test_edit_profile_owner_only(self):
        """US 01.06 - author can edit their own profile, not others"""
        self.client.login(username="alice", password="password")
        resp = self.client.get(reverse("edit_profile", args=[self.author2.id]))
        self.assertEqual(resp.status_code, 403)

    def test_manage_profile_owner_only(self):
        """US 01.07 - browser manage page, owner-only"""
        self.client.login(username="alice", password="password")

        # alice can access her manage page
        resp_ok = self.client.get(reverse("manage_profile", args=[self.author1.id]))
        self.assertEqual(resp_ok.status_code, 200)

        # alice cannot access rachel's manage page
        resp_forbidden = self.client.get(reverse("manage_profile", args=[self.author2.id]))
        self.assertEqual(resp_forbidden.status_code, 403)


class PostCRUDTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="alice", password="password")
        self.author = make_author(self.user, "alice")
        self.client.login(username="alice", password="password")

    def test_create_post_plain_text(self):
        """US 02.01 + US 02.06 - create plain text entry"""
        resp = self.client.post(
            reverse("create_post", args=[self.author.id]),
            {
                "title": "Test Post",
                "content": "Hello world",
                "type": Post.Type.TEXT,
                "visibility": Post.Visibility.PUBLIC,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Post.objects.count(), 1)

        post = Post.objects.first()
        self.assertEqual(post.type, Post.Type.TEXT)
        self.assertEqual(post.content_type, "text/plain")
        self.assertFalse(post.is_deleted)

    def test_create_post_commonmark(self):
        """US 02.05 """
        resp = self.client.post(
            reverse("create_post", args=[self.author.id]),
            {
                "title": "MD",
                "content": "# Hello",
                "type": Post.Type.COMMONMARK,
                "visibility": Post.Visibility.PUBLIC,
            },
        )
        self.assertEqual(resp.status_code, 302)
        post = Post.objects.get(title="MD")
        self.assertEqual(post.type, Post.Type.COMMONMARK)
        self.assertEqual(post.content_type, "text/markdown")

    def test_edit_post_owner_only(self):
        """US 02.03 + US 02.12 - only owner can edit"""
        post = Post.objects.create(
            author=self.author,
            title="Original",
            content="Test",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
        )

        resp = self.client.post(
            reverse("edit_post", args=[self.author.id, post.id]),
            {"title": "Updated", "content": "Updated", "visibility": Post.Visibility.PUBLIC},
        )
        self.assertEqual(resp.status_code, 302)
        post.refresh_from_db()
        self.assertEqual(post.title, "Updated")

    def test_delete_post_soft_delete(self):
        """US 02.09 + US 08.14 - soft delete"""
        post = Post.objects.create(
            author=self.author,
            title="Delete Me",
            content="Content",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
        )

        resp = self.client.post(reverse("delete_post", args=[self.author.id, post.id]))
        self.assertEqual(resp.status_code, 302)

        post.refresh_from_db()
        self.assertTrue(post.is_deleted)
        self.assertEqual(Post.objects.filter(id=post.id).count(), 1)


class VisibilityAndStreamTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username="alice", password="password")
        self.user2 = User.objects.create_user(username="rachel", password="password")
        self.author1 = make_author(self.user1, "alice")
        self.author2 = make_author(self.user2, "rachel")

    def test_public_post_visible_to_anonymous_stream(self):
        """US 04.01 + US 04.06 - public visible to everyone in stream"""
        Post.objects.create(
            author=self.author1,
            title="Public Post",
            content="Visible",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
        )
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Public Post")

    def test_unlisted_not_in_public_stream_but_accessible_by_link(self):
        """US 04.02 + US 04.07 - unlisted not in stream, but accessible by direct URL"""
        post = Post.objects.create(
            author=self.author1,
            title="Unlisted Post",
            content="Hidden",
            content_type="text/plain",
            visibility=Post.Visibility.UNLISTED,
            type=Post.Type.TEXT,
        )

        # should not appear in public stream
        resp_stream = self.client.get(reverse("home"))
        self.assertNotContains(resp_stream, "Unlisted Post")

        # but direct link should work even without login
        resp_detail = self.client.get(reverse("post_detail", args=[self.author1.id, post.id]))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, "Unlisted Post")

    def test_deleted_not_in_stream(self):
        """US 03.01.04 + US 04.09 - deleted entries not shown in stream"""
        Post.objects.create(
            author=self.author1,
            title="Deleted Post",
            content="Gone",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
            is_deleted=True,
        )
        resp = self.client.get(reverse("home"))
        self.assertNotContains(resp, "Deleted Post")

    def test_stream_sorted_newest_first(self):
        """US 03.02 - stream newest first"""
        old = Post.objects.create(
            author=self.author1,
            title="Old",
            content="Old",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
        )

        Post.objects.filter(id=old.id).update(created_at=timezone.now() - timezone.timedelta(minutes=10))

        new = Post.objects.create(
            author=self.author1,
            title="New",
            content="New",
            content_type="text/plain",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
        )
        Post.objects.filter(id=new.id).update(created_at=timezone.now())

        resp = self.client.get(reverse("home"))
        html = resp.content.decode("utf-8")

        self.assertTrue(html.index("New") < html.index("Old"))



class UserStoryTests(TestCase):

    def setUp(self):
        self.client = Client()

        self.user_a = User.objects.create_user(username="alice", password="pass123")
        self.author_a = Author.objects.create(
            user=self.user_a,
            displayName="Alice",
            host="http://testserver/",
            github="",
            profileImage="",
        )

        self.user_b = User.objects.create_user(username="rachel", password="pass123")
        self.author_b = Author.objects.create(
            user=self.user_b,
            displayName="Rachel",
            host="http://testserver/",
            github="",
            profileImage="",
        )
        Inbox = apps.get_model("authors", "Inbox")
        Inbox.objects.get_or_create(author=self.author_a)
        Inbox.objects.get_or_create(author=self.author_b)

    # helpers

    def _make_post(
        self,
        *,
        author: Author,
        title: str,
        visibility: str,
        type_: str = Post.Type.TEXT,
        content: str = "hello",
        content_type: str = "text/plain",
        created_at=None,
        is_deleted: bool = False,
    ) -> Post:
        post = Post.objects.create(
            author=author,
            title=title,
            content=content,
            visibility=visibility,
            type=type_,
            content_type=content_type,
            is_deleted=is_deleted,
        )
        if created_at is not None:
            Post.objects.filter(id=post.id).update(created_at=created_at)
            post.refresh_from_db()
        return post

    # 0.02 — node can host multiple authors

    def test_US_0_02_authors_list_shows_multiple_authors(self):
        url = reverse("authors_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")

        self.assertIn("Alice", html)
        self.assertIn("Rachel", html)

    # 01.05 — profile shows public posts, newest first

    def test_US_01_05_profile_shows_public_posts_newest_first(self):
        now = timezone.now()
        old_pub = self._make_post(
            author=self.author_a,
            title="Old Public",
            visibility=Post.Visibility.PUBLIC,
            created_at=now - timedelta(days=2),
        )
        self._make_post(
            author=self.author_a,
            title="Unlisted Should Not Appear",
            visibility=Post.Visibility.UNLISTED,
            created_at=now - timedelta(days=1),
        )
        new_pub = self._make_post(
            author=self.author_a,
            title="New Public",
            visibility=Post.Visibility.PUBLIC,
            created_at=now,
        )

        url = reverse("author_profile", kwargs={"id": self.author_a.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")

        # public posts show up
        self.assertIn(old_pub.title, html)
        self.assertIn(new_pub.title, html)
        self.assertNotIn("Unlisted Should Not Appear", html)

        # newest first
        self.assertLess(html.index(new_pub.title), html.index(old_pub.title))

    # 02.11 — manage posts via browser

    def test_US_02_11_create_edit_delete_post_via_browser(self):
        self.client.login(username="alice", password="pass123")

        # create TEXT
        create_url = reverse("create_post", kwargs={"id": self.author_a.id})
        resp = self.client.post(
            create_url,
            data={
                "title": "Initial",
                "content": "hello",
                "visibility": Post.Visibility.PUBLIC,
                "type": Post.Type.TEXT,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        post = Post.objects.get(author=self.author_a, title="Initial")
        self.assertFalse(post.is_deleted)

        # edit
        edit_url = reverse(
            "edit_post", kwargs={"id": self.author_a.id, "post_id": post.id}
        )
        resp2 = self.client.post(
            edit_url,
            data={
                "title": "Updated",
                "content": "new content",
                "visibility": Post.Visibility.UNLISTED,
            },
            follow=True,
        )
        self.assertEqual(resp2.status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.title, "Updated")
        self.assertEqual(post.content, "new content")
        self.assertEqual(post.visibility, Post.Visibility.UNLISTED)

        # delete
        delete_url = reverse(
            "delete_post", kwargs={"id": self.author_a.id, "post_id": post.id}
        )
        resp3 = self.client.post(delete_url, follow=True)
        self.assertEqual(resp3.status_code, 200)
        post.refresh_from_db()
        self.assertTrue(post.is_deleted)
        self.assertTrue(Post.objects.filter(id=post.id).exists())

        # not shown in own post list after deletion
        list_url = reverse("post_list", kwargs={"id": self.author_a.id})
        list_resp = self.client.get(list_url)
        self.assertEqual(list_resp.status_code, 200)
        self.assertNotIn("Updated", list_resp.content.decode("utf-8"))

    # 02.07 — Image posts can be created 

    def test_US_02_07_create_image_post_stores_base64(self):
        self.client.login(username="alice", password="pass123")

        img_bytes = b"\x89PNG\r\n\x1a\n" + b"FAKEPNGDATA"
        upload = SimpleUploadedFile("x.png", img_bytes, content_type="image/png")

        create_url = reverse("create_post", kwargs={"id": self.author_a.id})
        resp = self.client.post(
            create_url,
            data={
                "title": "My Image",
                "visibility": Post.Visibility.PUBLIC,
                "type": Post.Type.IMAGE, 
                "img": upload,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        post = Post.objects.get(author=self.author_a, title="My Image")
        self.assertEqual(post.type, Post.Type.IMAGE)
        self.assertEqual(post.content_type, "image/png")

        decoded = base64.b64decode(post.content.encode("utf-8"))
        self.assertEqual(decoded, img_bytes)

    # 03.01 — public post listing behavior 

    def test_US_03_01_public_post_list_shows_only_public(self):
        now = timezone.now()
        self._make_post(
            author=self.author_a,
            title="Public Old",
            visibility=Post.Visibility.PUBLIC,
            created_at=now - timedelta(hours=2),
        )
        self._make_post(
            author=self.author_a,
            title="Unlisted Hidden",
            visibility=Post.Visibility.UNLISTED,
            created_at=now - timedelta(hours=1),
        )
        self._make_post(
            author=self.author_a,
            title="Friends Hidden",
            visibility=Post.Visibility.FRIENDS,
            created_at=now,
        )

        list_url = reverse("post_list", kwargs={"id": self.author_a.id})
        resp = self.client.get(list_url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")

        self.assertIn("Public Old", html)
        self.assertNotIn("Unlisted Hidden", html)
        self.assertNotIn("Friends Hidden", html)

    # 03.01.01 — Logged in author sees all of their own not deleted posts

    def test_US_03_01_01_author_sees_all_own_posts_in_list(self):
        self._make_post(author=self.author_a, title="P", visibility=Post.Visibility.PUBLIC)
        self._make_post(author=self.author_a, title="U", visibility=Post.Visibility.UNLISTED)
        self._make_post(author=self.author_a, title="F", visibility=Post.Visibility.FRIENDS)
        self._make_post(
            author=self.author_a,
            title="D",
            visibility=Post.Visibility.PUBLIC,
            is_deleted=True,
        )

        self.client.login(username="alice", password="pass123")
        list_url = reverse("post_list", kwargs={"id": self.author_a.id})
        resp = self.client.get(list_url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")

        self.assertIn("P", html)
        self.assertIn("U", html)
        self.assertIn("F", html)
        self.assertNotIn("<h3>D</h3>", html)  

    # 03.01.02 / 03.01.03 — unlisted is not on list but is accessible by direct link

    def test_US_03_01_02_unlisted_hidden_from_list_but_accessible_by_link(self):
        post = self._make_post(
            author=self.author_a,
            title="Secret Link",
            visibility=Post.Visibility.UNLISTED,
        )

        list_url = reverse("post_list", kwargs={"id": self.author_a.id})
        list_resp = self.client.get(list_url)
        self.assertEqual(list_resp.status_code, 200)
        self.assertNotIn("Secret Link", list_resp.content.decode("utf-8"))

        detail_url = reverse(
            "post_detail", kwargs={"id": self.author_a.id, "post_id": post.id}
        )
        detail_resp = self.client.get(detail_url)
        self.assertEqual(detail_resp.status_code, 200)

    # 04.03 — friends only posts which not accessible unless you're the author
    # 04.08 — non friends cannot access friends only posts

    def test_US_04_03_04_08_friends_only_hidden_from_non_author(self):
        post = self._make_post(
            author=self.author_a,
            title="Friends Only",
            visibility=Post.Visibility.FRIENDS,
        )

        detail_url = reverse(
            "post_detail", kwargs={"id": self.author_a.id, "post_id": post.id}
        )

        anon_resp = self.client.get(detail_url)
        self.assertEqual(anon_resp.status_code, 404)

        self.client.login(username="rachel", password="pass123")
        other_resp = self.client.get(detail_url)
        self.assertEqual(other_resp.status_code, 404)

        # owner is allowed
        self.client.logout()
        self.client.login(username="alice", password="pass123")
        owner_resp = self.client.get(detail_url)
        self.assertEqual(owner_resp.status_code, 200)

    # 04.10 — author can always view their own not deleted posts regardless of visibility

    def test_US_04_10_author_can_view_own_posts_regardless_of_visibility(self):
        pub = self._make_post(author=self.author_a, title="P", visibility=Post.Visibility.PUBLIC)
        unl = self._make_post(author=self.author_a, title="U", visibility=Post.Visibility.UNLISTED)
        fri = self._make_post(author=self.author_a, title="F", visibility=Post.Visibility.FRIENDS)

        self.client.login(username="alice", password="pass123")
        for post in (pub, unl, fri):
            url = reverse(
                "post_detail", kwargs={"id": self.author_a.id, "post_id": post.id}
            )
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)

    # 08.11 — delete keeps data but hides it from normal views

    def test_US_08_11_soft_delete_keeps_row_in_db(self):
        self.client.login(username="alice", password="pass123")
        post = self._make_post(
            author=self.author_a,
            title="SoftDelete",
            visibility=Post.Visibility.PUBLIC,
        )

        delete_url = reverse(
            "delete_post", kwargs={"id": self.author_a.id, "post_id": post.id}
        )
        self.client.post(delete_url, follow=True)

        self.assertTrue(Post.objects.filter(id=post.id).exists())
        post.refresh_from_db()
        self.assertTrue(post.is_deleted)


class APISurfaceTests(TestCase):
    def setUp(self):
        self.client = APIClient()  
        self.user = User.objects.create_user(username="u", password="pass123")
        self.author = Author.objects.create(
            user=self.user,
            displayName="U",
            host="http://testserver/",
            github="",
            profileImage="",
        )
        Inbox = apps.get_model("authors", "Inbox")
        Inbox.objects.get_or_create(author=self.author)

    def test_api_delete_post_marks_deleted(self):
        post = Post.objects.create(
            author=self.author,
            title="x",
            content="y",
            visibility=Post.Visibility.PUBLIC,
            type=Post.Type.TEXT,
            content_type="text/plain",
        )

        url = reverse("api_entry_detail", kwargs={"id": self.author.id, "post_id": post.id})

        self.client.force_authenticate(user=self.user)

        resp = self.client.delete(url)

        self.assertIn(resp.status_code, (200, 204))

        post.refresh_from_db()
        self.assertTrue(post.is_deleted)