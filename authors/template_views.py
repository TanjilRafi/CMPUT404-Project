# ────────────────────────────────────────────────────────────────
# Imports
# ────────────────────────────────────────────────────────────────
from django.shortcuts import render, get_object_or_404, redirect
from .models import Author, Post, Inbox, Entry, Comment, Like
from .forms import AuthorForm
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
from .serializers import AuthorSerializer, PostCreateSerializer, PostSerializer, EntrySerializer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from drf_spectacular.types import OpenApiTypes

from .helpers import helper_post_detail, push_post_to_remote # all other functions that are not views

# ────────────────────────────────────────────────────────────────
# HTML / Browser views (non-API)
# ────────────────────────────────────────────────────────────────
def author_profile(request, id):
    """
    Displays a single author's public profile page.
     - Retrieves the Author object based on the provided ID.
     - Renders the 'authors/profile.html' template with the author's information.
     - If the author does not exist, returns a 404 error.

    Every author in a distributed social network must have a stable, publicly accessible identity page.
    This page allows other users and nodes to view author information using their permanent UUID-based URL.
    Using UUID ensures identity consistency across nodes, prevents identity conflicts, and the author's identity can be reliably accessed, shared, and referenced even if display names change.  
    """
    author = get_object_or_404(Author, id=id)

    # Calculate relationship counts (US 06.08: node tracks and displays relationships)
    following_count = author.following.count()
    followers_count = author.followers.count()
    friends_count = author.friends.count() if request.user.is_authenticated and hasattr(request.user, 'author') and request.user.author == author else 0

    # Common context (shared between owner and non-owner views)
    context = {
        'author': author,
        'following_count': following_count,
        'followers_count': followers_count,
        'friends_count': friends_count,  # Will be 0 for non-owners -> hides in template
        'is_user': False,  # Default: override below if needed
    }

    if request.user.is_authenticated and hasattr(request.user, "author") and request.user.author==author:
        # User's own profile (full access)
        posts = Post.objects.filter(author=author, is_deleted=False).order_by('-created_at')
        context['posts'] = posts
        context['is_user'] = True

        return render(request, 'authors/profile.html', context)
    
    else: 
    # fixed the crash for unauthenticated users by adding an additional check for authentication before trying to access 
    # request.user.author; now unauthenticated users can view the public profile page without crashing
        # Public / other user's profile
        public_posts  = (Post.objects.filter(
                                            is_deleted=False,
                                            visibility=Post.Visibility.PUBLIC,
                                            author_id__exact=author.id))
        if request.user.is_authenticated and hasattr(request.user, 'author'):
            # logged-in user viewing someone else
            inbox_posts = request.user.author.inbox.posts.filter(is_deleted=False, author_id__exact=author.id)
            posts = public_posts.union(inbox_posts).order_by('-created_at')
            authenticated = True

            if request.user.author.following.filter(id=author.id).exists() or request.user.author.friends.filter(id=author.id).exists():
                following_status = "FOLLOWING"
            elif author.inbox.incoming_follow_requests.filter(id=request.user.author.id).exists():
                following_status = "REQUESTED"
            else:
                following_status = "NOT FOLLOWING"
        else:
            # not logged in
            posts = public_posts.order_by('-created_at')
            authenticated = False
            following_status = "NOT FOLLOWING"
        
        context['posts'] = posts
        context['authenticated'] = authenticated
        context['following_status'] = following_status

        return render(request, 'authors/profile.html', context)


def authors_list(request):
    """
    Displays a list of all authors hosted on THIS node.

    This fulfills the requirement that a node must be able to host multiple authors.

    In a distributed social network, each node acts as a server responsible for managing its own authors.
    This view proves that our node can store, manage, and present multiple independent author identities.

    This list also becomes the foundation for future features like:
    - discovering authors
    - following authors
    - browsing profiles
    - federation with other nodes

    Without this, the node would only support a single user, which violates the distributed social network model.
    """
    # Retrieve all authors stored in THIS node's database.
    authors = Author.objects.all()

    return render(request, 'authors/authors_list.html', {
        'authors': authors
    })

