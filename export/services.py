"""Bygger Visma Lön 600:s tidsredovisningsfil (.tlu, XML, ISO-8859-1) - se
https://support.spiris.se/visma-lon-600/content/online-help/filformat-tidsredovisningsfil.htm

Två syskonsektioner byggs under varje Employee, i den ordning en genuin
Timeplan-export använder (se nedan om varför ordningen spelar roll):
SalaryData > SalaryDataEmployee > Employee > Times > Time (en per
attesterad frånvaropost, se absence.models.AbsenceEntry) och > RegOutlays
> RegOutlay (EN per löneart/OutlayCode och anställd, summerad över
periodens Utlägg/Kilometerrapporter och daterad sista dagen i perioden,
se _merged_regoutlays - RegOutlay
är Vismas begrepp för precis det ett svenskt "utlägg" är, skilda åt via
OutlayCode/Unit). Frånvaro kan INTE uttryckas som RegOutlay - formatet har
ingen "heldag"-enhet för Time-elementet heller, bara SumOfHours, därav
absence.models.AbsenceEntry.workday_hours_snapshot för Hel dag-poster.
RegOutlays byggs alltid sist bland Employees syskonelement (även när
Employee saknar tidrapportering) - en genuin Timeplan-export lägger den
efter NormalWorkingTimes/Times/TimeAdjustments/TimeBalances, aldrig före.
Vismas publicerade spec säger inget uttryckligt om elementordning, men vi
matchar referensexporten rakt av hellre än att gissa vilka avsteg som är
ofarliga - RegOutlays låg tidigare först, oklart om det bidrog till några
av importfelen vi jagat.

Löneart-koder för RegOutlay (Category.code / MileageRate.export_code)
listas i en <RegOutlayCodes>-katalog (syskon till SalaryDataEmployee, en
<RegOutlayCode> per förekommande kod). Enligt Vismas spec är den inte
obligatorisk, men det är den Visma uppdaterar sitt utläggsregister från -
utan den hanteras egentillagda utläggskoder inte korrekt vid importen.
TimeCodes är däremot uttryckligen obligatoriskt ("elementet är
obligatoriskt") - därför byggs ett <TimeCodes>-element (syskon till
SalaryDataEmployee) med en <TimeCode Code="…" TimeCodeName="…"/> per unik
AbsenceType.export_code som faktiskt förekommer i batchen. Utan det
elementet svarar Visma "Importen av tidkoder misslyckades" vid inläsning,
även om varje enskild <Time TimeCode="…"> refererar en giltig kod.

Varje Employee som har någon Times-post får också ett NormalWorkingTimes-
block (syskon till RegOutlays/Times under samma Employee) med en
NormalWorkingTime-rad per kalenderdag med schemalagd arbetstid i personens
deklarerade period - Visma kräver detta ("måste finnas minst en rad/dag")
och validerar värdet mot personens schema i Lön (specen är explicit:
NormalWorkingTimeHours "ska stämma överens med Löns schema"); saknas
blocket helt, eller stämmer värdena inte, svarar Visma "Normalarbetstid
saknas eller har fel format i filen" resp. "Skillnad i normalarbetstid i
tid och löns schema". Timmarna per veckodag kommer från
absence.models.WorkSchedule (samma per-anställd schema som styr Hel
dag-omräkningen, se AbsenceEntry.workday_hours_snapshot) - måste alltså
hållas i synk med vad som faktiskt är konfigurerat på personens
arbetsschema i Visma Lön, annars avvisas importen även om filen i övrigt
är korrekt formaterad - det här är ett dataproblem per anställd, inte
något exportformatet kan garantera bort. Varje NormalWorkingTime-rad har
även ett tomt
FlexTimeHours-attribut - enligt Vismas spec är det "optional, not used",
men en genuin Timeplan-export skriver alltid ut det (tomt), så vi gör
likadant för att minimera avvikelser mot en fil vi vet fungerar. Dagar
utan schemalagd arbetstid (helger, samt helgdagar/julafton/nyårsafton/
midsommarafton som infaller på en vardag - se
absence.holidays.is_non_working_day) hoppas över helt istället för att
skrivas ut som en 0.00-rad; en genuin Timeplan-export gör likadant, och
det var så vi hittade den här skillnaden.

TimeAdjustments/TimeBalances är enligt spec obligatoriska syskonelement
till NormalWorkingTimes/Times när filen innehåller tidsregistreringar - vi
använder inga tidssaldon/justeringar så de byggs alltid tomma
(<TimeAdjustments />/<TimeBalances />), men elementen måste ändå finnas.

Times-raderna byggs av _merged_time_rows (se dess docstring), som både
sorterar på (datum, tidkod) - specen kräver uttryckligen "sorterade efter
datum och tidkod", vilket en genuin Timeplan-export också gör konsekvent,
och AbsenceEntry.Meta.ordering ("-date", nyast först) är fel ordning för
exporten - och slår ihop poster som annars skulle ge en dubblett av samma
(datum, tidkod): specen kräver att varje sådan kombination är unik inom
Times, men AbsenceEntry tillåter medvetet flera poster samma
datum+frånvaroart (t.ex. delad vård av barn, se AbsenceEntry-
docstringen). Summan av timmarna för de sammanslagna posterna skrivs ut
som en enda Time-rad.
"""

