# ────────────────────────────────────────────────────────────────
# Imports
# ────────────────────────────────────────────────────────────────
from django.shortcuts import render, get_object_or_404, redirect
from authors.models import Author, Post, Inbox, Entry, Comment, Like, Node
from authors.forms import AuthorForm
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotFound, Http404, JsonResponse

from django.contrib.auth.decorators import login_required       # to confirm logins before creating posts
from django.views.decorators.http import require_http_methods
from markdown_it import MarkdownIt
from django.db.models import Q
from django.urls import reverse
from django.core.paginator import Paginator

import base64 # to handle images
import urllib.parse
import requests

# for api views
import json
import uuid
from django.views.decorators.http import require_http_methods       # to automatically reject (405 error) for unaccepted methods
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, authentication_classes, permission_classes, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse, OpenApiParameter
from authors.serializers import AuthorSerializer, EntrySerializer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .models import Node
from urllib.parse import urljoin

from drf_spectacular.types import OpenApiTypes


def helper_post_detail(request, author, post):
    """
    Helper function to render post detail page with comments and likes.
    """
    comments = list(Comment.objects.filter(post = post).select_related('author').order_by('published'))
    
    for comment in comments:
        comment.likes_count = comment.likes.count()
        
    likes_count = post.likes.count()
    user_liked = False
    like_comment_ids = set()
    
    if request.user.is_authenticated and hasattr(request.user, 'author'):
        user_liked = post.likes.filter(author = request.user.author, post = post).exists()
        like_comment_ids = set(Like.objects.filter(author = request.user.author, comment__in = comments).values_list('comment_id', flat=True))
        
    return {
        "author": author,
        "post": post,
        "likes_count": likes_count,
        "comments": comments,
        "user_liked": user_liked,
        "like_comment_ids": like_comment_ids
    }
    
def serialize_like(like):
    """Helper to format like objects as per spec example"""
    if like.comment:
        object = like.comment.post.api_url
    elif like.post:
        object = like.post.api_url
    return {
        "type":"like",
        "author":{
            "type":"author",
            "id": like.author.api_url, 
            "web": like.author.url,
            "host": like.author.host,
            "displayName": like.author.displayName,
            "github": like.author.github or "",
            "profileImage": like.author.profileImage or "",
        },
        "published": like.published.isoformat(),
        "id": like.api_url, # was like.id — that was a UUID, not a URL string
        "object": object,
    }

def _comment_to_api(comment: Comment):
    comment_likes = comment.likes.select_related("author").order_by("-published")[:50]
    return {
        "type": "comment",
        "author": {
            "type": "author",
            "id": comment.author.api_url,
            "web": comment.author.url,
            "host": comment.author.host,
            "displayName": comment.author.displayName,
            "github": comment.author.github or "",
            "profileImage": comment.author.profileImage or "",
        },
        "comment": comment.content,
        "contentType": comment.contentType,
        "published": comment.published.isoformat(),
        "id": comment.api_url,       # use stored vals from api, not reconstructed
        "entry": comment.post.api_url,
        "web": comment.url,
        "likes": {
            "type": "likes",
            "web": comment.url,
            "id": f"{comment.api_url}/likes",
            "page_number": 1,
            "size": 50,
            "count": comment.likes.count(),
            "src": [serialize_like(like) for like in comment_likes],
        },
    }

def _comment_id_from_fqid(comment_fqid: str):
    decoded = urllib.parse.unquote_plus(comment_fqid).rstrip("/")
    comment_id = decoded.split("/")[-1]
    return comment_id


