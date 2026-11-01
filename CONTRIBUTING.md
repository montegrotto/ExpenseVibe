# Bidra

Buggrapporter och pull requests är välkomna. Svenska eller engelska går lika bra.

## Innan du skickar en PR

- Läs [CLAUDE.md](CLAUDE.md). Den beskriver vad systemet ska göra, hur
  koden är uppdelad och hur vi arbetar med brancher och PR:ar. Den är
  skriven för AI-assistenter men gäller lika mycket för människor.
- Kör det CI kör: `ruff check .` och `python manage.py test`.
- Ändrat något som [användarguiden](docs/anvandarguide.md) beskriver?
  Uppdatera guiden i samma PR.
- Ändrat `requirements*.txt`? Generera om lockfilerna, se CLAUDE.md.

## Vad som är svårt att få in

- Nya betalda tredjepartsintegrationer. Systemet ska vara kostnadsfritt i drift.
- Ändringar i Visma-exportens format utan en verklig testimport i Visma Lön 600.
- Affärslogik i API-vyerna eller iPhone-appen. De återanvänder webbappens
  formulär och modeller.

Genom att skicka en PR går du med på att ditt bidrag licensieras under
projektets MIT-licens.
