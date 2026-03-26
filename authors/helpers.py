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
    elif post.visibility == Post.Visibility.DELETED:
        reciever = [inbox.author for inbox in post.sent_to.all() if inbox.author.host != author.host]
    else:
        return  # dont push if unknown visibility

    post_body = {
        "type": "entry",
        "title": post.title,
        "id": post.api_url,
        "web": post.url,
        "contentType": post.contentType,
        "content": post.content,
        "visibility": post.visibility,
        "author": {
            "type": "author",
            "id": author.api_url,
            "host": author.host,
            "displayName": author.displayName,
            "web": author.url,
            "github": author.github or "",
            "profileImage": author.profileImage or "",
        },
    }

    for follower in reciever:
        # only push to remote followers (different host)
        if follower.host == author.host:
            continue

        # check if the remote node is enabled
        node = Node.objects.filter(url=follower.host, is_enabled=True).first()
        if not node:
            continue

        # got help from Claude, Accessed 18 March 2026
        inbox_url = f"{follower.api_url}/inbox"
        try:
            requests.post(
                inbox_url,
                json=post_body,
                auth=(node.username, node.password),
                timeout=5,
            )
        except requests.RequestException:
            # dont let a failed push crash the local operation
            pass

# GET a single author - remote
def get_or_fetch_author(fqid):
    fqid = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")

    # 1. Check locally
    author = Author.objects.filter(api_url=fqid).first()
    if author:
        return author

    # 2. Fetch from remote
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

        # 🔥 IMPORTANT: store/update locally
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