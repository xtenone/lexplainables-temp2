"""
Geparametriseerde SPARQL-bouwers voor de kennisgraaf.

Deze module is de code-vorm van de queryrecepten; ze stonden eerder als proza in de
system-prompt stonden: de eigen-IRI-ruimte-filters die owl:sameAs-tweelingen
ontdubbelen, de directe artikel-/lid-IRI-patronen, de Lucene-FTS en de
verwijzings-/SKOS-vormen. De invoer wordt gevalideerd/ge-escaped zodat het model
geen SPARQL kan injecteren via een tool-argument.

Bron van de patronen: de eerdere agent/prompts.py (kennisgraaf-verkenning).
"""
from __future__ import annotations

import re

from ..namespace import BASIS, ONTOLOGIE, SEP

PREFIXES = f"""PREFIX bwb: <{ONTOLOGIE}>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX luc: <http://www.ontotext.com/connectors/lucene#>
PREFIX inst: <http://www.ontotext.com/connectors/lucene/instance#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

# Eigen IRI-ruimte — filter hierop om owl:sameAs-tweelingen (wetten.overheid.nl)
# buiten tellingen/resultaten te houden.
NS = BASIS

_BWB_RE = re.compile(r"^BWBR\d+$")
_ART_RE = re.compile(r"^[0-9]+[a-z]*$", re.IGNORECASE)
_NUM_RE = re.compile(r"^[0-9]+[a-z]*$", re.IGNORECASE)
# Vrij bepaling-nummer: staat decimale (divisie-)vormen en letters toe: "9", "9.1", "22a", "22bis".
_NUMMER_VRIJ_RE = re.compile(r"^[0-9]+(\.[0-9]+)*[a-z]*$", re.IGNORECASE)


def _bwb(value: str) -> str:
    v = str(value).strip()
    if not _BWB_RE.match(v):
        raise ValueError(f"Ongeldig BWB-id: {value!r} (verwacht 'BWBR' gevolgd door cijfers).")
    return v


def _art(value: str) -> str:
    v = str(value).strip()
    if not _ART_RE.match(v):
        raise ValueError(f"Ongeldig artikelnummer: {value!r}.")
    return v


def _num(value: str) -> str:
    v = str(value).strip()
    if not _NUM_RE.match(v):
        raise ValueError(f"Ongeldig nummer: {value!r}.")
    return v


def _nummer_vrij(value: str) -> str:
    v = str(value).strip()
    if not _NUMMER_VRIJ_RE.match(v):
        raise ValueError(f"Ongeldig bepaling-nummer: {value!r} (verwacht bv. '9', '9.1', '22a').")
    return v


def _lit(text: str) -> str:
    """Veilige SPARQL-stringliteral."""
    s = str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


# ------------------------------------------------------------------
# IRI-bouwers
# ------------------------------------------------------------------

def regeling_iri(bwb_id: str) -> str:
    return f"{NS}{_bwb(bwb_id)}"


def artikel_iri(bwb_id: str, artikel: str) -> str:
    return f"{NS}{_bwb(bwb_id)}{SEP}artikel{SEP}{_art(artikel)}"


def lid_iri(bwb_id: str, artikel: str, lid: str) -> str:
    return f"{artikel_iri(bwb_id, artikel)}{SEP}lid{SEP}{_num(lid)}"


# ------------------------------------------------------------------
# Query-bouwers
# ------------------------------------------------------------------

def fts(query: str, limit: int = 10) -> str:
    """Full-text search via de Lucene-index inst:bwb_tekst."""
    lim = max(1, min(int(limit), 50))
    return PREFIXES + f"""SELECT ?node ?score ?label ?tekst WHERE {{
  [] a inst:bwb_tekst ; luc:query {_lit(query)} ; luc:entities ?node .
  ?node luc:score ?score .
  OPTIONAL {{ ?node rdfs:label ?label }}
  OPTIONAL {{ ?node bwb:tekst ?tekst }}
}} ORDER BY DESC(?score) LIMIT {lim}"""


def list_regelingen() -> str:
    return PREFIXES + f"""SELECT DISTINCT ?regeling ?citeertitel ?soort WHERE {{
  ?regeling a bwb:Regeling .
  FILTER(STRSTARTS(STR(?regeling), "{NS}"))
  OPTIONAL {{ ?regeling bwb:citeertitel ?citeertitel }}
  OPTIONAL {{ ?regeling bwb:soort ?soort }}
}} ORDER BY ?citeertitel"""


def get_artikel(bwb_id: str, artikel: str) -> str:
    """Artikel met zijn leden, plus de onderdelen die rechtstreeks onder het artikel hangen.

    Die directe onderdelen (`heeftOnderdeel`) zijn er bij artikelen zónder leden — een opsomming
    a/b/c direct onder het artikel — en ontbraken volledig. Onderdelen die onder een *lid* hangen
    komen bewust niet mee: bij een definitieartikel zijn dat er tientallen en dan kapt de
    8000-tekenslimiet het resultaat af. Daarvoor is `get_lid`, dat ze wél levert.
    """
    iri = artikel_iri(bwb_id, artikel)
    return PREFIXES + f"""SELECT ?tekst ?jci ?lid ?lidnummer ?lidtekst ?onderdeel ?onderdeeltekst WHERE {{
  OPTIONAL {{ <{iri}> bwb:tekst ?tekst }}
  OPTIONAL {{ <{iri}> bwb:jci ?jci }}
  OPTIONAL {{
    <{iri}> bwb:heeftLid ?lid .
    FILTER(STRSTARTS(STR(?lid), "{NS}"))
    OPTIONAL {{ ?lid bwb:nummer ?lidnummer }}
    OPTIONAL {{ ?lid bwb:tekst ?lidtekst }}
  }}
  OPTIONAL {{
    <{iri}> bwb:heeftOnderdeel ?o .
    FILTER(STRSTARTS(STR(?o), "{NS}"))
    OPTIONAL {{ ?o bwb:nummer ?onderdeel }}
    OPTIONAL {{ ?o bwb:tekst ?onderdeeltekst }}
  }}
}} ORDER BY ?lid ?o"""


def get_lid(bwb_id: str, artikel: str, lid: str) -> str:
    """Lid mét zijn onderdelen.

    Zonder de onderdelen is een definitielid nagenoeg leeg: artikel 2, lid 1 IW 1990 heeft als
    eigen tekst alleen "Deze wet verstaat onder:" — de 25 definities zitten in de onderdelen a t/m
    t. De agent ging dat compenseren met een reeks raw_sparql-pogingen (acht beurten voor één
    definitievraag). `bwb:bevat` is vlak opgeslagen, dus dit haalt ook geneste onderdelen op.
    """
    iri = lid_iri(bwb_id, artikel, lid)
    # De onderdelen in één cel (GROUP_CONCAT) i.p.v. één rij per onderdeel: anders herhaalt de
    # lidtekst zich per onderdeel en loopt een definitielid tegen de 8000-tekenslimiet, waarna juist
    # de laatste onderdelen wegvallen. De subquery met ORDER BY houdt de volgorde a, b, c, …
    return PREFIXES + f"""SELECT ?nummer ?tekst ?jci
       (GROUP_CONCAT(?regel; separator=" ⏐ ") AS ?onderdelen) WHERE {{
  OPTIONAL {{ <{iri}> bwb:nummer ?nummer }}
  OPTIONAL {{ <{iri}> bwb:tekst ?tekst }}
  OPTIONAL {{ <{iri}> bwb:jci ?jci }}
  OPTIONAL {{
    {{ SELECT ?regel WHERE {{
        <{iri}> bwb:bevat ?o .
        FILTER(STRSTARTS(STR(?o), "{NS}"))
        OPTIONAL {{ ?o bwb:nummer ?on }}
        OPTIONAL {{ ?o bwb:tekst ?ot }}
        OPTIONAL {{ ?o bwb:jci ?oj }}
        # De jci van het onderdeel zélf meegeven, niet die van het lid: anders citeert de agent
        # "onderdeel k" maar verwijst de vindplaats naar het hele definitielid. Ook geneste
        # onderdelen hebben er een (…&o=aa&o=1).
        #
        # Zonder de datumstaart (&z=…&g=…): die is voor 25 onderdelen ~700 tekens aan herhaling en
        # staat al in de jci van het lid hierboven. Wat overblijft is een geldige jci-verwijzing.
        BIND(IF(BOUND(?oj),
                IF(CONTAINS(?oj, "&z="), STRBEFORE(?oj, "&z="), ?oj),
                "") AS ?ojk)
        BIND(CONCAT(COALESCE(?on, ""), " ", COALESCE(?ot, ""),
                    IF(?ojk != "", CONCAT(" [", ?ojk, "]"), "")) AS ?regel)
      }} ORDER BY ?o }}
  }}
}} GROUP BY ?nummer ?tekst ?jci"""


def get_bepaling(bwb_id: str, nummer: str) -> str:
    """Haal een bepaling op via haar `bwb:nummer` binnen de regeling — werkt voor artikelen ("9",
    "25", "22a") én divisies/decimale nummers ("9.1") van beleidsregels/circulaires (bv. de Leidraad
    Invordering 2008), waar het artikel/lid-IRI-patroon niet opgaat."""
    return PREFIXES + f"""SELECT ?nummer ?tekst ?label ?jci WHERE {{
  ?node bwb:nummer {_lit(_nummer_vrij(nummer))} ; bwb:tekst ?tekst .
  FILTER(STRSTARTS(STR(?node), "{NS}{_bwb(bwb_id)}"))
  BIND({_lit(_nummer_vrij(nummer))} AS ?nummer)
  OPTIONAL {{ ?node rdfs:label ?label }}
  OPTIONAL {{ ?node bwb:jci ?jci }}
}} LIMIT 5"""


def get_regeling_info(bwb_id: str) -> str:
    iri = regeling_iri(bwb_id)
    return PREFIXES + f"""SELECT ?citeertitel ?opschrift ?afkorting ?soort
       ?geldigVanaf ?geldigTot ?organisatie ?ondertekenaar WHERE {{
  OPTIONAL {{ <{iri}> bwb:citeertitel ?citeertitel }}
  OPTIONAL {{ <{iri}> bwb:opschrift ?opschrift }}
  OPTIONAL {{ <{iri}> bwb:afkorting ?afkorting }}
  OPTIONAL {{ <{iri}> bwb:soort ?soort }}
  OPTIONAL {{ <{iri}> bwb:geldigVanaf ?geldigVanaf }}
  OPTIONAL {{ <{iri}> bwb:geldigTot ?geldigTot }}
  OPTIONAL {{ <{iri}> bwb:uitgegevenDoor ?org . OPTIONAL {{ ?org rdfs:label ?organisatie }} }}
  OPTIONAL {{ <{iri}> bwb:ondertekendDoor ?ond . OPTIONAL {{ ?ond rdfs:label ?ondertekenaar }} }}
}}"""


def follow_verwijzingen(bwb_id: str, artikel: str, lid: str | None = None) -> str:
    node = lid_iri(bwb_id, artikel, lid) if lid else artikel_iri(bwb_id, artikel)
    return PREFIXES + f"""SELECT ?ankerTekst ?naar ?soort ?doelSoort WHERE {{
  <{node}> bwb:heeftVerwijzing ?v .
  OPTIONAL {{ ?v bwb:ankerTekst ?ankerTekst }}
  OPTIONAL {{ ?v bwb:naar ?naar }}
  OPTIONAL {{ ?v bwb:soort ?soort }}
  OPTIONAL {{ ?v bwb:doelSoort ?doelSoort }}
}}"""


def referenced_by(bwb_id: str, artikel: str) -> str:
    iri = artikel_iri(bwb_id, artikel)
    return PREFIXES + f"""SELECT DISTINCT ?regeling ?citeertitel WHERE {{
  <{iri}> bwb:verwijzingDoor ?regeling .
  FILTER(STRSTARTS(STR(?regeling), "{NS}"))
  OPTIONAL {{ ?regeling bwb:citeertitel ?citeertitel }}
}} ORDER BY ?citeertitel"""


def resolve_begrip(term: str) -> str:
    return PREFIXES + f"""SELECT DISTINCT ?concept ?label ?related WHERE {{
  ?concept a skos:Concept .
  {{ ?concept skos:prefLabel ?label }} UNION {{ ?concept rdfs:label ?label }}
  FILTER(CONTAINS(LCASE(STR(?label)), LCASE({_lit(term)})))
  OPTIONAL {{ ?concept skos:related|skos:broader|skos:narrower ?related }}
}} LIMIT 25"""


def count_by_type() -> str:
    return PREFIXES + f"""SELECT ?type (COUNT(DISTINCT ?s) AS ?aantal) WHERE {{
  ?s a ?type .
  FILTER(STRSTARTS(STR(?s), "{NS}"))
}} GROUP BY ?type ORDER BY DESC(?aantal)"""


def context(bwb_id: str, artikel: str, lid: str | None = None) -> str:
    """GraphRAG-subgraaf: de bepaling met haar structurele buurt in één query.

    Levert per relatie-soort (?relatie) een rij: de bepaling zelf (label/tekst/jci),
    de bevattende structuurdelen, de leden, de uitgaande verwijzingen en wie naar het
    artikel verwijst. Zo ziet het model de bepaling ingebed in samenhang i.p.v. losse
    triples. Eén round-trip via UNION.
    """
    node = lid_iri(bwb_id, artikel, lid) if lid else artikel_iri(bwb_id, artikel)
    art = artikel_iri(bwb_id, artikel)
    return PREFIXES + f"""SELECT ?relatie ?a ?b WHERE {{
  {{ BIND("1-zelf-label" AS ?relatie) <{node}> rdfs:label ?a . }}
  UNION {{ BIND("2-zelf-tekst" AS ?relatie) <{node}> bwb:tekst ?a . }}
  UNION {{ BIND("3-zelf-jci" AS ?relatie) <{node}> bwb:jci ?a . }}
  UNION {{ BIND("4-bevat-door" AS ?relatie) ?p bwb:bevat <{node}> .
    FILTER(STRSTARTS(STR(?p), "{NS}")) OPTIONAL {{ ?p rdfs:label ?a }} BIND(STR(?p) AS ?b) }}
  UNION {{ BIND("5-lid" AS ?relatie) <{node}> bwb:heeftLid ?l .
    FILTER(STRSTARTS(STR(?l), "{NS}")) OPTIONAL {{ ?l bwb:nummer ?a }} OPTIONAL {{ ?l bwb:tekst ?b }} }}
  UNION {{ BIND("6-verwijst-naar" AS ?relatie) <{node}> bwb:heeftVerwijzing ?v .
    OPTIONAL {{ ?v bwb:ankerTekst ?a }} OPTIONAL {{ ?v bwb:naar ?b }} }}
  UNION {{ BIND("7-verwezen-door" AS ?relatie) <{art}> bwb:verwijzingDoor ?r .
    FILTER(STRSTARTS(STR(?r), "{NS}")) OPTIONAL {{ ?r bwb:citeertitel ?a }} BIND(STR(?r) AS ?b) }}
}} ORDER BY ?relatie"""
