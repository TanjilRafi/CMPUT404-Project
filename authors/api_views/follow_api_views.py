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
from authors.serializers import AuthorSerializer, EntrySerializer, FollowRequestSerializer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from drf_spectacular.types import OpenApiTypes
from authors.node_auth import NodeBasicAuthentication

@extend_schema(
    summary="Get a list authors that the selected author is following",
    description="""**When to use**: When the author wants a list of authors they are following.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send GET \"/api/authors/{id}/following/\"."""
    ,
    responses={
        200: OpenApiResponse(response=AuthorSerializer(many=True), description="Operation successfull", examples=[
                OpenApiExample(
                    name="list of following",
                    value={"type": "following", 
                           "following": [{"type":"author",
                                          "id": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb",
                                          "host": "http://darkorchid/api/",
                                          "displayName": "Amy",
                                          "github": "http://github.com/amy",
                                          "profileImage": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/entries/1a083be8-e6ca-458e-a0b0-3abf5e012aec/image",
                                          "web": "http://darkorchid/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb"},
                                         {"type":"author",
                                          "id": "http://darkorchid/api/authors/3a083be8-e6ca-458e-a0b0-3abf5e012aef",
                                          "host": "http://darkorchid/api/",
                                          "displayName": "Jane",
                                          "github": "http://github.com/jane",
                                          "profileImage": "http://darkorchid/api/authors/3a083be8-e6ca-458e-a0b0-3abf5e012aef/entries/5a083be8-e6ca-458e-a0b0-3abf5e012aee/image",
                                          "web": "http://darkorchid/authors/3a083be8-e6ca-458e-a0b0-3abf5e012aef"}
                                        ]})]),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="Author does not exist")
    }
)
@api_view(["GET"])
@authentication_classes([SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def api_following_list(request, id):
    """
    GET a list of authors that the selected author is following
    """
    author = get_object_or_404(Author, id=id)
    if not (hasattr(request.user, "author") and request.user.author==author):
        return JsonResponse({"error": "not authorized"}, status=403)
    
    following_list = author.following.all() | author.friends.all()
    data = {"type": "following", "following": AuthorSerializer(following_list, many=True).data}
        
    return JsonResponse(data=data, status=200)

@extend_schema(
    summary="Get a list of the selected author's followers",
    description="""**When to use**: When the author wants a list of followers.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send GET \"/api/authors/{id}/followers/\"."""
    ,
    responses={
        200: OpenApiResponse(response=AuthorSerializer(many=True), description="Operation successfull", examples=[
                OpenApiExample(
                    name="list of followers",
                    value={"type": "followers", 
                           "followers": [{"type":"author",
                                          "id": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb",
                                          "host": "http://darkorchid/api/",
                                          "displayName": "Amy",
                                          "github": "http://github.com/amy",
                                          "profileImage": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/entries/1a083be8-e6ca-458e-a0b0-3abf5e012aec/image",
                                          "web": "http://darkorchid/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb"},
                                         {"type":"author",
                                          "id": "http://darkorchid/api/authors/3a083be8-e6ca-458e-a0b0-3abf5e012aef",
                                          "host": "http://darkorchid/api/",
                                          "displayName": "Jane",
                                          "github": "http://github.com/jane",
                                          "profileImage": "http://darkorchid/api/authors/3a083be8-e6ca-458e-a0b0-3abf5e012aef/entries/5a083be8-e6ca-458e-a0b0-3abf5e012aee/image",
                                          "web": "http://darkorchid/authors/3a083be8-e6ca-458e-a0b0-3abf5e012aef"}
                                        ]})]),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="Author does not exist")
    }
)
@api_view(["GET"])
@authentication_classes([SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def api_followers_list(request, id):
    """
    GET a list of the selected author's followers
    """
    author = get_object_or_404(Author, id=id)
    if not (hasattr(request.user, "author") and request.user.author==author):
        return JsonResponse({"error": "not authorized"}, status=403)
    
    followers_list = author.followers.all() | author.friends.all()
    data = {"type": "followers", "followers": AuthorSerializer(followers_list, many=True).data}
        
    return JsonResponse(data=data, status=200)

@extend_schema(
    methods=["GET"],
    summary="Check if following author",
    description="""**When to use**: When the author wants check if they are following another author.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send GET to \"/api/authors/{id}/following/{fqid}/\"."""
    ,
    responses={
        200: OpenApiResponse(response=AuthorSerializer(), description="Operation successfull", examples=[OpenApiExample(
                        name="GET specific author in following",
                        value={"type":"author",
                               "id": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb",
                               "host": "http://darkorchid/api/",
                               "displayName": "Amy",
                               "github": "http://github.com/amy",
                               "profileImage": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/entries/1a083be8-e6ca-458e-a0b0-3abf5e012aec/image",
                               "web": "http://darkorchid/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb"})]),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="Operation not successfull")
    }
)
@extend_schema(
    methods=["PUT"],
    summary="send follow request",
    description="""**When to use**: When the author wants follow (send request) to another author.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send PUT to \"/api/authors/{id}/following/{fqid}/\"."""
    ,
    responses={
        200: OpenApiResponse(description="Successfully sent follow request to fqid"),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="Problem with foreign node of fqid author")
    }
)
@extend_schema(
    methods=["DELETE"],
    summary="unfollow an author",
    description="""**When to use**: When the author wants to unfollow another author.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send DELETE to \"/api/authors/{id}/following/{fqid}/\"."""
    ,
    responses={
        200: OpenApiResponse(description="Successfully unfollowed fqid author or revoked follow request"),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="not following fqid author")
    }
)
@api_view(["GET", "PUT", "DELETE"])
# @authentication_classes([SessionAuthentication, BasicAuthentication]) # old - before US 08.09