@login_required
def edit_profile(request, id):
    """
    Allows an author to edit their profile information.

    Authors must be able to update their identity metadata while preserving their permanent identity.

    This view ensures:
    - Editable fields can be updated
    - Permanent identity fields remain unchanged
    - Changes persist in the database
    """
    author = get_object_or_404(Author, id=id)

    # Ensure the logged-in user matches the author
    if request.user.pk != author.user.pk:
        return HttpResponseForbidden("You cannot edit another author's profile.")

    if request.method == 'POST':

        # This safely applies submitted changes while ensuring only allowed fields are modified.
        form = AuthorForm(request.POST, instance=author)

        if form.is_valid():

            # Saves updated profile data without affecting permanent identity.
            form.save()

            # Redirect prevents duplicate submissions & confirms update success.
            return redirect('author_profile', id=author.id)

    else:

        # Pre-populates form with current author data so user can edit existing values.
        form = AuthorForm(instance=author)

    return render(request, 'authors/edit_profile.html', {
        'form': form,
        'author': author,
    })

@login_required
def manage_profile(request, id):
    """
    Provides a browser-based profile management interface.

    Authors must be able to manage their identity using normal web pages, not backend admin tools or APIs.

    This view serves as the central hub where authors can:
    - View their identity info
    - Navigate to edit their profile
    - Manage their presence on the node
    """
    author = get_object_or_404(Author, id=id)

    # Ensure the logged-in user matches the author
    if request.user.pk != author.user.pk:
        return HttpResponseForbidden("You cannot manage another author's profile.")

    return render(request, 'authors/manage_profile.html', {
        'author': author
    })

def signup(request):
    """
    Provides browser-based signup interface.

    New users are created but marked inactive (is_active=False) until approved by admin to prevent spam/unwanted users (US 08.03).
    After approval, the user can log in and use the node.
    An admin must approve the account via the admin panel.
    """
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False) # don't save yet
            user.is_active = False # prevent login until admin approval
            user.save()

            # Construct host URL for author identity
            host = request.scheme + "://" + request.get_host() + "/api/"

            # Create author profile
            author = Author.objects.create(displayName=user.username, user=user, host=host)

            # Every author must have an inbox for federation
            Inbox.objects.create(author=author) 
            # login(request, user)
            # return redirect('home')

            # Don't log in yet; user must wait for approval
            return render(request, 'registration/signup_pending.html', {
                'message': 'Account created! Waiting for admin approval.'
            })
        else:
            return render(request, 'registration/signup.html', {'form': form})
    # elif request.method == 'GET':
    # GET request - show empty form
    form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

def home(request):
    """
    Displays the with newest posts first.
    Posts are populated based on visibility to user. Allows unauthenticated users to view public posts.
    The stream is the primary content consumption interface in a social network.
    Authors expect to see the most recent content first so they can stay up-to-date.

    This view aggregates posts visible to the logged-in author and sorts them newest-first using created_at descending order.

    Key responsibilities:
    - Prevent deleted posts from appearing (data integrity)
    - Enforce visibility rules (security and privacy)
    - Sort newest-first
    - Render posts in browser-accessible format (not API)
    """
    
    # check if user is authenticated and if the user has an author (admin superusers created with cmd do not have author objects)
    if request.user.is_authenticated and hasattr(request.user, "author"):
        # select public posts and posts that arrived in inbox
        # filter(is_deleted=False): deleted posts must never appear in the stream unless explicitly requested by admins, to preserve expected social network behavior & prevent showing "ghost" posts
        # order_by('-created_at'): minus sign sorts descending, ensuring newest posts appear 1st  
        current_author = request.user.author
        
        posts  = (Post.objects.filter(is_deleted=False).filter(visibility=Post.Visibility.PUBLIC).exclude(author_id__exact=current_author.id) | current_author.inbox.posts.all()).distinct().order_by('-created_at')
    else:
        # select public posts that aren't deleted and order them by descending created_at
        posts = Post.objects.filter(is_deleted=False).filter(visibility=Post.Visibility.PUBLIC).order_by('-created_at')

    # Markdown rendering: posts stored as CommonMark must be converted to HTML before display, otherwise users would see raw markdown syntax instead of formatted content
    md = MarkdownIt('commonmark', {'breaks': True, 'html': True})

    for p in posts:
        if p.type == Post.Type.COMMONMARK:
            p.content = md.render(p.content)

    # separate template because the stream is conceptually different from viewing posts of 1 author; it aggregates posts from multiple authors & represents a timeline
    return render(request, 'home.html', {
        'posts': posts,
        'user': request.user
    })

