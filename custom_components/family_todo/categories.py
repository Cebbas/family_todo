"""Förvalda butikskategorier för inköpslistor + gissning av kategori per vara.

En kategori blir en vanlig sektion i listan (se store.py:Section) med
`category` satt till kategorins nyckel - ingen egen datamodell. Det gör att
kategorierna går att döpa om, ta bort, flytta och dra-och-släppa precis som
vilken sektion som helst, och att en lista utan förvalda kategorier fungerar
exakt som förut.

`guess_category` används när en vara läggs till utan vald sektion (från
panelen, HA:s todo-kort eller röstassistenten) - se
FamilyTodoListEntity.async_create_todo_item. Ren Python, inget hass-beroende,
så matchningen kan enhetstestas för sig.
"""
from __future__ import annotations

import re
from typing import Iterable

# Ordningen här är också ordningen sektionerna skapas i - ungefär hur en
# vanlig svensk mataffär är upplagd från ingången och inåt.
PRESET_CATEGORIES: list[dict] = [
    {
        "key": "produce",
        "name": "Frukt & grönt",
        "icon": "mdi:food-apple",
        "keywords": [
            "äpple", "äpplen", "banan", "bananer", "päron", "apelsin", "apelsiner", "citron", "lime",
            "druvor", "vindruvor", "melon", "kiwi", "avokado", "mango", "ananas", "bär", "jordgubbar",
            "blåbär", "hallon", "tomat", "tomater", "gurka", "sallad", "isberg", "ruccola", "spenat",
            "paprika", "lök", "rödlök", "vitlök", "purjolök", "potatis", "morot", "morötter", "broccoli",
            "blomkål", "kål", "vitkål", "zucchini", "squash", "aubergine", "svamp", "champinjoner",
            "selleri", "ingefära", "chili", "majs", "sparris", "rädisor", "rödbetor", "dill",
            "persilja", "basilika", "koriander", "frukt", "grönsaker", "clementiner", "nektariner",
        ],
    },
    {
        "key": "bakery",
        "name": "Bröd",
        "icon": "mdi:baguette",
        "keywords": [
            "bröd", "limpa", "baguette", "frallor", "fralla", "bullar", "bulle", "knäckebröd",
            "tunnbröd", "tortilla", "tortillas", "pitabröd", "hamburgerbröd", "korvbröd", "kaka",
            "kakor", "skorpor", "rostbröd", "toast", "croissant", "croissanter", "kanelbullar",
        ],
    },
    {
        "key": "dairy",
        "name": "Mejeri",
        "icon": "mdi:cheese",
        "keywords": [
            "mjölk", "fil", "filmjölk", "yoghurt", "kvarg", "grädde", "matlagningsgrädde", "vispgrädde",
            "gräddfil", "creme fraiche", "crème fraiche", "smör", "bregott", "margarin", "ost", "hushållsost",
            "präst", "brie", "mozzarella", "fetaost", "halloumi", "keso", "ägg", "kefir", "havredryck",
            "mellanmjölk", "lättmjölk", "standardmjölk", "cottage", "parmesan", "riven",
        ],
    },
    {
        "key": "meat",
        "name": "Kött & fisk",
        "icon": "mdi:food-steak",
        "keywords": [
            "kött", "köttfärs", "färs", "nötfärs", "fläskfärs", "kyckling", "kycklingfilé", "kycklinglår",
            "fläsk", "fläskfilé", "karré", "bacon", "skinka", "korv", "falukorv", "prinskorv", "wienerkorv",
            "salami", "pålägg", "kalkon", "lamm", "biff", "entrecote", "oxfilé", "köttbullar", "fisk",
            "lax", "torsk", "sej", "räkor", "tonfisk", "sill", "kaviar", "kassler", "leverpastej",
            "fiskpinnar",
        ],
    },
    {
        "key": "frozen",
        "name": "Frys",
        "icon": "mdi:snowflake",
        "keywords": [
            "glass", "fryst", "frysta", "frysen", "pizza", "pommes", "ärtor", "wokgrönsaker",
            "frysgrönsaker", "isglass", "piroger",
        ],
    },
    {
        "key": "pantry",
        "name": "Skafferi",
        "icon": "mdi:pasta",
        "keywords": [
            "pasta", "spaghetti", "makaroner", "ris", "nudlar", "mjöl", "vetemjöl", "socker", "salt",
            "peppar", "kryddor", "buljong", "fond", "olja", "olivolja", "rapsolja", "vinäger", "ketchup",
            "senap", "majonnäs", "soja", "sylt", "honung", "müsli", "flingor", "havregryn", "gryn",
            "krossade", "passerade", "tomatpuré", "bönor", "linser", "kikärtor", "konserv", "tacokrydda",
            "tacosås", "chips", "godis", "choklad", "nötter", "kaffe", "te", "kakao", "jäst",
            "bakpulver", "vaniljsocker", "kex", "popcorn", "russin",
        ],
    },
    {
        "key": "drinks",
        "name": "Dryck",
        "icon": "mdi:bottle-soda",
        "keywords": [
            "läsk", "juice", "saft", "vatten", "kolsyrat", "mineralvatten", "öl", "vin", "cider",
            "festis", "cola", "energidryck", "smoothie",
        ],
    },
    {
        "key": "household",
        "name": "Hushåll",
        "icon": "mdi:spray-bottle",
        "keywords": [
            "toapapper", "hushållspapper", "papper", "diskmedel", "maskindiskmedel", "disktabletter",
            "tvättmedel", "sköljmedel", "soppåsar", "påsar", "plastpåsar", "fryspåsar", "folie",
            "aluminiumfolie", "bakplåtspapper", "plastfolie", "rengöring", "allrengöring", "svampar",
            "batterier", "glödlampa", "lampa", "servetter", "ljus", "tändstickor",
        ],
    },
    {
        "key": "hygiene",
        "name": "Hygien",
        "icon": "mdi:toothbrush-paste",
        "keywords": [
            "tandkräm", "tandborste", "schampo", "balsam", "tvål", "duschtvål", "deodorant", "deo",
            "rakhyvel", "bindor", "tamponger", "blöjor", "våtservetter", "bomull", "plåster",
            "solkräm", "hudkräm", "nässpray", "alvedon", "ipren", "tandtråd",
        ],
    },
]