def push_post_to_remote(post, author):
    """
    Push a post to the inboxes of all remote followers and friends.
    Only sends to nodes that are enabled.
    Remote followers are those whose host differs from the local author's host.
    """
    from .models import Node

    if post.visibility == Post.Visibility.PUBLIC:
        # reciever = list(Author.objects.get(~Q(host=author.host))) # only select remote authors
        reciever = list(Author.objects.exclude(host=author.host))
    elif post.visibility == Post.Visibility.UNLISTED:
        reciever = list(author.followers.all()) + list(author.friends.all())
    elif post.visibility == Post.Visibility.FRIENDS:
        reciever = list(author.friends.all())
    # elif post.visibility == Post.Visibility.DELETED:
    #     reciever = [inbox.author for inbox in post.sent_to.all() if inbox.author.host != author.host]
    else:
        return  # dont push if unknown visibility or deleted

    # post_body = {
    #     "type": "entry",
    #     "title": post.title,
    #     "id": post.api_url,
    #     "web": post.url,
    #     "contentType": post.contentType,
    #     "content": post.content,
    #     "visibility": post.visibility,
    #     "author": {
    #         "type": "author",
    #         "id": author.api_url,
    #         "host": author.host,
    #         "displayName": author.displayName,
    #         "web": author.url,
    #         "github": author.github or "",
    #         "profileImage": author.profileImage or "",
    #     },
    # }
    post_body = EntrySerializer(post).data

    for follower in reciever:
        # only push to remote followers (different host)
        if follower.host == author.host:
            continue

        # check if the remote node is enabled
        node = Node.objects.filter(url=follower.host, is_enabled=True).first()
        if not node:
            continue

        # got help from Claude, Accessed 18 March 2026
        # inbox_url = urljoin(follower.api_url.rstrip('/') + '/', "inbox")
        # try:
        #     response = requests.post(
        #         inbox_url,
        #         json=post_body,
        #         auth=(node.username, node.password),
        #         timeout=5,
        #     )
        #     print("PUSHING POST TO REMOTE")
        #     print("Inbox URL:", inbox_url)
        #     print("Payload:", post_body)
        #     print("Response:", response.status_code, response.text)
        # except requests.RequestException:
        #     # dont let a failed push crash the local operation
        #     pass

        base_url = follower.api_url.rstrip('/')
        inbox_variants = [
            f"{base_url}/inbox",
            f"{base_url}/inbox/"
        ]

        print("PUSHING POST TO REMOTE")
        print("Payload:", post_body)

        for inbox_url in inbox_variants:
            try:
                print("Trying Inbox URL:", inbox_url)

                response = requests.post(
                    inbox_url,
                    json=post_body,
                    auth=(node.username, node.password),
                    timeout=5,
                )

                print("Response:", response.status_code)

                if response.status_code < 300 and response.status_code >= 200:
                    print("Success with:", inbox_url)
                    break  # stop once one works

            except requests.exceptions.ChunkedEncodingError as e:
                print("ChunkedEncodingError (treating as success):", e)
                break
            except requests.RequestException as e:
                print("Failed on:", inbox_url, "| Error:", e)
                continue

    
# GET a single author - remote
def get_or_fetch_author(fqid):
    fqid = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")

    # Check locally
    author = Author.objects.filter(api_url=fqid).first()
    if author:
        return author

    # Fetch from remote
    parsed_url = urllib.parse.urlparse(fqid)
    remote_host = parsed_url.netloc

    node = Node.objects.filter(url__icontains=remote_host, is_enabled=True).first()
    if not node:
        return None

    try:
        response = requests.get(
            fqid,
            auth=(node.username, node.password),
            timeout=5
        )
        response.raise_for_status()
        data = response.json()

        # created with help of Claude AI, Accessed March 25, 2026
        # store/update locally
        author, _ = Author.objects.update_or_create(
            api_url=fqid,
            defaults={
                "displayName": data.get("displayName"),
                "host": data.get("host"),
                "url": data.get("url"),
                "github": data.get("github"),
                "profileImage": data.get("profileImage"),
            }
        )
        return author

    except Exception as e:
        print(f"[ERROR] Fetch failed: {e}")
        return None
    


