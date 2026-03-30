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
from authors.serializers import AuthorSerializer, EntrySerializer, EntriesSerializer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from drf_spectacular.types import OpenApiTypes
from authors.helpers import push_post_to_remote
from authors.node_auth import NodeBasicAuthentication

@extend_schema(
    methods=["GET"],
    summary="List all entries for an author",
    description="""**When to use**: When you need to retrieve all visible entries for a specific author.  
    **Why use it**: Returns entries filtered by your relationship to the author — public only, or more depending on if you follow or are friends with them.  
    **How to use**: Send a GET request to `/api/authors/<uuid>/entries/`. Authentication optional but affects visibility.  
    **Why not use UI**: This is the machine-readable/API version; use the browser post list for human viewing.""",
    parameters=[
        OpenApiParameter(
            name="id",
            type=str,
            location=OpenApiParameter.PATH,
            description="The UUID of the author whose entries you want to list.",
            required=True,
            examples=[
                OpenApiExample(
                    name="Valid UUID example",
                    value="c7d84ea2-27bb-44ba-8e9c-07bc149a88ee"
                )
            ]
        )
    ],
    responses={
        200: OpenApiResponse(
            response=EntrySerializer(many=True),
            description="List of entries visible to the requester.",
            examples=[
                OpenApiExample(
                    name="Successful response",
                    value={
                        "type": "entries",
                        "entries": [
                            {
                                "type": "entry",
                                "id": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee/entries/a1b2c3d4-0000-0000-0000-000000000000",
                                "title": "Hello World",
                                "content": "This is my first entry to the world :D.",
                                "contentType": "text/plain",
                                "visibility": "PUBLIC",
                                "author": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee",
                                "created_at": "2026-02-28T12:00:00Z"
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
            value="curl http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee/entries/",
            request_only=True
        )
    ]
)
@extend_schema(
    methods=["POST"],
    summary="Create a new entry for an author",
    description="""**When to use**: When you need to programmatically create an entry for an author.  
    **Why use it**: Allows automated or federated clients to publish entries without using the browser UI.  
    **How to use**: Send a POST request to `/api/authors/<uuid>/entries/` with title, content, visibility, and type in the body.  
    **Why not use for edits/deletes**: Use PUT or DELETE on `/api/authors/<uuid>/entries/<entry_id>/` instead.""",
    parameters=[
        OpenApiParameter(
            name="id",
            type=str,
            location=OpenApiParameter.PATH,
            description="The UUID of the author creating the entry.",
            required=True,
            examples=[
                OpenApiExample(
                    name="Valid UUID example",
                    value="c7d84ea2-27bb-44ba-8e9c-07bc149a88ee"
                )
            ]
        )
    ],
    request=OpenApiTypes.OBJECT,
    responses={
        201: OpenApiResponse(
            description="Entry created successfully.",
            examples=[
                OpenApiExample(
                    name="Successful creation",
                    value={
                        "message": "Entry created",
                        "id": "a1b2c3d4-0000-0000-0000-000000000000"
                    }
                )
            ]
        ),
        400: OpenApiResponse(description="Missing required fields.")
    },
    examples=[
        OpenApiExample(
            name="Curl request example",
            value='curl -X POST http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee/entries/ -H "Content-Type: application/json" -d \'{"title": "Hello", "content": "World", "visibility": "PUBLIC", "type": "TEXT"}\'',
            request_only=True
        ),
        OpenApiExample(
            name="Plain text entry",
            value={"title": "Hello", "content": "World", "visibility": "PUBLIC", "type": "TEXT"},
            request_only=True
        ),
        OpenApiExample(
            name="Markdown entry",
            value={"title": "Markdown Post", "content": "# Hi\n\n**bold**", "visibility": "FRIENDS", "type": "COMMONMARK"},
            request_only=True
        ),
        OpenApiExample(
            name="Unlisted entry",
            value={"title": "Secret", "content": "Only via link.", "visibility": "UNLISTED", "type": "TEXT"},
            request_only=True
        )
    ]
)
class ApiEntries(APIView):
    def get_authenticators(self):
        if self.request:
            if self.request.method == 'GET':
                return [NodeBasicAuthentication(), SessionAuthentication(), BasicAuthentication()]
            else:
                return [SessionAuthentication(), BasicAuthentication()]
        else:
            return []

    def get_permissions(self):
        return [IsAuthenticated()]
    
    # def get(self, request, id):
    #     """
    #     GET  /api/authors/{id}/entries/ — list entries
    #     """
    #     author = get_object_or_404(Author, id=id)

    #     if request.method == "GET":
    #         base_query = Post.objects.filter(author=author, is_deleted=False).exclude(visibility=Post.Visibility.UNLISTED)

    #         if request.user.is_authenticated and hasattr(request.user, 'author'):
    #             if request.user == author.user:
    #                 # Owner sees everything else
    #                 posts = base_query
    #             elif request.user.author in author.friends.all():
    #                 # Friends see public and friends-only
    #                 posts = base_query.filter(visibility__in=[Post.Visibility.PUBLIC, Post.Visibility.FRIENDS])
    #             elif request.user.author in author.followers.all():
    #                 # Followers see public only 
    #                 posts = base_query.filter(visibility=Post.Visibility.PUBLIC)
    #             else:
    #                 posts = base_query.filter(visibility=Post.Visibility.PUBLIC)
    #         else:
    #             posts = base_query.filter(visibility=Post.Visibility.PUBLIC)

    #         posts = posts.order_by('-created_at')

    #         try:
    #             page = int(request.GET.get('page', 1))
    #             size = int(request.GET.get('size', 10))
    #         except ValueError:
    #             return JsonResponse({"error": "Invalid page or size"}, status=400)

    #         start = (page - 1) * size
    #         end = start + size
    #         posts = posts[start:end]

    #         data = {
    #             "type": "entries",
    #             "page_number": page,
    #             "size": size,
    #             "count": Post.objects.filter(author=author, is_deleted=False)
    #                     .exclude(visibility=Post.Visibility.UNLISTED).count(),
    #             "src": EntrySerializer(posts, many=True).data,
    #         }
    #         return JsonResponse(data)

    def get(self, request, id):
        """
        GET  /api/authors/{id}/entries/ - list entries
        Returns entries the requester is allowed to see.
        """
        author = get_object_or_404(Author, id=id)

        # Start with all non-deleted posts by this author
        posts = Post.objects.filter(author=author, is_deleted=False)

        if request.user.is_authenticated and hasattr(request.user, 'author'):
            current = request.user.author

            if current == author:
                # Owner sees everything non-deleted
                pass
            elif current in author.friends.all():
                # Friends see PUBLIC + FRIENDS
                posts = posts.filter(visibility__in=[Post.Visibility.PUBLIC, Post.Visibility.FRIENDS])
            elif current in author.followers.all():
                # Followers see only PUBLIC
                posts = posts.filter(visibility=Post.Visibility.PUBLIC)
            else:
                # Strangers / not following → only PUBLIC
                posts = posts.filter(visibility=Post.Visibility.PUBLIC)
        else:
            # Not logged in -> only PUBLIC
            posts = posts.filter(visibility=Post.Visibility.PUBLIC)

        posts = posts.order_by('-created_at')

        # Pagination
        try:
            page = int(request.GET.get('page', 1))
            size = int(request.GET.get('size', 10))
        except ValueError:
            return JsonResponse({"error": "Invalid page or size"}, status=400)

        # Count total BEFORE slicing
        total_count = posts.count()

        start = (page - 1) * size
        end = start + size
        paginated_posts = posts[start:end]

        data = {
            "type": "entries",
            "page_number": page,
            "size": size,
            "count": total_count,
            "src": EntrySerializer(paginated_posts, many=True).data,
        }
        return JsonResponse(data)

    def post(self, request, id):
        """
        POST /api/authors/{id}/entries/ — create entry
        """
        author = get_object_or_404(Author, id=id)

        if request.method == "POST":
            data = request.data
            title = data.get('title', '').strip()
            content = data.get('content', '').strip()
            visibility = data.get('visibility', Post.Visibility.PUBLIC)
            content_type = data.get('contentType', 'text/plain')
            post_type = data.get('type', Post.Type.TEXT)

            if not title or not content:
                return Response({"error": "Missing fields"}, status=400)
            if not request.user.is_authenticated or request.user.pk != author.user.pk:
                return Response({"detail": "Forbidden"}, status=403)
            
            post = Post.objects.create(
                author=author,
                title=title,
                content=content,
                visibility=visibility,
                type=post_type,
                # content_type=content_type
                contentType=content_type
            )

            return Response({
                "type": "entry",
                "id": f"{author.host}authors/{author.id}/entries/{post.id}",
                "title": post.title,
                "content": post.content,
                "contentType": post.contentType,
                "visibility": post.visibility,
                "author": f"{author.host}authors/{author.id}",
                "created_at": post.created_at.isoformat(),
            }, status=201)


@extend_schema(
    methods=["GET"],
    summary="Get a specific entry",
    description="""Retrieves full details of a single entry.
    Visibility rules apply: FRIENDS entries only visible to friends, UNLISTED to anyone with the link.

    Pagination: Not applicable — single entry.
    """,
    responses={
        200: OpenApiResponse(
            response=EntrySerializer,
            description="Entry retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Single entry response",
                    value={
                        "type": "entry",
                        "id": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee/entries/a1b2c3d4-0000-0000-0000-000000000000",
                        "title": "Hello World",
                        "content": "This is my first entry to the world :D",
                        "contentType": "text/plain",
                        "visibility": "PUBLIC",
                        "author": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee",
                        "created_at": "2026-02-28T12:00:00Z"
                    }
                )
            ]
        ),
        403: OpenApiResponse(description="You are not authorized to view this entry."),
        404: OpenApiResponse(description="Entry not found or already deleted.")
    },
    examples=[
        OpenApiExample(
            name="Curl GET request example",
            request_only=True,
            value='curl -X GET http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee/entries/a1b2c3d4-0000-0000-0000-000000000000/'
        )
    ]
)
@extend_schema(
    methods=["PUT"],
    summary="Edit a specific entry",
    description="""Edits an existing entry. Only the author can edit their own entry.
    Send a JSON body with fields to update. Can update title, content, and visibility.

    Why NOT to use PUT to delete: Use DELETE instead.

    Pagination: Not applicable — single entry.
    """,
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'title': {'type': 'string', 'example': 'Updated Title'},
                'content': {'type': 'string', 'example': 'Updated content.'},
                'visibility': {'type': 'string', 'example': 'PUBLIC'},
            }
        }
    },
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Entry updated successfully.",
            examples=[
                OpenApiExample(
                    name="Entry updated response",
                    value={
                        "message": "Entry updated",
                        "id": "a1b2c3d4-0000-0000-0000-000000000000"
                    }
                )
            ]
        ),
        403: OpenApiResponse(description="You are not authorized to edit this entry."),
        404: OpenApiResponse(description="Entry not found or already deleted.")
    },
    examples=[
        OpenApiExample(
            name="Edit entry body",
            request_only=True,
            value={
                "title": "Updated Title",
                "content": "Updated content.",
                "visibility": "PUBLIC"
            }
        )
    ]
)
@extend_schema(
    methods=["DELETE"],
    summary="Delete a specific entry",
    description="""Soft-deletes an entry.
    Entry remains in database with is_deleted=True.
    Removed from all inboxes and hidden from UI and API.
    Cannot be undone via API. Node admins can still see deleted entries.

    Pagination: Not applicable — single entry.
    """,
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Entry deleted successfully.",
            examples=[
                OpenApiExample(
                    name="Entry deleted response",
                    value={"message": "Entry deleted"}
                )
            ]
        ),
        403: OpenApiResponse(description="You are not authorized to delete this entry."),
        404: OpenApiResponse(description="Entry not found or already deleted.")
    },
    examples=[
        OpenApiExample(
            name="Curl DELETE request example",
            request_only=True,
            value='curl -X DELETE http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee/entries/a1b2c3d4-0000-0000-0000-000000000000/ -u username:password'
        )
    ]
)
class ApiEntryDetail(APIView):
    def get_authenticators(self):
        if self.request:
            if self.request.method == 'GET':
                return [NodeBasicAuthentication(), SessionAuthentication(), BasicAuthentication()]
            else:
                return [SessionAuthentication(), BasicAuthentication()]
        else:
            return []

    def get_permissions(self):
        return [IsAuthenticated()]
    
    def get(self, request, id, post_id):
        """
        GET    /api/authors/{id}/entries/{post_id}/ — get entry
        """
        author = get_object_or_404(Author, id=id)
        post = get_object_or_404(Post, id=post_id, author=author)

        if request.method == "GET":
            if post.is_deleted and not (request.user.is_authenticated and request.user.is_staff):
                return Response({"detail": "Not found"}, status=404)

            if post.visibility == Post.Visibility.FRIENDS:
                if request.user.is_authenticated and hasattr(request.user, 'author') or request.user.author not in author.friends.all():
                    return Response(EntrySerializer(post).data)
                else:
                    return JsonResponse({"detail", "Not found"}, status=404)
            else:
                return Response(EntrySerializer(post).data)

    def put(self, request, id, post_id):
        """
        PUT    /api/authors/{id}/entries/{post_id}/ — edit entry
        """
        author = get_object_or_404(Author, id=id)
        post = get_object_or_404(Post, id=post_id, author=author)

        if request.method == "PUT":
            if not request.user.is_authenticated or request.user.pk != author.user.pk:
                return Response({"detail": "Forbidden"}, status=403)
            if post.is_deleted:
                return JsonResponse({"error": "Cannot update a deleted entry"}, status=404)

            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)

            title = body.get('title', post.title)
            content = body.get('content', post.content)
            visibility = body.get('visibility', post.visibility)
            contentType = body.get('contentType', post.contentType)
            if post.title != title or post.contentType != contentType or post.visibility != visibility or post.content != content:
                post_edited = True
            else:
                post_edited = False

            post.title = title
            post.content = content
            post.visibility = visibility
            post.contentType = contentType
            post.setType()
            post.save()

            if post_edited:
                push_post_to_remote(post, post.author)

            return JsonResponse({"message": "Entry updated", "id": str(post.id)})

        
    def delete(self, request, id, post_id):
        """
        DELETE /api/authors/{id}/entries/{post_id}/ — delete entry
        """
        author = get_object_or_404(Author, id=id)
        post = get_object_or_404(Post, id=post_id, author=author)
        if request.method == "DELETE":
            if not request.user.is_authenticated or request.user.pk != author.user.pk:
                return JsonResponse({"error": "Forbidden"}, status=403)
            if post.is_deleted:
                return JsonResponse({"error": "Cannot update a deleted entry"}, status=404)

            post.is_deleted = True
            post.save()

            # remove from local inboxes
            for user in Author.objects.all():
                if post in user.inbox.posts.all():
                    user.inbox.posts.remove(post)


            return JsonResponse({"message": "Entry deleted"})