@login_required
def follow_requests(request):
    user_author = request.user.author 
    if request.method == "GET":
        return render(request, 'requests.html', {"follow_requests": user_author.inbox.incoming_follow_requests.all()})
    elif request.method == "POST":
        request_author = Author.objects.get(id=request.POST["id"])


        if request.POST["action"] == "accept":
            if request_author in user_author.following.all():
                user_author.following.remove(request_author)
                user_author.friends.add(request_author)

                # Add friend's unlisted and friends posts to inbox if not already present
                friend_posts = user_author.posts.filter(is_deleted=False, visibility=Post.Visibility.FRIENDS)
                posts = friend_posts.union(user_author.posts.filter(is_deleted=False, visibility=Post.Visibility.UNLISTED))

                for post in posts:
                    if post not in request_author.inbox.posts.all():
                        request_author.inbox.posts.add(post)

                # Since the users are both friends now, existing posts must also be sent to user's inbox
                friend_posts = request_author.posts.filter(is_deleted=False, visibility=Post.Visibility.FRIENDS)
                posts = friend_posts.union(request_author.posts.filter(is_deleted=False, visibility=Post.Visibility.UNLISTED))

                for post in posts:
                    if post not in user_author.inbox.posts.all():
                        user_author.inbox.posts.add(post)

            else:   # request author becomes a follower and can view unlisted posts
                user_author.followers.add(request_author)

                # Add their unlisted posts to request_author inbox if not already present
                unlisted_posts = user_author.posts.filter(is_deleted=False, visibility=Post.Visibility.UNLISTED)
                
                for post in unlisted_posts:
                    if post not in request_author.inbox.posts.all():
                        request_author.inbox.posts.add(post)


        user_author.inbox.incoming_follow_requests.remove(request_author)
        user_author.save()
        return render(request, 'requests.html', {"follow_requests": user_author.inbox.incoming_follow_requests.all()})
    
@login_required
@require_http_methods(["POST"])
def follow(request, id):
    if request.method == "POST":
        actor = request.user.author
        recipient = get_object_or_404(Author, id=id)
        recipient.inbox.incoming_follow_requests.add(actor)
        # actor.following.add(recipient)
        # actor.save()

        recipient.save()
        return redirect('author_profile', id=recipient.id)

@login_required
@require_http_methods(["POST"])
def unfollow(request, id):
    if request.method == "POST":
        actor = request.user.author
        other = get_object_or_404(Author, id=id)

        if actor.friends.filter(id=other.id).exists():
            actor.friends.remove(other)
            actor.followers.add(other)

            # Remove other's friends-only posts from actor inbox
            posts_to_remove = actor.inbox.posts.filter(author=other, visibility=Post.Visibility.FRIENDS)
            for post in posts_to_remove:
                actor.inbox.posts.remove(post)

            # Remove actor's friends-only posts from other inbox
            posts_to_remove = other.inbox.posts.filter(author=actor, visibility=Post.Visibility.FRIENDS)
            for post in posts_to_remove:
                other.inbox.posts.remove(post)
                

        elif actor.following.filter(id=other.id).exists():      # following, not friends
            actor.following.remove(other)

            # Just following so remove unlisted posts only
            posts_to_remove = actor.inbox.posts.filter(author=other, visibility=Post.Visibility.UNLISTED)
            for post in posts_to_remove:
                actor.inbox.posts.remove(post)

        else:
            raise Http404()
        
        actor.save()
        other.save()
        return redirect('author_profile', id=other.id)

# Views for posts
@login_required
def create_post(request, id):
    """
    Allows authors to create posts. Must include the title and content. Add set visibility options
    """
    author = get_object_or_404(Author, id=id)

    # Ensure the logged-in user matches the author
    if request.user.pk != author.user.pk:
        return HttpResponseForbidden("You cannot create a post for another author.")
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        type = request.POST.get('type')
        if type == Post.Type.TEXT:
            content = request.POST.get('content', '').strip()
            content_type = "text/plain"
        elif type == Post.Type.COMMONMARK:
            content = request.POST.get('content', '').strip()
            content_type = "text/markdown"
        else:
            # https://stackoverflow.com/questions/18747730/storing-images-in-db-using-django-models
            # https://www.geeksforgeeks.org/python/python-convert-image-to-string-and-vice-versa/
            # https://tutorialreference.com/python/examples/faq/python-how-to-convert-image-to-base64-string-and-viceversa 
            content_type = request.FILES['img'].content_type
            content = base64.b64encode(request.FILES['img'].read()).decode('utf-8')
            
        visibility = request.POST.get('visibility')

        # basic validation
        if title and content:
            post = Post.objects.create(author=author, title=title, type=type, content=content, content_type=content_type, visibility=visibility)
            push_post_to_remote(post, author) # for remote
            # send to inbox
            if visibility == Post.Visibility.UNLISTED:
                for follower in author.followers.all() | author.friends.all():
                    follower.inbox.posts.add(post)
            if visibility == Post.Visibility.FRIENDS:
                for friend in author.friends.all():
                    friend.inbox.posts.add(post)

            return redirect('post_detail', author.id, post.id)
        
    return render(request, 'posts/create_post.html', {'author': author, 'visibility_choices': Post.Visibility.choices, 'type_choices': Post.Type.choices})


