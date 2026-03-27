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

from drf_spectacular.types import OpenApiTypes
from authors.node_auth import NodeBasicAuthentication

@extend_schema(
    summary="Post a follow request or entry to inbox",
    description="""**When to use**: When a node wants to inform about a post or friend request.  
    **Why use it**: This is the standard, federated way to create posts.  
    **How to use**: POST to `/api/authors/<id>/inbox/` with form data following example.""",
    responses={
        200: OpenApiResponse( 
            response=OpenApiTypes.OBJECT,
            description="Follow request or entry saved successfully",
            examples=[
                OpenApiExample(
                    name="Follow request response",
                    value={"message": "Friend request added"}
                ),
                OpenApiExample(
                    name="Entry response",
                    value={"message": "Post added"}
                )
            ]
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="The object author does not match the inbox author",
            examples=[
                OpenApiExample(
                    name="Mismatching object author",
                    value={"error": "Wrong inbox or object"}
                ),
                OpenApiExample(
                    name="Invalid JSON",
                    value={"error": "Invalid JSON"}
                ),
            ]
        ),
        403: OpenApiResponse(description="Not authorized"),
        404: OpenApiResponse(description="Inbox's author not found")
    },
    request=OpenApiTypes.OBJECT,
    examples=[
        OpenApiExample(
            name="Follow request body",
            value = {
                "type": "follow",      
                "actor":{
                    "type":"author",
                    "id":"http://darkorchid/api/authors/<id>",
                    "host":"http://darkorchid/api/",
                    "displayName":"Amy",
                    "web": "http://darkorchid/authors/<id>",
                    "github": "http://github.com/amy",
                    "profileImage": "http://darkorchid/api/authors/<id>/entries/<post_id>/image",
                },
                "object":{
                    "type":"author",
                    "id":"http://darkorchid/api/authors/<id>",
                    "host":"http://darkorchid/api/",
                    "displayName":"Jane",
                    "web":"http://darkorchid/authors/<id>",
                    "github": "http://github.com/jane",
                    "profileImage": "http://darkorchid/api/authors/<id>/entries/<post_id>/image"
                }
            }, request_only=True               
        ),
        OpenApiExample(
            name="Entry body",
            value = {
                "type":"entry",
                "title":"An entry title about things",
                "id":"http://darkorchid/api/authors/<id>/entries/<post_id>",
                "web": "http://darkorchid/authors/<id>/entries/<post_id>",
                "contentType":"text/plain",
                "content":"Lorem ipsum",
                "author":{
                    "type":"author",
                    "id":"http://darkorchid/api/authors/<id>",
                    "host":"http://darkorchid/api/",
                    "displayName":"Amy",
                    "web":"http://darkorchid/authors/<id>",
                    "github": "http://github.com/amy",
                    "profileImage": "http://darkorchid/api/authors/<id>/entries/<post_id>/image"
                },
                "published":"2025-03-09T13:07:04+00:00",
                "visibility":"PUBLIC"
            }, request_only=True 
        )
    ]
)


# @authentication_classes([SessionAuthentication, BasicAuthentication]) # old decorator before US 08.09

