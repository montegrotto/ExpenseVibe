# CLAUDE.md

Instruktioner till Claude Code för det här projektet.

ExpenseVibe är en utläggshanteringssystem där användare kan gå in och ladda upp bilagor och sätta kategori för dessa. Det uppladdade bilagorna tolkas med fördel av systerprojektet [ReInvGrabber](https://github.com/montegrotto/ReInvGrabber). Bilagehanteringen gör med fördel like den i projektet [SaldoVibe](https://github.com/montegrotto/SaldoVibe).

Man ska även kunna lägga in kilometerrappoter där man anger datum, från och till, syfte med resan samt hur många kilometer man har kört.

En adminfunktion ska finnas där man kan lägga upp användare till systemet. Användarna ska även få lösenord.

Det ska också finns en roll som har rätt att attestera utläggen. Denna roll sätts också av administratören.

Administratören ska kunna få ut exporter på utläggen som sedan ska kunna läsas in i Visma Lön 600.

ExpenseVibe är ett webbprogram skriven i Python. Grafiskt kan man med fördel använda utseendet av [SaldoVibe](https://github.com/montegrotto/SaldoVibe).

## iPhone-app (SwiftUI)

Katalogen `ios/` innehåller en SwiftUI-app som pratar med JSON-API:t i
`api/` - se [ios/README.md](ios/README.md). Appen gör bara det man gör på
språng: lägga upp utlägg, kilometerrapporter och frånvaro (och markera
månadens tidrapport som färdig) samt attestera dem. Skrivbordssaker (export
till Visma, användare, inställningar, frånvaroarter, perioder) görs i
webbappen. API-vyerna återanvänder webbappens ModelForms och
modeller och ska inte få egen affärslogik.

## Arbetssätt

- Committa aldrig direkt på `main`. Varje uppgift får en egen branch från ett
  uppdaterat `main` (`git switch -c <slug>`), och ändringar landar på `main`
  via pull request.
- Branchnamn är en kort svensk slug med bindestreck som beskriver ändringen,
  utan prefix eller ärendenummer, t.ex. `ta-bort-electron` eller
  `skattekonto-notis-5-dagar`. Samma konvention som i SaldoVibe.
- Innan PR: `ruff check .` och `python manage.py test`. CI
  (`.github/workflows/ci.yml`) kör samma sak på varje PR.
- Ändrat `requirements*.txt`? Ta bort `.lock`-filerna och generera om dem
  med kommandot i respektive lockfils header. uv behåller annars gamla
  transitiva pinnar.
