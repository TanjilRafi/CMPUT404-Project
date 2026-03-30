from django.contrib import admin
from .models import Author, Post, Inbox, Entry, Like, Comment, Node
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

@admin.action(description="Approve selected users (set is_active=True)")
def approve_users(modeladmin, request, queryset):
    """
    Admin action: Approve selected inactive users so they can log in.
    Implements US 08.03: admin approval for sign-up.
    """
    updated = queryset.update(is_active=True)
    modeladmin.message_user(request, f"{updated} user(s) approved and activated.")

# Unregister default User admin so we can customize it
admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_active', 'date_joined')
    list_filter = ('is_active', 'is_staff')
    actions = [approve_users]  # Add custom approval action

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'visibility', 'created_at')
    list_filter = ('visibility',)
    search_fields = ('title', 'content')


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    readonly_fields = ('inbox',)
    list_display = ('displayName', 'host')

@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ('url', 'username', 'is_enabled')
    list_filter = ('is_enabled',)
    search_fields = ('url', 'username')

admin.site.register(Comment)
admin.site.register(Like)
admin.site.register(Inbox)
