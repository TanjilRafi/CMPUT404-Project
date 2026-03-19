from django.urls import path
from . import template_views
from . import api_views
from django.contrib.auth import views as auth_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [

    # Authors list page URL pattern: this endpoint allows access to the list of all authors hosted on THIS node, demonstrating that the node can manage multiple authors.
    path('authors/', template_views.authors_list, name='authors_list'),

    # Author profile page URL pattern: this endpoint provides permanent, predictable identity URLs for individual authors, ensuring consistency.
    path('authors/<uuid:id>/', template_views.author_profile, name='author_profile'),

    # Editing author profile URL pattern: this endpoint allows authors to update their editable identity metadata while preserving their permanent identity fields.
    path('authors/<uuid:id>/edit/', template_views.edit_profile, name='edit_profile'),

    # Manage profile URL pattern: this endpoint provides a dedicated interface for authors to manage their profile info, ensuring that identity management is user-friendly & browser-accessible.
    path('authors/<uuid:id>/manage/', template_views.manage_profile, name='manage_profile'),

    # Posts list page URL pattern
    path('authors/<uuid:id>/posts/', template_views.post_list, name='post_list'),

    # Creating post URL pattern
    path('authors/<uuid:id>/posts/create/', template_views.create_post, name='create_post'),

    # Editing post URL pattern
    path('authors/<uuid:id>/posts/<uuid:post_id>/edit/', template_views.edit_post, name='edit_post'),

    # Deleting post URL pattern
    path('authors/<uuid:id>/posts/<uuid:post_id>/delete/', template_views.delete_post, name='delete_post'),
    
    # Unlisted posts for people with this direct link URL pattern
    path('authors/<uuid:id>/posts/<uuid:post_id>/', template_views.post_detail, name='post_detail'),

    path('follow_requests', template_views.follow_requests, name='follow_requests'),

    path('authors/<uuid:id>/follow', template_views.follow, name='follow'),

    path('authors/<uuid:id>/unfollow', template_views.unfollow, name='unfollow'),

    path('signup', template_views.signup, name='signup'),

    path('login',  auth_views.LoginView.as_view(next_page='home'), name='login'),

    path('logout', auth_views.LogoutView.as_view(next_page='home'), name='logout'),

    path('', template_views.home, name='home'),

    # ────────────────────────────────────────────────────────────────
    # Relationship list views (US 06.08: display tracked relationships)
    # ────────────────────────────────────────────────────────────────
    # Own relationships – only accessible when logged in (my- prefix)
    path('my-followers/', template_views.my_followers, name='my_followers'),
    path('my-following/', template_views.my_following, name='my_following'),
    path('my-friends/',    template_views.my_friends,    name='my_friends'),

    # Public view of another author's followers / following (no friends)
    path('followers/<uuid:id>/', template_views.my_followers, name='followers'),
    path('following/<uuid:id>/', template_views.my_following, name='following'),
    # No public path for friends, keep it private to owner only
    
    # ────────────────────────────────────────────────────────────────
    # API Endpoints
    # ───────────────────────────────────────────────────────────────
    path('api/authors/', api_views.api_authors_list, name='api_authors_list'),
    
    # GET single author
    path('api/authors/<uuid:id>/', api_views.api_author_profile, name='api_author_profile'),

    # POST create new entries
    path('api/authors/<uuid:id>/entries/', api_views.api_entries, name='api_entries'),

    # PUT + DELETE for RESTful practice
    path('api/authors/<uuid:id>/entries/<uuid:post_id>/', api_views.api_entry_detail, name='api_entry_detail'),

    # GET, PUT, DELETE to handle following
    path('api/authors/<uuid:id>/following/<path:fqid>', api_views.api_following, name='api_following'),

    # GET, PUT, DELETE to handle followers
    path('api/authors/<uuid:id>/followers/<path:fqid>', api_views.api_followers, name='api_followers'),

    # GET list of following
    path('api/authors/<uuid:id>/following/', api_views.api_following_list, name='api_following_list'),

    # Get list of followers
    path('api/authors/<uuid:id>/followers/', api_views.api_followers_list, name='api_followers_list'),

    # POST inbox
    path('api/authors/<uuid:id>/inbox', api_views.api_inbox, name='api_inbox'),

    # GET image entry file
    path('api/authors/<uuid:id>/entries/<uuid:post_id>/image', api_views.entry_image, name='api_entry_image'),

    # GET image entry file fqid ver.
    path('api/entries/<path:fqid>/image', api_views.entry_image_fqid, name='api_entry_image_fqid'),

    # Comments API
    path('api/authors/<uuid:author_id>/entries/<uuid:post_id>/comments/', api_views.api_entry_comments, name='api_entry_comments'),
    # Comment API (FQID)
    path('api/entries/<path:fqid>/comments', api_views.api_entry_comments_fqid, name='api_entry_comments_fqid'),
    path('api/entries/<path:fqid>/comments/', api_views.api_entry_comments_fqid),
    path('api/authors/<uuid:author_id>/entries/<uuid:post_id>/comments/<path:comment_fqid>/', api_views.api_entry_comment_detail_fqid, name='api_entry_comment_detail_fqid'),

    # Commented API
    path('api/authors/<uuid:author_id>/commented/', api_views.api_author_commented, name='api_author_commented'),
    path('api/authors/<uuid:author_id>/commented/<uuid:comment_id>/', api_views.api_author_commented_detail, name='api_author_commented_detail'),
    path('api/commented/<path:comment_fqid>/', api_views.api_commented_detail_fqid, name='api_commented_detail_fqid'),

    # Streams
    path('stream/', template_views.stream, name='stream'),

    # GET stream of posts visible to this author
    path("api/authors/<uuid:author_id>/stream", api_views.api_author_stream, name="api_author_stream"),
    # path("api/authors/<uuid:author_id>/stream", views.api_author_stream, name="api_author_stream_noslash"),

    # GET list of follow requests
    path("api/authors/<uuid:author_id>/follow_requests/", api_views.api_follow_requests, name="api_follow_requests"),
    
    # POST to toggle like on a post
    path('authors/<uuid:author_id>/posts/<uuid:post_id>/like/', api_views.like_post, name='like_post'),

    # POST to comment on a post
    path('authors/<uuid:author_id>/posts/<uuid:post_id>/comment/', api_views.post_comment, name='post_comment'),

    # POST to toggle like on a comment
    path('authors/<uuid:author_id>/posts/<uuid:post_id>/comments/<uuid:comment_id>/like/', api_views.like_comment, name='like_comment'),

    # Likes API
    path('api/authors/<uuid:id>/entries/<uuid:post_id>/likes/', api_views.api_entry_likes, name='api_entry_likes'),
    path('api/entries/<path:fqid>/likes', api_views.api_entry_likes_fqid, name='api_entry_likes_fqid'),
    path('api/entries/<path:fqid>/likes/', api_views.api_entry_likes_fqid),
    
    # Liked API
    path('api/authors/<uuid:id>/liked/', api_views.api_author_liked, name='api_author_liked'),
    path('api/authors/<uuid:id>/liked/<str:like_serial>/', api_views.api_author_liked, name='api_like_serial'),
    path('api/authors/<path:fqid>/liked', api_views.api_author_liked_fqid, name='api_author_liked_fqid'),
    path('api/authors/<path:fqid>/liked/', api_views.api_author_liked_fqid),
    path('api/liked/<path:fqid>',api_views.api_single_like, name='api_single_like'),
    
    # Comment Likes
    # path('api/authors/<uuid:id>/entries/<uuid:post_id>/comments/<path:comment_id>/likes', views.api_comment_likes, name='api_comment_likes'),


    # swagger documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
