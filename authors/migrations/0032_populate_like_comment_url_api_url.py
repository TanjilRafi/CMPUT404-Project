from django.db import migrations, models


def populate_url_api_url(apps, schema_editor):
    Author = apps.get_model('authors', 'Author')
    Post = apps.get_model('authors', 'Post')
    Comment = apps.get_model('authors', 'Comment')
    Like = apps.get_model('authors', 'Like')
    
    for comment in Comment.objects.all():
        comment.url = comment.post.url
        comment.api_url = f"{comment.author.api_url}/commented/{comment.id}"
        comment.save()
    
    for like in Like.objects.all():
        if like.post != None:
            like.url = like.post.url
        else:
            like.url = like.comment.post.url
        like.api_url = f"{like.author.api_url}/liked/{like.id}"
        like.save()

class Migration(migrations.Migration):

    dependencies = [
        ('authors', '0031_fix_post_url'),
    ]
    # referenced Gemini 3, Google. Prompt: how to auto fill a new field when migrating in django 
    operations = [
        migrations.RunPython(populate_url_api_url)
    ]