from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_chart_types command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="chart_types")
        self.stdout.write(self.style.SUCCESS("seeded chart_types"))
