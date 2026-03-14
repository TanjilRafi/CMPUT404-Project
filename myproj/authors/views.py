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

import base64 # to handle images
import urllib.parse
import requests

# for api views
import json
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
            inbox_posts = request.user.author.inbox.posts.filter(is_deleted=False)
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
    if request.user != author.user:
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
    if request.user != author.user:
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
    if request.user != author.user:
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
    if request.user != author.user:
        return HttpResponseForbidden("You cannot edit a post for another author.")

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        new_visibility = request.POST.get('visibility', post.visibility)

        if post.type == Post.Type.IMAGE:
            image = request.FILES['img']
            content_type = image.content_type
            content = base64.b64encode(image.read()).decode('utf-8')
        else:
            content_type = post.content_type

        if title and content:
            old_visibility = post.visibility
            post.title = title
            post.content = content
            post.content_type = content_type
            post.visibility = new_visibility
            post.save()

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

    return render(request, 'posts/edit_post.html', {'author': author, 'post': post, 'visibility_choices': Post.Visibility.choices})


@login_required
def delete_post(request, id, post_id):
    """
    Allows the author to delete their post. Authenticates login.
    """
    author = get_object_or_404(Author, id=id)
    post = get_object_or_404(Post, id=post_id, author=author)

    # Ensure logged-in user matches author
    if request.user != author.user:
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

# ────────────────────────────────────────────────────────────────
# API views
# ────────────────────────────────────────────────────────────────

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
    return JsonResponse({"type": "authors", "authors": serializer.data}, status=200)





""" TODO: Will need to change/remove these to follow specs: START """


@api_view(["GET", "POST"])
def api_author_posts(request, id):
    author = get_object_or_404(Author, id=id)

    if request.method == "GET":
        # tests expect {"items": [...]}
        posts = (
            Post.objects.filter(author=author, is_deleted=False)
            .exclude(visibility=Post.Visibility.UNLISTED)
            .order_by("-created_at")
        )
        return Response({"type": "posts", "items": PostSerializer(posts, many=True).data}, status=200)

    if not request.user.is_authenticated or author.user_id != request.user.id:
        return Response({"detail": "Forbidden"}, status=403)

    serializer = PostCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    post = serializer.save(author=author)
    return Response(PostSerializer(post).data, status=201)