import datetime as dt
import xml.etree.ElementTree as ET
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from absence.holidays import is_non_working_day
from absence.models import WorkSchedule

INTERN_NOTE = "Utlägg"
# Filformatsversion 1.4 = den som införde RegOutlayCodes och PricePerUnit.
EXPORT_VERSION = "1.4"


def _amount(value):
    if value is None:
        return None
    return f"{Decimal(value):.2f}"


def _truncate(value, length):
    return (value or "").strip()[:length]


def _regoutlay_attrs_for_expense(expense):
    # DateOfReport/OutlayCode/OutlayCodeName/OutlayType/NoOfPrivate/Unit/
    # SumOfPrivate/SumOfPrivateTax/InternNote är enligt Vismas spec
    # obligatoriska attribut på varje RegOutlay som faktiskt förekommer
    # (värdet får vara tomt, men attributet måste finnas) - saknas något av
    # dem avvisar Visma hela filen. OutlayType ska vara OutlayCode och
    # OutlayCodeName sammanslagna med " - " emellan, se filformatsspecen.
    # InternNote är texten som syns på lönebeskedet - bara "Utlägg" på
    # första raden per anställd (sätts i _merged_regoutlays), tomt på
    # resten. Kvittobeskrivningar/resesyften ska inte dit.
    return {
        "DateOfReport": expense.expense_date.isoformat(),
        "OutlayCode": expense.category.code,
        "OutlayCodeName": expense.category.name,
        "OutlayType": f"{expense.category.code} - {expense.category.name}",
        "NoOfPrivate": "",
        "Unit": "",
        "SumOfPrivate": _amount(expense.amount),
        "SumOfPrivateTax": _amount(expense.vat_amount) if expense.vat_amount is not None else "",
        "InternNote": "",
    }


def _regoutlay_attrs_for_mileage(report):
    code = report.mileage_rate.export_code if report.mileage_rate else ""
    name = report.mileage_rate.export_code_name if report.mileage_rate else ""
    attrs = {
        "DateOfReport": report.date.isoformat(),
        "OutlayCode": code,
        "OutlayCodeName": name,
        "OutlayType": f"{code} - {name}" if code else "",
        "NoOfPrivate": str(report.distance_km),
        "Unit": "km",
        "SumOfPrivate": _amount(report.compensation_amount),
        "SumOfPrivateTax": "",
        "InternNote": "",
    }
    # PricePerUnit är inte obligatoriskt (till skillnad från de andra
    # attributen ovan) - bäddas bara in när det finns.
    if report.rate_snapshot is not None:
        attrs["PricePerUnit"] = _amount(report.rate_snapshot)
    return attrs


def _merged_regoutlays(rows, report_date):
    """Summerar RegOutlay-rader per löneart (OutlayCode) till EN rad per
    anställd och kod, daterad sista dagen i perioden - lönearter ska inte
    levereras dag för dag till Visma Lön. Belopp/moms/antal summeras,
    PricePerUnit behålls bara om alla sammanslagna rader har samma sats."""
    merged = {}
    for row in rows:
        acc = merged.get(row["OutlayCode"])
        if acc is None:
            merged[row["OutlayCode"]] = acc = {**row, "DateOfReport": report_date.isoformat()}
        else:
            for key in ("SumOfPrivate", "SumOfPrivateTax", "NoOfPrivate"):
                acc[key] = _sum_str(acc[key], row[key], key)
            if acc.get("PricePerUnit") != row.get("PricePerUnit"):
                acc.pop("PricePerUnit", None)
    rows = [merged[code] for code in sorted(merged)]
    if rows:
        rows[0]["InternNote"] = INTERN_NOTE
    return rows