# We will likely need a section of this to be authenticated for logins. As a team, we should decide if this is a public page of posts and if it is, create a sep page for friends only, all, etc. Can filter posts by visibility.
@require_http_methods(["GET"])
def post_list(request, id): 
    """
    Allows an author to view a list of their non-deleted posts.
    """
    author = get_object_or_404(Author, id=id)
    if request.user == author.user:
        posts = Post.objects.filter(author=author, is_deleted=False).order_by('-created_at')
    else:
        posts = Post.objects.filter(author=author, is_deleted=False, visibility=Post.Visibility.PUBLIC).order_by('-created_at') # Add selection for folower when implemented
    md = MarkdownIt('commonmark', {'breaks':True,'html':True})
    for p in posts:
        if p.type == Post.Type.COMMONMARK:
            p.content = md.render(p.content)
    return render(request, 'posts/post_list.html', {'author': author, 'posts': posts})


@login_required
def edit_post(request, id, post_id):
    """
    Allows the author to edit their post. Authenticates the correct user has logged in.
    Author can change visibility when editing.
    """
    author = get_object_or_404(Author, id=id)
    post = get_object_or_404(Post, id=post_id, author=author)

    # Ensure logged-in user matches author
    if request.user.pk != author.user.pk:
        return HttpResponseForbidden("You cannot edit a post for another author.")

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        type = request.POST.get('type')
        if type == Post.Type.TEXT:
            content = request.POST.get('content', '').strip()
            content_type = "text/plain"
        elif type == Post.Type.COMMONMARK:
            content = request.POST.get('content', '').strip()
            content_type = "text/markdown"
        elif type == Post.Type.IMAGE:
            if request.FILES:
                content_type = request.FILES['img'].content_type
                content = base64.b64encode(request.FILES['img'].read()).decode('utf-8')
            elif type == post.type:
                content_type = post.content_type
                content = post.content
            else: 
                content = None
        new_visibility = request.POST.get('visibility', post.visibility)

        if title and content:
            old_visibility = post.visibility
            post.title = title
            post.type = type
            post.content = content
            post.content_type = content_type
            post.visibility = new_visibility
            post.save()
            push_post_to_remote(post, author)

            # Remove from inboxes if visibility is restricted
            if old_visibility != new_visibility:
                # Remove from all inboxes first
                for user in Author.objects.all():
                    if post in user.inbox.posts.all():
                        user.inbox.posts.remove(post)

            # Add to inboxes based on new visibility
            if new_visibility == Post.Visibility.UNLISTED:
                for follower in author.followers.all() | author.friends.all():
                    follower.inbox.posts.add(post)
            elif new_visibility == Post.Visibility.FRIENDS:
                for friend in author.friends.all():
                    friend.inbox.posts.add(post)

            return redirect('post_detail', author.id, post.id)

    return render(request, 'posts/edit_post.html', {'author': author, 'post': post, 'visibility_choices': Post.Visibility.choices, "type_choices": Post.Type.choices})


@login_required
def delete_post(request, id, post_id):
    """
    Allows the author to delete their post. Authenticates login.
    """
    author = get_object_or_404(Author, id=id)
    post = get_object_or_404(Post, id=post_id, author=author)

    # Ensure logged-in user matches author
    if request.user.pk != author.user.pk:
        return HttpResponseForbidden("You cannot delete a post for another author.")

    if request.method == 'POST':
        post.is_deleted = True      # maintains the deleted entry in the database, but no longer shown on posts list
        post.save()

        # Remove from all inboxes
        for user in Author.objects.all():
            if post in user.inbox.posts.all():
                user.inbox.posts.remove(post)
            
        return redirect('post_list', id=author.id)

    return render(request, 'posts/delete_post.html', {'author': author, 'post': post})

