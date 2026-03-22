from django.db import migrations, models


def fix_post_url(apps, schema_editor):
    Post = apps.get_model('authors', 'Post')
    
    for post in Post.objects.all():
        post.url = post.url.replace("entries", "posts")
        post.save()

class Migration(migrations.Migration):

    dependencies = [
        ('authors', '0030_comment_api_url_comment_url_like_api_url_like_url'),
    ]
    operations = [
        migrations.RunPython(fix_post_url)
    ]