def push_post_to_delete(post, author):
    """
    Push a post to the inboxes of all remote followers and friends.
    Only sends to nodes that are enabled.
    Remote followers are those whose host differs from the local author's host.
    """
    from .models import Node

    if post.visibility == Post.Visibility.PUBLIC:
        # reciever = list(Author.objects.get(~Q(host=author.host))) # only select remote authors
        reciever = list(Author.objects.exclude(host=author.host))
    elif post.visibility == Post.Visibility.UNLISTED:
        reciever = list(author.followers.all()) + list(author.friends.all())
    elif post.visibility == Post.Visibility.FRIENDS:
        reciever = list(author.friends.all())
    else:
        return  # dont push if unknown visibility
    
    original_visibility = post.visibility
    post.visibility = Post.Visibility.DELETED

    # post_body = {
    #     "type": "entry",
    #     "title": post.title,
    #     "id": post.api_url,
    #     "web": post.url,
    #     "contentType": post.contentType,
    #     "content": post.content,
    #     "visibility": post.visibility,
    #     "author": {
    #         "type": "author",
    #         "id": author.api_url,
    #         "host": author.host,
    #         "displayName": author.displayName,
    #         "web": author.url,
    #         "github": author.github or "",
    #         "profileImage": author.profileImage or "",
    #     },
    # }
    post_body = EntrySerializer(post).data

    for follower in reciever:
        # only push to remote followers (different host)
        if follower.host == author.host:
            continue

        # check if the remote node is enabled
        node = Node.objects.filter(url=follower.host, is_enabled=True).first()
        if not node:
            continue

        # got help from Claude, Accessed 18 March 2026
        # inbox_url = urljoin(follower.api_url.rstrip('/') + '/', "inbox")
        # try:
        #     response = requests.post(
        #         inbox_url,
        #         json=post_body,
        #         auth=(node.username, node.password),
        #         timeout=5,
        #     )
        #     print("PUSHING POST TO DELETE")
        #     print("Inbox URL:", inbox_url)
        #     print("Payload:", post_body)
        #     print("Response:", response.status_code, response.text)
        # except requests.RequestException:
        #     # dont let a failed push crash the local operation
        #     pass
        base_url = follower.api_url.rstrip('/')
        inbox_variants = [
            f"{base_url}/inbox",
            f"{base_url}/inbox/"
        ]

        print("PUSHING POST TO REMOTE")
        print("Payload:", post_body)

        for inbox_url in inbox_variants:
            try:
                print("Trying Inbox URL:", inbox_url)

                response = requests.post(
                    inbox_url,
                    json=post_body,
                    auth=(node.username, node.password),
                    timeout=5,
                )

                print("Response:", response.status_code, response.text)

                if response.status_code < 300 and response.status_code >= 200:
                    print("Success with:", inbox_url)
                    break  # stop once one works

            except requests.exceptions.ChunkedEncodingError as e:
                print("ChunkedEncodingError (treating as success):", e)
                break
            except requests.RequestException as e:
                print("Failed on:", inbox_url, "| Error:", e)
                continue

# def push_like_to_remote(like, liker_author, post):
#     """
#     Push a like to the post author's inbox if they are on a remote node.
#     Only fires when the post author lives on a different host than the liker.
#     """
#     from .models import Node
#     from authors.serializers import AuthorSerializer

#     post_author = post.author
#     # post is local, no push needed, the like is already in our DB
#     if post_author.host == liker_author.host:
#         return

#     node = Node.objects.filter(url=post_author.host, is_enabled=True).first()
#     if not node:
#         return

#     like_body = {
#         "type": "like",
#         "author": AuthorSerializer(liker_author).data,
#         "object": post.api_url,
#         "id": like.api_url,
#     }

#     inbox_url = f"{post_author.api_url}/inbox"
#     try:
#         requests.post(
#             inbox_url,
#             json=like_body,
#             auth=(node.username, node.password),
#             timeout=5,
#         )
#     except requests.RequestException:
#         pass


# def push_comment_like_to_remote(like, liker_author, comment):
#     """
#     Push a comment like to the post author's inbox if they are on a remote node.
#     """
#     from .models import Node
#     from authors.serializers import AuthorSerializer

#     post_author = comment.post.author
#     if post_author.host == liker_author.host:
#         return

#     node = Node.objects.filter(url=post_author.host, is_enabled=True).first()
#     if not node:
#         return

#     like_body = {
#         "type": "like",
#         "author": AuthorSerializer(liker_author).data,
#         "object": comment.api_url,
#         "id": like.api_url,
#     }

#     inbox_url = f"{post_author.api_url}/inbox"
#     try:
#         requests.post(
#             inbox_url,
#             json=like_body,
#             auth=(node.username, node.password),
#             timeout=5,
#         )
#     except requests.RequestException:
#         pass


