import uuid
from django.db import models
from django.conf import settings

class Author(models.Model):
    """
    Represents an author identity hosted on this node.
    A description allows authors to provide additional identity info about themselves.
    This supports richer identity representation & prepares the system for social network features.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # Consistent, unique id (permanent identity)
    displayName = models.CharField(max_length=225)
    description = models.TextField(blank=True) # Field for additional identity info (for personalization)
    github = models.URLField(blank=True, null = True)
    profileImage = models.URLField(blank=True, null=True)
    host = models.URLField() # our node (e.g., http://127.0.0.1:8000/)
    url = models.URLField(unique=True, blank=True, editable=False) # full author URL (e.g., http://127.0.0.1:8000/authors/<uuid>)
    github = models.URLField(blank=True)
    profileImage = models.URLField(blank=True)
    host = models.URLField() # our node (e.g., http://127.0.0.1:8000/api/)
    url = models.URLField(unique=True, blank=True) # full author URL (e.g., http://127.0.0.1:8000/authors/<uuid>/)
    api_url = models.URLField(unique=True, blank=True) # (e.g., http://127.0.0.1:8000/api/authors/<uuid>/)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)
    
    followers = models.ManyToManyField("self", symmetrical=False, related_name='following', blank=True)
    friends = models.ManyToManyField("self", blank=True)

    def save(self, *args, **kwargs):
        """
        Override the save method to automatically generate the URL if it's not set.
         - The URL is constructed using the host & author's ID.
         - Ensures that every author has a unique URL based on their ID.
         - Calls the superclass's save method to save the instance to the database.
         
        This allows for consistent URL generation without requiring manual input.
        This approach simplifies the management of author profiles & their associated URLs in a social distribution network.
         - It also helps in maintaining a clear & organized structure for author profiles, making it easier to access & share them across different platforms.
        
        Overall, this method ensures that each author has a unique & accessible URL.
        """
        if not self.url:
            self.url = f"{self.host[0:-4]}authors/{self.id}"
        
        if not self.api_url:
            self.api_url = f"{self.host}authors/{self.id}"

        super().save(*args, **kwargs)


    def __str__(self):
        """
        String representation of the Author model, showing the display name.
        """
        return self.displayName
    

class Post(models.Model):
    """
    Represents an post referencing a specific author.
    Includes a title and content with different content types (plain text, common mark?).
    Added visibility markers
    TO DO: handle images as content (check for common mark as well)
    We are also keeping deleted posts in the system for node admins to view using the is_deleted field (soft delete).
    
    Visibility:
      PUBLIC: everyone can see it
      UNLISTED: followers and anyone else with the direct link can see it
      FRIENDS: only friends can see it (enforcement could be added when follow is implemented?).
    """
    class Visibility(models.TextChoices):
        PUBLIC   = 'PUBLIC',   'Public'
        UNLISTED = 'UNLISTED', 'Unlisted'
        FRIENDS  = 'FRIENDS',  'Only Friends'

    class Type(models.TextChoices):
        TEXT   = 'TEXT',   'Text'
        COMMONMARK = 'COMMONMARK', 'CommonMark'
        IMAGE  = 'IMAGE',  'Image'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)   # Consistent, unique id (permanent identity)
    author = models.ForeignKey('Author', on_delete=models.CASCADE, related_name='posts')
    title = models.CharField(max_length=200)
    content = models.TextField() # stores images, commonmark and text
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)     # allows for a soft delete. node admins can still view 'deleted' posts
    visibility = models.CharField( # author can set it to their choice when creating the post
        max_length = 8,  # cause unlisted has the most characters which is 8
        choices = Visibility.choices,
        default = Visibility.PUBLIC,
    )
    content_type = models.CharField(max_length=18, null=True)
    type = models.CharField(choices = Type.choices, default = Type.TEXT)
    url = models.URLField(unique=True, blank=True) # (e.g., http://127.0.0.1:8000/authors/<uuid>/entries/<post_id>/)
    api_url = models.URLField(unique=True, blank=True) # (e.g., http://127.0.0.1:8000/api/authors/<uuid>/entries/<post_id>/)

    def save(self, *args, **kwargs):
        """
        Override the save method to automatically generate the URL if it's not set.
         - The URL is constructed using the author's url.
         - Ensures that every post has a unique URL based on their ID and the author's URL.
         - Calls the superclass's save method to save the instance to the database.
         
        This allows for consistent URL generation without requiring manual input.
        This approach simplifies the management of posts & their associated URLs in a social distribution network.
         - It also helps in maintaining a clear & organized structure for posts, making it easier to access & share them across different platforms.
        
        Overall, this method ensures that each post has a unique & accessible URL.
        """
        if not self.url:
            self.url = f"{self.author.url}/entries/{self.id}"
        
        if not self.api_url:
            self.api_url = f"{self.author.api_url}/entries/{self.id}"

        super().save(*args, **kwargs)

    def is_visible_to(self, user):
        """
        Returns True if the given user may see this post.

        US 04.09 — deleted posts visible only to node admins (is_staff).
        US 04.10 — author always sees their own non-deleted posts.
        US 04.01 — PUBLIC: visible to everyone.
        US 04.02 — UNLISTED: author sees it in lists; others use the direct link (post_detail).
        US 04.03 — FRIENDS: stub until Follow is implemented; denied for now.
        """
        # deleted posts are visible to node admins only
        if self.is_deleted:
            if user is None or not user.is_authenticated or not user.is_staff:
                return False
            return True

        # author can always see their own posts
        if user is not None and user.is_authenticated:
            try:
                if user.author == self.author:
                    return True
            except Author.DoesNotExist:
                pass

        # is for the public
        if self.visibility == self.Visibility.PUBLIC:
            return True

        # unlisted, only followers and anyone with link can see it
        if self.visibility == self.Visibility.UNLISTED:
            return False

        # friends only
        if self.visibility == self.Visibility.FRIENDS:
            return False

        return False
    
    def setType(self):
        if self.content_type == "text/plain":
            self.type = self.Type.TEXT
        elif self.content_type == "text/markdown":
            self.type = self.Type.COMMONMARK
        else:
            self.type = self.Type.IMAGE

    def __str__(self):
        """
        String representation of the Post model, showing the title.
        """
        return self.title
    
class Inbox(models.Model):
    """
    Represents all items that arrive to an authors inbox
    Contains follow requests and entries
    """
    author = models.OneToOneField(Author, on_delete=models.CASCADE)
    incoming_follow_requests = models.ManyToManyField(Author, symmetrical=False, related_name="outgoing_follow_requests")
    posts = models.ManyToManyField(Post, symmetrical=False)

class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) 
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='comments')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    contentType = models.CharField(max_length=50, default="text/plain")
    published = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        """
        String representation of the Comment model, showing the content.
        """
        return f"Comment by {self.author.displayName} on {self.post.title}"
    
class Like(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes', null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='likes', null=True, blank=True)
    published = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [
            ("author", "post"), 
            ("author", "comment")]  # prevents duplicates in db
        
    def __str__(self):
        """
        String representation of the Like model, showing the author and the object liked.
        """
        if self.post:
            return f"{self.author.displayName} likes post {self.post.title}"
        return f"{self.author.displayName} likes a comment on {self.comment.post.title}"

class Entry(models.Model):
    # US 08.11: Well-indexed relational structure

    id = models.URLField(primary_key=True) 
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    published = models.DateTimeField(auto_now_add=True, db_index=True)
    visibility = models.CharField(max_length=20, default='PUBLIC')
    content = models.TextField()
    contentType = models.CharField(max_length=50, default="text/plain")

    # US 08.14: Logic for deleted entries
    VISIBILITY_CHOICES = [
        ('PUBLIC', 'Public'),
        ('FRIENDS', 'Friends-Only'),
        ('UNLISTED', 'Unlisted'),
        ('DELETED', 'Deleted'),
    ]
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='PUBLIC')
