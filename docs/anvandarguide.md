# ExpenseVibe – användarguide

ExpenseVibe används för att redovisa utlägg, kilometerersättning och
frånvaro. En attestant godkänner det som skickats in, och en
administratör för över det till Visma Lön 600.

Guiden är uppdelad efter roll:

- [Alla användare](#alla-anvandare): inloggning, utlägg, kilometerrapporter och frånvaro.
- [Attestant](#attestant): godkänna eller avvisa det andra skickat in.
- [Administratör](#administrator): användare, inställningar och export till Visma.

En person kan ha flera roller. Din roll visas längst ned i sidomenyn
under ditt namn.

---

<a id="alla-anvandare"></a>
## Alla användare

### Logga in

Logga in med din e-postadress och det lösenord du fått av
administratören. Första gången måste du byta till ett eget lösenord
innan du kommer vidare. Samma sak händer om administratören har satt ett
nytt lösenord åt dig.

Glömt lösenordet? Be administratören sätta ett nytt. Det finns ingen
återställning via e-post. Vill du själv byta lösenord någon gång går du
till adressen `/konto/byt-losenord/`.

Vill du använda iPhone-appen går du till **Mobilappen** i menyn och
klickar **Visa QR-kod för inloggning**. Tryck sedan **Skanna QR-kod** i
appen. Koden gäller i 15 minuter och fungerar bara en gång.

Logga ut med pilknappen längst ned i sidomenyn.

### Översikt

Startsidan visar hur många av dina utlägg, kilometerrapporter och
tidrapporter som väntar, är attesterade eller avvisade, plus de senaste
du skickat in. Klicka på en rad för att öppna den.

ExpenseVibe skickar inga e-postmeddelanden. Titta här för att se om
något du skickat in har attesterats eller avvisats.

### Status på det du skickar in

| Status     | Betyder                                    | Kan du ändra eller ta bort? |
|------------|--------------------------------------------|-----------------------------|
| Inskickad  | Väntar på attestering                      | Ja                          |
| Avvisad    | Attestanten har skickat tillbaka den. Läs kommentaren | Ja. När du sparar skickas den in igen |
| Attesterad | Godkänd, väntar på att föras över till lönen | Nej                       |
| Exporterad | Överförd till Visma Lön                    | Nej                         |

Det finns inget utkastläge. Ett utlägg eller en kilometerrapport är
inskickad så fort du sparar den.

### Utlägg

1. Välj **Nytt utlägg** och ladda upp kvittot eller fakturan (PDF, PNG
   eller JPG).
2. Fyll i kategori, beskrivning, datum, belopp och eventuell moms.
   Fält kan vara förifyllda från en automatisk tolkning av kvittot.
   Det är bara förslag, så kontrollera dem. En gul ruta betyder att
   tolkningen saknas eller är osäker.
3. Tryck **Skicka in**.

**Ange beloppet i kronor.** Valutafältet sparas men beloppet förs över
till lönen som det står, utan omräkning.

Avbryter du efter steg 1 hamnar kvittot i **Bilageinkorg**. Där kan du
välja **Skapa utlägg** och fortsätta senare, eller ta bort det.

Saknas en passande kategori? Hör med administratören.

**Rätta ett avvisat utlägg:** Öppna det under **Mina utlägg**, läs
attestantens kommentar, välj **Redigera** och spara. Utlägget skickas
då in igen automatiskt.

### Kilometerrapporter

Välj **Ny kilometerrapport** och fyll i datum, från, till, syftet med
resan och antal kilometer. Ersättningen räknas ut automatiskt med den
km-sats som gällde den dag resan gjordes. Gör en rapport per resa.

Visas meddelandet *"Ingen km-sats är konfigurerad för detta datum"*
behöver administratören lägga in en km-sats för den perioden.

Du ändrar, tar bort och rättar kilometerrapporter på samma sätt som
utlägg, under **Mina kilometerrapporter**.

<a id="franvaro-och-tidrapport"></a>
### Frånvaro och tidrapport

Frånvaro (sjukdom, semester, vård av barn och så vidare) rapporteras
dag för dag i **Frånvarokalender** och skickas in en gång per månad som
en tidrapport.

1. Bläddra fram rätt månad. Står det att perioden inte är öppnad
   ännu, kontakta administratören.
2. Klicka på **+** i dagens ruta och välj frånvaroart. Ange antal
   timmar om frånvaroarten räknas i timmar. Lämna timmar tomt om den
   alltid är en hel dag. En hel dag räknas som dina schemalagda timmar
   den veckodagen. Klicka på en registrerad post för att ändra eller ta
   bort den.
3. När månaden är klar trycker du **Markera som färdig**. Tidrapporten
   skickas då till attestering. Det går också om du inte haft någon
   frånvaro alls.

Kalendern spärrar vissa registreringar:

- En hel dag kan inte kombineras med annan frånvaro samma datum.
- Flera timposter samma dag får tillsammans inte överstiga dina
  schemalagda timmar.
- Lördagar, söndagar och helgdagar är gråmarkerade och går normalt inte
  att rapportera på. Det gäller även julafton, nyårsafton och
  midsommarafton.

När tidrapporten är inskickad kan dagarna inte längre ändras. Avvisas
den visas attestantens kommentar överst i kalendern. Rätta dagarna och
tryck **Markera som färdig** igen. Under **Mina tidrapporter** ser du
alla dina tidrapporter och deras status.

### iPhone-appen

Med iPhone-appen kan du skicka in utlägg (fotografera kvittot direkt),
kilometerrapporter (under **Körjournal**) och frånvaro (under
**Frånvaro**). Är du attestant kan du också attestera utlägg,
kilometerrapporter och tidrapporter i appen.

Under **Frånvaro** bläddrar du mellan månaderna med pilarna. Tryck **+**
för att registrera frånvaro och svep åt vänster på en post för att ta
bort den. **Markera som färdig** skickar tidrapporten precis som i
webben. Vill du ändra en post tar du bort den och lägger in den på nytt.

- Första gången anger du serverns adress (den du får av
  administratören) och loggar in med samma e-post och lösenord som i
  webben.
- Måste du byta lösenord gör du det först i webbappen. Appen släpper
  inte in dig innan dess.
- Sätter administratören ett nytt lösenord åt dig loggas du ut från
  appen.

Allt som rör administration görs i webbappen.

---

## Attestant

Under **Attesteringskö** i sidomenyn visas allt som väntar på beslut,
med det äldsta först: utlägg, kilometerrapporter och tidrapporter i var
sin lista. Siffran i menyn är antalet väntande poster.

- Klicka på beskrivningen eller sträckan för att se detaljerna och
  öppna kvittot.
- **Attestera** godkänner posten. Ett beslut går inte att ångra.
- **Avvisa** skickar tillbaka posten. Du måste skriva en anledning. Den
  anställde ser anledningen och kan rätta och skicka in igen.

Som attestant ser du allas utlägg, kilometerrapporter och tidrapporter
under **Mina …**-menyerna, inte bara dina egna.

ExpenseVibe hindrar inte en attestant från att attestera sina egna
poster. Om det inte är tillåtet hos er behöver den regeln följas
manuellt.

---

<a id="administrator"></a>
## Administratör

### Kom igång

Det allra första kontot skapas via länken på inloggningssidan. Länken
syns bara så länge systemet saknar användare. Kontot blir
administratör men **inte attestant**. Kryssa i **Attestant** på dig
själv under **Användare** om du också ska attestera.

Gör sedan detta innan någon börjar använda systemet:

1. Lägg upp användarna.
2. Skapa kategorier för utlägg.
3. Lägg in minst en km-sats.
4. Skapa frånvaroarter och kontrollera arbetsschemana, om frånvaro ska
   rapporteras.
5. Kontrollera att innevarande månad finns under **Perioder**.

Koderna du anger i steg 2–4 måste redan finnas i Visma Lön 600.
ExpenseVibe skapar inga nya koder där.

### Användare

| Fält               | Kommentar |
|--------------------|-----------|
| E-post             | Används för inloggning. |
| Anställningsnummer | **Måste vara samma som i Visma Lön 600.** Visma hittar rätt anställd med det. |
| Personnummer       | Valfritt. |
| Attestant          | Får attestera allas poster. |
| Administratör      | Får allt under Administration. |
| Lösenord           | Sätts av dig. Användaren måste byta det vid första inloggningen. |

- **Nytt lösenord:** Användaren måste byta det vid nästa inloggning och
  loggas ut från iPhone-appen.
- **Sluta använda ett konto:** Användare tas inte bort. Bocka ur
  **Aktiv** så kan personen inte längre logga in. Historiken finns kvar.
- Den sista aktiva administratören kan inte inaktiveras eller förlora
  administratörsrollen.

### Kategorier

Namn, kod (lönearten i Visma) och om kategorin är aktiv. En kategori
som redan har utlägg kan inte tas bort. Den inaktiveras då i stället och
visas inte längre för nya utlägg.

### Km-satser

Ändras ersättningen per kilometer lägger du in en **ny** km-sats med det
datum den börjar gälla. Gamla satser ska inte ändras. Varje resa
ersätts med den sats som gällde på resans datum, så redan inskickade
rapporter påverkas inte. Ange även lönearten och den benämning som ska
synas i Visma.

### Frånvaroarter

Namn, tidkod i Visma och om arten räknas i **Timmar** eller som **Hel
dag**. Precis som för kategorier inaktiveras en frånvaroart i stället
för att tas bort om den redan har använts.

### Arbetsscheman

Varje anställd har ett veckoschema med timmar per veckodag. Nya
anställda får måndag–fredag 8 timmar. Justera schemat för deltidare.

- **Schemat måste stämma med personens schema i Visma Lön.** Annars
  avvisar Visma importen av frånvaron.
- Ändrar du ett schema påverkar det heldagsposter som läggs in eller
  ändras efter ändringen. Befintliga poster behåller sina timmar.
  Exportens normalarbetstid räknas däremot alltid fram från schemat som
  gäller när exporten skapas.

### Perioder

Frånvaro rapporteras per kalendermånad. En månad måste vara **Öppen**
för att den anställde ska kunna rapportera. Normalt öppnas varje månad
automatiskt den 1:a. Uteblir det, eller vill du öppna en månad i
förväg, anger du månaden (ÅÅÅÅ-MM) och trycker **Öppna**.

När en period exporteras får den statusen **Rapporterad** och stängs
för fler ändringar. Det sker bara när ingen tidrapport i perioden
längre väntar på attestering. Behöver en rapporterad period rättas
väljer du **Återöppna**.

### Frånvaroinställningar

Här styr du om lördagar, söndagar och helgdagar ska vara spärrade för
frånvarorapportering. Spärren är på som standard. Svenska helgdagar
räknas ut automatiskt och behöver inte läggas in.

### Export till Visma Lön 600

1. Gå till **Export till Visma** och välj **Ny export**.
2. Fyll i **Period från** och **Period till** och tryck **Filtrera**.
   Sätt *Period till* till löneperiodens sista dag (se nedan).
3. Kontrollera listorna. Alla attesterade utlägg och kilometerrapporter
   i intervallet är förvalda, och under **Frånvaro** alla perioder med
   attesterade tidrapporter. Bocka ur det som inte ska med.
4. Tryck **Skapa export** och sedan **Hämta .tlu**.
5. Läs in filen i Visma Lön 600.

Bra att veta:

- **Utlägg och kilometer summeras.** Varje anställd får en rad per
  löneart, daterad *Period till*. Lämnas fältet tomt används datumet för
  personens senaste post.
- **Frånvaro väljs per månad.** Att välja en period tar med alla dess
  attesterade tidrapporter.
- **Inget exporteras två gånger.** Exporterade poster får statusen
  Exporterad och visas inte igen. Tidigare filer kan hämtas på nytt
  från exportlistan.
- **Gör en testimport i Visma** innan ni börjar använda exporten på
  riktigt, och efter ändringar av koder eller scheman.

Avvisar Visma importen, kontrollera först:

- Att anställningsnumren stämmer med Visma.
- Att kategorier, km-satser och frånvaroarter har koder som finns i
  Visma.
- Att arbetsschemana stämmer med Visma Lön, om Visma klagar på
  *normalarbetstid*.
