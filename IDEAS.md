# Family Todo – idélista / checklista

## Grundfunktioner (v0.1)
- [x] Varje lista är en riktig `todo.*`-entitet (en config entry per lista,
  samma modell som cal_combiner använder för sammanslagna kalendrar)
- [x] Skapa/döp om/ta bort listor direkt i sidopanelen, ingen omväg via
  Inställningar krävs för varje ny lista
- [x] Skapa/redigera/bocka av/ta bort/flytta uppgifter (CRUD + ordning)
  via HA:s vanliga todo-gränssnitt (röstassistent, todo-kortet, panelen)
- [x] Tilldelad person per uppgift (fritext, eller vald bland
  `person.*`-entiteter) – egen utökningsdata, se README
- [x] Delsteg (checklista) per uppgift – egen utökningsdata, se README
- [x] Lagring städas bort när en lista tas bort (samma lärdom som
  cal_combiner redan dragit för sina egna kalendrar)
- [x] Sektioner inom en lista, valfritt kopplade till en HA-area (rum) –
  eller helt utan area-koppling för icke-rumsbaserade grupperingar. Att
  ta bort en sektion tar inte bort dess uppgifter, bara grupperingen.
- [x] Återkommande uppgifter (t.ex. "Byt sängkläder" var 14:e dag): en
  uppgift kan få ett intervall (N dagar/veckor/månader). Att bocka av den
  – från panelen, HA:s eget todo-kort eller röstassistenten, alla går via
  samma entitetsmetod – öppnar den igen automatiskt med förfallodatumet
  framflyttat och ev. delsteg nollställda, istället för att lämna den
  avklarad. Skiljer sig från övrig utökningsdata genom att den faktiskt
  ändrar beteendet överallt, inte bara i panelen.
- [x] Snabb delsteg-checklista direkt i uppgiftsraden: X/Y-märket är nu en
  knapp som fäller ut en kryssa-av-bara-lista (ingen redigeringspanel
  behövs för att bocka av ett delsteg) - lägg till/ta bort/deadline
  ligger kvar bakom pennan som förut
- [x] Eget förfallodatum + eget återkommande-intervall per delsteg, inte
  bara på hela uppgiften – en kugghjuls-knapp per delsteg öppnar en liten
  editor. Avbockning med aktivt delsteg-intervall rullar bara det
  delstegets datum framåt (ws_api.py:_roll_recurring_subtasks), oberoende
  av uppgiftens egen återkommande-logik
- [x] Påminnelser: en uppgift med tid (inte bara datum) på förfallodatumet
  skickar en mobilpush till den tilldelade personen om den fortfarande
  inte är avbockad när tiden är inne - en gång, via en person -> notify.*-
  mappning konfigurerad under panelens Notiser-tabb (notify_map.py) och en
  60-sekunders bakgrundskoll (reminders.py). Bredare i scope än ursprungs-
  idén nedan under Sysslor - gäller alla uppgifter med tid, inte bara
  återkommande sysslor.

## Inköpslistor (v0.5)
- [x] Egen listtyp (`list_type`: `tasks`/`shopping`, `const.py`) - inte en
  separat datamodell eller egen entitetsklass, samma `todo.*`-entitet och
  `FamilyTodoStore` som en vanlig lista, bara en flagga på config entryn
  som styr vad panelen visar. Väljs vid listskapande (sidopanelens
  "Ny lista"-kort och det vanliga config-flow-formuläret), redigerbar i
  efterhand via `update_list`.
- [x] Egen ikon (kundvagn, `mdi:cart`) som förval på en Inköp-lista,
  används både i flikraden och listkortets header om ingen egen ikon
  satts.
- [x] Snabbare, enklare uppgiftsformulär för Inköp-listor: `_renderItemDetail`
  hoppar helt över förfallodatum, tilldelning, återkommande och delsteg -
  bara sektion (om listan har några - funkar fint som hylla-/butik-
  gruppering utan att kräva en egen kategori-funktion) och kopiera-till-
  rum blir kvar. Lägg-till-raden var redan minimal (titel + valfri
  sektion + Enter-för-att-lägga-till) och behövde ingen ändring.
