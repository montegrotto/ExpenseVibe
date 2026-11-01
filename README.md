# ExpenseVibe

Utläggshantering för små svenska företag: anställda laddar upp kvitton och
fakturor, registrerar kilometerersättning och frånvaro, en attestant
godkänner och en administratör exporterar till Visma Lön 600. Webbapp i
Django, med en SwiftUI-app för iPhone.

Dokumentation: **[expensevibe.se](https://expensevibe.se)**

- [Användarguide](docs/anvandarguide.md) - per roll: anställd, attestant, administratör.
- [Installation och drift](docs/installation.md) - miljövariabler, Docker, Visma-export, kända begränsningar.
- [iPhone-app](ios/README.md).

Färdigbyggda imager (amd64 och arm64) publiceras på Docker Hub som
[`montegrotto/expensevibe`](https://hub.docker.com/r/montegrotto/expensevibe).

## Snabbstart

Kräver Python 3.13 och Node.js (för att vendora Bootstrap).

```
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
npm install
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Öppna http://127.0.0.1:8000 och skapa det första kontot via länken på
inloggningssidan - det blir automatiskt administratör.

## Tester och lint

```
python manage.py test
ruff check .
```

## Licens

MIT, se [LICENSE](LICENSE).
