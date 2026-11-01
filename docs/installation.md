# Installation och drift

Den här sidan beskriver installation, konfiguration och drift av
ExpenseVibe. Hur man använder systemet står i [användarguiden](anvandarguide.md).
Källkoden finns på [GitHub](https://github.com/montegrotto/ExpenseVibe).

Bilagor tolkas (best effort) av systerprojektet
[ReInvGrabber](https://github.com/montegrotto/ReInvGrabber) via dess
`/process-one`-endpoint - se `attachments/extraction_client.py`. Integrationen
är frivillig och avstängd tills `REINVGRABBER_URL` sätts. Bilagehantering och
visuellt uttryck är medvetet byggt likt
[SaldoVibe](https://github.com/montegrotto/SaldoVibe).

## Förutsättningar

- Python 3.13
- Node.js/npm (för att vendora Bootstrap lokalt)

## Installation

```
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
npm install
```

## Körning

```
cp .env.example .env   # sätter DJANGO_DEBUG=1 lokalt, annars krävs collectstatic
source .venv/bin/activate
python manage.py migrate
python manage.py runserver
```

Öppna sedan http://127.0.0.1:8000 - så länge systemet inte har en enda
användare visas en länk på inloggningssidan för att skapa det första
kontot, som automatiskt blir administratör (inget CLI-kommando krävs).
Så fort det kontot finns stängs den vägen permanent - alla efterföljande
användare skapas av en administratör via adminmenyn. Skapa fler användare,
kategorier och en km-sats via adminmenyn innan du testar hela flödet.

Sätt miljövariabeln `REINVGRABBER_URL` (t.ex. `http://127.0.0.1:5001`) för
att slå på automatisk tolkning av uppladdade kvitton - tom/osatt betyder
att integrationen är avstängd och uppladdning fungerar precis ändå, bara
utan förifyllda fält.

### Miljövariabler

| Variabel | Standard | Beskrivning |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | osäker dev-nyckel, bara med `DJANGO_DEBUG=1` | Utan DEBUG vägrar appen starta om den saknas. |
| `DJANGO_DEBUG` | av | `1` lokalt, annars krävs `collectstatic`. |
| `EXPENSEVIBE_PUBLIC_URL` | – | Publik adress, t.ex. `https://expensevibe.example.se`. Ger `ALLOWED_HOSTS` och `CSRF_TRUSTED_ORIGINS` om de inte sätts explicit. |
| `DJANGO_ALLOWED_HOSTS` | – | Kommaseparerad. `localhost`/`127.0.0.1`/`[::1]` läggs alltid till. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | – | Kommaseparerad. |
| `DATABASE_ENGINE`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`, `DATABASE_PORT` | SQLite | Sätt `DATABASE_ENGINE=django.db.backends.postgresql` för Postgres. |
| `EXPENSEVIBE_DATA_DIR` | repo-roten | Var SQLite-databas och media hamnar. |
| `EXPENSEVIBE_MAX_UPLOAD_BYTES` | 10 MB | Uppladdningsgräns i minnet. nginx har egen gräns (`client_max_body_size`). |
| `REINVGRABBER_URL` | tom (av) | ReInvGrabber-tjänstens adress. |
| `REINVGRABBER_TIMEOUT` | 15 | Sekunder innan tolkningen ges upp. |

## Tester

```
python manage.py test
```

## Lint

```
ruff check .
```

## iPhone-app

SwiftUI-app för det man gör på språng: lägga upp utlägg och
kilometerrapporter samt attestera dem. Den pratar med JSON-API:t under
`/api/` på samma server - se [ios/README.md](https://github.com/montegrotto/ExpenseVibe/blob/main/ios/README.md).

## Docker

`Dockerfile` bygger produktionsimagen (Python, Node.js, WhiteNoise, Gunicorn)
och `docker-compose.yml` kör den med PostgreSQL, nginx och ReInvGrabber i
samma nätverk. Utveckling sker utan Docker, se Körning ovan.

```
cp .env.example .env   # avkommentera produktionsraderna och fyll i riktiga värden
docker compose up --build -d
```

Compose läser `.env` automatiskt, både för `${NGINX_HTTP_PORT}` i själva
YAML-filen och (via `env_file`) som miljö i containrarna. Ändra
`NGINX_HTTP_PORT` där (t.ex. till 8080) om port 80 redan är upptagen på din
maskin.

Migrationer körs automatiskt vid uppstart av `web`-tjänsten, se
`scripts/docker-entrypoint.sh`.

## Frånvarorapportering

Användarflödet (kalender, tidrapport, perioder, arbetsscheman) beskrivs i
[användarguiden](anvandarguide.md#franvaro-och-tidrapport). Här bara
det som rör drift och kod.

Varje anställds veckoschema (`absence.models.WorkSchedule`) styr både
omräkningen av Hel dag-frånvaro till timmar, taket för summan av
timbaserade poster samma dag och Visma-exportens NormalWorkingTime-block
(se nedan). Hel dag-poster sparar timmarna från schemat vid varje
sparning (`AbsenceEntry.workday_hours_snapshot`); inlämnade poster sparas
aldrig om och påverkas därför inte av senare schemaändringar.

Redovisning sker per kalendermånad (`absence.models.Period`) - saknas en
Period-rad för en månad är den stängd för rapportering. Perioder öppnas
normalt av `open_period`-kommandot, tänkt att köras via extern cron den
1:a varje månad:

```
0 0 1 * * docker compose exec -T web python manage.py open_period
```

Kommandot är idempotent (ofarligt att köra flera gånger) och kan även
öppna en annan månad manuellt: `python manage.py open_period --month 2026-04`.
Adminsidan "Perioder" har samma funktion som fallback om cron missas.

Svenska helgdagar (inklusive påsk-baserade som beräknas om varje år)
räknas ut av `absence/holidays.py`, listas aldrig manuellt och kräver
inget admin-underhåll. Julafton, nyårsafton och midsommarafton räknas som
arbetsfria både i kalendern och i exportens normalarbetstid.

## Export till Visma Lön 600

Exporten bygger en `.tlu`-fil (Vismas tidsredovisningsformat, XML,
ISO-8859-1) enligt [Vismas egen specifikation](https://support.spiris.se/visma-lon-600/content/online-help/filformat-tidsredovisningsfil.htm) -
se `export/services.py`. Löneart-/tidkoder (`Category.code` /
`MileageRate.export_code` / `AbsenceType.export_code`) måste motsvara koder
som redan är konfigurerade i Visma Lön 600 - ExpenseVibe definierar inga nya
koder där. **Gör en verklig testimport i Visma Lön 600 innan skarp drift.**

Utlägg och kilometerrapporter väljs radvis inom ett fritt datumintervall
men summeras i filen till en `RegOutlay` per anställd och löneart, daterad
"Period till" (eller personens sista postdatum om fältet är tomt) - se
`_merged_regoutlays`. Frånvaro väljs periodvis istället (kryssrutor per
period under "Frånvaro" i exportvyn) - att välja en period exporterar alla
dess attesterade tidrapporter i samma `.tlu`-fil som utläggen/kilometer-
rapporterna, och markerar perioden "rapporterad" om inga oattesterade
tidrapporter återstår för den. Om någon anställds tidrapport ännu inte är
attesterad när perioden exporteras förblir perioden öppen tills den är
det, så en tidig export inte permanent stänger ute sena rapporter. En
period som ändå behöver rättas efter att den blivit "rapporterad" (t.ex.
en sent avvisad tidrapport) kan återöppnas manuellt under "Perioder".

Frånvaro i filen kräver två extra element utöver `RegOutlay`/`Time`, båda
upptäckta genom verkliga testimporter i Visma (inte dokumenterade som
"obligatoriska" på ett sätt som var uppenbart i förväg):
- `<TimeCodes>` - en katalog (syskon till `SalaryDataEmployee`) som listar
  `Code`/`TimeCodeName` för varje `AbsenceType.export_code` som faktiskt
  förekommer i exporten. `TimeCodes` är obligatoriskt; saknas det ger
  Visma "Importen av tidkoder misslyckades". Motsvarande katalog för
  utlägg, `RegOutlayCodes`, skrivs också ut (en rad per `OutlayCode` som
  förekommer) - det är den Visma uppdaterar sitt utläggsregister från, så
  utan den hanteras egentillagda utläggskoder inte korrekt vid importen.
- `<NormalWorkingTimes>` per anställd som har frånvaro med i exporten - en
  rad per kalenderdag i personens period, med timmar hämtade från
  personens `Arbetsschema` (se ovan). Saknas det, eller stämmer det inte
  mot personens schema i Visma Lön, ger Visma "Normalarbetstid saknas
  eller har fel format i filen".

## Kända begränsningar (v1)

- Ingen e-postnotifiering - attestanter/anställda måste själva logga in och kolla status.
- Ingen jävsspärr - en attestant kan attestera sina egna poster (medvetet beslut).
- Ingen automatisk uppdatering av km-sats mot Skatteverket - admin lägger in nya satser manuellt.
- Enda-företag - ingen multi-tenant-modell.
- Ingen fullständig ändringshistorik för attestbeslut, bara senaste beslutet.
- Arbetsscheman är ett enkelt veckoschema (samma timmar varje vecka), inte
  versionerat eller datumbegränsat. En ändring slår igenom på Hel dag-poster
  som skapas eller sparas om efter ändringen, och på exportens
  NormalWorkingTimes för alla perioder som exporteras därefter - även
  redan inlämnade. Ingen hantering av tillfälligt ändrat schema (t.ex. en
  enskild vecka med andra tider).
- Periodlåsning vid export är periodgranulär, inte per anställd - att
  exportera en period stänger den för samtliga anställda samtidigt (så
  fort ingen oattesterad tidrapport återstår för den).
- Ingen valutaomräkning - `Expense.currency` sparas men exporten skickar
  `amount` rakt av till Visma som kronor.
- Ingen länk för frivilligt lösenordsbyte i menyn - sidan finns på
  `/konto/byt-losenord/`.
- Första kontot (via "skapa det första kontot") blir administratör men
  inte attestant.