# NodeBasicAuthentication checks the Node table so remote nodes can POST to inboxes using the credentials 
# a local admin registered (US 08.09). SessionAuthentication keeps browser-based testing working.
@api_view(["POST"])
@csrf_exempt
@authentication_classes([NodeBasicAuthentication, SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def api_inbox(request, id):
    """
    POST /api/authors/<id>/inbox - send a post, follow request, or like
    """
    # US 03.02: Require authentication for inbox
    # if not request.user.is_authenticated:
    #     return JsonResponse({"error": "Authentication required"}, status=401)

    # Both node-to-node callers (authenticated via NodeBasicAuthentication, where request.user is the 
    # sentinel string "node:<url>") and local session users must be authenticated. Unauthenticated POSTs 
    # to the inbox are rejected to prevent anonymous spam (US 08.09).
    # if not request.user and not request.auth:
    #     return JsonResponse({"error": "Authentication required"}, status=401)

    # A valid caller is either:
    #   (a) a remote node authenticated via NodeBasicAuthentication (request.auth is a Node), or
    #   (b) a local Django session user (request.user.is_authenticated is True).
    # Anything else is rejected. Implements US 08.09 without breaking existing browser-based usage.
    is_node_caller = isinstance(request.auth, Node)
    # is_session_user = request.user and request.user.is_authenticated

    # request.user is a string sentinel ("node:<url>") when NodeBasicAuthentication
    # succeeds, so we check its type before calling .is_authenticated, which only
    # exists on Django User objects.
    is_session_user = hasattr(request.user, 'is_authenticated') and request.user.is_authenticated

    if not is_node_caller and not is_session_user:
        return JsonResponse({"error": "Authentication required"}, status=401)
        
    author = get_object_or_404(Author, id=id)
    
    # Safely get JSON data
    try:
        body = request.data
        if not body and request.body:
            body = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    type_str = body.get("type", "")
    actor_json = body.get("actor", {})
    object_json = body.get("object", {})

    if type_str == "follow":
        if str(author.api_url) != object_json.get("id", ""):
            return Response({"error": "Wrong inbox"}, status=400)
        try:
            actor, created = Author.objects.get_or_create(api_url=actor_json.get("id"), defaults={ # should look up by api_url, not both api and url cause then it will make duplicates
                "url": actor_json.get("web", None),
                "host": actor_json.get("host"),
                "displayName": actor_json.get("displayName", "Unknown"),
                "github": actor_json.get("github", ""),
                "profileImage": actor_json.get("profileImage", ""),
            })
            Inbox.objects.get_or_create(author=actor)
            author.inbox.incoming_follow_requests.add(actor)
            return JsonResponse({"message": "Friend request added"})
        except:
            return JsonResponse({"error": "Incorrect json"}, status=400)
         
    if type_str == "like":
        author_data = body.get("author", {})

        # US 08.16: Uses full api url as author identifier not just uuid,
        # to avoid collisions between nodes with the same uuids
        liker_api_url = (author_data.get("id") or "").rstrip("/")

        if not liker_api_url:
        # 
            return JsonResponse({"error": "Missing author ID"}, status=400)
        # get_or_create the author to ensure we have a local Author object for 
        # the liker which is needed for the Like foreign key
        object_url = (body.get("object") or "").rstrip("/")
        if not object_url:
            return JsonResponse({"error": "Missing 'object' field in Like object"}, status=400)

        remote_author, created = Author.objects.get_or_create(
            # US 08.16: Uses full api url as unique identifier for remote 
            # authors to prevent collisions across nodes not just uuid
            api_url=liker_api_url,
            defaults={
                "displayName": author_data.get("displayName", "Unknown"),
                # Stores url if available, otherwise fall back to the api 
                # url which is not ideal but ensures we have something to link to
                "host": author_data.get("host", ""),
                "url": author_data.get("web", liker_api_url),
            }
        )
        
        if created:
            Inbox.objects.get_or_create(author=remote_author)
        target_entry = Post.objects.filter(api_url=object_url).first()
        target_comment = Comment.objects.filter(api_url=object_url).first()
        if target_entry is None and target_comment is None:
            return JsonResponse({"error": "Object does not exist"}, status=404)
        try:
            # US 08.16: Like objects can be uniquely identified by their 
            # api url if provided which prevents duplicates if the same like 
            # is sent multiple times due to retries or from different nodes. 
            like_api_url = (body.get("id") or "").rstrip("/")
            if like_api_url:
                Like.objects.get_or_create(
                    api_url=like_api_url,
                    defaults={
                        "author": remote_author,
                        "post": target_entry,
                        "comment": target_comment,
                    },
                )
            else:
                Like.objects.get_or_create(
                    author=remote_author,
                    post=target_entry,
                    comment=target_comment,
                )
            # If no API URL is provided for the like, we fall back to matching 
            # by author and target, which may create duplicates but ensures the 
            # like is still recorded
            return JsonResponse({"message": "Like received"}, status=200)

        except Exception as e:
            # keep compatibility with local unique constraints while preferring
            # remote object id when provided
            return JsonResponse({"message": "Like could not be processed locally", "error": str(e)}, status=400)
    
    if type_str == "entry":
        try:
            author_data = body.get("author", {}) # changing to get or create for remote node logic
            actor, _ = Author.objects.get_or_create(
                api_url=author_data.get("id"),
                defaults={
                    "url": author_data.get("web", ""),
                    "host": author_data.get("host", ""),
                    "displayName": author_data.get("displayName", "Unknown"),
                    "github": author_data.get("github", ""),
                    "profileImage": author_data.get("profileImage", ""),
                }
            )
            Inbox.objects.get_or_create(author=actor)
            
            # Wrote delete functionality with the help of Copilot, Accessed 26th March, 2026
            incoming_visibility = body.get("visibility", "PUBLIC").upper().strip()

            # handle DELETED before get_or_create to avoid saving a deleted post
            if incoming_visibility == Post.Visibility.DELETED:
                post_api_url = body.get("id")
                try:
                    post = Post.objects.get(api_url=post_api_url)
                    author.inbox.posts.remove(post)
                    post.is_deleted = True
                    post.save()
                except Post.DoesNotExist:
                    pass  # already gone, nothing to do
                return JsonResponse({"message": "Post deleted from inbox"})
        
            post, _ = Post.objects.get_or_create(
                api_url=body.get("id"),
                defaults={"author": actor, "url": body.get("web", "")}
            )
            post.title = body.get("title")
            post.content = body.get("content")
            post.content_type = body.get("contentType")
            post.visibility = incoming_visibility
            post.setType()
            post.save()


            # Handle nested likes and comments in the entry body (US 08.09)
            # this allows remote nodes to include likes and comments when they POST an entry, 
            # so the receiving node can save them without needing separate API calls.
            post_likes = body.get("likes", {}).get("src", [])
            comments = body.get("comments", {}).get("src", [])

            def _get_or_create_author(author_payload):
                if not isinstance(author_payload, dict):
                    return None

                author_api_url = author_payload.get("id")
                if not author_api_url:
                    return None

                remote_author, _ = Author.objects.get_or_create(
                    api_url=author_api_url,
                    defaults={
                        "url": author_payload.get("web", ""),
                        "host": author_payload.get("host", ""),
                        "displayName": author_payload.get("displayName", "Unknown"),
                        "github": author_payload.get("github", ""),
                        "profileImage": author_payload.get("profileImage", ""),
                    },
                )
                Inbox.objects.get_or_create(author=remote_author)
                return remote_author

            if isinstance(post_likes, list):
                for like_payload in post_likes:
                    if not isinstance(like_payload, dict):
                        continue
                    like_id = like_payload.get("id")
                    like_author = _get_or_create_author(like_payload.get("author", {}))
                    if not like_id or like_author is None:
                        continue
                    Like.objects.get_or_create(
                        api_url=like_id,
                        defaults={
                            "author": like_author,
                            "post": post,
                        },
                    )

            if isinstance(comments, list):
                for comment_payload in comments:
                    if not isinstance(comment_payload, dict):
                        continue
                    comment_id = comment_payload.get("id")
                    comment_author = _get_or_create_author(comment_payload.get("author", {}))
                    if not comment_id or comment_author is None:
                        continue

                    saved_comment, _ = Comment.objects.get_or_create(
                        api_url=comment_id,
                        defaults={
                            "author": comment_author,
                            "post": post,
                            "content": comment_payload.get("comment", ""),
                            "contentType": comment_payload.get("contentType", "text/plain"),
                        },
                    )

                    comment_likes = comment_payload.get("likes", {}).get("src", [])
                    if not isinstance(comment_likes, list):
                        continue

                    for comment_like_payload in comment_likes:
                        if not isinstance(comment_like_payload, dict):
                            continue
                        comment_like_id = comment_like_payload.get("id")
                        comment_like_author = _get_or_create_author(comment_like_payload.get("author", {}))
                        if not comment_like_id or comment_like_author is None:
                            continue

                        Like.objects.get_or_create(
                            api_url=comment_like_id,
                            defaults={
                                "author": comment_like_author,
                                "comment": saved_comment,
                            },
                        )


            # only add to inbox if still following/friends
            # if post.visibility == Post.Visibility.PUBLIC:
            #     author.inbox.posts.add(post)
            # elif post.visibility == Post.Visibility.UNLISTED and (author.following.filter(author=actor).exists() or author.friends.filter(author=actor).exists()):
            #     author.inbox.posts.add(post)
            # elif post.visibility == Post.Visibility.UNLISTED and author.friends.filter(author=actor).exists():
            #     author.inbox.posts.add(post)
            
            # Always add to inbox for now (visibility filtering happens on read)
            author.inbox.posts.add(post)
            return JsonResponse({"message": "Post saved"})
        except:
            return JsonResponse({"error": "Incorrect json"}, status=400)
        
    if type_str == "comment":
        try:
            author_data = body.get("author", {})
            commenter_api_url = (author_data.get("id") or "").rstrip("/")
            if not commenter_api_url:
                return JsonResponse({"error": "Missing comment author id"}, status=400)

            commenter, _ = Author.objects.get_or_create(
                api_url=commenter_api_url,
                defaults={
                    "url": author_data.get("web", commenter_api_url),
                    "host": author_data.get("host", ""),
                    "displayName": author_data.get("displayName", "Unknown"),
                    "github": author_data.get("github", ""),
                    "profileImage": author_data.get("profileImage", ""),
                },
            )

            entry_fqid = (body.get("entry") or "").rstrip("/")
            if not entry_fqid:
                return JsonResponse({"error": "Missing comment entry"}, status=400)
            post_uuid_str = entry_fqid.rstrip("/").split("/")[-1]
            # got help from claude for the logic below 
            # match by full API URL or fall back to UUID if there's a trailing slash mismatch
            post = Post.objects.filter(
                Q(api_url=entry_fqid) | Q(api_url=entry_fqid + "/") | Q(id__icontains=post_uuid_str)
            ).first()

            if not post:
                return JsonResponse({"error": "Entry not found on this node"}, status=404)

            comment_api_url = (body.get("id") or "").rstrip("/")
            if not comment_api_url:
                return JsonResponse({"error": "Missing comment id"}, status=400)
            saved_comment, _ = Comment.objects.get_or_create(
                api_url=comment_api_url,
                defaults={
                    "author": commenter,
                    "post": post,
                    "content": body.get("comment", ""),
                    "contentType": body.get("contentType", "text/plain"),
                }
            )

            # added for persist embedded likes on this incoming comment
            comment_likes = body.get("likes", {}).get("src", [])
            if isinstance(comment_likes, list):
                for like_payload in comment_likes:
                    if not isinstance(like_payload, dict):
                        continue

                    like_id = (like_payload.get("id") or "").rstrip("/")
                    like_author_data = like_payload.get("author", {})
                    like_author_api_url = (like_author_data.get("id") or "").rstrip("/")
                    if not like_id or not like_author_api_url:
                        continue

                    liker, _ = Author.objects.get_or_create(
                        api_url=like_author_api_url,
                        defaults={
                            "url": like_author_data.get("web", like_author_api_url),
                            "host": like_author_data.get("host", ""),
                            "displayName": like_author_data.get("displayName", "Unknown"),
                            "github": like_author_data.get("github", ""),
                            "profileImage": like_author_data.get("profileImage", ""),
                        },
                    )
                    Inbox.objects.get_or_create(author=liker)

                    Like.objects.get_or_create(
                        api_url=like_id,
                        defaults={
                            "author": liker,
                            "comment": saved_comment,
                        },
                    )

            return JsonResponse({"message": "Comment saved"}, status=200)
        except Exception as e:
            return JsonResponse({"error": f"Incorrect comment json: {e}"}, status=400)
            
    return JsonResponse({"error": "Unsupported type or missing data"}, status=400)