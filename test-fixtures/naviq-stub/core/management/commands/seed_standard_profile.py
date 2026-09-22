from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """No-op stand-in for real NaViQ's seed_standard_profile - see test-fixtures/naviq-stub/README.md."""

    help = "No-op (stub NaViQ fixture, CI docker-smoke job only)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("naviq-stub: seed_standard_profile skipped (no-op)"))
