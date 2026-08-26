"""
Annotatie-grounding-helpers: parse de JAS-JSON van het model en verifieer elk element **brongetrouw**
(het fragment moet letterlijk in de opgehaalde artikeltekst voorkomen). Niet-onderbouwde of
ongeldig-geclassificeerde voorstellen worden verworpen (nooit stil doorgelaten). Gebruikt door de
annoteer-stap in `orchestrator.py` (`_parse_elementen`/`_verwerk`).
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Iterator
from typing import Any, NamedTuple

from .jas_klassen import GELDIGE_JAS_KLASSEN
from .models import (
    AnnotatieAlternatief, AnnotatieVoorstel, CriticOordeel, OntbrekendItem, VerworpenFragment,
)

logger = logging.getLogger("graph_qa.annotatie")

_AANDACHT = {"groen", "geel", "rood"}
_ACTIES = {"behoud", "vervang", "verwijder"}

_WS = re.compile(r"\s+")


def _normaliseer(s: str) -> str:
    """Collapse witruimte, zodat een fragment ondanks layout-verschillen matcht."""
    return _WS.sub(" ", s or "").strip()


def komt_letterlijk_voor(corpus: str, fragment: str) -> bool:
    """Staat dit fragment letterlijk in de opgehaalde tekst?

    Dezelfde eis (en dezelfde normalisatie) waarmee `_verwerk` de voorstellen van het model afkeurt,
    maar los bruikbaar — bijvoorbeeld voor de markeringen die de jurist meestuurt. Ook die moeten in
    de bepaling staan die is opgehaald: een Critic-oordeel over een fragment dat hij niet voor zich
    heeft is geen oordeel.
    """
    norm = _normaliseer(fragment)
    return bool(norm) and _normaliseer(corpus).find(norm) >= 0


def sleutel_van(tekst: str, lid: str) -> tuple[str, str]:
    """Identiteit van een markering los van zijn id: fragment + lid.

    Twee elementen met dezelfde sleutel zijn dezelfde markering, ook al dragen ze een ander id. Dat
    gebeurt als een herziening een bestaand fragment opnieuw voorstelt zonder het id mee te sturen —
    en dan krijgt de jurist twee identieke kaartjes te reviewen.

    **Bewust ZONDER klasse**, gelijk aan de terugval in de api-merge (`routers/annotatie.py:_sleutel`)
    en aan `mergeVoorstellen` in de werkplek: een herziening mág juist de klasse veranderen en moet
    dan hetzelfde element treffen. Stond de klasse er wél in, dan werd een herclassificatie zonder
    id een tweede element — en zag de jurist dezelfde tekstspan twee keer met tegenstrijdige
    klassen. Dit is de canonieke regel; wie hem elders nabouwt, bouwt hem hiernaar.
    """
    return (_normaliseer(tekst).lower(), (lid or "").strip())


class PatchTelling(NamedTuple):
    """Wat de patcher deed: hoeveel uitgevoerd, en hoeveel als twijfel doorgegeven."""

    toegepast: int
    alternatief: int

    def __bool__(self) -> bool:
        return bool(self.toegepast or self.alternatief)


def pas_critic_toe(
    voorstellen: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    corpus: str,
) -> tuple[list[dict[str, Any]], PatchTelling, list[dict[str, Any]]]:
    """Voer de correcties van de Critic uit.

    Geeft terug: (nieuwe voorstellen, telling, **onafgehandelde instructies**). Dat laatste is wat de
    herziener nog te doen heeft. Zonder die scheiding kreeg hij de volledige feedback opnieuw — ook
    de correcties die hier net waren uitgevoerd, en ook de gele voorkeuren die hier bewust NIET zijn
    uitgevoerd. Dan voert een taalmodel alsnog uit wat we juist aan de jurist wilden voorleggen, en
    dat was op dev meteen zichtbaar: "2 aanwijzingen toegepast" gevolgd door "4 aangepast".

    De Critic leverde altijd al een uitvoerbare instructie — `actie` met `voorstel_klasse` en/of
    `voorstel_tekst`. Die ging vervolgens naar een tweede LLM (de herziener) die hem moest lezen,
    uitvoeren, en alle ongemoeide elementen ongewijzigd terugtypen. Dat is werk dat code exact doet
    en een taalmodel bij benadering: het kostte een call met het volle corpus, en het maakte van de
    keten een onderhandeling tussen twee modellen — met vier guards nodig om te laten stoppen.

    Wat hier NIET gebeurt, gebeurt nog steeds door het model: een bijna-goed citaat repareren en een
    gemeld ontbrekend element toevoegen. Dat vraagt de brontekst lezen, geen instructie uitvoeren.

    **Het aandacht-niveau bepaalt hoe hard een `vervang` landt.** Bij ROOD is de Critic er zeker van
    dat er iets mis is en wordt de correctie uitgevoerd. Bij GEEL twijfelt hij, en dan wordt een
    voorgestelde klasse een **alternatief** op het element: de werkplek toont die als aanklikbare chip
    ("Twijfel — klik om te wisselen"), zodat de jurist hem met één klik overneemt en het als zijn eigen
    beslissing in het auditspoor landt. Zo hoeft de Critic zijn voorkeur niet in te slikken en wordt
    er ook niets op een vermoeden veranderd.

    Drie grenzen, en ze zijn geen van drieën nieuw:
    - **Een markering van de jurist blijft ongemoeid.** Een oordeel daarover is een suggestie; dat
      staat zo in de api (`critic_suggestie`: "puur advies, wordt nooit toegepast") en het hoort hier
      niet alsnog stilletjes te worden doorgevoerd.
    - **Een voorgesteld fragment moet letterlijk in het corpus staan.** Dezelfde eis als bij een vers
      voorstel (`_verwerk`); een Critic die parafraseert corrigeert niets, hij verzint.
    - **Verwijderen alleen bij rood.** `_verwerk_critic` normaliseert dat al; hier vertrouwen we daar
      niet blind op — het is de enige onomkeerbare handeling in deze functie.
    """
    op_id = {str(f.get("id", "")): f for f in feedback if f.get("id")}
    uit: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    toegepast = 0
    alternatief = 0

    for v in voorstellen:
        f = op_id.get(str(v.get("id", "")))
        actie = str((f or {}).get("actie", "behoud"))
        if f is None or actie == "behoud" or v.get("van_jurist"):
            uit.append(v)
            continue

        rood = str(f.get("aandacht", "")) == "rood"
        klasse = str(f.get("voorstel_klasse", "")).strip()

        if actie == "verwijder" and rood:
            toegepast += 1
            _markeer_toegepast(v)
            continue

        nieuw = dict(v)

        # GEEL VERANDERT NOOIT IETS. Een voorgestelde klasse wordt een alternatief — de werkplek
        # maakt er een aanklikbare chip van, dus de jurist neemt hem over met één klik en dan staat
        # het als zíjn beslissing in het spoor. Een voorgesteld frágment kent die tussenvorm niet en
        # blijft dus alleen in de motivatie staan; de jurist kan het fragment zelf herselecteren.
        #
        # In beide gevallen is de instructie hier AFGEHANDELD en gaat hij niet door naar de
        # herziener. Deed hij dat wel, dan voerde een taalmodel alsnog uit wat we juist ter
        # beoordeling wilden voorleggen — op dev kortte hij zo twee fragmenten in op een geel advies.
        if actie in ("vervang", "verwijder") and not rood:
            if klasse in GELDIGE_JAS_KLASSEN and klasse != nieuw.get("klasse"):
                alts = list(nieuw.get("alternatieven") or [])
                if not any(str(a.get("klasse")) == klasse for a in alts):
                    alts.append({"klasse": klasse, "motivatie": str(f.get("motivatie", "")).strip()})
                    nieuw["alternatieven"] = alts
                    alternatief += 1
            uit.append(nieuw)
            continue

        gewijzigd = False
        if actie == "vervang" and rood and klasse in GELDIGE_JAS_KLASSEN and klasse != nieuw.get("klasse"):
            nieuw["klasse"] = klasse
            # Stond die klasse al als alternatief op het element (bijv. omdat hetzelfde fragment in
            # twee klassen was voorgesteld en `_voeg_alternatief_toe` er een alternatief van maakte),
            # dan is hij nu de hoofdklasse. Hem laten staan levert de jurist een chip op die naar de
            # keuze wijst die er al staat — op dev kregen twee elementen zo een alternatief dat gelijk
            # was aan hun eigen klasse. Dezelfde invariant die `_voeg_alternatief_toe` bewaakt.
            alts = [a for a in (nieuw.get("alternatieven") or []) if str(a.get("klasse")) != klasse]
            if alts != (nieuw.get("alternatieven") or []):
                nieuw["alternatieven"] = alts
            gewijzigd = True
        tekst = str(f.get("voorstel_tekst", "")).strip()
        if (
            actie == "vervang"
            and rood
            and tekst
            and tekst != nieuw.get("tekst")
            and komt_letterlijk_voor(corpus, tekst)
        ):
            nieuw["tekst"] = tekst
            gewijzigd = True

        if gewijzigd:
            toegepast += 1
            _markeer_toegepast(nieuw)
            # Het oordeel ging over de vórige versie. Leeg laten zou hem uit de aandacht-filters
            # laten vallen zonder dat iemand er iets van vindt; daarom volgt er een tweede
            # Critic-pas over het gecorrigeerde resultaat (zie `route_na_patch`).
            nieuw["aandacht"] = ""
            nieuw["critic"] = ""
        else:
            # Rood, maar niets uitvoerbaars: het voorgestelde fragment staat niet letterlijk in de
            # bron, of de klasse was al zo. Dít is wat de herziener nog kan oplossen — hij mag de
            # brontekst lezen en het bedoelde fragment opzoeken.
            rest.append(f)
        uit.append(nieuw)

    return uit, PatchTelling(toegepast=toegepast, alternatief=alternatief), rest


def demp_zelfweerspreking(voorstellen: list[dict[str, Any]]) -> int:
    """Zwak een eindoordeel af dat de eigen uitgevoerde correctie terugdraait. Geeft het aantal terug.

    De eindbeoordeling gaat rechtstreeks naar de jurist — daar zit geen patcher meer achter die hem
    kan wegen. Komt de Critic daar terug op een klasse die hij zélf in de vorige ronde liet
    aanbrengen, dan levert dat een rode kaart op waarin de agent zichzelf tegenspreekt. Op dev stond
    er zo "dit is een Rechtsobject, geen Rechtsbetrekking" op een element dat hij één ronde eerder
    van Rechtsobject náár Rechtsbetrekking had gebracht.

    Dat is geen zekerheid maar twijfel: hetzelfde fragment, twee keer gewogen, twee uitkomsten. Dus
    behandelen we het als twijfel — de klasse blijft staan, het niveau zakt naar geel en de andere
    lezing komt als alternatief naast de kaart te liggen. De jurist ziet beide en kiest.

    Een eindoordeel over iets ánders (het fragment, overlap, een klasse die de Critic niet zelf heeft
    aangebracht) blijft onaangeroerd: dat is wél een nieuw bezwaar.
    """
    gedempt = 0
    for v in voorstellen:
        rondes = v.get("critic_rondes") or []
        if len(rondes) < 2 or str(rondes[-1].get("aandacht", "")) != "rood":
            continue
        klasse = str(rondes[-1].get("voorstel_klasse", "")).strip()
        huidig = str(v.get("klasse", ""))
        if not klasse or klasse == huidig:
            continue
        if not any(r.get("toegepast") and str(r.get("voorstel_klasse", "")) == huidig
                   for r in rondes[:-1]):
            continue

        alts = list(v.get("alternatieven") or [])
        if not any(str(a.get("klasse")) == klasse for a in alts):
            alts.append({"klasse": klasse, "motivatie": str(rondes[-1].get("motivatie", "")).strip()})
            v["alternatieven"] = alts
        v["aandacht"] = "geel"
        rondes[-1]["aandacht"] = "geel"
        gedempt += 1
    return gedempt


# De spaties eromheen blijven van de motivatie, niet van de match — anders plakken de woorden
# aan weerszijden van een vervangen id aan elkaar.
_ELEMENT_ID = re.compile(r"(?:\[|\()?(?:id\s*=\s*)?\b([0-9a-f]{12})\b(?:\]|\))?")


def vervang_ids_door_citaat(motivatie: str, voorstellen: list[dict[str, Any]]) -> str:
    """Zet interne element-ids in een Critic-motivatie om naar het fragment waar ze op slaan.

    De Critic krijgt de ids in zijn prompt omdat hij zijn oordeel eraan moet hangen, en verwijst
    vervolgens naar buurelementen met diezelfde id — "de Voorwaarde zit eigenlijk in [635074d49a74]".
    Die motivatie staat één-op-één op de reviewkaart, dus de jurist las een hexcode. Dat gebeurde op
    dev in drie van de zestien kaarten.

    Een id dat bij geen enkel voorstel hoort (de Critic verzint er soms een) wordt neutraal
    weggeschreven in plaats van blijven staan; anders ruilt de kaart een hexcode in voor een
    verkeerde verwijzing.
    """
    if not motivatie:
        return motivatie
    op_id = {str(v.get("id", "")): str(v.get("tekst", "")) for v in voorstellen}

    def _vervang(m: re.Match[str]) -> str:
        tekst = op_id.get(m.group(1), "")
        if not tekst:
            return "een ander element"
        kort = tekst if len(tekst) <= 45 else tekst[:44].rstrip() + "…"
        # Zette de Critic er zelf al aanhalingstekens omheen ("element '[<id>]'"), dan zouden die van
        # ons erbij komen: element ''zo'n fragment''. De zijne winnen.
        omsloten = motivatie[m.start() - 1: m.start()] in "'\u2018\u201c" and (
            motivatie[m.end(): m.end() + 1] in "'\u2019\u201d")
        return kort if omsloten else f"'{kort}'"

    return _ELEMENT_ID.sub(_vervang, motivatie).strip()


def openstaand_voorstel(voorstel: dict[str, Any], corpus: str) -> tuple[str, str, str]:
    """Wat de EINDbeoordeling voorstelt maar niemand meer uitvoert: (klasse, fragment, reden).

    De patcher draait vóór de eindbeoordeling; wat de Critic dáár nog voorstelt, komt door geen enkele
    stap meer heen. Op dev gebeurde dat twee keer in één run: "overweeg het fragment te beperken tot
    'is aansprakelijk'", met het exacte fragment in de data, terwijl de jurist het met de hand moest
    naselecteren. Hetzelfde geldt voor een voorgestelde klasse: bij een eerdere ronde maakt de patcher
    daar een alternatief van, maar in de eindronde draait die niet meer.

    Uitvoeren doen we het niet — het oordeel ís het sluitstuk, en er komt geen ronde meer overheen die
    er iets van kan vinden. Maar het als aanklikbare suggestie naast de kaart leggen kan wel; dan
    landt het als een beslissing van de jurist. Dezelfde eis als overal: letterlijk in de bron.
    """
    leeg = ("", "", "")
    rondes = voorstel.get("critic_rondes") or []
    if not rondes:
        return leeg
    laatste = rondes[-1]
    if str(laatste.get("actie", "")) != "vervang" or laatste.get("toegepast"):
        return leeg

    klasse = str(laatste.get("voorstel_klasse", "")).strip()
    if klasse not in GELDIGE_JAS_KLASSEN or klasse == str(voorstel.get("klasse", "")):
        klasse = ""

    tekst = str(laatste.get("voorstel_tekst", "")).strip()
    if tekst == str(voorstel.get("tekst", "")) or not komt_letterlijk_voor(corpus, tekst):
        tekst = ""

    if not klasse and not tekst:
        return leeg
    return klasse, tekst, str(laatste.get("motivatie", "")).strip()


def _markeer_toegepast(voorstel: dict[str, Any]) -> None:
    """Zet `toegepast` op de laatste Critic-ronde van dit element.

    Zonder dit verschilt "de Critic vroeg erom" niet van "het is ook gebeurd" — en juist dat verschil
    moet een auditspoor kunnen laten zien.
    """
    rondes = voorstel.get("critic_rondes") or []
    if rondes:
        rondes[-1]["toegepast"] = True


def _balanced_objecten(text: str) -> Iterator[str]:
    """Yield elke gebalanceerde {…}-substring op élk niveau (string-/escape-bewust).

    Elementen zitten genest in de wrapper `{"elementen": [ {…}, {…} ]}`, dus we moeten ook geneste
    objecten opleveren. Een afgekapt (nooit-gesloten) object levert niets op — precies wat we willen.
    """
    stack: list[int] = []
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}":
            if stack:
                yield text[stack.pop() : i + 1]


def _parse_elementen(text: str) -> list[dict[str, Any]]:
    """Haal de element-objecten uit de LLM-respons.

    Fast-path: de hele respons als één JSON-object met `elementen`. Faalt dat (proza eromheen,
    afgekapt op max_tokens, code-fences), dan **salvagen** we de losse gebalanceerde {…}-objecten die
    op een element lijken (met `klasse` én `tekst`) — zo overleeft een afgekapt of omlijst antwoord
    (het onvolledige laatste object valt weg, de complete blijven) i.p.v. dat álles wegvalt.
    """
    raw = (text or "").strip()
    kandidaat = raw
    if kandidaat.startswith("```"):
        kandidaat = kandidaat.strip("`")
        if kandidaat.lower().startswith("json"):
            kandidaat = kandidaat[4:]
    s, e = kandidaat.find("{"), kandidaat.rfind("}")
    if s != -1 and e > s:
        try:
            data = json.loads(kandidaat[s : e + 1])
            if isinstance(data, dict) and isinstance(data.get("elementen"), list):
                return [x for x in data["elementen"] if isinstance(x, dict)]
        except json.JSONDecodeError:
            pass
    gered: list[dict[str, Any]] = []
    for obj in _balanced_objecten(raw):
        try:
            d = json.loads(obj)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and "klasse" in d and "tekst" in d:
            gered.append(d)
    return gered


def _voeg_alternatief_toe(voorstel: AnnotatieVoorstel, klasse: str, motivatie: str) -> None:
    """Neem een tweede lezing van dezelfde span op als alternatief bij het eerste voorstel.

    Doet niets als het dezelfde klasse is (dan is het een echte herhaling) of als de klasse al als
    alternatief staat — anders groeit de lijst met dubbelen bij elke ronde.
    """
    if klasse == voorstel.klasse or any(a.klasse == klasse for a in voorstel.alternatieven):
        return
    voorstel.alternatieven.append(AnnotatieAlternatief(klasse=klasse, motivatie=motivatie))


def _verwerk(
    llm_text: str, corpus: str, bwb_id: str, artikel: str, scope_lid: str | None = None,
    geldige_ids: set[str] | None = None,
) -> tuple[list[AnnotatieVoorstel], list[VerworpenFragment]]:
    """Parse de LLM-JSON, valideer klasse + brongetrouwheid, bereken vindplaats.

    Is een `scope_lid` gezet (annotatie tot één lid), dan wint dat voor de vindplaats — elke markering
    verwijst dan naar dat lid, ook als het model het lid-veld leeg laat.

    `geldige_ids` begrenst welke id's het model mag hergebruiken, en wordt door de **herziening**
    meegegeven: daar krijgt het model bestaande voorstellen te zien, en een verwisseld id zou dan
    element A overschrijven met de inhoud van B — inclusief de beslissingen van de jurist en het
    auditspoor die eraan hangen. Een id buiten de set wordt genegeerd; het voorstel krijgt een vers
    id en komt er dus naast te staan in plaats van iets stuk te maken.

    De eerste ronde geeft het bewust niet mee: daar bestaat binnen de beurt nog geen element om te
    overschrijven, dus een id uit het model is hooguit een raar id.

    Dezelfde strengheid die `_verwerk_critic` al hanteerde: die valideert oordelen ook tegen de
    aangeboden id's. Dat de twee parsers daarin verschilden was een gat, geen keuze.

    Geeft naast de gegronde voorstellen de VERWORPEN fragmenten terug. Die gingen eerder als kale
    teller verloren, terwijl ze de bruikbaarste feedback voor een herzieningsronde zijn: een bijna
    goed citaat is met de aanwijzing "dit staat niet letterlijk in de tekst" prima te repareren.
    """
    norm_corpus = _normaliseer(corpus)
    voorstellen: list[AnnotatieVoorstel] = []
    verworpen: list[VerworpenFragment] = []
    rauw = _parse_elementen(llm_text)
    if not rauw and llm_text.strip():
        logger.warning("annotatie: geen element-objecten uit de respons gehaald")

    gezien: dict[tuple[str, str], AnnotatieVoorstel] = {}
    for e in rauw:
        klasse = str(e.get("klasse", "")).strip()
        fragment = str(e.get("tekst", "")).strip()
        norm_frag = _normaliseer(fragment)
        idx = norm_corpus.find(norm_frag) if norm_frag else -1
        # Verwerp ongeldige klasse of niet-onderbouwd fragment: nooit stil doorlaten.
        if klasse not in GELDIGE_JAS_KLASSEN or idx < 0:
            verworpen.append(VerworpenFragment(
                klasse=klasse, tekst=fragment,
                reden="ongeldige_klasse" if klasse not in GELDIGE_JAS_KLASSEN else "niet_letterlijk",
            ))
            continue
        lid = str(scope_lid).strip() if scope_lid and str(scope_lid).strip() else str(e.get("lid", "")).strip()
        alts = [
            AnnotatieAlternatief(klasse=str(a.get("klasse", "")).strip(), motivatie=str(a.get("motivatie", "")).strip())
            for a in e.get("alternatieven", [])
            if isinstance(a, dict) and str(a.get("klasse", "")).strip() in GELDIGE_JAS_KLASSEN
        ]
        # Twee keer hetzelfde fragment in één ronde: het model herhaalt zich. De eerste telt —
        # die draagt eventueel het id uit een eerdere ronde, en daaraan hangen de beslissingen.
        # Gaat het om dezelfde span met een ANDERE klasse, dan is dat geen herhaling maar twijfel:
        # de tweede lezing wordt een alternatief op het eerste voorstel in plaats van een tweede
        # element. Eén klasse per element, de andere lezing zichtbaar — stil weggooien zou precies
        # de twijfel verbergen die de jurist moet zien.
        sleutel = sleutel_van(fragment, lid)
        if (eerste := gezien.get(sleutel)) is not None:
            _voeg_alternatief_toe(eerste, klasse, str(e.get("toelichting", "")).strip())
            continue
        vindplaats = f"{bwb_id} art. {artikel}" + (f" lid {lid}" if lid else "")
        # Een id uit een eerdere ronde behouden (herziening van een bestaand element); anders een
        # nieuw id. Zo blijft de koppeling met de Critic én met de api-elementen intact — maar
        # alléén voor een id dat het model ook echt is aangeboden.
        bestaand_id = str(e.get("id", "")).strip()
        if geldige_ids is not None and bestaand_id and bestaand_id not in geldige_ids:
            logger.info("annotatie: onbekend element-id genegeerd", extra={"element_id": bestaand_id[:40]})
            bestaand_id = ""
        voorstel = AnnotatieVoorstel(
            id=bestaand_id or uuid.uuid4().hex[:12],
            klasse=klasse,
            tekst=fragment,
            lid=lid,
            toelichting=str(e.get("toelichting", "")).strip(),
            alternatieven=alts,
            grounded=True,
            vindplaats=vindplaats,
        )
        gezien[sleutel] = voorstel
        voorstellen.append(voorstel)
    return voorstellen, verworpen


def _verwerk_critic(llm_text: str, ids: list[str]) -> tuple[dict[str, CriticOordeel], list[OntbrekendItem]]:
    """Parse het Critic-JSON: per element-id een oordeel + een ontbrekend-lijst.

    Koppelt op `id`, met `index` (positie in `ids`) als terugval — een model dat het id-veld vergeet
    verliest zo niet stilzwijgend álles. Op positie alleen koppelen kan niet meer: zodra een
    herzieningsronde een element toevoegt of weglaat, schuiven de indices en landt een oordeel op het
    verkeerde element.

    Robuust tegen proza/afkapping (fast-path hele-JSON, anders de gebalanceerde {…}-objecten).
    Ongeldige aandacht-waarden, onbekende id's en indices buiten bereik worden genegeerd. Nooit
    exceptions naar de caller — de Critic mag de annotatie niet breken.
    """
    oordelen: dict[str, CriticOordeel] = {}
    ontbrekend: list[OntbrekendItem] = []
    geldige_ids = set(ids)

    data: dict[str, Any] | None = None
    raw = (llm_text or "").strip()
    kandidaat = raw.strip("`")
    if kandidaat.lower().startswith("json"):
        kandidaat = kandidaat[4:]
    s, e = kandidaat.find("{"), kandidaat.rfind("}")
    if s != -1 and e > s:
        try:
            parsed = json.loads(kandidaat[s : e + 1])
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = None
    # Fallback: los de gebalanceerde objecten op en herken oordeel-/ontbrekend-objecten.
    oordeel_objs: list[dict[str, Any]] = []
    ontbrekend_objs: list[dict[str, Any]] = []
    if isinstance(data, dict):
        oordeel_objs = [o for o in data.get("oordelen", []) if isinstance(o, dict)]
        ontbrekend_objs = [o for o in data.get("ontbrekend", []) if isinstance(o, dict)]
    else:
        for obj in _balanced_objecten(raw):
            try:
                d = json.loads(obj)
            except json.JSONDecodeError:
                continue
            if not isinstance(d, dict):
                continue
            if ("id" in d or "index" in d) and "aandacht" in d:
                oordeel_objs.append(d)
            elif "klasse" in d and "reden" in d:
                ontbrekend_objs.append(d)

    for o in oordeel_objs:
        element_id = str(o.get("id", "")).strip()
        if element_id not in geldige_ids:
            # Terugval: positie in de aangeboden lijst.
            try:
                idx = int(o.get("index"))
            except (TypeError, ValueError):
                continue
            if not (0 <= idx < len(ids)):
                continue
            element_id = ids[idx]

        aandacht = str(o.get("aandacht", "")).strip().lower()
        if aandacht not in _AANDACHT:
            continue

        actie = str(o.get("actie", "behoud")).strip().lower()
        if actie not in _ACTIES:
            actie = "behoud"
        voorstel_klasse = str(o.get("voorstel_klasse", "")).strip()
        if voorstel_klasse and voorstel_klasse not in GELDIGE_JAS_KLASSEN:
            voorstel_klasse = ""
        voorstel_tekst = str(o.get("voorstel_tekst", "")).strip()

        # Weggooien is de zwaarste ingreep: alleen bij een expliciet rood oordeel. En vervangen
        # zonder te zeggen wát het moet worden is geen instructie maar een klacht.
        if actie == "verwijder" and aandacht != "rood":
            actie = "vervang"
        if actie == "vervang" and not (voorstel_klasse or voorstel_tekst):
            actie = "behoud"

        oordelen[element_id] = CriticOordeel(
            aandacht=aandacht,
            motivatie=str(o.get("motivatie", "")).strip(),
            actie=actie,
            voorstel_klasse=voorstel_klasse,
            voorstel_tekst=voorstel_tekst,
        )

    for o in ontbrekend_objs:
        klasse = str(o.get("klasse", "")).strip()
        if klasse in GELDIGE_JAS_KLASSEN:
            ontbrekend.append(OntbrekendItem(
                klasse=klasse,
                reden=str(o.get("reden", "")).strip(),
                tekst=str(o.get("tekst", "")).strip(),
            ))

    return oordelen, ontbrekend