def _sum_str(a, b, key):
    if not a and not b:
        return ""
    total = Decimal(a or "0") + Decimal(b or "0")
    return str(total) if key == "NoOfPrivate" else _amount(total)


def _merged_time_rows(entries):
    """Grupperar AbsenceEntry-poster på (datum, tidkod) och summerar
    timmarna till en rad per unik kombination. Vismas spec kräver att
    varje (datum, tidkod)-kombination i Times är unik ("Varje rad ska ha
    en unik kombination av datum, tidkod..."), men AbsenceEntry tillåter
    medvetet flera poster samma datum+frånvaroart (se AbsenceEntry-
    docstringen, t.ex. delad sjuk/vård av barn) - utan sammanslagningen
    skulle en sådan batch exportera dubbletter av (datum, tidkod) och
    bryta mot unikhetskravet. Returnerar (datum, tidkod, timmar)-tripplar,
    sorterade på (datum, tidkod) precis som specen kräver för Times."""
    hours_by_key = {}
    for entry in entries:
        key = (entry.date, entry.absence_type.export_code)
        hours_by_key[key] = hours_by_key.get(key, Decimal("0.00")) + (entry.effective_hours or Decimal("0.00"))
    return sorted((date, time_code, hours) for (date, time_code), hours in hours_by_key.items())


def _time_attrs(date, time_code, hours):
    # DateOfReport/TimeCode/SumOfHours är enligt Vismas spec obligatoriska
    # attribut på varje Time (samma "får vara tomt, men måste finnas"-
    # mönster som RegOutlay-attributen ovan) - om t.ex. AbsenceType saknar
    # export_code (fältet tillåter blankt) ska attributet ändå skrivas ut,
    # bara tomt, aldrig utelämnas helt.
    return {
        "DateOfReport": date.isoformat(),
        "TimeCode": time_code,
        "SumOfHours": _amount(hours) or "",
    }


def _new_employee_bucket():
    return {"expenses": [], "mileage": [], "time_reports": []}


def _timecode_attrs(absence_type):
    return {"Code": absence_type.export_code, "TimeCodeName": absence_type.name}


def _normal_working_time_hours(schedule, day):
    # Helgdagar/julafton/nyårsafton/midsommarafton är arbetsfria oavsett
    # veckodagsschema - se absence.holidays.is_non_working_day. En sådan
    # dag som infaller på en vardag ska alltid ge 0 timmar normalarbetstid,
    # oavsett vad AbsenceSettings.block_weekends_and_holidays är satt till
    # (den inställningen kan stängas av helt, det här kan den inte).
    return Decimal("0.00") if is_non_working_day(day) else schedule.hours_for_date(day)


