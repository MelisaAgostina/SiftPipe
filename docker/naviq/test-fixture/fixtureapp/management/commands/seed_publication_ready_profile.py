from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_publication_ready_profile command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="publication_ready_profile")
        self.stdout.write(self.style.SUCCESS("seeded publication_ready_profile"))
