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

from authors.helpers import _comment_to_api, _comment_id_from_fqid # all other functions that are not api views


# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get comments on an entry",
    description="""Retrieves the comments on a specific entry.

Returns a Comments object as defined in the API specification.

Pagination parameters:
- `page` — page number (default 1)
- `size` — number of comments per page

Comments should be returned newest first.
""",
    parameters=[
        OpenApiParameter(
            name="page",
            description="Page number for pagination.",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            default=1
        ),
        OpenApiParameter(
            name="size",
            description="Number of comments per page.",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            default=5
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Comments retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Comments object response",
                    value={
                        "type": "comments",
                        "id": "http://nodebbbb/api/authors/222/entries/249/comments",
                        "web": "http://nodebbbb/authors/222/entries/249",
                        "page_number": 1,
                        "size": 5,
                        "count": 2,
                        "src": [
                            {
                                "type": "comment",
                                "author": {
                                    "type": "author",
                                    "id": "http://nodeaaaa/api/authors/111",
                                    "web": "http://nodeaaaa/authors/greg",
                                    "host": "http://nodeaaaa/api/",
                                    "displayName": "Greg Johnson",
                                    "github": "http://github.com/gjohnson",
                                    "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                                },
                                "comment": "Sick Olde English",
                                "contentType": "text/markdown",
                                "published": "2015-03-09T13:07:04+00:00",
                                "id": "http://nodeaaaa/api/authors/111/commented/130",
                                "entry": "http://nodebbbb/api/authors/222/entries/249",
                                "web": "http://nodebbbb/authors/222/entries/249"
                            }
                        ]
                    }
                )
            ]
        ),
        404: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Entry not found."
        )
    },
    examples=[
        OpenApiExample(
            name="Curl GET request example",
            request_only=True,
            value="curl -X GET http://127.0.0.1:8000/api/authors/{AUTHOR_ID}/entries/{ENTRY_ID}/comments/?page=1&size=5"
        )
    ]
)
@api_view(["GET"])
def api_entry_comments(request, author_id, post_id):
    post = get_object_or_404(Post, id=post_id, author_id=author_id)
    comments = Comment.objects.filter(post=post).select_related("author").order_by("published")
    
    # Pagination
    page = int(request.GET.get('page', 1))
    size = int(request.GET.get('size', 50))
    start = (page - 1) * size
    
    paginated = comments[start:start + size]
    
    return JsonResponse({
        "type": "comments",
        "id": post.api_url + "/comments", # added — spec requires this
        "web": post.url,
        "page_number": page,
        "size": size,
        "count": comments.count(),
        "src": [_comment_to_api(c) for c in paginated],
    })


# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get comments for an entry by FQID",
    description="""Retrieves comments for an entry using its fully-qualified ID (FQID).

This endpoint returns the comments that **this node knows about** for the specified entry.

Pagination parameters:
- `page` — page number (default 1)
- `size` — number of comments per page

Returns a **Comments object** as defined in the API specification.
""",
    parameters=[
        OpenApiParameter(
            name="fqid",
            description="Fully qualified ID of the entry.",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH
        ),
        OpenApiParameter(
            name="page",
            description="Page number.",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            default=1
        ),
        OpenApiParameter(
            name="size",
            description="Number of comments per page.",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            default=5
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Comments retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Comments object response",
                    value={
                        "type": "comments",
                        "id": "http://nodebbbb/api/authors/222/entries/249/comments",
                        "web": "http://nodebbbb/authors/222/entries/249",
                        "page_number": 1,
                        "size": 5,
                        "count": 1,
                        "src": [
                            {
                                "type": "comment",
                                "author": {
                                    "type": "author",
                                    "id": "http://nodeaaaa/api/authors/111",
                                    "web": "http://nodeaaaa/authors/greg",
                                    "host": "http://nodeaaaa/api/",
                                    "displayName": "Greg Johnson",
                                    "github": "http://github.com/gjohnson",
                                    "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                                },
                                "comment": "Sick Olde English",
                                "contentType": "text/markdown",
                                "published": "2015-03-09T13:07:04+00:00",
                                "id": "http://nodeaaaa/api/authors/111/commented/130",
                                "entry": "http://nodebbbb/api/authors/222/entries/249",
                                "web": "http://nodebbbb/authors/222/entries/249"
                            }
                        ]
                    }
                )
            ]
        ),
        404: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Entry not found."
        )
    },
    examples=[
        OpenApiExample(
            name="Curl GET request example",
            request_only=True,
            value="curl -X GET http://127.0.0.1:8000/api/entries/{ENTRY_FQID}/comments/?page=1&size=5"
        )
    ]
)
@api_view(["GET"])
def api_entry_comments_fqid(request, fqid):  # Fixed parameter name!
    entry_api_url = urllib.parse.unquote_plus(fqid).rstrip("/")
    post_uuid = entry_api_url.split("/")[-1]
    
    # Safe lookup to handle missing /api/ segments or trailing slashes
    post = Post.objects.filter(Q(api_url=entry_api_url) | Q(id__icontains=post_uuid)).first()
    if not post:
        return JsonResponse({"detail": "Not found."}, status=404)
        
    comments = Comment.objects.filter(post=post).select_related("author").order_by("published")
    
    page = int(request.GET.get('page', 1))
    size = int(request.GET.get('size', 50))
    start = (page - 1) * size
    
    paginated = comments[start:start + size]
    
    return JsonResponse({
        "type": "comments",
        "id": post.api_url + "/comments",
        "web": post.url,
        "page_number": page,
        "size": size,
        "count": comments.count(),
        "src": [_comment_to_api(c) for c in paginated],
    })


# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get a specific comment on an entry",
    description="""Retrieves a single comment on an entry.

The comment is identified using a **fully qualified comment ID (FQID)**.

Example request:
GET /api/authors/{AUTHOR_SERIAL}/entries/{ENTRY_SERIAL}/comments/{REMOTE_COMMENT_FQID}

Returns a **Comment object** as defined in the API specification.
""",
    parameters=[
        OpenApiParameter(
            name="author_id",
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
            name="comment_fqid",
            description="Fully qualified ID of the comment.",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Comment retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Comment object response",
                    value={
                        "type": "comment",
                        "author": {
                            "type": "author",
                            "id": "http://nodeaaaa/api/authors/111",
                            "web": "http://nodeaaaa/authors/greg",
                            "host": "http://nodeaaaa/api/",
                            "displayName": "Greg Johnson",
                            "github": "http://github.com/gjohnson",
                            "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                        },
                        "comment": "Sick Olde English",
                        "contentType": "text/markdown",
                        "published": "2015-03-09T13:07:04+00:00",
                        "id": "http://nodeaaaa/api/authors/111/commented/130",
                        "entry": "http://nodebbbb/api/authors/222/entries/249"
                    }
                )
            ]
        ),
        404: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Entry or comment not found."
        )
    },
    examples=[
        OpenApiExample(
            name="Curl GET request example",
            request_only=True,
            value="curl -X GET http://127.0.0.1:8000/api/authors/{AUTHOR_ID}/entries/{ENTRY_ID}/comments/{COMMENT_FQID}"
        )
    ]
)
@api_view(["GET"])
def api_entry_comment_detail_fqid(request, author_id, post_id, comment_fqid):
    post = get_object_or_404(Post, id=post_id, author_id=author_id)
    comment_id = _comment_id_from_fqid(comment_fqid)
    comment = get_object_or_404(Comment, id=comment_id, post=post)
    return JsonResponse(_comment_to_api(comment))


# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get comments made by an author",
    description="""Retrieves a paginated list of comments made by the specified author.

Local requests return comments on **any entry** that this node knows about.

Pagination parameters:
- `page` — page number (default 1)
- `size` — number of comments per page (default 10)

Returns a **Comments object** containing comment metadata and the first page of comments.
""",
    parameters=[
        OpenApiParameter(
            name="author_id",
            description="UUID of the author whose comments are requested.",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
        ),
        OpenApiParameter(
            name="page",
            description="Page number for pagination.",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            default=1,
        ),
        OpenApiParameter(
            name="size",
            description="Number of comments per page.",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            default=10,
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Comments retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Comments list response",
                    value={
                        "type": "comments",
                        "page_number": 1,
                        "size": 5,
                        "count": 1,
                        "src": [
                            {
                                "type": "comment",
                                "author": {
                                    "type": "author",
                                    "id": "http://nodeaaaa/api/authors/111",
                                    "web": "http://nodeaaaa/authors/greg",
                                    "host": "http://nodeaaaa/api/",
                                    "displayName": "Greg Johnson",
                                    "github": "http://github.com/gjohnson",
                                    "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                                },
                                "comment": "Sick Olde English",
                                "contentType": "text/markdown",
                                "published": "2015-03-09T13:07:04+00:00",
                                "id": "http://nodeaaaa/api/authors/111/commented/130",
                                "entry": "http://nodebbbb/api/authors/222/entries/249",
                                "web": "http://nodebbbb/authors/222/entries/249"
                            }
                        ]
                    }
                )
            ]
        ),
        404: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Author not found."
        )
    }
)
@extend_schema(
    methods=["POST"],
    summary="Create a comment",
    description="""Creates a new comment by the specified author.

The request body must contain a **Comment object** with:
- `type` = "comment"
- `entry` = fully qualified ID of the entry
- `comment` = comment text
- `contentType` = content format

If successful, the newly created comment object is returned.

The node receiving the comment is responsible for forwarding it to the appropriate inbox if necessary.
""",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "example": "comment"
                },
                "entry": {
                    "type": "string",
                    "example": "http://nodebbbb/api/authors/222/entries/249"
                },
                "comment": {
                    "type": "string",
                    "example": "Sick Olde English"
                },
                "contentType": {
                    "type": "string",
                    "example": "text/markdown"
                }
            },
            "required": ["type", "entry", "comment"]
        }
    },
    responses={
        201: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Comment created successfully.",
            examples=[
                OpenApiExample(
                    name="Created comment response",
                    value={
                        "type": "comment",
                        "author": {
                            "type": "author",
                            "id": "http://nodeaaaa/api/authors/111",
                            "displayName": "Greg Johnson"
                        },
                        "comment": "Sick Olde English",
                        "contentType": "text/markdown",
                        "published": "2015-03-09T13:07:04+00:00",
                        "id": "http://nodeaaaa/api/authors/111/commented/130",
                        "entry": "http://nodebbbb/api/authors/222/entries/249"
                    }
                )
            ]
        ),
        400: OpenApiResponse(description="Invalid request body."),
        403: OpenApiResponse(description="Forbidden."),
        404: OpenApiResponse(description="Entry not found.")
    },
    examples=[
        OpenApiExample(
            name="Example request body",
            request_only=True,
            value={
                "type": "comment",
                "entry": "http://nodebbbb/api/authors/222/entries/249",
                "comment": "Sick Olde English",
                "contentType": "text/markdown"
            }
        )
    ]
)
@api_view(["GET", "POST"])
def api_author_commented(request, author_id):
    author = get_object_or_404(Author, id=author_id)

    if request.method == "GET":
        comments = Comment.objects.filter(author=author).select_related("post", "author").order_by("-published")

        try:
            page = int(request.GET.get("page", 1))
            size = int(request.GET.get("size", 10))
            if page < 1 or size < 1:
                raise ValueError
        except ValueError:
            return JsonResponse({"error": "Invalid page or size"}, status=400)

        start = (page - 1) * size
        end = start + size
        paginated_comments = comments[start:end]

        return JsonResponse({
            "type": "comments",
            "page_number": page,
            "size": size,
            "count": comments.count(),
            "src": [_comment_to_api(c) for c in paginated_comments],
        })

    if not request.user.is_authenticated or not hasattr(request.user, "author") or request.user.author != author:
        return JsonResponse({"error": "Forbidden"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if body.get("type") != "comment":
        return JsonResponse({"error": "type must be comment"}, status=400)

    entry_fqid = body.get("entry")
    content = (body.get("comment") or body.get("content") or "").strip()
    content_type = body.get("contentType", "text/plain")

    if not entry_fqid or not content:
        return JsonResponse({"error": "entry and comment are required"}, status=400)

    entry_api_url = urllib.parse.unquote_plus(entry_fqid).rstrip("/")

    post = Post.objects.filter(api_url=entry_api_url).first()
    if post is None:
        try:
            post_id = uuid.UUID(entry_api_url.split("/")[-1])
        except ValueError:
            return JsonResponse({"error": "Entry not found"}, status=404)

        post = get_object_or_404(Post, id=post_id)

    comment = Comment.objects.create(
        author=author,
        post=post,
        content=content,
        contentType=content_type,
    )
    return JsonResponse(_comment_to_api(comment), status=201)
 

# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get a specific comment made by an author",
    description="""Retrieves a single comment made by the specified author.

The comment is identified using its comment serial (local ID).

Example request:
GET /api/authors/{AUTHOR_SERIAL}/commented/{COMMENT_SERIAL}

Returns a **Comment object** as defined in the API specification.
""",
    parameters=[
        OpenApiParameter(
            name="author_id",
            description="UUID of the author who created the comment.",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
        ),
        OpenApiParameter(
            name="comment_id",
            description="UUID of the comment.",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Comment retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Comment object response",
                    value={
                        "type": "comment",
                        "author": {
                            "type": "author",
                            "id": "http://nodeaaaa/api/authors/111",
                            "web": "http://nodeaaaa/authors/greg",
                            "host": "http://nodeaaaa/api/",
                            "displayName": "Greg Johnson",
                            "github": "http://github.com/gjohnson",
                            "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                        },
                        "comment": "Sick Olde English",
                        "contentType": "text/markdown",
                        "published": "2015-03-09T13:07:04+00:00",
                        "id": "http://nodeaaaa/api/authors/111/commented/130",
                        "entry": "http://nodebbbb/api/authors/222/entries/249",
                        "web": "http://nodebbbb/authors/222/entries/249"
                    }
                )
            ]
        ),
        404: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Author or comment not found."
        )
    },
    examples=[
        OpenApiExample(
            name="Curl GET request example",
            request_only=True,
            value="curl -X GET http://127.0.0.1:8000/api/authors/{AUTHOR_ID}/commented/{COMMENT_ID}"
        )
    ]
)
@api_view(["GET"])
def api_author_commented_detail(request, author_id, comment_id):
    author = get_object_or_404(Author, id=author_id)
    comment = get_object_or_404(Comment, id=comment_id, author=author)
    return JsonResponse(_comment_to_api(comment))