@api_view(["GET", "PUT", "DELETE"])
def api_post_detail(request, id, post_id):
    author = get_object_or_404(Author, id=id)
    post = get_object_or_404(Post, id=post_id, author=author)

    # Deleted posts visible only to admins
    if post.is_deleted and not (request.user.is_authenticated and request.user.is_staff):
        return Response({"detail": "Not found"}, status=404)

    if request.method == "GET":
        return Response(PostSerializer(post).data, status=200)

    # PUT/DELETE must be owner
    if not request.user.is_authenticated or author.user_id != request.user.id:
        return Response({"detail": "Forbidden"}, status=403)

    if request.method == "PUT":
        serializer = PostCreateSerializer(post, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(PostSerializer(post).data, status=200)

    # DELETE = soft delete
    post.is_deleted = True
    post.save(update_fields=["is_deleted"])
    return Response(status=204)


""" TODO: Will need to change/remove these to follow specs: END """






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
        if not request.user.is_authenticated or request.user != author.user:
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
            response=PostSerializer(many=True),
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
    request=PostCreateSerializer,
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
@api_view(["GET", "POST"])
def api_entries(request, id):
    """
    GET  /api/authors/{id}/entries/ — list entries
    POST /api/authors/{id}/entries/ — create entry
    """
    author = get_object_or_404(Author, id=id)

    if request.method == "GET":
        if request.user.is_authenticated and hasattr(request.user, 'author'):
            if request.user == author.user:
                posts = Post.objects.filter(author=author, is_deleted=False).order_by('-created_at')
            elif request.user.author in author.friends.all():
                posts = Post.objects.filter(author=author, is_deleted=False).order_by('-created_at')
            elif request.user.author in author.followers.all():
                posts = Post.objects.filter(
                    author=author,
                    is_deleted=False,
                    visibility__in=[Post.Visibility.PUBLIC, Post.Visibility.UNLISTED]
                ).order_by('-created_at')
            else:
                posts = Post.objects.filter(author=author, is_deleted=False, visibility=Post.Visibility.PUBLIC).order_by('-created_at')
        else:
            posts = Post.objects.filter(author=author, is_deleted=False, visibility=Post.Visibility.PUBLIC).order_by('-created_at')

        try:
            page = int(request.GET.get('page', 1))
            size = int(request.GET.get('size', 10))
        except ValueError:
            return JsonResponse({"error": "Invalid page or size"}, status=400)

        start = (page - 1) * size
        end = start + size
        posts = posts[start:end]

        data = {
            "type": "entries",
            "entries": [
                {
                    "type": "entry",
                    # fixed, it was str(p.id) — now returns full API URL to match spec format
                    "id": f"{author.host}authors/{author.id}/entries/{p.id}",
                    "title": p.title,
                    "content": p.content,
                    "contentType": p.content_type,
                    "visibility": p.visibility,
                    "author": f"{author.host}authors/{author.id}",
                    "created_at": p.created_at.isoformat(),
                }
                for p in posts
            ]
        }
        return JsonResponse(data)

    elif request.method == "POST":
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        visibility = request.POST.get('visibility', Post.Visibility.PUBLIC)
        post_type = request.POST.get('type', Post.Type.TEXT)

        if not title or not content:
            return JsonResponse({"error": "Missing fields"}, status=400)

        post = Post.objects.create(
            author=author,
            title=title,
            content=content,
            visibility=visibility,
            type=post_type,
            content_type="text/plain"
        )

        return JsonResponse({"message": "Entry created", "id": str(post.id)}, status=201)


@extend_schema(
    methods=["GET"],
    summary="Get a specific entry",
    description="""Retrieves full details of a single entry.
    Visibility rules apply: FRIENDS entries only visible to friends, UNLISTED to anyone with the link.

    Pagination: Not applicable — single entry.
    """,
    responses={
        200: OpenApiResponse(
            response=PostSerializer,
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
@api_view(["GET", "PUT", "DELETE"])
def api_entry_detail(request, id, post_id):
    """
    GET    /api/authors/{id}/entries/{post_id}/ — get entry
    PUT    /api/authors/{id}/entries/{post_id}/ — edit entry
    DELETE /api/authors/{id}/entries/{post_id}/ — delete entry
    """
    author = get_object_or_404(Author, id=id)
    post = get_object_or_404(Post, id=post_id, author=author)

    if request.method == "GET":
        if post.is_deleted:
            return JsonResponse({"error": "Entry not found"}, status=404)

        if post.visibility == Post.Visibility.FRIENDS:
            if not request.user.is_authenticated or not hasattr(request.user, 'author') or request.user.author not in author.friends.all():
                return JsonResponse({"error": "Entry not found"}, status=404)

        data = {
            "type": "entry",
            # fixed, same as before, it was str(post.id), now returns full API URL to match spec format
            "id": f"{author.host}authors/{author.id}/entries/{post.id}",
            "title": post.title,
            "content": post.content,
            "contentType": post.content_type,
            "visibility": post.visibility,
            "author": f"{post.author.host}authors/{post.author.id}",
            "created_at": post.created_at.isoformat(),
        }
        return JsonResponse(data)

    elif request.method == "PUT":
        if not request.user.is_authenticated or request.user != author.user:
            return JsonResponse({"error": "Forbidden"}, status=403)
        if post.is_deleted:
            return JsonResponse({"error": "Cannot update a deleted entry"}, status=404)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        post.title = body.get('title', post.title)
        post.content = body.get('content', post.content)
        post.visibility = body.get('visibility', post.visibility)
        post.save()

        return JsonResponse({"message": "Entry updated", "id": str(post.id)})

    elif request.method == "DELETE":
        if not request.user.is_authenticated or request.user != author.user:
            return JsonResponse({"error": "Forbidden"}, status=403)
        if post.is_deleted:
            return JsonResponse({"error": "Cannot update a deleted entry"}, status=404)

        post.is_deleted = True
        post.save()

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
def entry_image(request, id, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.type == Post.Type.IMAGE:
        img = base64.b64decode(post.content.encode('utf-8'))
        return HttpResponse(img, content_type=post.content_type)
    else:
        return JsonResponse("This post doesn't have an image file", status=404)
    
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
def entry_image_fqid(request, fqid):
    api_url = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")
    post = get_object_or_404(Post, api_url=api_url)
    if post.type == Post.Type.IMAGE:
        img = base64.b64decode(post.content.encode('utf-8'))
        return HttpResponse(img, content_type=post.content_type)
    else:
        return JsonResponse("This post doesn't have an image file", status=404)


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

    # Logged-in user is guaranteed to exist because of @login_required; used to determine what content they are allowed to see
    current_author = request.user.author

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


    serializer = PostSerializer(paginated_posts, many=True)

    return JsonResponse({
        "type": "posts",
        "page": page,
        "page_size": size,
        "total_posts": posts.count(),
        "items": serializer.data
    }, status=200)


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
    if request.user != author.user:
        return Response({"error": "Forbidden"}, status=403)

    # Get or create the inbox for the author
    inbox, _ = Inbox.objects.get_or_create(author=author)

    # Loop directly over incoming_follow_requests to match API specs
    follow_requests = []
    for actor in inbox.incoming_follow_requests.all():
        follow_requests.append({
            "type": "follow",
            "summary": f"{actor.displayName} wants to follow {author.displayName}",
            "actor": AuthorSerializer(actor).data,      # serializer already displays full ids
            "object": AuthorSerializer(author).data
        })

    return Response({"type": "follow_requests", "items": follow_requests})

class StreamView(APIView):
    """
    US 08.14: Stream shows all entries the node knows about, 
    but MUST NOT show entries that have been deleted.
    """
    def get(self, request):
        queryset = Entry.objects.exclude(visibility='DELETED').order_by('-published')
    
        serializer = EntrySerializer(queryset, many=True)
        return Response({
            "type": "entries",
            "src": serializer.data
        }, status=status.HTTP_200_OK)
    
class EntryDeleteView(APIView):
    """
    US 08.14: Deleted entries stay in DB but are removed from UI/API.
    """
    def delete(self, request, entry_id):
        try:
            entry = Entry.objects.get(id=entry_id)
            entry.visibility = 'DELETED'
            entry.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Entry.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
@extend_schema(
    summary="Get a list authors that the selected author is following",
    description="""**When to use**: When the author wants a list of authors they are following.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send GET \"/api/authors/<id>/following/<url_encoded_fqid>/\"."""
    ,
    responses={
        200: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Operation successfull", examples=[
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
    },
    examples=[
        OpenApiExample(
            name="get a list of following",
            value="curl -u \"username:password\" -X GET http://127.0.0.1:8000/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/following/",
            request_only=True
        )
    ]
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
    data = []
    for following in following_list:
        data.append({"type":"author",
                     "id":following.api_url,
                     "host": following.host,
                     "displayName":following.displayName,
                     "github": following.github,
                     "profileImage": following.profileImage,
                     "web": following.url})
        
    return JsonResponse(data={"type": "following", "following": data}, status=200)

@extend_schema(
    summary="Get a list of the selected author's followers",
    description="""**When to use**: When the author wants a list of followers.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send GET \"/api/authors/<id>/followers/<url_encoded_fqid>/\"."""
    ,
    responses={
        200: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Operation successfull", examples=[
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
    },
    examples=[
        OpenApiExample(
            name="get a list of followers",
            value="curl -u \"username:password\" -X GET http://127.0.0.1:8000/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/followers/",
            request_only=True
        )
    ]
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
    data = []
    for followers in followers_list:
        data.append({"type":"author",
                     "id":followers.api_url,
                     "host": followers.host,
                     "displayName":followers.displayName,
                     "github": followers.github,
                     "profileImage": followers.profileImage,
                     "web": followers.url})
        
    return JsonResponse(data={"type": "followers", "followers": data}, status=200)

@extend_schema(
    summary="GET: Check if following author, PUT: send follow request, DELETE: unfollow an author",
    description="""**When to use**: When the author wants check, follow (send request), or unfollow another author.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send GET, PUT, or DELETE to \"/api/authors/<id>/following/<url_encoded_fqid>/\"."""
    ,
    responses={
        200: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Operation successfull", examples=[OpenApiExample(
                        name="GET specific author in following",
                        value={"type":"author",
                               "id": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb",
                               "host": "http://darkorchid/api/",
                               "displayName": "Amy",
                               "github": "http://github.com/amy",
                               "profileImage": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/entries/1a083be8-e6ca-458e-a0b0-3abf5e012aec/image",
                               "web": "http://darkorchid/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb"})]),
        400: OpenApiResponse(description="Error with the urlencode fqid"),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="Operation not successfull")
    },
    request=OpenApiTypes.OBJECT, 
    examples=[
        OpenApiExample(
            name="check if following fqid author",
            value="curl -u \"username:password\" -X GET http://127.0.0.1:8000/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/following/http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fauthors%2Ff3e32f7d-2411-47ce-ae4b-3db74103a599%2F",
            request_only=True
        ),
        OpenApiExample(
            name="send a friend request to fqid author",
            value="curl -u \"username:password\" -X PUT http://127.0.0.1:8000/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/following/http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fauthors%2Ff3e32f7d-2411-47ce-ae4b-3db74103a599%2F",
            request_only=True
        ),
        OpenApiExample(
            name="unfollow fqid author",
            value="curl -u \"username:password\" -X DELETE http://127.0.0.1:8000/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/following/http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fauthors%2Ff3e32f7d-2411-47ce-ae4b-3db74103a599%2F",
            request_only=True
        )
    ]
)
@api_view(["GET", "PUT", "DELETE"])
@authentication_classes([SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def api_following(request, id, fqid):
    """
    GET    /api/authors/{id}/following/{url_encoded_fqid} - check if following fqid author
    PUT    /api/authors/{id}/following/{url_encoded_fqid} - send a friend request to fqid author
    DELETE /api/authors/{id}/following/{url_encoded_fqid} - unfollow fqid author
    """
    author = get_object_or_404(Author, id=id)
    if not (hasattr(request.user, "author") and request.user.author==author):
        return JsonResponse({"error": "not authorized"}, status=403)
    
    api_url = urllib.parse.unquote_plus(fqid.rstrip("/")).rstrip("/")

    if request.method == "GET":
        try:
            author_to_check = (author.following.all() | author.friends.all()).get(api_url=api_url)
            return JsonResponse({"type":"author",
                     "id":author_to_check.api_url,
                     "host": author_to_check.host,
                     "displayName":author_to_check.displayName,
                     "github": author_to_check.github,
                     "profileImage": author_to_check.profileImage,
                     "web": author_to_check.url}, status=200)
        except:
            return JsonResponse({"error": "not following fqid author"}, status=404)

    elif request.method == "PUT":
        author_to_add = Author.objects.get(api_url = api_url)
        if urllib.parse.urlparse(api_url).netloc != request.get_host():
            # remote
            data = {"type":"follow", 
                    "actor": {"type":"author",
                              "id":author.api_url,
                              "host": author.host,
                              "displayName":author.displayName,
                              "github": author.github,
                              "profileImage": author.profileImage,
                              "web": author.url},
                    "object": {"type":"author",
                               "id":author_to_add.api_url,
                               "host": author_to_add.host,
                               "displayName":author_to_add.displayName,
                               "github": author_to_add.github,
                               "profileImage": author_to_add.profileImage,
                               "web": author_to_add.url},
                    }
            response = requests.post(f"{author_to_add.api_url}/inbox", data=data, auth=("username", "password")) # TODO change to remote node credential when implemented
            if response.status_code!=200:
                return Response({"error": "Problem with foreign node of fqid author)"}, status=400) 
        else:
            # local
            author_to_add.inbox.incoming_follow_requests.add(author)
        return JsonResponse({"message": "sent follow request to fqid"}, status=200)

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
            return JsonResponse({"message": "fqid author is unfollowed or request revoked"}, status=200)
        except:
            return JsonResponse({"error": "ERROR not following fqid author"}, status=404)

@extend_schema(
    summary="GET: Check if an author in followers, PUT: accept follow request, DELETE: decline follow request/remove follower",
    description="""**When to use**: When the author wants check if another author is a follower, accept follow request, or deny request/remove another author from followers.  
    **Why use it**: Allows the use of third-party ui while communicating with our server.
    **How to use**: Send GET, PUT, or DELETE to \"/api/authors/<id>/followers/<url_encoded_fqid>/\"."""
    ,
    responses={
        200: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Operation successfull", examples=[OpenApiExample(
                        name="GET specific author in followers",
                        value={"type":"author",
                               "id": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb",
                               "host": "http://darkorchid/api/",
                               "displayName": "Amy",
                               "github": "http://github.com/amy",
                               "profileImage": "http://darkorchid/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/entries/1a083be8-e6ca-458e-a0b0-3abf5e012aec/image",
                               "web": "http://darkorchid/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb"})]),
        400: OpenApiResponse(description="Error with the urlencode fqid"),
        403: OpenApiResponse(description="You are not authorized"),
        404: OpenApiResponse(description="Operation not successfull")
    },
    request=OpenApiTypes.OBJECT, 
    examples=[
        OpenApiExample(
            name="check if fqid author is a follower",
            value="curl -u \"username:password\" -X GET http://127.0.0.1:8000/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/following/http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fauthors%2Ff3e32f7d-2411-47ce-ae4b-3db74103a599%2F",
            request_only=True
        ),
        OpenApiExample(
            name="decline fqid author's friend request",
            value="curl -u \"username:password\" -X PUT http://127.0.0.1:8000/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/following/http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fauthors%2Ff3e32f7d-2411-47ce-ae4b-3db74103a599%2F",
            request_only=True
        ),
        OpenApiExample(
            name="remove fqid author from followers",
            value="curl -u \"username:password\" -X DELETE http://127.0.0.1:8000/api/authors/0a083be8-e6ca-458e-a0b0-3abf5e012aeb/following/http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fauthors%2Ff3e32f7d-2411-47ce-ae4b-3db74103a599%2F",
            request_only=True
        )
    ]
)
@api_view(["GET", "PUT", "DELETE"])
@authentication_classes([SessionAuthentication, BasicAuthentication])
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
            return JsonResponse({"type":"author",
                     "id":author_to_check.api_url,
                     "host": author_to_check.host,
                     "displayName":author_to_check.displayName,
                     "github": author_to_check.github,
                     "profileImage": author_to_check.profileImage,
                     "web": author_to_check.url}, status=200)
        except:
            return JsonResponse({"error": "not in followers"}, status=404)

    elif request.method == "PUT":
        if author.inbox.incoming_follow_requests.filter(api_url=api_url).exists():
            author_to_add = Author.objects.get(api_url=api_url)
            author.inbox.incoming_follow_requests.remove(author_to_add)
            if author.following.filter(api_url=api_url).exists():
                author.following.remove(author_to_add)
                author.friends.add(author_to_add)
            else:
                author.followers.add(author_to_add)
            return JsonResponse({"message": "accepted fqid author's request"}, status=200)
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
            return JsonResponse({"message": "removed fqid author form followers and/or request their request"}, status=200)
        except:
            return JsonResponse({"error": "fqid author is not a follower and has not requested"}, status=404)

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
@api_view(["POST"])
@authentication_classes([SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def api_inbox(request, id):
    """
    GET    /api/authors/<id>/inbox - send a post or a follow request
    
    """
    author = get_object_or_404(Author, id=id)
    
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    type = body.get("type")
    actor_json = body.get("actor")
    object_json = body.get("object")

    if type == "follow":
        if author.id!=object_json.get(id):
            return JsonResponse({"error": "Wrong inbox or object"}, status=400)
        try:
            actor, created = Author.objects.get_or_create(url=actor_json.get("web"), api_url=actor_json.get("id"))
            if created:
                actor.host = actor_json.get("host")
                actor.displayName = actor_json.get("displayName")
                actor.github = actor_json.get("github")
                actor.profileImage = actor_json.get("profileImage")
                actor.save()
            author.inbox.incoming_follow_requests.add(actor)
            return JsonResponse({"message": "Friend request added"})
        except:
            return JsonResponse({"error": "Incorrect json"}, status=400)

    if type == "entry":
        try:
            actor = Author.objects.get(url=actor_json.get("web"), api_url=actor_json.get("id"))
            post = Post.objects.get_or_create(author=actor, url=object_json.get("web"), api_url=object_json.get("id"))
            post.title = object_json.get("title")
            post.content = object_json.get("content")
            post.content_type = object_json.get("contentType")
            post.setType()
            post.save()        
            author.inbox.posts.add(post)
            return JsonResponse({"message": "Post saved"})
        except:
            return JsonResponse({"error": "Incorrect json"}, status=400)

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
    