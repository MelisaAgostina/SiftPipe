from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_example_charts command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="example_charts")
        self.stdout.write(self.style.SUCCESS("seeded example_charts"))
