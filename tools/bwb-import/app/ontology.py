"""OWL/RDFS-ontologie (T-Box) voor het BWB-vocabulaire, met ELI-alignment.

``build_ontology`` levert de schema-graaf die naast de instance-data wordt
geladen (eigen named graph). De ``rdfsplus-optimized``-ruleset van de
repository materialiseert daarmee o.a. de ELI-views: elke ``bwb:Regeling``
wordt vindbaar als ``eli:LegalResource``, elke ``bwb:heeftArtikel`` als
``eli:has_part``, enzovoort.

De klassen-/property-tabellen zijn de bron van waarheid voor het schema; de
driftbescherming in ``tests/test_ontology.py`` dwingt af dat elke term die de
writer daadwerkelijk gebruikt hier gedeclareerd is.
"""

from __future__ import annotations

from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef

from app.rdf_vocab import Vocab

ELI = Namespace("http://data.europa.eu/eli/ontology#")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")

# Klasse -> (label, toelichting, superklassen: bwb-naam (str) of externe URIRef).
_KLASSEN: dict[str, tuple[str, str, tuple[str | URIRef, ...]]] = {
    "Regeling": (
        "Regeling",
        "Een regeling uit het Basiswettenbestand (wet, AMvB, ministeriële "
        "regeling, beleidsregel, circulaire, …).",
        (ELI.LegalResource,),
    ),
    "Wet": ("Wet", "Wet in formele zin.", ("Regeling",)),
    "AMvB": ("AMvB", "Algemene maatregel van bestuur.", ("Regeling",)),
    "KoninklijkBesluit": ("koninklijk besluit", "Koninklijk besluit.", ("Regeling",)),
    "MinisterieleRegeling": (
        "ministeriële regeling",
        "Ministeriële regeling.",
        ("Regeling",),
    ),
    "Beleidsregel": ("beleidsregel", "Beleidsregel (bv. een leidraad).", ("Regeling",)),
    "Circulaire": ("circulaire", "Circulaire.", ("Regeling",)),
    "Citeerbaar": (
        "Citeerbaar",
        "Tekstdeel met een eigen JuriConnect-identiteit; doel van verwijzingen.",
        (ELI.LegalResource,),
    ),
    "Structuurdeel": (
        "Structuurdeel",
        "Abstract structuurniveau van een wettekst (hoofdstuk, afdeling, …).",
        (ELI.LegalResourceSubdivision,),
    ),
    "Hoofdstuk": ("Hoofdstuk", "Hoofdstuk van een wettekst.", ("Structuurdeel",)),
    "Titeldeel": ("Titeldeel", "Titeldeel van een wettekst.", ("Structuurdeel",)),
    "Afdeling": ("Afdeling", "Afdeling van een wettekst.", ("Structuurdeel",)),
    "Paragraaf": ("Paragraaf", "Paragraaf van een wettekst.", ("Structuurdeel",)),
    "Artikel": (
        "Artikel",
        "Wetsartikel; citeerbaar op JuriConnect-sleutel.",
        ("Citeerbaar", ELI.LegalResourceSubdivision),
    ),
    "Lid": ("Lid", "Genummerd lid binnen een artikel.", (ELI.LegalResourceSubdivision,)),
    "Onderdeel": (
        "Onderdeel",
        "Opsommings- of definitieonderdeel (<li>) binnen een lijst.",
        (ELI.LegalResourceSubdivision,),
    ),
    "Divisie": (
        "Divisie",
        "Divisie van een circulaire/beleidsregel; container én tekstdrager.",
        ("Citeerbaar", ELI.LegalResourceSubdivision),
    ),
    "Bijlage": (
        "Bijlage",
        "Bijlage van een regeling; container (eigen artikelen/onderdelen) én "
        "tekstdrager, citeerbaar op JuriConnect-sleutel.",
        ("Citeerbaar", ELI.LegalResourceSubdivision),
    ),
    "Illustratie": (
        "Illustratie",
        "Afbeelding (uit <plaatje>/<illustratie>) binnen een tekstdrager.",
        (),
    ),
    "Ondertekenaar": (
        "Ondertekenaar",
        "Persoon die de regeling heeft ondertekend (functie + naam).",
        (FOAF.Agent,),
    ),
    "Organisatie": (
        "Organisatie",
        "Verantwoordelijke organisatie/ministerie van een regeling (uit de WTI).",
        (FOAF.Agent,),
    ),
    "Verwijzing": (
        "Verwijzing",
        "Gereïficeerde verwijzing met soort/doel-metadata.",
        (),
    ),
}