# Documentation created with the help of Microsoft Copilot, Accessed March 16, 2026
@extend_schema(
    methods=["GET"],
    summary="Get a specific comment by FQID",
    description="""Retrieves a single comment using its fully qualified ID (FQID).

This endpoint is typically used for remote comments or for fetching a comment when you only know its FQID.

Returns a **Comment object** as defined in the API specification.
""",
    parameters=[
        OpenApiParameter(
            name="comment_fqid",
            description="Fully qualified ID (FQID) of the comment. URL-encoded if needed.",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
        )
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Comment retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Comment object response",
                    value={
                        "type": "comment",
                        "author": {
                            "type": "author",
                            "id": "http://nodeaaaa/api/authors/111",
                            "web": "http://nodeaaaa/authors/greg",
                            "host": "http://nodeaaaa/api/",
                            "displayName": "Greg Johnson",
                            "github": "http://github.com/gjohnson",
                            "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
                        },
                        "comment": "Sick Olde English",
                        "contentType": "text/markdown",
                        "published": "2015-03-09T13:07:04+00:00",
                        "id": "http://nodeaaaa/api/authors/111/commented/130",
                        "entry": "http://nodebbbb/api/authors/222/entries/249",
                        "web": "http://nodebbbb/authors/222/entries/249"
                    }
                )
            ]
        ),
        404: OpenApiResponse(description="Comment not found.")
    },
    examples=[
        OpenApiExample(
            name="Curl GET request example",
            request_only=True,
            value="curl -X GET http://127.0.0.1:8000/api/commented/{COMMENT_FQID}"
        )
    ]
)
@api_view(["GET"])
def api_commented_detail_fqid(request, comment_fqid):
    comment_id = _comment_id_from_fqid(comment_fqid)
    comment = get_object_or_404(Comment, id=comment_id)
    return JsonResponse(_comment_to_api(comment))
    
@login_required
@require_http_methods(["POST"])        
def post_comment(request, author_id, post_id):
    """
    Comment on post.
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
            
    content = request.POST.get("content", "").strip()
    if content:
        Comment.objects.create(post=post, author=request.user.author, content=content)
        
    return redirect(reverse('post_detail', args=[author_id, post_id])) # got help from claude here, wanted to implement redirecting to the post detail