- [x] Kvantitet/mängd per vara som eget fält (`quantity`, fritext - "2",
  "500 g"). Eget Antal-fält i lägg-till-raden och i varans redigeringsvy,
  visas som en liten pill före titeln och speglas in i description-blocket
  ("🔢 2 l") så HA:s todo-kort också ser den.
- [x] Förvalda butikskategorier (`categories.py`): knappen "Lägg till
  butikskategorier" skapar vanliga sektioner (Frukt & grönt, Bröd, Mejeri,
  Kött & fisk, Frys, Skafferi, Dryck, Hushåll, Hygien) märkta med
  `category`. Nya varor sorteras in automatiskt via nyckelord (även
  sammansättningar som "lättmjölk") - även när de läggs till via
  röstassistenten/HA:s todo-kort. En egen sektion som heter exakt som en
  kategori ("Mejeri") räknas också. Lägg-till-radens "Automatiskt" är
  förval; "Ingen sektion" eller en vald sektion vinner över gissningen.

## Sysslor/chores med tilldelning och rotation (delvis påbörjat)
Ursprungligen ett alternativt scope för hela integrationen – landade
istället som en idé att bygga ovanpå v0.1 istället för att vara grunden,
för att inte låsa fast datamodellen i ett smalare användningsfall från
början. Själva återkommande-delen är klar (se ovan); resten återstår.

- [ ] Rotation mellan flera personer – syslan tilldelas automatiskt nästa
  person i tur när den blivit avbockad/schemat går vidare, istället för
  att alltid ligga på samma tilldelade person
- [ ] Poäng/streak-räkning per person (hur många sysslor gjorda denna
  vecka, i rad, osv.) – "gamification" för att göra sysslor mer
  motiverande för barn
- [x] "Veckan"-fliken i panelen: veckans sysslor från alla att-göra-
  listor grupperat per person (ws `agenda`, `agenda.py`), med försenade
  uppgifter för innevarande vecka, delsteg med eget förfallodatum som egna
  rader, bläddring mellan veckor, avbockning direkt (`complete_item`/
  `complete_subtask` - återkommande rullar vidare som vanligt) och klick på
  listnamnet för att hoppa till uppgiften.
- [x] ~~Notis/påminnelse när en syssla inte är avbockad vid en viss tid~~ -
  löst bredare, för alla uppgifter, se "Påminnelser" ovan under
  Grundfunktioner

## Synlighet för delsteg/tilldelning utanför panelen
- [x] Skriva in en sammanfattning av delstegsstatus ("2/5 delsteg klara")
  och tilldelad person i uppgiftens `description`-fält vid varje ändring,
  så det syns även i HA:s eget todo-kort och röstassistenten. Löst utan
  att blanda ihop med användarens egen text genom en markör-rad
  (`⸻ Family Todo ⸻`) som alltid går att hitta och ersätta - se
  `combine_description`/`split_description` i store.py.
  Panelen visar/redigerar bara den rena användartexten
  (`split_description`, används i `_item_to_dict`); det fulla fältet med
  blocket är bara det HA:s todo-schema (och därmed röstassistenten och
  standardkortet) faktiskt ser. Löste även idén nedan om prefix i
  titeln för tilldelad person - samma block täcker båda behoven, så ett
  extra titel-prefix bedömdes onödigt.

## Robusthet
- [x] Repair-issue när en listas lagringsfil inte går att läsa in helt -
  två olika fall:
  - **Ogiltig JSON**: redan löst av HA-kärnan, ingen egen kod behövs:
    `Store` (homeassistant/helpers/storage.py) fångar JSONDecodeError,
    byter namn på filen till `<nyckel>.corrupt.<tidsstämpel>`, faller
    tillbaka på tom data och skapar själv en `storage_corruption`-issue.
    Testat live 2026-09-19 (försök `de3948f` med egen kod för just detta,
    reverterad i `2b289d4` - den kunde aldrig nås).
  - **Giltig JSON men trasig struktur** (t.ex. en uppgift utan `uid` efter
    en manuell redigering) - det fallet fångar HA inte, och tidigare
    kraschade `TodoListData.from_dict` då hela listans uppstart.
    `from_dict` hoppar nu över enskilda trasiga uppgifter/sektioner;
    originalet sparas i `.storage/family_todo_list_<id>.backup_<tid>` och
    en egen `corrupt_list`-issue skapas (se `FamilyTodoStore.async_load`).