def post_detail(request, id, post_id):
    """
    Displays a single post's detail page based on its visibility settings.
    """
    author = get_object_or_404(Author, id=id)
    post = get_object_or_404(Post, id=post_id, author=author)

    # Markdown rendering: posts stored as CommonMark must be converted to HTML before display, otherwise users would see raw markdown syntax instead of formatted content
    md = MarkdownIt('commonmark', {'breaks': True, 'html': True})

    if post.type == Post.Type.COMMONMARK:
        post.content = md.render(post.content)

    # deleted posts are only visible to node admins (is_admin)
    if post.is_deleted:
        if not (request.user.is_authenticated and request.user.is_admin):
            raise Http404("Post not found.")
        return render(request, 'posts/post_detail.html', helper_post_detail(request, author, post))
    
    if request.user.is_authenticated:
        try:
            if request.user.author == author:
                return render(request, 'posts/post_detail.html', helper_post_detail(request, author, post))
        except Author.DoesNotExist:
            pass
            
    if post.visibility == Post.Visibility.PUBLIC:
        return render(request, 'posts/post_detail.html', helper_post_detail(request, author, post))
    
    # no login required to access the unlisted link
    if post.visibility == Post.Visibility.UNLISTED:
        return render(request, 'posts/post_detail.html', helper_post_detail(request, author, post))
    
    # user must be a friend to access FRIENDS posts
    if post.visibility == Post.Visibility.FRIENDS:
        if request.user.is_authenticated and request.user.author in author.friends.all():
            return render(request, 'posts/post_detail.html', helper_post_detail(request, author, post))
        raise Http404("Post not found. Not a friend of this user.")

    return render(request, 'posts/post_detail.html', helper_post_detail(request, author, post))

@login_required
def stream(request):
    """
    Displays the authenticated author's stream with newest posts first.
    The stream is the primary content consumption interface in a social network.
    Authors expect to see the most recent content first so they can stay up-to-date.

    This view aggregates posts visible to the logged-in author and sorts them newest-first using created_at descending order.

    Key responsibilities:
    - Prevent deleted posts from appearing (data integrity)
    - Enforce visibility rules (security and privacy)
    - Sort newest-first
    - Render posts in browser-accessible format (not API)
    """

    # Logged-in user is guaranteed to exist because of @login_required; used to determine what content they are allowed to see
    current_author = request.user.author

    # filter(is_deleted=False): deleted posts must never appear in the stream unless explicitly requested by admins, to preserve expected social network behavior & prevent showing "ghost" posts
    # order_by('-created_at'): minus sign sorts descending, ensuring newest posts appear 1st
    posts = Post.objects.filter(
        is_deleted=False
    ).filter(
        visibility=Post.Visibility.PUBLIC
    ).order_by('-created_at')

    # Markdown rendering: posts stored as CommonMark must be converted to HTML before display, otherwise users would see raw markdown syntax instead of formatted content
    md = MarkdownIt('commonmark', {'breaks': True, 'html': True})

    for p in posts:
        if p.type == Post.Type.COMMONMARK:
            p.content = md.render(p.content)

    # separate template because the stream is conceptually different from viewing posts of 1 author; it aggregates posts from multiple authors & represents a timeline
    return render(request, 'streams/stream.html', {
        'posts': posts,
        'current_author': current_author
    })

@login_required
def my_followers(request, id=None):
    """
    US 06.08: Display list of authors following me (followers).
    Node tracks followers so author doesn't have to.
    - If id is provided: show the target author's public followers list.
    - If no id: show the logged-in user's own followers (accessed via /my-followers/).
    """
    if id:
        # Viewing someone else's followers
        author = get_object_or_404(Author, id=id)
        title = f"{author.displayName}'s Followers"
    else:
        # Viewing own followers
        author = request.user.author
        title = "My Followers"

    followers = author.followers.all()
    print(f"Followers for {author.displayName}: {followers.count()}")  # add this line
    return render(request, 'authors/followers.html', {
        'followers': followers,
        'title': title,
        'author': author,  # Pass author so template can use displayName if needed
    })

@login_required
def my_following(request, id=None):
    """
    US 06.08: Display list of authors I am following.
    Node tracks following list automatically.
    - If id provided: show target author's following list (public).
    - No id: show logged-in user's own following (via /my-following/).
    """
    if id:
        author = get_object_or_404(Author, id=id)
        title = f"{author.displayName}'s Following"
    else:
        author = request.user.author
        title = "My Following"

    following = author.following.all()
    return render(request, 'authors/following.html', {
        'following': following,
        'title': title,
        'author': author,
    })

@login_required
def my_friends(request, id=None):
    """
    US 06.08: Display list of my friends (mutual follow).
    Node maintains friends list for visibility rules.
    - Only accessible for the logged-in user (no public id param).
    - Friends are private -> redirect or 404 if id provided.
    """
    if id:
        # Friends are private -> deny access to others' friends list
        return render(request, 'authors/error.html', {'message': 'Friends list is private.'}, status=403)

    author = request.user.author
    title = "My Friends"
    friends = author.friends.all()

    return render(request, 'authors/friends.html', {
        'friends': friends,
        'title': title,
        'author': author,
    })