# def push_comment_to_remote(comment, commenter_author, post):
#     """
#     Push a new comment to the post author's inbox if they are on a remote node.
#     """
#     from .models import Node
#     from authors.serializers import AuthorSerializer

#     post_author = post.author
#     if post_author.host == commenter_author.host:
#         return

#     node = Node.objects.filter(url=post_author.host, is_enabled=True).first()
#     if not node:
#         return

#     comment_body = {
#         "type": "comment",
#         "id": comment.api_url,
#         "author": AuthorSerializer(commenter_author).data,
#         "comment": comment.content,
#         "contentType": comment.contentType,
#         "published": comment.published.isoformat(),
#         "entry": post.api_url,
#     }

#     inbox_url = f"{post_author.api_url}/inbox"
#     try:
#         requests.post(
#             inbox_url,
#             json=comment_body,
#             auth=(node.username, node.password),
#             timeout=5,
#         )
#     except requests.RequestException:
#         pass

# using ClaudeAI to help with debug statements
def push_like_to_remote(like, liker_author, post):
    """
    Push a new like on a post to the post author's inbox if they are on a remote node.
    """
    from .models import Node
    from authors.serializers import AuthorSerializer

    post_author = post.author

    print(f"[DEBUG LIKE PUSH] Like by {liker_author.displayName} on post '{post.title}' → target post author: {post_author.displayName} ({post_author.host})")

    # Same node → no remote push needed
    if post_author.host.rstrip('/').rstrip('/api').rstrip('/') == liker_author.host.rstrip('/').rstrip('/api').rstrip('/'):
        print(f"[DEBUG LIKE PUSH] Same node - skipping remote push")
        return

    # Find enabled Node record for the remote author
    target_host = post_author.host.rstrip('/').rstrip('/api').rstrip('/') + "/api/"
    node = Node.objects.filter(url__startswith=target_host[:target_host.find("/api")], is_enabled=True).first()

    if not node:
        print(f"[DEBUG LIKE PUSH] ❌ No enabled Node found for host: {post_author.host}")
        print(f"[DEBUG LIKE PUSH] Tried matching: {target_host}")
        return

    print(f"[DEBUG LIKE PUSH] ✅ Found enabled Node for remote host: {node.url}")

    like_body = {
        "type": "like",
        "author": AuthorSerializer(liker_author).data,
        "object": post.api_url,
        "id": like.api_url,
    }

    # inbox_url = f"{post_author.api_url.rstrip('/')}/inbox"
    # print(f"[DEBUG LIKE PUSH] Sending like to inbox: {inbox_url}")

    # try:
    #     response = requests.post(
    #         inbox_url,
    #         json=like_body,
    #         auth=(node.username, node.password),
    #         timeout=8,
    #     )
    #     print(f"[DEBUG LIKE PUSH] ✅ Remote like sent - status: {response.status_code}")
    # except requests.RequestException as e:
    #     print(f"[DEBUG LIKE PUSH] ❌ Failed to send like to remote: {e}")

    base_url = post_author.api_url.rstrip('/')
    inbox_variants = [
        f"{base_url}/inbox",
        f"{base_url}/inbox/"
    ]

    print("[DEBUG LIKE PUSH] Payload:", like_body)

    success = False

    for inbox_url in inbox_variants:
        try:
            print(f"[DEBUG LIKE PUSH] Trying inbox: {inbox_url}")

            response = requests.post(
                inbox_url,
                json=like_body,
                auth=(node.username, node.password),
                timeout=8,
            )

            print(f"[DEBUG LIKE PUSH] Response: {response.status_code}")

            if response.status_code < 300 and response.status_code >= 200:
                print(f"[DEBUG LIKE PUSH] ✅ Success with {inbox_url}")
                success = True
                break

        except requests.exceptions.ChunkedEncodingError as e:
            print(f"[DEBUG LIKE PUSH] ChunkedEncodingError (treating as success): {e}")
            success = True
            break
        except requests.RequestException as e:
            print(f"[DEBUG LIKE PUSH] ❌ Failed on {inbox_url}: {e}")
            continue

    if not success:
        print(f"[DEBUG LIKE PUSH] ❌ Both inbox endpoints failed for {post_author.api_url}")


