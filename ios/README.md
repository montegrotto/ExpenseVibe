# ExpenseVibe för iPhone

SwiftUI-app mot JSON-API:t i `api/` (samma Django-server som webbappen).
Anställda skickar in utlägg (foto på kvittot + uppgifter, förifyllt från
ReInvGrabber när det är påslaget) och kilometerrapporter, och rapporterar
frånvaro månad för månad (Markera som färdig skickar tidrapporten);
attestanter attesterar/avvisar utlägg, kilometerrapporter och tidrapporter. En PDF eller bild kan
också delas till appen från t.ex. Mail (Dela → ExpenseVibe), då öppnas ett
nytt utlägg med filen som kvitto. Allt annat - export till
Visma, användare, kategorier, km-satser, frånvaroarter, perioder - görs i webbappen.

## Bygga

```sh
brew install xcodegen
cd ios && xcodegen generate && open ExpenseVibe.xcodeproj
```

`ExpenseVibe.xcodeproj` genereras från `project.yml` och är inte incheckat.
Sätt ditt eget Team under Signing & Capabilities för att köra på en riktig
telefon. Vid första starten anger man serveradressen (t.ex.
`http://192.168.1.10:8000` mot `manage.py runserver 0.0.0.0:8000` - http
tillåts bara mot lokala nät, en riktig server ska köra https).

Alternativt skannar man QR-koden på webbsidan **Mobilappen**
(`expensevibe://login?server=…&token=…`, samma upplägg som SaldoVibe).
Koden gäller i 15 minuter och bara en gång. Under **Mobilappen** syns också inloggade
enheter, som kan återkallas. Säger koden `http://` för ett domännamn provar appen https först. Sätt `EXPENSEVIBE_PUBLIC_URL`
på servern så att adressen i koden blir rätt bakom en proxy.

## API

Alla anrop utom inloggningen bär `Authorization: Bearer <token>`; token
hämtas med `POST /api/login/` (eller via QR-koden) och raderas när admin återställer
användarens lösenord. Se `api/views.py` för endpoints - de återanvänder
webbappens ModelForms, så valideringen är identisk.

## TestFlight

```sh
ios/scripts/testflight.sh
```

Arkiverar i Release och laddar upp till App Store Connect (`ExportOptions.plist`).
Byggnumret blir aktuell minut (`yyyymmddHHMM`). Kräver att Xcode är inloggat med
ett Apple-ID i team `7MV2FUVY65` och att appen (bundle-id `se.damadev.ExpenseVibe`)
finns i App Store Connect.
