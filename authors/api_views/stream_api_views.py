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

@extend_schema(
    summary="Get visible stream for a specific author",
    description="""
        Gets the visible stream (posts) for a specific author, sorted newest-first (by created_at descending).

        When to use: Use this endpoint to display the inbox of posts an author is allowed to see.  
        How to use: Send a GET request with the author's UUID.  
        Pagination: Use query parameters: ?page=<number>&size=<number>

        Example usage (curl):
        curl -u username:password -X GET "http://127.0.0.1:8000/api/authors/<author_id>/stream/"
        """
    ,
    parameters=[
        OpenApiParameter(
            name="author_id",
            description="UUID of the author whose visible stream is requested",
            required=True,
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.PATH,
            examples=[OpenApiExample(name="Author UUID", value="c7d84ea2-27bb-44ba-8e9c-07bc149a88ee")]
        ),
        OpenApiParameter(
            name="page",
            description="Page number (1-indexed) for pagination",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            examples=[OpenApiExample(name="Page number", value=1)]
        ),
        OpenApiParameter(
            name="size",
            description="Number of posts per page for pagination",
            required=False,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            examples=[OpenApiExample(name="Page size", value=10)]
        )
    ],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Paginated list of posts in the author's visible stream",
            examples=[
                OpenApiExample(
                    name="Author stream response (paginated)",
                    value={
                        "type": "posts",
                        "page": 1,
                        "page_size": 10,
                        "total_posts": 25,
                        "items": [
                            {
                                "type": "entry",
                                "id": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee/entries/a1b2c3d4",
                                "title": "My public post",
                                "content": "Hello world!",
                                "contentType": "text/plain",
                                "visibility": "PUBLIC",
                                "author": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee",
                                "created_at": "2026-03-11T12:00:00Z"
                            },
                            {
                                "type": "entry",
                                "id": "http://127.0.0.1:8000/api/authors/another-author-id/entries/b2c3d4e5",
                                "title": "Another public post",
                                "content": "Sample content here.",
                                "contentType": "text/plain",
                                "visibility": "PUBLIC",
                                "author": "http://127.0.0.1:8000/api/authors/another-author-id",
                                "created_at": "2026-03-10T18:30:00Z"
                            }
                        ]
                    }
                )
            ]
        ),
        400: OpenApiResponse(description="Invalid page or size"),
        403: OpenApiResponse(description="You must be logged in to view this stream."),
        404: OpenApiResponse(description="Author not found.")
    }
)
@api_view(['GET'])
@login_required
def api_author_stream(request, author_id):
    """
    API endpoint to retrieve a specific author's visible stream (posts they can see).
    Returns posts sorted newest-first (created_at descending).
    Currently only includes public posts; inbox/follower-based posts to be added later.
    """
    # author = get_object_or_404(Author, id=author_id)

    current_author = getattr(request.user, 'author', None)
    if not current_author:
    # Fallback for users/admins without an Author profile
        posts = Post.objects.filter(is_deleted=False, visibility=Post.Visibility.PUBLIC).order_by('-created_at')
    else:

    # filter(is_deleted=False): deleted posts must never appear in the stream unless explicitly requested by admins, to preserve expected social network behavior & prevent showing "ghost" posts
    # order_by('-created_at'): minus sign sorts descending, ensuring newest posts appear 1st
    # show public posts that aren't the user's own, and show all posts that arrived in the user's inbox
        posts  = (Post.objects.filter(is_deleted=False)
                .filter(visibility=Post.Visibility.PUBLIC)
                .exclude(author_id__exact=current_author.id) | current_author.inbox.posts.all()).distinct().order_by('-created_at')

    # Pagination
    try:
        page = int(request.GET.get('page', 1))
        size = int(request.GET.get('size', 10))
        if page < 1 or size < 1:
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "Invalid page or size"}, status=400)

    start = (page - 1) * size
    end = start + size
    paginated_posts = posts[start:end]


    serializer = EntrySerializer(paginated_posts, many=True)

    return JsonResponse({
        "type": "posts",
        "page": page,
        "page_size": size,
        "total_posts": posts.count(),
        "items": serializer.data
    }, status=200)