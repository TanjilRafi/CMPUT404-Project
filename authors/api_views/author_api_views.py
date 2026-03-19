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
from authors.serializers import AuthorSerializer, PostCreateSerializer, PostSerializer, EntrySerializer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from drf_spectacular.types import OpenApiTypes

@extend_schema(
    summary="List all authors on this node (paginated)",
    description="""**When to use**: Discover all authors hosted on this node, for federation or author directories.  
    **Why use it**: Other nodes use this to discover authors for federation.  
    **How to use**: Send a GET request to `/api/authors/`. Use `page` and `size` query params to paginate.  
    **Why not use UI**: This is the machine-readable/API version; use the browser authors list for human viewing.""",
    parameters=[
        OpenApiParameter(
            name="page",
            type=int,
            location=OpenApiParameter.QUERY,
            description="Page number to retrieve.",
            required=False,
            examples=[OpenApiExample(name="Page 2", value=2)]
        ),
        OpenApiParameter(
            name="size",
            type=int,
            location=OpenApiParameter.QUERY,
            description="Number of authors per page.",
            required=False,
            examples=[OpenApiExample(name="5 per page", value=5)]
        )
    ],
    responses={
        200: OpenApiResponse(
            response=AuthorSerializer(many=True),
            description="Paginated list of authors on this node.",
            examples=[
                OpenApiExample(
                    name="Successful response",
                    value={
                        "type": "authors",
                        "authors": [
                            {
                                "type": "author",
                                "id": "http://nodeaaaa/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee",
                                "host": "http://nodeaaaa/api/",
                                "displayName": "Cristy",
                                "github": "https://github.com/PinguinoF78",
                                "profileImage": "https://picsum.photos/200",
                                "web": "http://nodeaaaa/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee"
                            }
                        ]
                    }
                )
            ]
        )
    },
    examples=[
        OpenApiExample(
            name="Curl request example",
            value="curl http://127.0.0.1:8000/api/authors?page=1&size=5",
            request_only=True
        )
    ]
)
@api_view(["GET"])
def api_authors_list(request):
    # GET /api/authors
    authors = Author.objects.all().order_by("id")

    # Pagination
    try:
        page = int(request.GET.get('page', 1))
        size = int(request.GET.get('size', 10))
    except ValueError:
        return JsonResponse({"error": "Invalid page or size"}, status=400)

    start = (page - 1) * size
    end = start + size
    paginated = authors[start:end]

    serializer = AuthorSerializer(paginated, many=True)
    return JsonResponse({"type": "authors", "items": serializer.data}, status=200)

@extend_schema(
    methods=["GET"],
    summary="Get a single author by ID",
    description="""GET: Returns a single author's public profile as JSON.

    When to use GET: When you need to look up a specific author's identity info by UUID.

    How to use GET: Send a GET request with the author's UUID in the URL. No authentication required.

    Pagination: Not applicable — returns a single object.
    """,
    responses={
        200: OpenApiResponse(
            response=AuthorSerializer,
            description="Author found and returned.",
            examples=[
                OpenApiExample(
                    name="Author response",
                    value={
                        "type": "author",
                        "id": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee",
                        "host": "http://127.0.0.1:8000/api/",
                        "displayName": "Cristy",
                        "github": "https://github.com/PinguinoF78",
                        "profileImage": "https://picsum.photos/200",
                        "web": "http://127.0.0.1:8000/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee"
                    }
                )
            ]
        ),
        404: OpenApiResponse(description="Author not found.")
    }
)
@extend_schema(
    methods=["PUT"],
    summary="Update a single author by ID",
    description="""PUT: Updates the author's profile fields.

    When to use PUT: When an author wants to update their displayName, github, or profileImage via the API.

    How to use PUT: Send a PUT request with a JSON body containing the fields to update. Must be authenticated as the author.

    Why NOT to use PUT: Do not use PUT to change the author's UUID or host — these are permanent.

    Pagination: Not applicable — returns a single object.
    """,
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'displayName': {
                    'type': 'string',
                    'example': 'Mysterio',
                    'description': 'The display name of the author. Can be updated.'
                },
                'github': {
                    'type': 'string',
                    'example': 'http://github.com/mysterio',
                    'description': 'GitHub profile URL of the author. Can be updated.'
                },
                'profileImage': {
                    'type': 'string',
                    'example': 'https://i.imgur.com/k7XVwpB.jpeg',
                    'description': 'URL of the author profile image. Can be updated.'
                },
            }
        }
    },
    responses={
        200: OpenApiResponse(
            response=AuthorSerializer,
            description="Author updated successfully.",
            examples=[
                OpenApiExample(
                    name="Updated author response",
                    value={
                        "type": "author",
                        "id": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee",
                        "host": "http://127.0.0.1:8000/api/",
                        "displayName": "Jane Doe",
                        "github": "http://github.com/janedoe",
                        "profileImage": "https://i.imgur.com/k7XVwpB.jpeg",
                        "web": "http://127.0.0.1:8000/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee"
                    }
                )
            ]
        ),
        403: OpenApiResponse(description="You are not authorized to update this author."),
        404: OpenApiResponse(description="Author not found.")
    }
)
@api_view(["GET", "PUT"])
@authentication_classes([SessionAuthentication, BasicAuthentication])
def api_author_profile(request, id):
    """
    GET /api/authors/{id}/ — get author
    PUT /api/authors/{id}/ — update author
    """
    author = get_object_or_404(Author, id=id)

    if request.method == "GET":
        # using AuthorSerializer instead of manual dict
        serializer = AuthorSerializer(author)
        return JsonResponse(serializer.data)

    elif request.method == "PUT":
        if not request.user.is_authenticated or request.user.pk != author.user.pk:
            return JsonResponse({"error": "Forbidden"}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        author.displayName = body.get('displayName', author.displayName)
        author.github = body.get('github', author.github)
        author.profileImage = body.get('profileImage', author.profileImage)
        author.save()

        serializer = AuthorSerializer(author)
        return JsonResponse(serializer.data)