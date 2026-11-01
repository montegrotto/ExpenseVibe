from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from absence.services import open_period


class Command(BaseCommand):
    help = (
        "Skapar och öppnar redovisningsperioden för innevarande månad (eller en angiven "
        "månad via --month). Tänkt att köras via extern cron den 1:a varje månad, t.ex. "
        "`0 0 1 * * docker compose exec -T web python manage.py open_period` - men är "
        "idempotent och ofarlig att köra flera gånger eller manuellt."
    )

    def add_arguments(self, parser):
        parser.add_argument("--month", help="Månad att öppna, format ÅÅÅÅ-MM. Standard: innevarande månad.")

    def handle(self, *args, **options):
        if options["month"]:
            try:
                year, month = options["month"].split("-")
                target = date(int(year), int(month), 1)
            except (ValueError, TypeError) as exc:
                raise CommandError("Ange månad som ÅÅÅÅ-MM, t.ex. 2026-03.") from exc
        else:
            target = timezone.localdate().replace(day=1)

        period, created = open_period(target)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Period {period} öppnad."))
        else:
            self.stdout.write(f"Period {period} fanns redan (status: {period.get_status_display()}).")
