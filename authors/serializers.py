from rest_framework import serializers
from .models import Author, Post, Entry, Comment, Like

class AuthorSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="author", read_only=True)
    id = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()
    host = serializers.SerializerMethodField()

    class Meta:
        model = Author
        fields = ['type', 'id', 'displayName', 'description', 'github', 'profileImage', 'host', 'web']

    def get_id(self, obj):
        # Full API URL: http://node/api/authors/<uuid>
        # return f"{obj.host}api/authors/{obj.id}"
        return obj.api_url

    def get_web(self, obj):
        # Browser-facing HTML profile URL
        return obj.url  # assuming obj.url already stores the /authors/<uuid> browser URL
    
    def get_host(self, obj):        # formats host to include trailing /api/
        base = obj.host.rstrip("/")     # obj.host is only the node (e.g., http://127.0.0.1:8000/)
        if not base.endswith("/api"):
            base += "/api"
        return base + "/"


# class PostCreateSerializer(serializers.ModelSerializer):
#     contentType = serializers.CharField(source="content_type")

#     class Meta:
#         model = Post
#         fields = ['title', 'content', 'contentType', 'type', 'visibility']

# class PostSerializer(serializers.ModelSerializer):
#     """
#     This serializer defines the API representation of a Post.

#     The database model contains internal Django objects and fields that cannot be safely or consistently
#     exposed over a federated API. Serializers convert database objects into standardized JSON format
#     that other nodes and clients can understand.

#     This ensures:
#     - consistent federation format
#     - safe exposure of only intended fields
#     - automatic documentation generation via drf-spectacular
#     """

#     author = serializers.SerializerMethodField()
#     contentType = serializers.CharField(source="content_type")

#     class Meta:
#         model = Post
#         fields = ["id", "title", "content", "contentType",  "type", "visibility", "author", "created_at"]

#     def get_author(self, obj):
#         """
#         We return author as URL instead of raw database reference because:
#         Distributed social networks identify authors using URLs, not database IDs.
#         This allows federation across nodes where database IDs have no meaning.
#         """
#         return obj.author.url
    
# class EntrySerializer(serializers.ModelSerializer):
#     author = AuthorSerializer(read_only=True)
#     type = serializers.CharField(default="entry", read_only=True)

#     class Meta:
#         model = Entry
#         # US 08.11 & 08.14: Include visibility and relational fields
#         fields = ['type', 'title', 'id', 'web', 'description', 'contentType', 'content', 'author', 'comments', 'likes', 'published', 'visibility']

class EntrySerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="entry", read_only=True)
    id = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    published = serializers.SerializerMethodField()
    author = AuthorSerializer(read_only=True)
    # comments = CommentsSerializer(read_only=True)
    # likes = LikesSerializer(read_only=True)

    class Meta:
        model = Post
        # US 08.11 & 08.14: Include visibility and relational fields
        fields = ['type', 'title', 'id', 'web', 'description', 'contentType', 'content', 'author', 'comments', 'likes', 'published', 'visibility']

    def get_published(self, obj):
        return obj.created_at
    
    def get_description(self, obj):
        return obj.title        # TODO: temporary solution
    
    def get_web(self, obj):
        # Browser-facing HTML profile URL: "http://nodebbbb/authors/222/posts/293
        return obj.url
    
    def get_id(self, obj):
        # Full API URL: http://nodebbbb/api/authors/222/entries/249
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
        return f"{obj['actor'].displayName} wants to follow {obj['object'].displayName}"
    


class CommentSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="comment", read_only=True)

class CommentsSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="comments", read_only=True)



class LikeSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="like", read_only=True)

class LikesSerializer(serializers.ModelSerializer):
    type = serializers.CharField(default="likes", read_only=True)