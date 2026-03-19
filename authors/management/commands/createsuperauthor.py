from django.core.management.base import BaseCommand
from django.core import management
from django.contrib.auth.models import User
from authors.models import Author, Inbox
import getpass

# Referenced Gemini, Google response to prompts 
# "is there a way for a custon command to wrap a createsuperuser command" 
# "is there a way to copy the interactive part of createsuperuser"
class Command(BaseCommand):
    help = "Create an author for a super user"
    
    def handle(self, *args, **options):
        username = input("Username: ").strip()

        if not User.objects.filter(username=username).exists():
            email = input("Email address: ").strip()
            password = None
            password_confirm = None
            while password==None or password!=password_confirm:
                password = getpass.getpass("Password: ")
                password_confirm = getpass.getpass("Password (again): ")
                if password != password_confirm:
                    self.stderr.write("Error: Passwords do not match.")

            management.call_command('createsuperuser', interactive=False, username=username, email=email)                
            admin_user = User.objects.get(username=username)
            admin_user.set_password(password)
            admin_user.save()

            host = "http://127.0.0.1:8000/api/"
            answer = input(f"Use host {host}? (Y/n)").strip().lower()
            if answer not in ("yes", "y", ""):
                host = input("Host: ").strip()

            author = Author.objects.create(displayName=username, user=admin_user, host=host)
            Inbox.objects.create(author=author)
            
            self.stdout.write(self.style.SUCCESS(f"Author created successfully!\nHost used: {host}"))

        elif not hasattr(User.objects.get(username=username), 'author'):
            host = "http://127.0.0.1:8000/api/"
            answer = input(f"Use host {host}? (Y/n)").strip().lower()
            if answer not in ("yes", "y", ""):
                host = input("Host: ").strip()

            admin_user = User.objects.get(username=username)
            author = Author.objects.create(displayName=username, user=admin_user, host=host)
            Inbox.objects.create(author=author)

            self.stdout.write(self.style.SUCCESS(f"Author created successfully!\nHost used: {host}"))

        else:
            self.stdout.write("Author already exists")