def push_comment_like_to_remote(like, liker_author, comment):
    """
    Push a like on a comment to the post author's inbox if remote.
    """
    from .models import Node
    from authors.serializers import AuthorSerializer

    post_author = comment.post.author

    print(f"[DEBUG COMMENT-LIKE PUSH] Like by {liker_author.displayName} on comment → post author: {post_author.displayName} ({post_author.host})")

    if post_author.host.rstrip('/').rstrip('/api').rstrip('/') == liker_author.host.rstrip('/').rstrip('/api').rstrip('/'):
        print(f"[DEBUG COMMENT-LIKE PUSH] Same node - skipping remote push")
        return

    target_host = post_author.host.rstrip('/').rstrip('/api').rstrip('/') + "/api/"
    node = Node.objects.filter(url__startswith=target_host[:target_host.find("/api")], is_enabled=True).first()

    if not node:
        print(f"[DEBUG COMMENT-LIKE PUSH] ❌ No enabled Node found for host: {post_author.host}")
        return

    print(f"[DEBUG COMMENT-LIKE PUSH] ✅ Found enabled Node")

    like_body = {
        "type": "like",
        "author": AuthorSerializer(liker_author).data,
        "object": comment.api_url,
        "id": like.api_url,
    }

    # inbox_url = f"{post_author.api_url.rstrip('/')}/inbox"
    # print(f"[DEBUG COMMENT-LIKE PUSH] Sending comment-like to: {inbox_url}")

    # try:
    #     response = requests.post(
    #         inbox_url,
    #         json=like_body,
    #         auth=(node.username, node.password),
    #         timeout=8,
    #     )
    #     print(f"[DEBUG COMMENT-LIKE PUSH] ✅ Remote comment-like sent - status: {response.status_code}")
    # except requests.RequestException as e:
    #     print(f"[DEBUG COMMENT-LIKE PUSH] ❌ Failed: {e}")

    base_url = post_author.api_url.rstrip('/')
    inbox_variants = [
        f"{base_url}/inbox",
        f"{base_url}/inbox/"
    ]

    print("[DEBUG COMMENT-LIKE PUSH] Payload:", like_body)

    success = False

    for inbox_url in inbox_variants:
        try:
            print(f"[DEBUG COMMENT-LIKE PUSH] Trying: {inbox_url}")

            response = requests.post(
                inbox_url,
                json=like_body,
                auth=(node.username, node.password),
                timeout=8,
            )

            print(f"[DEBUG COMMENT-LIKE PUSH] Response: {response.status_code}")

            if response.status_code < 300 and response.status_code >= 200:
                print(f"[DEBUG COMMENT-LIKE PUSH] ✅ Success with {inbox_url}")
                success = True
                break

        except requests.exceptions.ChunkedEncodingError as e:
            print(f"[DEBUG COMMENT-LIKE PUSH] ChunkedEncodingError (treating as success): {e}")
            success = True
            break
        except requests.RequestException as e:
            print(f"[DEBUG COMMENT-LIKE PUSH] ❌ Failed on {inbox_url}: {e}")
            continue

    if not success:
        print(f"[DEBUG COMMENT-LIKE PUSH] ❌ Both inbox endpoints failed for {post_author.api_url}")