# Objectproperty -> (label, toelichting, superproperties, rdfs:range of None).
_OBJECT_PROPS: dict[str, tuple[str, str, tuple[URIRef, ...], str | None]] = {
    "heeftHoofdstuk": ("heeft hoofdstuk", "Wet bevat hoofdstuk.", (ELI.has_part,), "Hoofdstuk"),
    "heeftTiteldeel": ("heeft titeldeel", "Bevat titeldeel.", (ELI.has_part,), "Titeldeel"),
    "heeftAfdeling": ("heeft afdeling", "Bevat afdeling.", (ELI.has_part,), "Afdeling"),
    "heeftParagraaf": ("heeft paragraaf", "Bevat paragraaf.", (ELI.has_part,), "Paragraaf"),
    "heeftArtikel": ("heeft artikel", "Bevat artikel.", (ELI.has_part,), "Artikel"),
    "heeftLid": ("heeft lid", "Artikel bevat lid.", (ELI.has_part,), "Lid"),
    "heeftOnderdeel": ("heeft onderdeel", "Bevat lijstonderdeel.", (ELI.has_part,), "Onderdeel"),
    "heeftDivisie": ("heeft divisie", "Bevat circulaire-divisie.", (ELI.has_part,), "Divisie"),
    "heeftBijlage": ("heeft bijlage", "Regeling bevat bijlage.", (ELI.has_part,), "Bijlage"),
    "bevatIllustratie": (
        "bevat illustratie",
        "Tekstdrager bevat een afbeelding.",
        (),
        "Illustratie",
    ),
    "ondertekendDoor": (
        "ondertekend door",
        "Regeling is ondertekend door deze persoon.",
        (ELI.passed_by,),
        "Ondertekenaar",
    ),
    "volgtOp": ("volgt op", "Documentvolgorde binnen dezelfde ouder.", (), None),
    "verwijstNaar": (
        "verwijst naar",
        "Citatie naar een ander citeerbaar tekstdeel (open-world doel).",
        (ELI.cites,),
        "Citeerbaar",
    ),
    "heeftVerwijzing": (
        "heeft verwijzing",
        "Koppelt de gereïficeerde verwijzing aan de bron.",
        (),
        "Verwijzing",
    ),
    "naar": ("naar", "Doel van de gereïficeerde verwijzing.", (), "Citeerbaar"),
    "toestandUrl": (
        "toestand-URL",
        "Identiteit van de geïmporteerde toestand (versie) op wetten.overheid.nl.",
        (),
        None,
    ),
    "heeftGrondslag": (
        "heeft grondslag",
        "Regeling waarop deze regeling (mede) is gebaseerd (uit de WTI).",
        (ELI.based_on,),
        "Regeling",
    ),
    "uitgegevenDoor": (
        "uitgegeven door",
        "Verantwoordelijke organisatie/ministerie van de regeling (uit de WTI).",
        (ELI.responsibility_of,),
        "Organisatie",
    ),
    "inFamilie": (
        "in familie",
        "Verwante regeling binnen dezelfde wetsfamilie (uit de WTI).",
        (),
        "Regeling",
    ),
    "grondslagVoor": (
        "grondslag voor",
        "Regeling die (mede) op dit tekstdeel is gebaseerd (WTI-regelingelement).",
        (),
        "Regeling",
    ),
    "bevoegdheidVoor": (
        "bevoegdheid voor",
        "Regeling waarvoor dit tekstdeel de wettelijke bevoegdheid geeft (WTI).",
        (),
        "Regeling",
    ),
    "verwijzingDoor": (
        "verwijzing door",
        "Regeling die naar dit tekstdeel verwijst (WTI-regelingelement).",
        (),
        "Regeling",
    ),
}