# Remote nodes call these endpoints to check / update follow relationships across nodes; 
# NodeBasicAuthentication validates their Node credentials (US 08.09).
@authentication_classes([NodeBasicAuthentication, SessionAuthentication, BasicAuthentication])

@permission_classes([IsAuthenticated])
def api_following(request, id, fqid):
    """
    GET    /api/authors/{id}/following/{fqid} - check if following fqid author
    PUT    /api/authors/{id}/following/{fqid} - send a follow request to fqid author
    DELETE /api/authors/{id}/following/{fqid} - unfollow fqid author
    """
    author = get_object_or_404(Author, id=id)
    if not (hasattr(request.user, "author") and request.user.author==author):
        return JsonResponse({"error": "not authorized"}, status=403)
    
    api_url = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")

    # Parse the url into components: 
    # parsed.scheme is http or https, parsed.path
    # parsed.netloc is example.com:8000, which helps distinguish remote notes
    parsed = urllib.parse.urlparse(api_url)
    is_remote = parsed.netloc != request.get_host()

    # If the author is remote, we can create a local author within our database
    author_to_add, _ = Author.objects.get_or_create(
        api_url=api_url,
        defaults={
            "host": f"{parsed.scheme}://{parsed.netloc}/",
            "displayName": api_url.split("/")[-1],  # fallback to take the last part of the url (authors uuid) for remote authors not yet in database
        }
    )

    if request.method == "GET":
        try:
            author_to_check = (author.following.all() | author.friends.all()).get(api_url=api_url)
            return JsonResponse(AuthorSerializer(author_to_check).data, status=200)
        except:
            return JsonResponse({"error": "not following fqid author"}, status=404)

    elif request.method == "PUT":
        # Try to fetch the remote author's data
        try:
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                remote_data = response.json()
                author_to_add.displayName = remote_data.get("displayName", author_to_add.displayName)
                author_to_add.host = remote_data.get("host", author_to_add.host)
                author_to_add.url = remote_data.get("url", author_to_add.url)
                author_to_add.github = remote_data.get("github", author_to_add.github)
                author_to_add.profileImage = remote_data.get("profileImage", author_to_add.profileImage)
                author_to_add.save()
        except Exception as e:
            print(f"[WARN] Could not fetch remote author: {e}")     # fallback will be maintained

        # Prevent sending duplicate follow requests
        if author.following.filter(api_url=api_url).exists():
            return JsonResponse({"message": "Already following"}, status=200)
        
        if is_remote:
            # remote
            serializer = FollowRequestSerializer({
                "actor": author,
                "object": author_to_add
            })

            data = serializer.data

            try:
                node = Node.objects.get(url=author_to_add.host, is_enabled=True)
                response = requests.post(f"{author_to_add.api_url}/inbox", json=data, auth=(node.username, node.password))
                
                if response.status_code not in [200, 201]:
                    return Response({"error": "Problem with foreign node of fqid author"}, status=404) 
                else:
                    author.following.add(author_to_add)     # A's node can assume that A is following B, even before author B accepts or denies the request.
            except Exception as e:
                print(f"{e}")
                return Response({"error": "Node not accessible"}, status=404)
        else:
            # local
            inbox, _ = Inbox.objects.get_or_create(author=author_to_add)

            # Prevent sending duplicate follow requests
            if inbox.incoming_follow_requests.filter(id=author.id).exists():        
                return JsonResponse({"message": "Already following"}, status=200)
            
            if not author.following.filter(id=author_to_add.id).exists():       # checks if A is already following B
                author_to_add.inbox.incoming_follow_requests.add(author)

        return JsonResponse({"message": "Successfully sent follow request to fqid"}, status=200)

    elif request.method == "DELETE":
        try:
            author_to_delete = Author.objects.get(api_url=api_url)
            if author_to_delete.inbox.incoming_follow_requests.filter(api_url=author.api_url).exists():
                author_to_delete.inbox.incoming_follow_requests.remove(author)
            elif author.friends.filter(api_url=api_url).exists():
                author.friends.remove(author_to_delete)
                author.followers.add(author_to_delete)
            elif author.following.filter(api_url=api_url).exists():
                author.following.remove(author_to_delete)
            else:
                return JsonResponse({"error": "not following fqid author"}, status=404)
            return JsonResponse({"message": "Successfully unfollowed fqid author or revoked follow request"}, status=200)
        except:
            return JsonResponse({"error": "not following fqid author"}, status=404)

