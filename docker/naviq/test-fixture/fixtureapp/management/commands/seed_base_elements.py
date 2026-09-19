from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_base_elements command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="base_elements")
        self.stdout.write(self.style.SUCCESS("seeded base_elements"))
