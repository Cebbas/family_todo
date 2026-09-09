# Family Todo – Home Assistant custom integration

Skapar riktiga att-göra-listor i Home Assistant:

- varje lista är en riktig `todo.*`-entitet – syns i HA:s inbyggda
  todo-kort, går att bocka av/lägga till uppgifter i via röstassistenten
  (Assist), och fungerar med appar/automationer som redan pratar med
  HA:s todo-plattform
- skapa/döp om/ta bort listor direkt i sidopanelen, utan att gå via
  Inställningar → Enheter & tjänster för varje ny lista
- varje uppgift kan ha en **tilldelad person** (fritext, eller valfri
  `person.*`-entitet från en rullgardin) och en egen **checklista med
  delsteg** – praktiskt för uppgifter som "Städa vardagsrummet" (dammsug,
  dammtorka, dammsug soffan) där du vill bocka av delar av jobbet, inte
  bara hela uppgiften på en gång

## Känd begränsning: delsteg och tilldelning syns bara i panelen

Home Assistants inbyggda `todo`-plattform har inget begrepp för delsteg
eller tilldelad person – ett todo-item har bara titel, status (klar/inte
klar), beskrivning och förfallodatum. Den begränsningen finns i HA själv,
inte något Family Todo kan runda.

Family Todo löser det genom att lagra delsteg och tilldelning som egen
utökningsdata vid sidan av, kopplad till uppgiftens id. Det betyder:

- **I sidopanelen**: full funktionalitet – lägg till/bocka av delsteg,
  välj tilldelad person, se hur många delsteg som är klara.
- **I HA:s eget todo-kort och i röstassistenten**: bara själva
  uppgiftstexten och avbockad/inte avbockad syns, som vilken todo-lista
  som helst. Delstegen och tilldelningen är osynliga där.

Vill du se hur många delsteg som är klara utan att öppna panelen, lägg
till listans todo-entitet på en dashboard – panelen visar en liten
"2/5"-badge per uppgift, kortet gör det inte (se IDEAS.md för en möjlig
lösning: skriva in en sammanfattning i uppgiftens `description`-fält).

## Installation

**Manuellt:**
1. Kopiera mappen `custom_components/family_todo/` till
   `config/custom_components/` på din HA-installation.
2. Starta om Home Assistant.
3. Inställningar → Enheter & tjänster → Lägg till integration → sök på
   **"Family Todo"** och skapa din första lista (du kan skapa fler direkt
   i sidopanelen efteråt).

**Via HACS (custom repository):**
1. HACS → tre punkter uppe till höger → *Anpassade repositories*
2. Lägg till `https://github.com/Cebbas/family_todo` med kategori
   *Integration*
3. Sök upp "Family Todo" i HACS och installera, starta om HA, lägg sedan
   till integrationen som i steg 3 ovan.

## Skapa och hantera listor

Efter installation dyker **Att göra** upp som en egen flik i sidomenyn
(inget adminkonto krävs). Där kan du:

- Skapa nya listor (flik "Ny lista") – varje lista blir direkt en
  `todo.*`-entitet, ingen omväg via Inställningar behövs
- Döpa om eller ta bort en lista
- Lägga till, bocka av, redigera och ta bort uppgifter
- Klicka på en uppgift för att öppna delstegs- och tilldelningsvyn

Vill du hellre skapa en lista via **Inställningar → Enheter & tjänster →
Lägg till integration → Family Todo** går det också – funkar precis
likadant, panelens "Ny lista"-flik är bara en genväg.

## Uppgifter

Varje uppgift har:

- **Titel** – texten som visas
- **Status** – klar/inte klar (bocka i via kryssrutan)
- **Beskrivning** och **förfallodatum** – valfria, redigerbara via HA:s
  vanliga todo-gränssnitt (röstassistent, todo-kortet, eller panelen)
- **Tilldelad person** – valfritt, fritext eller vald från en lista med
  `person.*`-entiteter på din HA-instans (panelen)
- **Delsteg** – valfri checklista, en rad per delsteg med egen
  avbockningsstatus (panelen)

## Tester

Modell-/entitetslogik (listmodell, CRUD, ordning, delstegs-räkning) täcks
av en pytest-svit under `tests/`, byggd på
`pytest-homeassistant-custom-component`. Köra lokalt:

```bash
pip install -r requirements_test.txt
pytest tests/ -q
```

Körs även automatiskt i CI (`.github/workflows/validate.yml`) vid varje
push/PR.

## Bygga vidare

Se `IDEAS.md` för en avbockningsbar lista över vad som är gjort och vad
som återstår – bland annat sysslor/chores med tilldelning och rotation,
som medvetet lämnats utanför den här första versionen.

## Filstruktur

```
custom_components/
  family_todo/
    __init__.py      # setup, registrerar panel + ws-api, städar lagring vid borttag
    todo.py             # todo.*-entiteten per lista (CRUD, ordning)
    store.py               # ren datamodell (TodoListData/TodoItemData/Subtask) + HA-lagring
    config_flow.py            # skapa ny lista (formulär, eller direkt från panelen)
    panel.py                     # registrerar sidopanelen + statiska filer
    ws_api.py                       # websocket-kommandon som panelen använder
    const.py
    manifest.json
    hacs.json
    strings.json
    translations/
      en.json
      sv.json
    www/
      family-todo-panel.js  # sidopanelens UI (vanilla JS)
tests/               # pytest-svit (modell, entitet)
requirements_test.txt
pytest.ini
```