@extend_schema(
    methods=["GET"],
    summary="Check if an author in followers",
    description="""**When to use**: When the author wants check if another author is a follower.  
    **Why use it**: Allows the use of third-party ui while communicating with our server and communication between node servers.
    **How to use**: Send GET to \"/api/authors/{id}/followers/{fqid}/\"."""
    ,
    responses={
        200: OpenApiResponse(response=AuthorSerializer(), description="fqid author is a follower", examples=[OpenApiExample(
                        name="GET specific author in followers",
                        value={"type":"author",
                               "id": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb",
                               "host": "http://darkorchid/api/",
                               "displayName": "Amy",
                               "github": "http://github.com/amy",
                               "profileImage": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/entries/1a083be8-e6ca-458e-a0b0-3abf5e012aec/image",
                               "web": "http://darkorchid/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb"})]),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="fqid author is not in followers")
    }
)
@extend_schema(
    methods=["PUT"],
    summary="To accept follow request",
    description="""**When to use**: When the author wants to accept a follow request.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send PUT to \"/api/authors/{id}/followers/{fqid}/\"."""
    ,
    responses={
        200: OpenApiResponse(description="Successfully accepted fqid author's request"),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="fqid author has not requested to follow")
    }
)
@extend_schema(
    methods=["DELETE"],
    summary="decline follow request/remove follower",
    description="""**When to use**: When the author wants to deny follow request or remove another author from followers.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send DELETE to \"/api/authors/{id}/followers/{fqid}/\"."""
    ,
    responses={
        200: OpenApiResponse(description="Successfully removed fqid author form followers and/or request their request"),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="fqid author is not a follower and has not requested")
    }
)
@api_view(["GET", "PUT", "DELETE"])
# @authentication_classes([SessionAuthentication, BasicAuthentication]) # old - before US 08.09

# Remote nodes call these endpoints to check / update follow relationships across nodes; 
# NodeBasicAuthentication validates their Node credentials (US 08.09).
@authentication_classes([NodeBasicAuthentication, SessionAuthentication, BasicAuthentication])

