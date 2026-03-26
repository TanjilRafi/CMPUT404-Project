from rest_framework import serializers
from .models import Author, Post, Entry, Like, Comment, Inbox
from drf_spectacular.utils import extend_schema_field, OpenApiTypes
from django.core.paginator import Paginator

class AuthorSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="author", read_only=True)
    id = serializers.SerializerMethodField() # US 08.16: full URL as id (prevents UUID collisions across nodes)
    web = serializers.SerializerMethodField()
    host = serializers.SerializerMethodField()

    class Meta:
        model = Author
        fields = ['type', 'id', 'host', 'displayName', 'github', 'profileImage', 'web']

    @extend_schema_field(OpenApiTypes.STR)
    def get_id(self, obj):
        """
        US 08.16: Return full API as the identifier --> http://node/api/authors/<uuid>
        This ensures no collision if 2 nodes use same UUIDs; uses pre-computed api_url from model save()
        """
        return obj.api_url

    @extend_schema_field(OpenApiTypes.STR)
    def get_web(self, obj):
        """
        Browser-facing HTML profile URL (non-API)
        """
        return obj.url  # assuming obj.url already stores the /authors/<uuid> browser URL
    
    @extend_schema_field(OpenApiTypes.STR)
    def get_host(self, obj):
        """
        Formats (normalized) host to include trailing /api/
        """
        base = obj.host.rstrip("/")     # obj.host is only the node (e.g., http://127.0.0.1:8000/)
        if not base.endswith("/api"):
            base += "/api"
        return base + "/"
    

class AuthorsSerializer(serializers.Serializer):
    type = serializers.CharField(default="authors", read_only=True)
    authors = AuthorSerializer(many=True)


class FollowRequestSerializer(serializers.Serializer):
    type = serializers.CharField(default="follow", read_only=True)
    summary = serializers.SerializerMethodField()
    actor = AuthorSerializer()
    object = AuthorSerializer()

    def get_summary(self, obj):
        actor = obj["actor"]
        target = obj["object"]
        return f"{actor.displayName} wants to follow {target.displayName}"


class LikeSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="like", read_only=True)
    id = serializers.CharField(source="api_url", read_only=True)
    object = serializers.SerializerMethodField()
    author = AuthorSerializer()
    class Meta:
        model = Like
        fields = ["type", "id", "author", "object", "published"]

    def get_object(self, obj):
        if obj.comment:
            return obj.comment.api_url
        elif obj.post:
            return obj.post.api_url
        else:
            return ""

class LikesSerializer(serializers.Serializer):
    # written whith reference to Google Gemini
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    web = serializers.CharField(source="url")
    page_number = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    src = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "likes"

    def get_id(self, obj):
        if isinstance(obj, Author):
            return f"{obj.api_url}/liked"
        elif isinstance(obj, Comment):
            return f"{obj.api_url}/likes"
        elif isinstance(obj, Post):
            return f"{obj.api_url}/likes"
        
    def get_size(self, obj):
        return self.context.get("size", 5)
        
    def get_page_number(self, obj):
        return self.context.get("page_number", 1)

    @extend_schema_field(LikeSerializer(many=True))
    def get_src(self, obj):
        size = getattr(obj, 'size', 5)
        page_number = getattr(obj, 'page_number', 1)
        if isinstance(obj, Author):
            p = Paginator(obj.like_set.all().order_by('-published'), size)
        else:
            p = Paginator(obj.likes.all().order_by('-published'), size)
        setattr(obj, 'count', p.count) # set count
        if page_number > p.num_pages:
            likes = []
        else:
            likes = p.page(page_number).object_list
        return LikeSerializer(likes, many=True).data
    
    count = serializers.IntegerField(read_only=True) # has to be at the bottom to work

class CommentSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="comment", read_only=True)
    id = serializers.CharField(source="api_url", read_only=True)
    comment = serializers.CharField(source="content", read_only=True)
    entry = serializers.SerializerMethodField()
    web = serializers.CharField(source="url", read_only=True)
    author = AuthorSerializer(read_only=True)
    likes = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["type", "author", "comment", "contentType", "published", "id", "entry", "web", "likes"]

    def get_entry(self, obj):
        return obj.post.api_url
    
    @extend_schema_field(LikesSerializer())
    def get_likes(self, obj):
        return LikesSerializer(obj).data

class CommentsSerializer(serializers.Serializer):
    type = serializers.SerializerMethodField()
    id = serializers.CharField()
    web = serializers.CharField(source="url")
    page_number = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    src = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "comments"

    def get_id(self, obj):
        if isinstance(obj, Post):
            return f"{obj.api_url}/comments"
        elif isinstance(obj, Author):
            return f"{obj.api_url}/commented"
        
    def get_size(self, obj):
        return self.context.get("size", 5)
        
    def get_page_number(self, obj):
        return self.context.get("page_number", 1)

    @extend_schema_field(CommentSerializer(many=True))
    def get_src(self, obj):
        size = getattr(obj, 'size', 5)
        page_number = getattr(obj, 'page_number', 1)
        p = Paginator(obj.comments.all().order_by('-published'), size)
        setattr(obj, 'count', p.count) # set count
        if page_number > p.num_pages:
            comments = []
        else:
            comments = p.page(page_number).object_list
        return CommentSerializer(comments, many=True).data
    
    count = serializers.IntegerField(read_only=True) # has to be at the bottom to work


class EntrySerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.CharField(source="api_url") # US 08.16: full API URL as id
    web = serializers.CharField(source="url")
    description = serializers.SerializerMethodField()
    published = serializers.CharField(source="created_at")
    author = AuthorSerializer(read_only=True)
    visibility = serializers.SerializerMethodField()        # # US 02.10
    comments = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField()

    class Meta:
        model = Post
        # US 08.11 & 08.14: Include visibility and relational fields
        fields = ['type', 'title', 'id', 'web', 'description', 'contentType', 'content', 'author', 'comments', 'likes', 'published', 'visibility']
    
    def get_type(self, obj):
        return "entry"
    
    def get_visibility(self, obj):      # US 02.10
        if obj.is_deleted:
            return "DELETED"
        return obj.visibility
    
    def get_description(self, obj):
        return obj.title        # TODO: temporary solution
    
    @extend_schema_field(LikesSerializer())
    def get_likes(self, obj):
        return LikesSerializer(obj).data

    @extend_schema_field(CommentsSerializer())
    def get_comments(self, obj):
        return CommentsSerializer(obj).data


class EntriesSerializer(serializers.Serializer): # Public only
    type = serializers.SerializerMethodField()
    page_number = serializers.IntegerField()
    size = serializers.IntegerField()
    src = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "entries"

    @extend_schema_field(EntrySerializer(many=True))
    def get_src(self, obj):
        size = getattr(self, "size", 5)
        page_number = getattr(self, "page_number", 1)
        p = Paginator(Post.objects.filter(visibility=Post.Visibility.PUBLIC).order_by('-created_at'), size)
        setattr(self, 'count', p.count) # set count
        if page_number > p.num_pages:
            entries = []
        else:
            entries = p.page(page_number).object_list
        return EntrySerializer(entries, many=True).data
    
    count = serializers.IntegerField(read_only=True) # has to be at the bottom to work
    
        


        