# Datatypeproperty -> (label, toelichting, superproperties, rdfs:range of None).
# Geen range op @nl-getagde tekstprops (langString ≠ xsd:string) en geen
# rdfs:domain op gedeelde props (nummer/tekst/soort leven op meerdere klassen).
_DATA_PROPS: dict[str, tuple[str, str, tuple[URIRef, ...], URIRef | None]] = {
    "bwbId": ("BWB-id", "Identificatie in het Basiswettenbestand.", (), XSD.string),
    "citeertitel": ("citeertitel", "Officiële citeertitel.", (ELI.title,), None),
    "opschrift": (
        "opschrift",
        "Intitulé/opschrift van de regeling.",
        (ELI.title_alternative,),
        None,
    ),
    "soort": ("soort", "Soort regeling of verwijzing.", (), None),
    "geldigVanaf": (
        "geldig vanaf",
        "Begin van het geldigheidsvenster van de toestand.",
        (ELI.first_date_entry_in_force,),
        XSD.date,
    ),
    "geldigTot": ("geldig tot", "Einde van het geldigheidsvenster.", (), XSD.date),
    "publicatiejaar": ("publicatiejaar", "Jaar van de oorspronkelijke publicatie.", (), XSD.gYear),
    "publicatienr": ("publicatienummer", "Nummer van de oorspronkelijke publicatie.", (), None),
    "ondertekeningsdatum": (
        "ondertekeningsdatum",
        "Datum van ondertekening.",
        (ELI.date_document,),
        XSD.date,
    ),
    "uitgiftedatum": ("uitgiftedatum", "Datum van uitgifte.", (ELI.date_publication,), XSD.date),
    "dossier": ("dossier", "Kamerdossiernummer.", (), None),
    "nummer": ("nummer", "Nummer binnen de ouder (artikel-/lid-/onderdeelnummer).", (), None),
    "label": ("label", "Structuurlabel uit de bron-XML.", (), None),
    "titel": ("titel", "Titel van het structuurdeel of de divisie.", (), None),
    "tekst": ("tekst", "Lopende tekst van het tekstdeel.", (), None),
    "refKey": ("ref-sleutel", "JuriConnect-afgeleide identiteitssleutel.", (), XSD.string),
    "labelId": ("label-id", "WTI-koppelsleutel (label-id uit de bron-XML).", (), XSD.string),
    "jci": ("jci", "Ruwe JuriConnect-verwijzing uit de bron.", (), XSD.string),
    "inwerking": ("inwerking", "Datum inwerkingtreding van dit tekstdeel.", (), XSD.date),
    "terugwerkendTot": (
        "terugwerkend tot",
        "Retroactieve ingangsdatum van de wijziging die dit tekstdeel zijn " "huidige inhoud gaf.",
        (),
        XSD.date,
    ),
    "bron": ("bron", "Publicatiebron (bv. Stb.2009-265).", (), None),
    "effect": ("effect", "Effect van de laatste wijziging.", (), None),
    "status": ("status", "Redactionele status.", (), None),
    "wijzigingsbronnen": ("wijzigingsbron", "Stb-bron van een wijziging (<juncto>).", (), None),
    "doelLid": ("doel-lid", "Lidnummer waarop de verwijzing mikt.", (), None),
    "doelSoort": ("doel-soort", "Niveau van het verwijsdoel (artikel/lid/…).", (), None),
    "doelPad": ("doel-pad", "bwb-ng-variabel-deel van het verwijsdoel.", (), None),
    "ankerTekst": ("ankertekst", "Tekst waarmee de verwijzing in de bron staat.", (), None),
    "verwijzingId": ("verwijzing-id", "Bron-id van de verwijzing.", (), XSD.string),
    "betrouwbaarheid": (
        "betrouwbaarheid",
        "Betrouwbaarheid van een gedetecteerde (tekstuele) verwijzing.",
        (),
        None,
    ),
    "doc": ("doc", "Ruwe jci-doc van de verwijzing.", (), XSD.string),
    "aanhef": ("aanhef", "Aanhef van de regeling.", (), None),
    "considerans": ("considerans", "Considerans (overwegingen) van de regeling.", (), None),
    "voetnoot": ("voetnoot", "Voetnoot bij het tekstdeel.", (), None),
    "definieertBegrip": (
        "definieert begrip",
        "Begrip dat in dit tekstdeel wordt gedefinieerd.",
        (),
        None,
    ),
    "afkorting": ("afkorting", "Gangbare afkorting van de regeling (uit de WTI).", (), None),
    "alternatieveTitel": (
        "alternatieve titel",
        "Niet-officiële titel van de regeling (uit de WTI).",
        (ELI.title_alternative,),
        None,
    ),
    "eerstverantwoordelijke": (
        "eerstverantwoordelijke",
        "Eerstverantwoordelijk ministerie (uit de WTI).",
        (),
        None,
    ),
    "naam": ("naam", "Naam (bestandsnaam van een illustratie of naam van een persoon).", (), None),
    "formaat": ("formaat", "Bestandsformaat van een illustratie (bv. png).", (), None),
    "breedte": ("breedte", "Breedte van een illustratie (bv. 1417px).", (), None),
    "hoogte": ("hoogte", "Hoogte van een illustratie (bv. 364px).", (), None),
    "alt": ("alt-tekst", "Alternatieve tekst/bijschrift van een illustratie.", (), None),
    "functie": ("functie", "Functie/hoedanigheid van de ondertekenaar.", (), None),
    "voornaam": ("voornaam", "Voornaam van de ondertekenaar.", (), None),
    "achternaam": ("achternaam", "Achternaam van de ondertekenaar.", (), None),
    "plaats": ("plaats", "Plaats van ondertekening.", (), None),
}