@extend_schema(
    summary="Get image entry as binary (specific author)",
    description="""Returns the image content of an entry as binary data instead of base64.
    
    When to use: Use this to display an image entry directly in an HTML img tag.
    
    How to use: Use the URL directly as the src of an img tag.
    
    Why to use: Allows markdown entries to embed images hosted on this node.
    
    Why NOT to use: Do not use this for non-image entries — returns 404.
    
    Pagination: Not applicable.

    Example usage (curl):
    curl -X GET "http://127.0.0.1:8000/api/authors/{author_id}/entries/{entry_id}/image/" -u username:password --output image.png
    """,
    responses={
        200: OpenApiResponse(response=OpenApiTypes.BINARY, description="Binary image data.",
                             examples=[
                                OpenApiExample(
                                    name="Successful image response", 
                                    value="""HTTP/1.1 200 OK Content-Type: image/png Content-Length: 54231 (binary image data)""",
                                    response_only=True)]),
        404: OpenApiResponse(description="Post is not an image.")
    },
    examples=[
        OpenApiExample(
            name="Curl request example",
            request_only=True,
            value="curl -X GET http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee/entries/a1b2c3d4/image/ -u username:password --output image.png"
        )
    ]
)   
@api_view(["GET"])
@authentication_classes([NodeBasicAuthentication, SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def entry_image(request, id, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.type == Post.Type.IMAGE and post.visibility != Post.Visibility.FRIENDS:
        img = base64.b64decode(post.content.encode('utf-8'))
        return HttpResponse(img, content_type=post.contentType)
    else:
        return JsonResponse({"error":"This post doesn't have an image file"}, status=404)
    
@extend_schema(
    summary="Get image entry as binary",
    description="""Returns the image content of an entry as binary data instead of base64.
    
    When to use: Use this to display an image entry directly in an HTML img tag.
    
    How to use: Use the URL directly as the src of an img tag.
    
    Why to use: Allows markdown entries to embed images hosted on this node.
    
    Why NOT to use: Do not use this for non-image entries — returns 404.
    
    Pagination: Not applicable.

    Example usage (curl):
    curl -X GET "http://127.0.0.1:8000/api/entries/<fqid>/image/" -u username:password --output image.png

    """,
    responses={
        200: OpenApiResponse(response=OpenApiTypes.BINARY, description="Binary image data.", examples=[
                OpenApiExample(
                    name="Successful image response",
                    value="HTTP/1.1 200 OK Content-Type: image/png Content-Length: 54231 (binary image data)",
                    response_only=True
                )
            ]),
        404: OpenApiResponse(description="Post is not an image.")
    }
)
@api_view(["GET"])
@authentication_classes([NodeBasicAuthentication, SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def entry_image_fqid(request, fqid):
    api_url = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")
    post = get_object_or_404(Post, api_url=api_url)
    if post.type == Post.Type.IMAGE and post.visibility != Post.Visibility.FRIENDS:
        img = base64.b64decode(post.content.encode('utf-8'))
        return HttpResponse(img, content_type=post.contentType)
    else:
        return JsonResponse({"error":"This post doesn't have an image file"}, status=404)
    

@extend_schema(
    methods=["GET"],
    summary="Get a specific entry by fqid",
    description="""Retrieves full details of a single entry.
    Visibility rules apply: FRIENDS entries only visible to friends, UNLISTED to anyone with the link.

    Pagination: Not applicable — single entry.
    """,
    responses={
        200: OpenApiResponse(
            response=EntrySerializer,
            description="Entry retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Single entry response",
                    value={
                        "type": "entry",
                        "id": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee/entries/a1b2c3d4-0000-0000-0000-000000000000",
                        "title": "Hello World",
                        "content": "This is my first entry to the world :D",
                        "contentType": "text/plain",
                        "visibility": "PUBLIC",
                        "author": "http://127.0.0.1:8000/api/authors/c7d84ea2-27bb-44ba-8e9c-07bc149a88ee",
                        "created_at": "2026-02-28T12:00:00Z"
                    }
                )
            ]
        ),
        403: OpenApiResponse(description="You are not authorized."),
        404: OpenApiResponse(description="Entry not found or already deleted.")
    }
)   
@api_view(["GET"])
@authentication_classes([SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def api_entry_fqid(request, fqid):
    fqid = fqid.rstrip("/")
    post = get_object_or_404(Post, api_url=fqid)
    if post.visibility == Post.Visibility.DELETED or post.is_deleted:
        return JsonResponse({"error":"Not found"}, status=404)
    else:
        if post.visibility == Post.Visibility.PUBLIC or post.visibility == Post.Visibility.UNLISTED:
            return JsonResponse(EntrySerializer(post).data, status=200)
        elif request.user and hasattr(request.user, "author"):
            if request.user.author == post.author:
                return JsonResponse(EntrySerializer(post).data, status=200)
            elif post.visibility == Post.Visibility.FRIENDS and post.author.friends.filter(id=request.user.author.id).exists():
                return JsonResponse(EntrySerializer(post).data, status=200)
            else:
                return JsonResponse({"error":"You are not authorized"}, status=403)
            
        else:
            return JsonResponse({"error":"Not found"}, status=404)

