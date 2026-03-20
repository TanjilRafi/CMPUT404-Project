# ────────────────────────────────────────────────────────────────
# Imports
# ────────────────────────────────────────────────────────────────
from django.shortcuts import render, get_object_or_404, redirect
from authors.models import Author, Post, Inbox, Entry, Comment, Like
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

from drf_spectacular.types import OpenApiTypes

from authors.helpers import serialize_like # all other functions that are not api views


@login_required
@require_http_methods(["POST"])
def like_post(request, author_id, post_id):
    """
    Making toggle to like a post.
    """
    author = get_object_or_404(Author, id=author_id)
    post = get_object_or_404(Post, id=post_id)

    if post.visibility == Post.Visibility.FRIENDS:
        if post.is_deleted:
            return HttpResponseForbidden("This post no longer exists.")
        
        isPostAuthor = hasattr(request.user, 'author') and request.user.author == author
        isFriend = hasattr(request.user, 'author') and request.user.author in author.friends.all()
        
        if not (isPostAuthor or isFriend):
            return HttpResponseForbidden("You must be friends to interact with this post.")
    
    like, created = Like.objects.get_or_create(post=post, author=request.user.author)
    if not created:
        like.delete()
        
    return redirect(reverse('post_detail', args=[author_id, post_id]))

@login_required
@require_http_methods(["POST"])
def like_comment(request, author_id, post_id, comment_id):
    """
    Making toggle to like a comment.
    """
    author = get_object_or_404(Author, id=author_id)
    post = get_object_or_404(Post, id=post_id)
    comment = get_object_or_404(Comment, id=comment_id)

    if post.visibility == Post.Visibility.FRIENDS:
        if post.is_deleted:
            return HttpResponseForbidden("This post no longer exists.")
        
        isPostAuthor = hasattr(request.user, 'author') and request.user.author == author
        isFriend = hasattr(request.user, 'author') and request.user.author in author.friends.all()
        
        if not (isPostAuthor or isFriend):
            return HttpResponseForbidden("You must be friends to interact with this post.")

    
    like, created = Like.objects.get_or_create(comment=comment, author=request.user.author)
    if not created:
        like.delete()
        
    return redirect(reverse('post_detail', args=[author_id, post_id]))

# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get likes on a specific entry",
    description="""Retrieves a paginated list of likes on the specified entry.

**Visibility rules:**
- PUBLIC entries: anyone can access.
- UNLISTED entries: anyone with the link.
- FRIENDS entries: only friends or the author can access.

Pagination is applied via query parameters `page` and `size`.

Returns a **Likes object** as defined in the API specification.
""",
    parameters=[
        OpenApiParameter(
            name="id",
            description="UUID of the author who owns the entry.",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH
        ),
        OpenApiParameter(
            name="post_id",
            description="UUID of the entry.",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH
        ),
        OpenApiParameter(
            name="page",
            description="Page number for pagination (default: 1).",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            name="size",
            description="Number of likes per page (default: 50).",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="List of likes retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Likes object response",
                    value={
                        "type": "likes",
                        "id": "http://nodeaaaa/api/authors/111/entries/222/likes",
                        "page_number": 1,
                        "size": 50,
                        "count": 2,
                        "src": [
                            {
                                "type": "like",
                                "author": {
                                    "type": "author",
                                    "id": "http://nodebbbb/api/authors/222",
                                    "web": "http://nodebbbb/authors/222",
                                    "host": "http://nodebbbb/api/",
                                    "displayName": "Lara Croft",
                                    "github": "http://github.com/laracroft",
                                    "profileImage": "http://nodebbbb/api/authors/222/entries/217/image"
                                },
                                "published": "2015-03-09T13:07:04+00:00",
                                "id": "http://nodeaaaa/api/authors/222/liked/255",
                                "object": "http://nodeaaaa/api/authors/111/entries/222"
                            }
                        ]
                    }
                )
            ]
        ),
        403: OpenApiResponse(description="Not authorized to view likes on this entry."),
        404: OpenApiResponse(description="Entry not found or deleted.")
    },
    examples=[
        OpenApiExample(
            name="Curl GET request example",
            request_only=True,
            value="curl -X GET http://127.0.0.1:8000/api/authors/{AUTHOR_ID}/entries/{ENTRY_ID}/likes"
        )
    ]
)
# @extend_schema(
#     summary="Get list of likes for a specific entry",
#     description="Returns a 'likes' object containing all likes for an entry identified by its serial ID.",
#     responses={200: OpenApiResponse(description="Likes object returned.")}
# )
@api_view(["GET"])
def api_entry_likes(request, id, post_id):
    author = get_object_or_404(Author, id=id)
    post = get_object_or_404(Post, id=post_id, author=author)
    
    # US 08.14: Check visibility
    if post.is_deleted:
        return Response({"error": "Entry not found"}, status=404)
    
    # Check FRIENDS visibility
    if post.visibility == Post.Visibility.FRIENDS:
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_403_FORBIDDEN)
        try:
            if request.user.author != post.author and request.user.author not in post.author.friends.all():
                return Response({"detail": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)
        except:
            return Response({"detail": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)
        
    likes = Like.objects.filter(post=post).order_by('-published')
    
    page = int(request.GET.get('page', 1))
    size = int(request.GET.get('size', 50))
    start = (page - 1) * size
    paginated_likes = likes[start:start + size]

    data = {
        "type": "likes",
        "id": f"{author.host}api/authors/{author.id}/entries/{post.id}/likes",
        "page_number": page,
        "size": size,
        "count": likes.count(),
        "src": [serialize_like(like) for like in paginated_likes]
    }
    return Response(data)


# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get likes on an entry by FQID",
    description="""Retrieves a paginated list of likes on the specified entry, identified by its fully-qualified ID (FQID).

This endpoint is equivalent to `GET /authors/{AUTHOR}/entries/{ENTRY}/likes` but allows fetching likes using the FQID.

Visibility rules:
- PUBLIC: anyone can view
- UNLISTED: anyone with the link
- FRIENDS: only friends or the author can view

Pagination is applied via query parameters `page` and `size`.

Returns a **Likes object** as defined in the API specification.
""",
    parameters=[
        OpenApiParameter(
            name="fqid",
            description="Fully-qualified ID (FQID) of the entry (URL-encoded if needed).",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH
        ),
        OpenApiParameter(
            name="page",
            description="Page number for pagination (default: 1).",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            name="size",
            description="Number of likes per page (default: 50).",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Likes retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Likes object example",
                    value={
                        "type": "likes",
                        "id": "http://nodeaaaa/api/authors/111/entries/222/likes",
                        "page_number": 1,
                        "size": 50,
                        "count": 2,
                        "src": [
                            {
                                "type": "like",
                                "author": {
                                    "type": "author",
                                    "id": "http://nodebbbb/api/authors/222",
                                    "web": "http://nodebbbb/authors/222",
                                    "host": "http://nodebbbb/api/",
                                    "displayName": "Lara Croft",
                                    "github": "http://github.com/laracroft",
                                    "profileImage": "http://nodebbbb/api/authors/222/entries/217/image"
                                },
                                "published": "2015-03-09T13:07:04+00:00",
                                "id": "http://nodeaaaa/api/authors/222/liked/255",
                                "object": "http://nodeaaaa/api/authors/111/entries/222"
                            }
                        ]
                    }
                )
            ]
        ),
        403: OpenApiResponse(description="Not authorized to view likes on this entry."),
        404: OpenApiResponse(description="Entry not found.")
    },
    examples=[
        OpenApiExample(
            name="Curl GET example",
            request_only=True,
            value="curl -X GET http://127.0.0.1:8000/api/entries/{ENTRY_FQID}/likes"
        )
    ]
)
@api_view(["GET"])
def api_entry_likes_fqid(request, fqid):
    api_url = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")
    post_uuid = api_url.split("/")[-1]
    
    post = Post.objects.filter(Q(api_url=api_url) | Q(id__icontains=post_uuid)).first()
    if not post:
        return Response({"detail": "Not found."}, status=404)
        
    return api_entry_likes(request._request, post.author.id, post.id)


# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get things liked by an author",
    description="""
Retrieves a list of things liked by the specified author, or a single like if `like_serial` is provided.

- Returns local and remote likes.
- Likes are ordered newest first.
- Pagination supported via `page` and `size` query parameters.
- Top-level likes object includes `id` (API URL) and `web` (HTML URL).
""",
    parameters=[
        OpenApiExample(name="page", value="1", description="Page number for pagination"),
        OpenApiExample(name="size", value="50", description="Number of likes per page"),
        OpenApiExample(name="like_serial", value="166", description="Optional serial to retrieve a single like")
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="A likes object or a single like object",
            examples=[
                OpenApiExample(
                    name="List of likes",
                    value={
                        "type": "likes",
                        "id": "http://nodeaaaa/api/authors/111/liked",
                        "web": "http://nodeaaaa/authors/111/liked",
                        "page_number": 1,
                        "size": 2,
                        "count": 2,
                        "src": [
                            {
                                "type": "like",
                                "id": "http://nodeaaaa/api/authors/111/liked/166",
                                "author": {
                                    "type": "author",
                                    "id": "http://nodeaaaa/api/authors/111",
                                    "host": "http://nodeaaaa/api/",
                                    "web": "http://nodeaaaa/authors/111",
                                    "displayName": "Greg Johnson",
                                    "github": "http://github.com/gjohnson",
                                    "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                                },
                                "published": "2015-03-09T13:07:04+00:00",
                                "object": "http://nodebbbb/api/authors/222/entries/249"
                            },
                            {
                                "type": "like",
                                "id": "http://nodeaaaa/api/authors/111/liked/167",
                                "author": {
                                    "type": "author",
                                    "id": "http://nodeaaaa/api/authors/111",
                                    "host": "http://nodeaaaa/api/",
                                    "web": "http://nodeaaaa/authors/111",
                                    "displayName": "Greg Johnson",
                                    "github": "http://github.com/gjohnson",
                                    "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                                },
                                "published": "2015-03-08T09:15:22+00:00",
                                "object": "http://nodebbbb/api/authors/333/entries/420"
                            }
                        ]
                    }
                ),
                OpenApiExample(
                    name="Single like response",
                    value={
                        "type": "like",
                        "id": "http://nodeaaaa/api/authors/111/liked/166",
                        "author": {
                            "type": "author",
                            "id": "http://nodeaaaa/api/authors/111",
                            "host": "http://nodeaaaa/api/",
                            "web": "http://nodeaaaa/authors/111",
                            "displayName": "Greg Johnson",
                            "github": "http://github.com/gjohnson",
                            "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                        },
                        "published": "2015-03-09T13:07:04+00:00",
                        "object": "http://nodebbbb/api/authors/222/entries/249"
                    }
                )
            ]
        ),
        403: OpenApiResponse(description="Not authorized"),
        404: OpenApiResponse(description="Author or like not found"),
    },
    examples=[
        OpenApiExample(
            name="GET list of likes",
            request_only=True,
            value="curl -u username:password -X GET http://127.0.0.1:8000/api/authors/111/liked/?page=1&size=5"
        ),
        OpenApiExample(
            name="GET single like",
            request_only=True,
            value="curl -u username:password -X GET http://127.0.0.1:8000/api/authors/111/liked/166"
        )
    ]
)
@api_view(["GET"])
@authentication_classes([SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def api_author_liked(request, id, like_serial=None):
    """GET list of things liked by this author, or single like by serial"""
    author = get_object_or_404(Author, id=id)
    
    # Single like by serial
    if like_serial:
        like = Like.objects.filter(author=author, id__endswith=like_serial).first()
        if not like:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serialize_like(like))
    
    # List of all likes
    likes = Like.objects.filter(author=author).order_by('-published')
    
    # Pagination
    page = int(request.GET.get('page', 1))
    size = int(request.GET.get('size', likes.count()))
    start = (page - 1) * size
    end = start + size
    
    data = {
        "type": "likes",
        "page_number": page,
        "size": size,
        "count": likes.count(),
        "src": [serialize_like(like) for like in likes[start:end]]
    }
    return Response(data)


# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get things liked by an author (FQID)",
    description="""
Retrieves a list of things liked by the specified author, identified by their fully-qualified ID (FQID).

- Returns local and remote likes.
- Likes are ordered newest first.
- Pagination supported via `page` and `size` query parameters.
- Top-level likes object includes `id` (API URL) and `web` (HTML URL).
""",
    parameters=[
        OpenApiExample(
            name="fqid",
            value="http%3A%2F%2Fnodeaaaa%2Fapi%2Fauthors%2F111",
            description="Fully-qualified ID of the author (URL-encoded)"
        ),
        OpenApiExample(
            name="page",
            value="1",
            description="Page number for pagination"
        ),
        OpenApiExample(
            name="size",
            value="50",
            description="Number of likes per page"
        )
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Likes object or a single like object",
            examples=[
                OpenApiExample(
                    name="List of likes",
                    value={
                        "type": "likes",
                        "id": "http://nodeaaaa/api/authors/111/liked",
                        "web": "http://nodeaaaa/authors/111/liked",
                        "page_number": 1,
                        "size": 2,
                        "count": 2,
                        "src": [
                            {
                                "type": "like",
                                "id": "http://nodeaaaa/api/authors/111/liked/166",
                                "author": {
                                    "type": "author",
                                    "id": "http://nodeaaaa/api/authors/111",
                                    "host": "http://nodeaaaa/api/",
                                    "web": "http://nodeaaaa/authors/111",
                                    "displayName": "Greg Johnson",
                                    "github": "http://github.com/gjohnson",
                                    "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                                },
                                "published": "2015-03-09T13:07:04+00:00",
                                "object": "http://nodebbbb/api/authors/222/entries/249"
                            }
                        ]
                    }
                )
            ]
        ),
        404: OpenApiResponse(description="Author not found"),
    },
    examples=[
        OpenApiExample(
            name="GET likes by FQID",
            request_only=True,
            value="curl -u username:password -X GET http://127.0.0.1:8000/api/authors/http%3A%2F%2Fnodeaaaa%2Fapi%2Fauthors%2F111/liked/"
        )
    ]
)
@api_view(["GET"])
def api_author_liked_fqid(request, fqid):
    """GET list of things liked by this author (FQID)"""
    api_url = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")
    author_uuid = api_url.split("/")[-1]
    
    # Check for exact URL match or fallback to UUID match
    author = Author.objects.filter(Q(api_url=api_url) | Q(id__icontains=author_uuid)).first()
    if not author:
        return Response({"detail": "Not found."}, status=404)
        
    return api_author_liked(request._request, author.id)


# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get a single like by FQID",
    description="""
Retrieves a single like object by its fully-qualified ID (FQID).

- FQID must match the `id` field of the like exactly.
- Returns the full like object, including author info, object liked, and timestamp.
""",
    parameters=[
        OpenApiExample(
            name="fqid",
            value="http%3A%2F%2Fnodeaaaa%2Fapi%2Fauthors%2F111%2Fliked%2F166",
            description="Fully-qualified ID of the like (URL-encoded)"
        )
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Single like object",
            examples=[
                OpenApiExample(
                    name="Single like response",
                    value={
                        "type": "like",
                        "id": "http://nodeaaaa/api/authors/111/liked/166",
                        "author": {
                            "type": "author",
                            "id": "http://nodeaaaa/api/authors/111",
                            "host": "http://nodeaaaa/api/",
                            "web": "http://nodeaaaa/authors/111",
                            "displayName": "Greg Johnson",
                            "github": "http://github.com/gjohnson",
                            "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                        },
                        "published": "2015-03-09T13:07:04+00:00",
                        "object": "http://nodebbbb/api/authors/222/entries/249"
                    }
                )
            ]
        ),
        404: OpenApiResponse(description="Like not found"),
    },
    examples=[
        OpenApiExample(
            name="GET single like by FQID",
            request_only=True,
            value="curl -X GET http://127.0.0.1:8000/api/liked/http%3A%2F%2Fnodeaaaa%2Fapi%2Fauthors%2F111%2Fliked%2F166/"
        )
    ]
)
@api_view(["GET"])
def api_single_like(request, fqid):
    """GET a single like object by its full FQID"""
    api_url = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")
    like = get_object_or_404(Like, id=api_url)
    return Response(serialize_like(like))