def build_ontology(vocab: Vocab) -> Graph:
    """Bouw de T-Box-graaf (puur; geen HTTP)."""
    g = Graph()
    g.bind("bwb", vocab.ns)
    g.bind("eli", ELI)
    g.bind("owl", OWL)

    g.add((vocab.ontology_resource, RDF.type, OWL.Ontology))
    g.add((vocab.ontology_resource, RDFS.label, Literal("BWB-ontologie", lang="nl")))
    g.add(
        (
            vocab.ontology_resource,
            RDFS.comment,
            Literal("Vocabulaire voor het Basiswettenbestand, gealigneerd op ELI.", lang="nl"),
        )
    )

    for naam, (label, comment, supers) in _KLASSEN.items():
        klasse = vocab.klasse(naam)
        g.add((klasse, RDF.type, OWL.Class))
        g.add((klasse, RDFS.label, Literal(label, lang="nl")))
        g.add((klasse, RDFS.comment, Literal(comment, lang="nl")))
        for super_ in supers:
            # Let op: URIRef is een str-subklasse, dus expliciet daarop testen.
            doel = super_ if isinstance(super_, URIRef) else vocab.klasse(super_)
            g.add((klasse, RDFS.subClassOf, doel))

    for naam, (label, comment, supers, range_) in _OBJECT_PROPS.items():
        prop = vocab.ns[naam]
        g.add((prop, RDF.type, OWL.ObjectProperty))
        g.add((prop, RDFS.label, Literal(label, lang="nl")))
        g.add((prop, RDFS.comment, Literal(comment, lang="nl")))
        for super_ in supers:
            g.add((prop, RDFS.subPropertyOf, super_))
        if range_ is not None:
            g.add((prop, RDFS.range, vocab.klasse(range_)))

    for naam, (label, comment, supers, range_) in _DATA_PROPS.items():
        prop = vocab.ns[naam]
        g.add((prop, RDF.type, OWL.DatatypeProperty))
        g.add((prop, RDFS.label, Literal(label, lang="nl")))
        g.add((prop, RDFS.comment, Literal(comment, lang="nl")))
        for super_ in supers:
            g.add((prop, RDFS.subPropertyOf, super_))
        if range_ is not None:
            g.add((prop, RDFS.range, range_))

    return g


def gedeclareerde_termen(vocab: Vocab) -> set[URIRef]:
    """Alle bwb-termen (klassen + properties) die de ontologie declareert."""
    termen = {vocab.klasse(naam) for naam in _KLASSEN}
    termen |= {vocab.ns[naam] for naam in _OBJECT_PROPS}
    termen |= {vocab.ns[naam] for naam in _DATA_PROPS}
    return termen
