from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_narrative_standard_profile command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="narrative_standard_profile")
        self.stdout.write(self.style.SUCCESS("seeded narrative_standard_profile"))