def push_comment_to_remote(comment, commenter_author, post):
    """
    Push a new comment to the post author's inbox if they are on a remote node.
    """
    from .models import Node
    from authors.serializers import AuthorSerializer

    post_author = post.author

    print(f"[DEBUG COMMENT PUSH] Comment by {commenter_author.displayName} on post '{post.title}' → target: {post_author.displayName} ({post_author.host})")

    if post_author.host.rstrip('/').rstrip('/api').rstrip('/') == commenter_author.host.rstrip('/').rstrip('/api').rstrip('/'):
        print(f"[DEBUG COMMENT PUSH] Same node - skipping remote push")
        return

    target_host = post_author.host.rstrip('/').rstrip('/api').rstrip('/') + "/api/"
    node = Node.objects.filter(url__startswith=target_host[:target_host.find("/api")], is_enabled=True).first()

    if not node:
        print(f"[DEBUG COMMENT PUSH] ❌ No enabled Node found for host: {post_author.host}")
        return

    print(f"[DEBUG COMMENT PUSH] ✅ Found enabled Node")

    comment_body = {
        "type": "comment",
        "id": comment.api_url,
        "author": AuthorSerializer(commenter_author).data,
        "comment": comment.content,
        "contentType": comment.contentType,
        "published": comment.published.isoformat() if hasattr(comment, 'published') and comment.published else None,
        "entry": post.api_url,
    }

    # inbox_url = f"{post_author.api_url.rstrip('/')}/inbox"
    # print(f"[DEBUG COMMENT PUSH] Sending comment to inbox: {inbox_url}")

    # try:
    #     response = requests.post(
    #         inbox_url,
    #         json=comment_body,
    #         auth=(node.username, node.password),
    #         timeout=8,
    #     )
    #     print(f"[DEBUG COMMENT PUSH] ✅ Remote comment sent - status: {response.status_code}")
    # except requests.RequestException as e:
    #     print(f"[DEBUG COMMENT PUSH] ❌ Failed to send comment: {e}")

    base_url = post_author.api_url.rstrip('/')
    inbox_variants = [
        f"{base_url}/inbox",
        f"{base_url}/inbox/"
    ]

    print("[DEBUG COMMENT PUSH] Payload:", comment_body)

    success = False

    for inbox_url in inbox_variants:
        try:
            print(f"[DEBUG COMMENT PUSH] Trying inbox: {inbox_url}")

            response = requests.post(
                inbox_url,
                json=comment_body,
                auth=(node.username, node.password),
                timeout=8,
            )

            print(f"[DEBUG COMMENT PUSH] Response: {response.status_code}")

            if response.status_code < 300 and response.status_code >= 200:
                print(f"[DEBUG COMMENT PUSH] Success with {inbox_url}")
                success = True
                break

        except requests.exceptions.ChunkedEncodingError as e:
            print(f"[DEBUG COMMENT PUSH] ChunkedEncodingError (treating as success): {e}")
            success = True
            break
        except requests.RequestException as e:
            print(f"[DEBUG COMMENT PUSH] Failed on {inbox_url}: {e}")
            continue

    if not success:
        print(f"[DEBUG COMMENT PUSH] Both inbox endpoints failed for {post_author.api_url}")

def push_post_to_single_author(post, author):
    node = Node.objects.filter(url=author.host, is_enabled=True).first()
    post_body = EntrySerializer(post).data
    # 
    
    base_url = author.api_url.rstrip('/')
    inbox_variants = [
        f"{base_url}/inbox",
        f"{base_url}/inbox/"
    ]

    print("PUSHING POST TO DELETE")
    print("Payload:", post_body)

    for inbox_url in inbox_variants:
        try:
            print("Trying Inbox URL:", inbox_url)

            response = requests.post(
                inbox_url,
                json=post_body,
                auth=(node.username, node.password),
                timeout=5,
            )

            print("Response:", response.status_code)

            if response.status_code < 300 and response.status_code >= 200:
                print("Success with:", inbox_url)
                break

        except requests.exceptions.ChunkedEncodingError as e:
            print("ChunkedEncodingError (treating as success):", e)
            break
        except requests.RequestException as e:
            print("Failed on:", inbox_url, "| Error:", e)
            continue
    else:
        print("Both inbox endpoints failed for:", author.api_url)

def follow_operation_local_and_remote(actor, recipient):
    """
    Requires the objects.
    Doesn't check if the operation is needed.
    :param actor
    :param recipient
    """
    if not actor.followers.filter(api_url=recipient.api_url).exists():
        actor.following.add(recipient)
        posts_to_add = recipient.posts.filter(is_deleted=False, visibility=Post.Visibility.UNLISTED)
        for post in posts_to_add:
            actor.inbox.posts.add(post)
    else:
        actor.friends.add(recipient)
        actor.followers.remove(recipient)
        posts_to_add = recipient.posts.filter(is_deleted=False, visibility__in=[Post.Visibility.UNLISTED, Post.Visibility.FRIENDS])
        for post in posts_to_add:
            actor.inbox.posts.add(post)
        send_posts = actor.posts.filter(is_deleted=False, visibility=Post.Visibility.FRIENDS)
        for post in send_posts:
            push_post_to_single_author(post, recipient)