"""Wegschrijven van het BWB-model naar GraphDB (RDF/SPARQL).

Consumeert de :class:`~app.collect.Batch` en vertaalt die naar triples volgens
het custom vocabulaire (:mod:`app.rdf_vocab`). Elke wet
komt in een eigen named graph; bij (her)import wordt die graaf integraal
vervangen (RDF4J Graph Store ``PUT``) → idempotent.

Cross-referenties (``verwijstNaar``) wijzen naar de ref_key-afgeleide doel-IRI.
Die doel-IRI hoeft nog niet te bestaan: RDF is open-world, dus de node krijgt
vanzelf inhoud zodra de doelwet later wordt geïmporteerd.
"""

from __future__ import annotations

import json
import logging

import requests
from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace, URIRef

from app.collect import collect
from app.models import ImportSummary, Wet
from app.ontology import build_ontology
from app.rdf_vocab import Vocab
from app.wti_parser import WtiInfo

logger = logging.getLogger(__name__)

DCTERMS = Namespace("http://purl.org/dc/terms/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

_STRUCTUUR = {"Hoofdstuk", "Titeldeel", "Afdeling", "Paragraaf"}

# bwb:soort (letterlijke bronwaarde, incl. casing) -> subklasse van bwb:Regeling.
# Onbekende soorten krijgen alleen het generieke type bwb:Regeling.
_SOORT_KLASSE = {
    "wet": "Wet",
    "AMvB": "AMvB",
    "KB": "KoninklijkBesluit",
    "ministeriele-regeling": "MinisterieleRegeling",
    "beleidsregel": "Beleidsregel",
    "circulaire": "Circulaire",
}


def _rdfs_label(entiteit: str, props: dict) -> str:
    """Leesbaar label per node (voor GraphDB's Visual Graph en de 3D-viewer)."""
    nummer = props.get("nummer")
    if entiteit == "Regeling":
        return (
            props.get("citeertitel") or props.get("opschrift") or props.get("bwb_id") or "Regeling"
        )
    if entiteit in _STRUCTUUR:
        basis = props.get("label") or entiteit
        if nummer:
            basis = f"{basis} {nummer}"
        titel = props.get("titel")
        return f"{basis} — {titel}" if titel else basis
    if entiteit == "Artikel":
        return props.get("label") or (f"Artikel {nummer}" if nummer else "Artikel")
    if entiteit == "Divisie":
        return (
            props.get("titel")
            or props.get("label")
            or (f"Divisie {nummer}" if nummer else "Divisie")
        )
    if entiteit == "Bijlage":
        basis = props.get("label") or (f"Bijlage {nummer}" if nummer else "Bijlage")
        titel = props.get("titel")
        return f"{basis} — {titel}" if titel else basis
    if entiteit == "Illustratie":
        return props.get("naam") or props.get("alt") or "Illustratie"
    if entiteit == "Ondertekenaar":
        return (
            props.get("naam") or props.get("achternaam") or props.get("functie") or "Ondertekenaar"
        )
    if entiteit == "Lid":
        return f"Lid {nummer}" if nummer else "Lid"
    if entiteit == "Onderdeel":
        return f"Onderdeel {nummer}" if nummer else "Onderdeel"
    return props.get("label") or props.get("titel") or entiteit


def _doel_label(row: dict) -> str | None:
    """Leesbaar fallback-label voor een (nog) niet-geïmporteerd verwijsdoel."""
    soort, bwb, nummer = row.get("doel_soort"), row.get("to_bwb"), row.get("to_nummer")
    if not bwb:
        return None
    if soort in ("artikel", "lid", "onderdeel") and nummer:
        return f"art. {nummer} ({bwb})"
    if soort == "wet":
        return bwb
    if nummer:
        return f"{soort} {nummer} ({bwb})"
    return None


# Naam van de Lucene-FTS-connector (GraphDB Connectors).
_FTS_CONNECTOR_NAAM = "bwb_tekst"
_LUC = "http://www.ontotext.com/connectors/lucene#"
_LUC_INST = "http://www.ontotext.com/connectors/lucene/instance#"

# Entiteiten en tekstprops die full-text doorzoekbaar moeten zijn.
_FTS_TYPES = (
    "Regeling",
    "Hoofdstuk",
    "Titeldeel",
    "Afdeling",
    "Paragraaf",
    "Artikel",
    "Lid",
    "Onderdeel",
    "Divisie",
    "Bijlage",
)
_FTS_VELDEN = (
    "tekst",
    "titel",
    "citeertitel",
    "opschrift",
    "aanhef",
    "considerans",
    "voetnoot",
    "definieertBegrip",
)


def _fts_connector_config(vocab: Vocab) -> dict:
    """createConnector-JSON voor de Lucene-index over de BWB-tekstvelden."""
    ns = str(vocab.ns)
    velden = [
        {"fieldName": naam, "propertyChain": [f"{ns}{naam}"], "analyzed": True}
        for naam in _FTS_VELDEN
    ]
    velden.append({"fieldName": "label", "propertyChain": [str(RDFS.label)], "analyzed": True})
    return {
        "types": [f"{ns}{t}" for t in _FTS_TYPES],
        "fields": velden,
        # Zowel @nl-getagde als ongetagde literals indexeren.
        "languages": ["nl", ""],
        "analyzer": "org.apache.lucene.analysis.nl.DutchAnalyzer",
    }


def _config_omvat(gewenst, bestaand) -> bool:
    """Is de gewenste config (recursief) vervat in de bestaande?

    GraphDB's ``listConnectors`` geeft de config terug aangevuld met defaults
    (per veld o.a. ``indexed``/``multivalued``); die extra sleutels mogen geen
    herindexering triggeren.
    """
    if isinstance(gewenst, dict):
        return isinstance(bestaand, dict) and all(
            _config_omvat(waarde, bestaand.get(sleutel)) for sleutel, waarde in gewenst.items()
        )
    if isinstance(gewenst, list):
        return (
            isinstance(bestaand, list)
            and len(gewenst) == len(bestaand)
            and all(_config_omvat(a, b) for a, b in zip(gewenst, bestaand, strict=True))
        )
    return gewenst == bestaand


# Minimale repository-config (RDF4J/GraphDB SAIL) voor auto-aanmaak.
_REPO_CONFIG_TTL = """\
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>.
@prefix rep: <http://www.openrdf.org/config/repository#>.
@prefix sr: <http://www.openrdf.org/config/repository/sail#>.
@prefix sail: <http://www.openrdf.org/config/sail#>.
@prefix graphdb: <http://www.ontotext.com/config/graphdb#>.

[] a rep:Repository ;
    rep:repositoryID "{repo}" ;
    rdfs:label "{repo}" ;
    rep:repositoryImpl [
        rep:repositoryType "graphdb:SailRepository" ;
        sr:sailImpl [
            sail:sailType "graphdb:Sail" ;
            graphdb:ruleset "rdfsplus-optimized" ;
            graphdb:base-URL "http://example.org/{repo}#" ;
            graphdb:repository-type "file-repository" ;
            graphdb:storage-folder "storage" ;
            graphdb:enable-context-index "true" ;
            graphdb:enablePredicateList "true" ;
            graphdb:enable-literal-index "true" ;
        ]
    ].
"""


class GraphDbWriter:
    """Schrijft een :class:`~app.models.Wet` als RDF naar een GraphDB-repository."""

    def __init__(
        self,
        *,
        url: str,
        repository: str,
        vocab: Vocab,
        user: str | None = None,
        password: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 60.0,
        tekstuele_refs: bool = True,
    ) -> None:
        self._url = url.rstrip("/")
        self._repo = repository
        self._vocab = vocab
        self._auth = (user, password) if user else None
        self._http = session or requests.Session()
        self._timeout = timeout
        self._tekstuele_refs = tekstuele_refs

    # ------------------------------------------------------------------ endpoints
    @property
    def _statements(self) -> str:
        return f"{self._url}/repositories/{self._repo}/statements"

    @property
    def _graph_store(self) -> str:
        return f"{self._url}/repositories/{self._repo}/rdf-graphs/service"

    # ------------------------------------------------------------- repo waarborgen
    def ensure_constraints(self) -> None:
        """Zorg dat de repository bestaat (maak 'm anders aan). RDF heeft geen
        constraints/indexen nodig; de naam sluit aan op de importpijplijn."""
        resp = self._http.get(
            f"{self._url}/rest/repositories", auth=self._auth, timeout=self._timeout
        )
        resp.raise_for_status()
        bestaand = {r.get("id") for r in resp.json()}
        if self._repo in bestaand:
            logger.info("GraphDB-repository %s bestaat al", self._repo)
            return
        config = _REPO_CONFIG_TTL.format(repo=self._repo)
        create = self._http.post(
            f"{self._url}/rest/repositories",
            files={"config": (f"{self._repo}.ttl", config, "text/turtle")},
            auth=self._auth,
            timeout=self._timeout,
        )
        create.raise_for_status()
        logger.info("GraphDB-repository %s aangemaakt", self._repo)

    # ------------------------------------------------------------------ schrijven
    def build_graph(self, wet: Wet, wti: WtiInfo | None = None) -> tuple[Graph, ImportSummary]:
        """Bouw de RDF-graaf voor één wet uit de gedeelde ``Batch`` (geen HTTP)."""
        batch, summary = collect(wet, tekstuele_refs=self._tekstuele_refs)
        v = self._vocab
        g = Graph()
        g.bind("bwb", v.ns)
        g.bind("dcterms", DCTERMS)
        g.bind("skos", SKOS)

        # 1) Nodes -> klassen + literals; onthoud id -> IRI voor de relaties.
        # Een node mét ref_key is JuriConnect-adresseerbaar: IRI uit de
        # ref_key (= verwijs-doel-IRI, open-world) + het Citeerbaar-type.
        iri_by_id: dict[str, URIRef] = {}
        # label-id -> IRI, voor het koppelen van WTI-regelingelementen aan hun node.
        label_iri: dict[str, URIRef] = {}
        for entiteit, rows in batch.nodes.items():
            klasse = v.klasse(entiteit)
            for row in rows:
                ref_key = row.get("ref_key")
                # Een wet-overstijgende entiteit (ondertekenaar/organisatie/…)
                # krijgt een deterministische slug-IRI zodat dezelfde entiteit over
                # wetten heen samenvalt; anders de ref_key-IRI (JuriConnect-
                # adresseerbaar) of een wet-lokale by_id-IRI.
                if row.get("iri_soort"):
                    iri = v.entiteit(row["iri_soort"], row["iri_sleutel"])
                elif ref_key:
                    iri = v.by_ref_key(ref_key)
                else:
                    iri = v.by_id(wet.bwb_id, row["id"])
                iri_by_id[row["id"]] = iri
                if row.get("label_id"):
                    label_iri[row["label_id"]] = iri
                g.add((iri, RDF.type, klasse))
                # Documenttype als subklasse van bwb:Regeling; expliciet
                # geassert (naast de inferentie) zodat exports zonder
                # inferentie het type zien.
                if entiteit == "Regeling":
                    subklasse = _SOORT_KLASSE.get(row.get("soort") or "")
                    if subklasse:
                        g.add((iri, RDF.type, v.klasse(subklasse)))
                if ref_key:
                    g.add((iri, RDF.type, v.klasse("Citeerbaar")))
                    # Canonieke identiteit op wetten.overheid.nl (jci-resolver).
                    canoniek = v.canonieke_url(ref_key)
                    if canoniek is not None:
                        g.add((iri, OWL.sameAs, canoniek))
                g.add((iri, RDFS.label, Literal(_rdfs_label(entiteit, row), lang="nl")))
                for key, value in row.items():
                    if v.skip_prop(key) or value is None:
                        continue
                    pred = v.predicaat_prop(key)
                    waarden = value if isinstance(value, list) else [value]
                    for item in waarden:
                        if item is None or item == "":
                            continue
                        g.add((iri, pred, v.literal(key, item)))

        # Toestand-identiteit (versie) op wetten.overheid.nl: ander FRBR-niveau
        # dan de wet zelf, dus een eigen property i.p.v. owl:sameAs.
        if wet.vast_deel_url:
            g.add((v.wet(wet.bwb_id), v.ns.toestandUrl, URIRef(wet.vast_deel_url)))

        # WTI-verrijking (citeertitels, thesaurustermen, grondslagen) — in
        # dezelfde named graph, dus atomair mee-vervangen bij re-import.
        if wti is not None:
            self._wti_verrijking(g, v.wet(wet.bwb_id), wti)
            self._wti_element_relaties(g, label_iri, wti)

        # 2) Structuur- en volgrelaties.
        for (_src, rel_type, _dst), rows in batch.rels.items():
            pred = v.predicaat_rel(rel_type)
            for row in rows:
                a, b = iri_by_id.get(row["from"]), iri_by_id.get(row["to"])
                if a is None or b is None:
                    continue
                g.add((a, pred, b))
            summary.relaties += len(rows)

        # 3) Verwijzingen: directe edge + tussenresource met doel-metadata.
        node_iris = set(iri_by_id.values())
        for row in batch.verwijzingen:
            bron = v.by_ref_key(row["from"])
            doel = v.by_ref_key(row["to"])
            # Extern doel (andere, nog niet geïmporteerde wet): geef het een leesbaar
            # label zodat het in de viewers niet als kaal nummer/IRI verschijnt.
            label = _doel_label(row) if doel not in node_iris else None
            if label:
                g.add((doel, RDFS.label, Literal(label, lang="nl")))
            g.add((bron, v.ns.verwijstNaar, doel))
            vw = v.verwijzing(bron, doel, row["soort"])
            g.add((bron, v.ns.heeftVerwijzing, vw))
            g.add((vw, RDF.type, v.klasse("Verwijzing")))
            g.add((vw, v.ns.naar, doel))
            g.add((vw, v.ns.soort, Literal(row["soort"])))
            for key, prop in (
                ("doc", v.ns.doc),
                ("doel_lid", v.ns.doelLid),
                ("doel_soort", v.ns.doelSoort),
                ("doel_pad", v.ns.doelPad),
                ("verwijzing_id", v.ns.verwijzingId),
                ("betrouwbaarheid", v.ns.betrouwbaarheid),
            ):
                if row.get(key):
                    g.add((vw, prop, Literal(row[key])))
            if row.get("anker_tekst"):
                g.add((vw, v.ns.ankerTekst, Literal(row["anker_tekst"], lang="nl")))
            summary.relaties += 1

        return g, summary

    def ensure_fts_connector(self) -> None:
        """Waarborg de Lucene-FTS-connector (zelfherstellend, idempotent).

        Bestaat de connector niet, dan wordt hij aangemaakt; wijkt zijn
        configuratie af van de gewenste, dan wordt hij opnieuw aangemaakt
        (drop + create = volledige herindexering; gelogd als waarschuwing).
        """
        gewenst = _fts_connector_config(self._vocab)
        bestaand = self._fts_bestaande_config()
        # Subset-vergelijking: GraphDB vult de opgeslagen config aan met
        # defaults; alleen afwijkingen in wat wíj instellen tellen.
        if bestaand is not None and _config_omvat(gewenst, bestaand):
            logger.info("FTS-connector %s bestaat al (config actueel)", _FTS_CONNECTOR_NAAM)
            return
        if bestaand is not None:
            logger.warning(
                "FTS-connector %s heeft een verouderde config; opnieuw aanmaken "
                "(volledige herindexering)",
                _FTS_CONNECTOR_NAAM,
            )
            self._sparql_update(
                f"INSERT DATA {{ <{_LUC_INST}{_FTS_CONNECTOR_NAAM}> <{_LUC}dropConnector> [] }}"
            )
        config_json = json.dumps(gewenst)
        self._sparql_update(
            f"INSERT DATA {{ <{_LUC_INST}{_FTS_CONNECTOR_NAAM}> "
            f"<{_LUC}createConnector> '''{config_json}''' }}"
        )
        logger.info("FTS-connector %s aangemaakt", _FTS_CONNECTOR_NAAM)

    def _fts_bestaande_config(self) -> dict | None:
        """Huidige createConnector-config van de connector, of ``None``."""
        query = (
            f"SELECT ?createString {{ <{_LUC_INST}{_FTS_CONNECTOR_NAAM}> "
            f"<{_LUC}listConnectors> ?createString }}"
        )
        resp = self._http.post(
            f"{self._url}/repositories/{self._repo}",
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            auth=self._auth,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        if not bindings:
            return None
        raw = bindings[0].get("createString", {}).get("value", "")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Sommige GraphDB-versies geven via listConnectors niet de JSON-config
            # maar bv. de connector-naam terug. De connector bestáát dan wél, maar we
            # weten niet wáárop hij indexeert.
            #
            # Dit gaf eerder de gewenste config terug, zodat de subset-check slaagde en
            # er niet onnodig geherindexeerd werd. Die aanname brak bij de overgang naar
            # de URN-namespace: de connector bleef op de oude predicaten staan en de
            # full-text-zoekopdrachten leverden daarna stil nul treffers. Stille
            # zoekuitval is erger dan een herindexering van enkele seconden, dus bij
            # twijfel bouwen we hem opnieuw.
            logger.warning(
                "FTS-connector %s bestaat maar de config is niet uitleesbaar (%r); "
                "opnieuw aanmaken om te voorkomen dat hij op verouderde predicaten blijft staan",
                _FTS_CONNECTOR_NAAM,
                raw,
            )
            return {}

    def _sparql_update(self, update: str) -> None:
        resp = self._http.post(
            f"{self._statements}",
            data={"update": update},
            auth=self._auth,
            timeout=self._timeout,
        )
        resp.raise_for_status()

    def write_ontology(self) -> None:
        """Vervang de ontologie-graaf (T-Box) in GraphDB (PUT = idempotent)."""
        graph = build_ontology(self._vocab)
        self._put_graph(self._vocab.ontology_graph(), graph)
        logger.info("Ontologie naar GraphDB geschreven (%d triples)", len(graph))

    def _put_graph(self, graph_iri: URIRef, graph: Graph) -> None:
        """RDF4J Graph Store PUT: vervang één named graph integraal."""
        resp = self._http.put(
            self._graph_store,
            params={"graph": str(graph_iri)},
            data=graph.serialize(format="turtle").encode("utf-8"),
            headers={"Content-Type": "text/turtle"},
            auth=self._auth,
            timeout=self._timeout,
        )
        resp.raise_for_status()

    def _wti_verrijking(self, g: Graph, wet_iri: URIRef, wti: WtiInfo) -> None:
        """WTI-triples op de wet-node: titels, thesaurustermen, grondslagen."""
        v = self._vocab
        for titel in wti.citeertitels:
            g.add((wet_iri, v.ns.citeertitel, Literal(titel, lang="nl")))
        for titel in wti.niet_officiele_titels:
            g.add((wet_iri, v.ns.alternatieveTitel, Literal(titel, lang="nl")))
        for afkorting in wti.afkortingen:
            g.add((wet_iri, v.ns.afkorting, Literal(afkorting)))
        if wti.eerstverantwoordelijke:
            g.add((wet_iri, v.ns.eerstverantwoordelijke, Literal(wti.eerstverantwoordelijke)))
        if wti.authority:
            # Verantwoordelijke organisatie als wet-overstijgende node (dezelfde
            # organisatie valt over regelingen heen samen op de slug-IRI).
            org = v.entiteit("organisatie", wti.authority)
            g.add((org, RDF.type, v.klasse("Organisatie")))
            g.add((org, RDFS.label, Literal(wti.authority, lang="nl")))
            g.add((org, v.ns.naam, Literal(wti.authority, lang="nl")))
            g.add((wet_iri, v.ns.uitgegevenDoor, org))
        for bwb_id in wti.wetsfamilie:
            g.add((wet_iri, v.ns.inFamilie, v.wet(bwb_id)))
        for hoofd, specifiek in wti.rechtsgebieden:
            hoofd_iri = self._begrip(g, hoofd)
            g.add((wet_iri, DCTERMS.subject, hoofd_iri))
            if specifiek:
                specifiek_iri = self._begrip(g, specifiek)
                g.add((specifiek_iri, SKOS.broader, hoofd_iri))
                g.add((wet_iri, DCTERMS.subject, specifiek_iri))
        for domein in wti.overheidsdomeinen:
            g.add((wet_iri, DCTERMS.subject, self._begrip(g, domein)))
        for bwb_id in wti.grondslagen:
            g.add((wet_iri, v.ns.heeftGrondslag, v.wet(bwb_id)))

    def _wti_element_relaties(self, g: Graph, label_iri: dict[str, URIRef], wti: WtiInfo) -> None:
        """Per-regelingelement uitgaande relaties uit de WTI: koppel het
        tekstdeel (via ``label-id``) aan de regelingen waarvoor het grondslag/
        bevoegdheid is, of die ernaar verwijzen. Doelen zijn open-world wet-IRI's."""
        v = self._vocab
        for label_id, rel in wti.element_relaties.items():
            bron = label_iri.get(label_id)
            if bron is None:
                continue  # geen node met dit label-id in deze wet
            for pred, bwb_ids in (
                (v.ns.grondslagVoor, rel.grondslag_voor),
                (v.ns.bevoegdheidVoor, rel.bevoegdheid_voor),
                (v.ns.verwijzingDoor, rel.verwijzing_door),
            ):
                for bwb_id in bwb_ids:
                    g.add((bron, pred, v.wet(bwb_id)))

    def _begrip(self, g: Graph, label: str) -> URIRef:
        """skos:Concept voor een thesaurusterm; convergeert open-world op slug-IRI."""
        iri = self._vocab.begrip(label)
        g.add((iri, RDF.type, SKOS.Concept))
        g.add((iri, SKOS.prefLabel, Literal(label, lang="nl")))
        g.add((iri, RDFS.label, Literal(label, lang="nl")))
        return iri

    def write_wet(self, wet: Wet, wti: WtiInfo | None = None) -> ImportSummary:
        """Bouw de graaf en vervang de named graph van deze wet in GraphDB."""
        graph, summary = self.build_graph(wet, wti=wti)
        self._put_graph(self._vocab.graph(wet.bwb_id), graph)
        logger.info("Wet %s naar GraphDB geschreven: %s", wet.bwb_id, summary.as_dict())
        return summary
