from rest_framework import serializers
from .models import Author, Post, Entry, Like, Comment, Inbox
from drf_spectacular.utils import extend_schema_field, OpenApiTypes

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


class EntrySerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="entry", read_only=True)
    id = serializers.SerializerMethodField() # US 08.16: full API URL as id
    web = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    published = serializers.SerializerMethodField()
    author = AuthorSerializer(read_only=True)
    visibility = serializers.SerializerMethodField()        # # US 02.10
    # comments = CommentsSerializer(read_only=True)
    # likes = LikesSerializer(read_only=True)

    class Meta:
        model = Post
        # US 08.11 & 08.14: Include visibility and relational fields
        fields = ['type', 'title', 'id', 'web', 'description', 'contentType', 'content', 'author', 'comments', 'likes', 'published', 'visibility']

    def get_published(self, obj):
        return obj.created_at
    
    def get_visibility(self, obj):      # US 02.10
        if obj.is_deleted:
            return "DELETED"
        return obj.visibility
    
    def get_description(self, obj):
        return obj.title        # TODO: temporary solution
    
    def get_web(self, obj):
        # Browser-facing HTML profile URL: "http://nodebbbb/authors/222/posts/293
        return obj.url
    
    def get_id(self, obj):
        """
        US 08.16: use stored api_url as canonical identifier.
        Ensures remote nodes can reference this entry uniquely without UUID conflicts.
        Full API URL: http://nodebbbb/api/authors/222/entries/249
        """
        return obj.api_url


class EntriesSerializer(serializers.Serializer):
    type = serializers.CharField(default="entries", read_only=True)
    page_number = serializers.IntegerField()
    size = serializers.IntegerField()
    count = serializers.IntegerField()
    src = EntrySerializer(many=True, read_only=True)


class FollowRequestSerializer(serializers.Serializer):
    type = serializers.CharField(default="follow", read_only=True)
    summary = serializers.SerializerMethodField()
    actor = AuthorSerializer()
    object = AuthorSerializer()

    def get_summary(self, obj):
        actor = obj["actor"]
        target = obj["object"]
        return f"{actor.displayName} wants to follow {target.displayName}"
    


class CommentSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="comment", read_only=True)
    id = serializers.CharField(source="api_url", read_only=True)
    comment = serializers.CharField(source="content")
    entry = serializers.SerializerMethodField()
    web = serializers.CharField(source="url", read_only=True)
    author = AuthorSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["type", "author", "comment", "contentType", "published", "id", "entry", "web"]

    def get_entry(self, obj):
        return obj.post.api_url

class CommentsSerializer(serializers.Serializer):
    type = serializers.CharField(default="comments", read_only=True)
    id = serializers.CharField()
    web = serializers.CharField()
    page_number = serializers.IntegerField()
    size = serializers.IntegerField()
    count = serializers.IntegerField()
    src = CommentSerializer(many=True, read_only=True)



class LikeSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="like", read_only=True)

class LikesSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="likes", read_only=True)