PRESET_BY_KEY: dict[str, dict] = {c["key"]: c for c in PRESET_CATEGORIES}

_WORD_RE = re.compile(r"[a-zåäöéü]+")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _keyword_score(words: list[str], text: str, keyword: str) -> int:
    """0 = ingen träff, annars längre = säkrare (längsta träffen vinner).

    Flerordsnyckelord ("creme fraiche") matchas mot hela texten. Ett
    enkelt ord matchar ett helt ord, eller - för svenska sammansättningar
    som "lättmjölk"/"vetemjöl" - som efterled (ordets slut), men bara för
    nyckelord på minst 4 bokstäver så att korta ord som "te"/"öl" inte
    råkar matcha mitt i allt möjligt.
    """
    if " " in keyword:
        return len(keyword) if keyword in text else 0
    for word in words:
        if word == keyword:
            return len(keyword) + 1  # exakt träff vinner över efterled av samma längd
        if len(keyword) >= 4 and word.endswith(keyword):
            return len(keyword)
    return 0


def guess_category(summary: str, available_keys: Iterable[str] | None = None) -> str | None:
    """Bästa kategorinyckeln för en vara, eller None om inget nyckelord matchar.

    `available_keys` begränsar till de kategorier som faktiskt finns som
    sektioner i listan - ingen idé att gissa "Frys" om listan saknar den.
    """
    allowed = set(available_keys) if available_keys is not None else set(PRESET_BY_KEY)
    if not summary or not allowed:
        return None
    text = summary.lower()
    words = _words(text)
    best_key, best_score = None, 0
    for category in PRESET_CATEGORIES:
        if category["key"] not in allowed:
            continue
        for keyword in category["keywords"]:
            score = _keyword_score(words, text, keyword)
            if score > best_score:
                best_key, best_score = category["key"], score
    return best_key


def section_category(section) -> str | None:
    """Kategorinyckeln för en sektion - satt explicit, eller via exakt förvalt namn.

    Namnmatchningen gör att en sektion som användaren själv döpt till t.ex.
    "Mejeri" (innan förvalen fanns) också får varor sorterade dit, utan att
    behöva skapas om.
    """
    if section.category in PRESET_BY_KEY:
        return section.category
    name = (section.name or "").strip().lower()
    for category in PRESET_CATEGORIES:
        if category["name"].lower() == name:
            return category["key"]
    return None


def guess_section_id(summary: str, sections) -> str | None:
    """Sektion (id) en ny vara bör hamna i, eller None."""
    by_key: dict[str, str] = {}
    for section in sections:
        key = section_category(section)
        if key and key not in by_key:
            by_key[key] = section.id
    key = guess_category(summary, by_key.keys())
    return by_key.get(key) if key else None
