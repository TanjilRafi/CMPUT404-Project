import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from authors.models import Author, Post

# The following function was completed with the asistance of OpenAI, ChatGPT-5. 2025-03-04.
class Command(BaseCommand):
    help = 'Fetches recent public GitHub activity and creates public Posts (US 01.04)'

    def add_arguments(self, parser):
        parser.add_argument('--author-id', type=str, help='Specific Author UUID (optional)')

    def handle(self, *args, **options):
        """
        US 01.04: Automatically turn new public GitHub activity into public entries.
        - Polls public GitHub events API (no auth needed for public repos).
        - Creates Post objects with visibility=PUBLIC.
        - Avoids duplicates by checking recent posts.
        - Can run for all authors or one specific author.
        - Uses GitHub public events API: https://api.github.com/users/{github_username}/events/public
        - Shows status messages (e.g., for no new recent activity, etc.)
        """
        author_id = options.get('author_id')

        if author_id:
            authors = Author.objects.filter(id=author_id)
        else:
            authors = Author.objects.exclude(github__isnull=True).exclude(github='')

        if not authors.exists():
            self.stdout.write(self.style.WARNING("No authors with GitHub linked."))
            return

        total_created = 0

        for author in authors:
            github_username = author.github.strip('/').split('/')[-1] # extract GitHub username from profile URL
            if not github_username:
                continue

            self.stdout.write(f"Checking GitHub activity for {author.displayName} ({github_username})")

            url = f"https://api.github.com/users/{github_username}/events/public"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                events = response.json()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error fetching GitHub: {e}"))
                continue

            if not events:
                self.stdout.write(self.style.WARNING(f"No public events found for {github_username}"))
                continue

            # Only take recent events (last 24h for simplicity)
            now = timezone.now()
            cutoff = now - timezone.timedelta(hours=24)

            recent_events = [e for e in events if timezone.datetime.fromisoformat(e['created_at'].replace('Z', '+00:00')) >= cutoff]

            # No recent activity to display since last shown/posted
            if not recent_events:
                self.stdout.write(self.style.WARNING(f"No activity in the last 24 hours for {github_username}"))
                continue

            self.stdout.write(f"Found {len(recent_events)} recent events")

            created_count = 0
            for event in recent_events:
                # Simple deduplication: check if similar post already exists
                if Post.objects.filter(
                    author=author,
                    title__icontains=event['type'],
                    created_at__gte=cutoff
                ).exists():
                    continue  # skip duplicate

                # Create a public post from GitHub event
                title = f"GitHub: {event['type']}"
                content = f"Activity on {event['repo']['name']}: {event.get('payload', {}).get('action', 'unknown')}"
                if event.get('payload', {}).get('commits'):
                    content += f"\nCommits: {len(event['payload']['commits'])}"

                Post.objects.get_or_create(
                    author=author,
                    title=title,
                    content=content,
                    visibility=Post.Visibility.PUBLIC,
                    type=Post.Type.TEXT,
                    content_type="text/plain"
                )
                self.stdout.write(self.style.SUCCESS(f"Created post: {title}"))
                created_count += 1

            if created_count == 0:
                self.stdout.write(self.style.NOTICE(f"No new unique activity to report for {github_username} (all recent events already posted)"))

            total_created += created_count

        if total_created == 0:
            self.stdout.write(self.style.SUCCESS("GitHub activity check complete. No new posts created."))
        else:
            self.stdout.write(self.style.SUCCESS(f"GitHub activity check complete. Created {total_created} new post(s)."))