@permission_classes([IsAuthenticated])
def api_followers(request, id, fqid):
    """
    GET    /api/authors/{id}/followers/{fqid} - check if fqid author is a follower
    PUT    /api/authors/{id}/followers/{fqid} - accept a follow request and add to followers
    DELETE /api/authors/{id}/followers/{fqid} - decline follow request or remove an author from followers
    """
    author = get_object_or_404(Author, id=id)
    if not (hasattr(request.user, "author") and request.user.author==author):
        return JsonResponse({"error": "not authorized"}, status=403)

    api_url = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")

    if request.method == "GET":
        try:
            author_to_check = (author.followers.all() | author.friends.all()).get(api_url=api_url)
            return JsonResponse(AuthorSerializer(author_to_check).data, status=200)
        except:
            return JsonResponse({"error": "fqid author is not in followers"}, status=404)

    elif request.method == "PUT":
        if author.inbox.incoming_follow_requests.filter(api_url=api_url).exists():
            author_to_add = Author.objects.get(api_url=api_url)
            author.inbox.incoming_follow_requests.remove(author_to_add)
            if author.following.filter(api_url=api_url).exists():
                author.following.remove(author_to_add)
                author.friends.add(author_to_add)
            else:
                author.followers.add(author_to_add)
            return JsonResponse({"message": "Successfully accepted fqid author's request"}, status=200)
        else:
            return JsonResponse({"error": "fqid author has not requested to follow"}, status=404)

    elif request.method == "DELETE":
        try:
            author_to_delete = Author.objects.get(api_url=api_url)
            if author.inbox.incoming_follow_requests.filter(api_url=api_url).exists():
                author.inbox.incoming_follow_requests.remove(author_to_delete)
            elif author.friends.filter(api_url=api_url).exists():
                author.friends.remove(author_to_delete)
                author.following.add(author_to_delete)
            elif author.followers.filter(api_url=api_url).exists():
                author.followers.remove(author_to_delete)
            else:
                return JsonResponse({"error": "fqid author is not a follower and has not requested"}, status=404)
            return JsonResponse({"message": "Successfully removed fqid author form followers and/or request their request"}, status=200)
        except:
            return JsonResponse({"error": "fqid author is not a follower and has not requested"}, status=404)      

@extend_schema(
    summary="List incoming follow requests",
    description=""" 
    **When to use:**  Use this endpoint when you want to see which authors are requesting to follow the authenticated author.  
    **Why use it:**  This allows the user to approve or deny follow requests and manage friend relationships.  
    **How to use it:**  Send a GET request to `/api/authors/{author_id}/follow_requests`. Only the authenticated author can access this endpoint.  
    
    **Response:**  Returns a JSON object with a `type` of `"follow_requests"` and an `items` list containing follow request objects. Each follow request object includes the `actor` (the author who wants to follow) and `object` (the authenticated author).  
    """,
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="List of follow requests retrieved successfully.",
            examples=[
                OpenApiExample(
                    name="Follow requests response",
                    value={
                        "type": "follow_requests",
                        "items": [
                            {
                                "type": "follow",
                                "summary": "Greg Johnson wants to follow Lara Croft",
                                "actor": {
                                    "type": "author",
                                    "id": "http://socialdistribution/api/authors/111",
                                    "host": "http://socialdistribution/api/",
                                    "displayName": "Greg Johnson",
                                    "github": "http://github.com/gjohnson",
                                    "profileImage": "https://i.imgur.com/k7XVwpB.jpeg",
                                    "web": "http://socialdistribution/authors/greg"
                                },
                                "object": {
                                    "type": "author",
                                    "id": "http://nodeb/api/authors/222",
                                    "host": "http://nodeb/api/",
                                    "displayName": "Lara Croft",
                                    "github": "http://github.com/laracroft",
                                    "profileImage": "http://nodeb/api/authors/222/entries/217/image",
                                    "web": "http://nodeb/authors/222"
                                }
                            }
                        ]
                    }
                )
            ]
        ),
        403: OpenApiResponse(description="Forbidden. Only the logged in author may view their incoming follow requests."),
        404: OpenApiResponse(description="Author not found.")
    }
)
# API views follow request
@api_view(['GET'])
@authentication_classes([SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def api_follow_requests(request, author_id):
    """
    GET /api/authors/{author_id}/follow_requests
    Retrieves all authors who have requested to follow this author.
    """
    author = get_object_or_404(Author, id=author_id)

    # Only the author themselves can view their incoming requests
    if request.user.pk != author.user.pk:
        return Response({"error": "Forbidden"}, status=403)

    # Get or create the inbox for the author
    inbox, _ = Inbox.objects.get_or_create(author=author)

    # Loop directly over incoming_follow_requests to match API specs
    follow_requests = []
    for actor in inbox.incoming_follow_requests.all():
        data = {
            "actor": actor,
            "object": author
        }
        follow_requests.append(FollowRequestSerializer(data).data)

    return Response({"type": "follow_requests", "items": follow_requests})