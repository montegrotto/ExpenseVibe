"""Beräknar svenska helgdagar (röda dagar) för ett givet år. Listan
beräknas, lagras aldrig i databasen - det håller den alltid korrekt utan
årligt admin-underhåll (påsk-baserade helgdagar flyttar sig varje år).

Bara de faktiska helgdagarna enligt lag/tradition ingår - inte
klämdagar/aftnar som midsommarafton, julafton eller nyårsafton, som inte
är "helgdagar" i strikt mening även om många verksamheter har stängt då."""

from datetime import date, timedelta


def _easter_sunday(year):
    """Påskdagens datum för `year`, enligt den anonyma gregorianska
    algoritmen (Meeus/Jones/Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    n = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * n) // 451
    month = (h + n - 7 * m + 114) // 31
    day = ((h + n - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _first_weekday_on_or_after(start, weekday):
    """Första datumet >= `start` som infaller på `weekday` (måndag=0 ...
    söndag=6)."""
    days_ahead = (weekday - start.weekday()) % 7
    return start + timedelta(days=days_ahead)


def swedish_public_holidays(year):
    """Dict {datum: namn} över `year`s svenska helgdagar."""
    easter = _easter_sunday(year)
    saturday = 5
    return {
        date(year, 1, 1): "Nyårsdagen",
        date(year, 1, 6): "Trettondedag jul",
        easter - timedelta(days=2): "Långfredagen",
        easter: "Påskdagen",
        easter + timedelta(days=1): "Annandag påsk",
        date(year, 5, 1): "Första maj",
        easter + timedelta(days=39): "Kristi himmelsfärdsdag",
        easter + timedelta(days=49): "Pingstdagen",
        date(year, 6, 6): "Sveriges nationaldag",
        _first_weekday_on_or_after(date(year, 6, 20), saturday): "Midsommardagen",
        _first_weekday_on_or_after(date(year, 10, 31), saturday): "Alla helgons dag",
        date(year, 12, 25): "Juldagen",
        date(year, 12, 26): "Annandag jul",
    }


def swedish_holiday_name(check_date):
    """Namnet på helgdagen `check_date` infaller på, eller None om det
    inte är en helgdag."""
    return swedish_public_holidays(check_date.year).get(check_date)


def _midsommarafton(year):
    """Midsommarafton - fredagen dagen före Midsommardagen (lördagen
    mellan 20-26 juni)."""
    saturday = 5
    return _first_weekday_on_or_after(date(year, 6, 20), saturday) - timedelta(days=1)


# Dagar utöver lagstadgade helgdagar som räknas som arbetsfria, både för
# NormalWorkingTime-syften (export/services.py) och för Frånvarokalendern
# (AbsenceSettings.blocks_date), trots att de inte är lagstadgade helgdagar
# - vanlig praxis för tjänstemän med månadslön. Justera här om ett visst
# kollektivavtal skiljer sig (t.ex. halvdag istället för heldag, eller
# fler/färre aftnar).
def _additional_non_working_days(year):
    """Dict {datum: namn} för `year`s aftnar/klämdagar - julafton och
    nyårsafton (fasta datum) samt midsommarafton (rörligt, dagen före
    Midsommardagen)."""
    return {
        date(year, 12, 24): "Julafton",
        date(year, 12, 31): "Nyårsafton",
        _midsommarafton(year): "Midsommarafton",
    }


def non_working_day_name(check_date):
    """Namnet på helgdagen eller aftonen `check_date` infaller på (se
    swedish_holiday_name och _additional_non_working_days), eller None om
    `check_date` är en vanlig dag."""
    name = swedish_holiday_name(check_date)
    if name is not None:
        return name
    return _additional_non_working_days(check_date.year).get(check_date)


def is_non_working_day(check_date):
    """Om `check_date` ska räknas som en arbetsfri dag - lagstadgade
    helgdagar (se swedish_public_holidays) plus julafton/nyårsafton/
    midsommarafton. Styr både NormalWorkingTime i Visma-exporten och
    (via AbsenceSettings.blocks_date) om frånvaro får rapporteras den
    dagen."""
    return non_working_day_name(check_date) is not None
