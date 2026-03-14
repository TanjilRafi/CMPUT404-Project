from rest_framework import serializers
from .models import Author, Post, Entry

class AuthorSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()

    class Meta:
        model = Author
        fields = ['type', 'id', 'displayName', 'description', 'github', 'profileImage', 'host', 'web']

    def get_type(self, obj):
        return "author"

    def get_id(self, obj):
        # Full API URL: http://node/api/authors/<uuid>
        return f"{obj.host}api/authors/{obj.id}"

    def get_web(self, obj):
        # Browser-facing HTML profile URL
        return obj.url  # assuming obj.url already stores the /authors/<uuid> browser URL

class PostCreateSerializer(serializers.ModelSerializer):
    contentType = serializers.CharField(source="content_type")

    class Meta:
        model = Post
        fields = ['title', 'content', 'contentType', 'type', 'visibility']

class PostSerializer(serializers.ModelSerializer):
    """
    This serializer defines the API representation of a Post.

    The database model contains internal Django objects and fields that cannot be safely or consistently
    exposed over a federated API. Serializers convert database objects into standardized JSON format
    that other nodes and clients can understand.

    This ensures:
    - consistent federation format
    - safe exposure of only intended fields
    - automatic documentation generation via drf-spectacular
    """

    author = serializers.SerializerMethodField()
    contentType = serializers.CharField(source="content_type")

    class Meta:
        model = Post
        fields = ["id", "title", "content", "contentType",  "type", "visibility", "author", "created_at"]

    def get_author(self, obj):
        """
        We return author as URL instead of raw database reference because:
        Distributed social networks identify authors using URLs, not database IDs.
        This allows federation across nodes where database IDs have no meaning.
        """
        return obj.author.url
    
class EntrySerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    type = serializers.CharField(default="entry", read_only=True)

    class Meta:
        model = Entry
        # US 08.11 & 08.14: Include visibility and relational fields
        fields = ['type', 'title', 'id', 'author', 'content', 'contentType', 'published', 'visibility']