def build_tlu_export(expenses, mileage_reports, time_reports=(), period_from=None, period_to=None):
    """Bygger .tlu-filens innehåll som bytes (ISO-8859-1). `expenses`,
    `mileage_reports` och `time_reports` ska vara attesterade (status=
    approved) poster som ännu inte exporterats - urvalet görs av anroparen
    (export/views.py). `time_reports` är TimeReport-rader; deras
    AbsenceEntry-poster hämtas via `.entries` (se absence.models).

    FromDate/ToDate på SalaryDataEmployee (hela batchens period) och på
    varje Employee (den anställdes period) skrivs ALLTID, aldrig utelämnade
    - Visma kräver uppenbarligen att SalaryDataEmployee deklarerar batchens
    period (utelämnas de helt, t.ex. när admin lämnar "period från/till"
    tomt på exportsidan, ger Visma "Felaktig period" vid inläsning). Varje
    Employees FromDate/ToDate är alltid de FAKTISKA min/max-datumen bland
    just den personens poster (aldrig period_from/period_to), så att en
    RegOutlay/Time aldrig kan hamna utanför sin egen Employees deklarerade
    period. `period_from`/`period_to` (valfria, satta av admin i export-
    vyns fria datumfilter) vidgar bara SalaryDataEmployees period om de
    sträcker sig utanför vad som faktiskt exporteras - de krymper den
    aldrig, så att t.ex. en frånvaroperiod som valts utanför det datum-
    intervallet ändå alltid ryms inom den deklarerade batch-perioden."""
    # ExportVersion är avgörande: enligt Vismas spec tolkas en fil utan
    # attributet (eller med 1.0) som version 1.0, och då ignoreras alla
    # nyare fält - RegOutlayCodes-katalogen (1.4) och PricePerUnit (1.4)
    # plockas då aldrig upp vid importen. Övriga rotattribut speglar en
    # genuin Timeplan-export (Sweden Timber_Visma_*.tlu); CompanyName/
    # OrgNo utelämnas medvetet - fel OrgNo stoppar importen, saknat ger
    # bara en info. Bokföringsfördelning används inte, därav 0/0.
    root = ET.Element(
        "SalaryData",
        {
            "ProgramName": "ExpenseVibe",
            "Version": "1.0",
            "ExportVersion": EXPORT_VERSION,
            "Created": dt.date.today().isoformat(),
            "Type": "SalaryData",
            "Language": "Swedish",
            "Imported": "0",
            "BookDistributionProject": "0",
            "BookDistributionResultUnit": "0",
        },
    )
    timecodes_el = ET.SubElement(root, "TimeCodes")
    regoutlaycodes_el = ET.SubElement(root, "RegOutlayCodes")
    salary_data_employee = ET.SubElement(root, "SalaryDataEmployee")
    outlaycodes_by_code = {}

    by_employee = {}
    for expense in expenses:
        by_employee.setdefault(expense.employee, _new_employee_bucket())["expenses"].append(expense)
    for report in mileage_reports:
        by_employee.setdefault(report.employee, _new_employee_bucket())["mileage"].append(report)
    for time_report in time_reports:
        by_employee.setdefault(time_report.employee, _new_employee_bucket())["time_reports"].append(time_report)

    batch_from_dates = [period_from] if period_from else []
    batch_to_dates = [period_to] if period_to else []
    timecodes_by_code = {}

    # (längd, sträng) sorterar numeriska anställningsnummer i talordning
    # ("9" före "10") och är ändå deterministisk för icke-numeriska.
    for employee in sorted(by_employee, key=lambda u: (len(u.employment_number), u.employment_number)):
        items = by_employee[employee]
        # `.entries` görs bara en gång per TimeReport (inte per användning
        # nedan) - det är en query, inte en cachad relation, eftersom
        # AbsenceEntry medvetet saknar en FK till TimeReport (se
        # absence.models.AbsenceEntry).
        entries_by_report = {tr.pk: list(tr.entries) for tr in items["time_reports"]}

        all_dates = [e.expense_date for e in items["expenses"]] + [m.date for m in items["mileage"]]
        for time_report in items["time_reports"]:
            # Perioden lägger alltid till en undre/övre gräns, även för en
            # tidrapport utan poster (inget att rapportera den månaden) -
            # annars kraschar min()/max() nedan på en tom lista.
            all_dates.append(time_report.period.month)
            all_dates.append(time_report.period.month_end)
            all_dates.extend(entry.date for entry in entries_by_report[time_report.pk])
        from_date = min(all_dates)
        to_date = max(all_dates)
        batch_from_dates.append(from_date)
        batch_to_dates.append(to_date)

        employee_el = ET.SubElement(
            salary_data_employee,
            "Employee",
            {
                "EmploymentNo": employee.employment_number,
                "FirstName": employee.first_name,
                "Name": employee.last_name or employee.email,
                "FromDate": from_date.isoformat(),
                "ToDate": to_date.isoformat(),
            },
        )
        if items["time_reports"]:
            # NormalWorkingTimes ska bara spegla tidrapporternas period -
            # inte hela Employee-intervallet (from_date/to_date ovan), som
            # även innehåller datum från orelaterade utlägg/kilometer i
            # samma batch. Annars blåses blocket upp med dagar utanför
            # tidrapporteringen och riskerar "Skillnad i normalarbetstid"-
            # fel i Visma.
            nwt_from = min(tr.period.month for tr in items["time_reports"])
            nwt_to = max(tr.period.month_end for tr in items["time_reports"])
            schedule = WorkSchedule.get_for_employee(employee)
            normal_working_times_el = ET.SubElement(employee_el, "NormalWorkingTimes")
            day = nwt_from
            while day <= nwt_to:
                hours = _normal_working_time_hours(schedule, day)
                # Dagar utan schemalagd arbetstid (helger, helgdagar) tas
                # inte med alls - referensexporter från Timeplan hoppar
                # över dem helt istället för att skriva ut en 0.00-rad.
                if hours:
                    ET.SubElement(
                        normal_working_times_el,
                        "NormalWorkingTime",
                        {
                            "DateOfReport": day.isoformat(),
                            "NormalWorkingTimeHours": _amount(hours),
                            "FlexTimeHours": "",
                        },
                    )
                day += timedelta(days=1)

            times_el = ET.SubElement(employee_el, "Times")
            all_entries = [
                entry for time_report in items["time_reports"] for entry in entries_by_report[time_report.pk]
            ]
            for entry in all_entries:
                if entry.absence_type.export_code:
                    timecodes_by_code[entry.absence_type.export_code] = entry.absence_type
            # _merged_time_rows sorterar på (datum, tidkod) och summerar
            # ihop poster som annars skulle ge dubbletter av samma (datum,
            # tidkod) - se docstringen där ovan och _merged_time_rows.
            # AbsenceEntry.Meta.ordering är "-date" (nyast först, för
            # kalendervyn) så all_entries själv är INTE i rätt ordning för
            # exporten; det är därför sorteringen görs här, inte i queryn.
            for date, time_code, hours in _merged_time_rows(all_entries):
                ET.SubElement(times_el, "Time", _time_attrs(date, time_code, hours))

            # TimeAdjustments/TimeBalances är enligt Vismas spec
            # obligatoriska syskonelement till NormalWorkingTimes/Times så
            # fort en Employee har någon tidrapportering ("mandatory for
            # time registrations") - vi använder varken tidssaldon eller
            # justeringar, så de lämnas alltid tomma, men elementen måste
            # ändå finnas (bekräftat mot en genuin Timeplan-export, där de
            # alltid skrivs ut som tomma <TimeAdjustments />/<TimeBalances
            # />, ett syskonpar per Employee).
            ET.SubElement(employee_el, "TimeAdjustments")
            ET.SubElement(employee_el, "TimeBalances")

        # RegOutlays är obligatoriskt (skrivs alltid ut, även tomt) men ska
        # enligt en genuin Timeplan-export komma EFTER NormalWorkingTimes/
        # Times/TimeAdjustments/TimeBalances under Employee, inte före -
        # bäddas därför in sist, oavsett om personen har någon
        # tidrapportering eller inte.
        regoutlays_el = ET.SubElement(employee_el, "RegOutlays")
        regoutlay_attrs = [_regoutlay_attrs_for_expense(e) for e in items["expenses"]]
        regoutlay_attrs += [_regoutlay_attrs_for_mileage(r) for r in items["mileage"]]
        # Sista dagen i perioden = admins period_to om satt, annars
        # personens sista postdatum. Employee.ToDate vidgas vid behov så
        # att raden aldrig hamnar utanför den deklarerade perioden.
        report_date = period_to or to_date
        if report_date > to_date:
            employee_el.set("ToDate", report_date.isoformat())
            batch_to_dates.append(report_date)
        for attrs in _merged_regoutlays(regoutlay_attrs, report_date):
            ET.SubElement(regoutlays_el, "RegOutlay", attrs)
            if attrs["OutlayCode"]:
                outlaycodes_by_code.setdefault(attrs["OutlayCode"], attrs["OutlayCodeName"])

    if batch_from_dates:
        salary_data_employee.set("FromDate", min(batch_from_dates).isoformat())
        salary_data_employee.set("ToDate", max(batch_to_dates).isoformat())

    for code in sorted(timecodes_by_code):
        ET.SubElement(timecodes_el, "TimeCode", _timecode_attrs(timecodes_by_code[code]))
    for code in sorted(outlaycodes_by_code):
        ET.SubElement(
            regoutlaycodes_el, "RegOutlayCode",
            {"Code": code, "RegOutlayCodeName": _truncate(outlaycodes_by_code[code], 50)},
        )
    if not len(regoutlaycodes_el):
        root.remove(regoutlaycodes_el)

    buffer = BytesIO()
    ET.ElementTree(root).write(buffer, encoding="ISO-8859-1", xml_declaration=True)
    return buffer.getvalue()