- [x] Diagnostics-stöd (`diagnostics.py`) för att exportera
  felsökningsdata via HA:s inbyggda diagnostics-gränssnitt - en config-
  entry (lista) i taget: hela dess sparade data (uppgifter/sektioner/
  ordning) + entryns egen config + den delade person->notify-mappningen,
  med `owner_user_id`/`notify_map` redigerade bort (identifierar en
  specifik persons HA-konto/telefon, inte relevant för att felsöka en
  lista/påminnelse)

## Sidopanel
- [x] Flikar per lista + en "Ny lista"-flik
- [x] Lägg till/bocka av/ta bort uppgifter direkt i panelen
- [x] Klicka på en uppgift för att expandera delsteg + tilldelning
- [x] Sektioner: skapa/döp om/ta bort direkt i listkortet, med
  area-väljare (namn föreslås automatiskt från vald area) eller helt
  fritt namn. Uppgifter grupperas under sina sektioner plus en
  "Utan sektion"-grupp; listor utan sektioner visas fortfarande platt.
- [x] Återkommande-växel i uppgiftens delstegs-/tilldelningsvy (på/av +
  intervall + enhet), med en "🔁"-badge och nästa förfallodatum synligt
  direkt i uppgiftsraden utan att behöva öppna den.
- [x] Drag-och-släpp för att ändra ordning på uppgifter - handtag
  (`mdi:drag`) per rad, pekar-baserat (pointer events) så det funkar med
  touch i HA-appen, inte bara mus
- [x] Drag-och-släpp för att flytta en uppgift till en annan sektion -
  släpp på en uppgift i målsektionen, eller på sektionen som helhet (t.ex.
  en tom sektion) för att lägga den sist där. `move_item` tar ett valfritt
  `section_id` så position och sektion ändras i ett anrop
- [x] Drag-och-släpp för att ändra ordning på sektionerna själva
  (handtag i sektionsrubriken, ws `move_section`)
- [x] Filtrera/sortera uppgifter per tilldelad person i panelen - "Visa:"
  (alla / en person / ej tilldelade) och "Sortera:" (egen ordning /
  förfallodatum / tilldelad / namn) per lista, sparas per webbläsare.
  Dra-och-släpp av uppgifter är bara aktivt i "Egen ordning"
- [ ] Släppyta för "Utan sektion" även när den gruppen är tom (idag syns
  den bara när den har uppgifter - flytta dit via rullgardinen annars)
- [x] "Kommande"-grupp per sektion: återkommande uppgifter med mer än
  20 % av intervallet kvar till nästa förfallodatum hamnar i en hopfälld
  "Kommande (n)"-grupp längst ner i sin sektion (`_isUpcoming` i panelen)
  och räknas inte i "ej klara"-badgen - så sektionen visar det som är
  aktuellt nu
- [x] Logg över utförda tillfällen för återkommande uppgifter och
  delsteg (`completion_log` på uppgiften, max 100): tidpunkt, vem (via
  HA-kontot -> person.*-namn) och vilket förfallodatum som gällde. Visas
  som "Historik" i uppgiftens redigeringsvy med "i tid"/"N dagar sent"

## Trevligt-att-ha (ej påbörjat)
- [ ] Koppling mot family-planner-card: visa dagens/veckans obockade
  uppgifter (särskilt sysslor tilldelade ett barn) i "Idag"-vyn, liknande
  hur family-planner-card redan visar binary_sensor-baserade "allmänna
  sensorer"
- [ ] Delade listor mellan flera HA-instanser (t.ex. två hushåll) –
  troligen orealistiskt utan en molntjänst, låg prioritet
