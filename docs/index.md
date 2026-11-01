# ExpenseVibe

ExpenseVibe är ett system för utlägg, kilometerersättning och frånvaro,
byggt för små svenska företag som kör Visma Lön 600. Det är öppen källkod
under MIT-licens.

- Anställda laddar upp kvitton och fakturor, sätter kategori och får
  beloppen förifyllda när kvittotolkning är påslagen.
- Kilometerrapporter med datum, från, till, syfte och antal kilometer.
- Frånvaro i en månadskalender som lämnas in som tidrapport.
- En attestant godkänner eller avvisar det som skickats in.
- Administratören exporterar attesterade poster som en `.tlu`-fil som
  läses in i Visma Lön 600.
- Finns som webbapp och som iPhone-app för det man gör på språng.

## Dokumentation

- [Användarguide](anvandarguide.md) - hur man använder systemet, per roll.
- [Installation och drift](installation.md) - kom igång lokalt, miljövariabler, Docker, Visma-export och kända begränsningar.
- [iPhone-app](https://github.com/montegrotto/ExpenseVibe/blob/main/ios/README.md) - bygga och distribuera via TestFlight.

## Hämta

- [Docker-image](https://hub.docker.com/r/montegrotto/expensevibe) - färdigbyggd för amd64 och arm64, körs med `docker-compose.yml` från källkoden.
- [Källkod på GitHub](https://github.com/montegrotto/ExpenseVibe) - för webbappen och Docker-drift.
