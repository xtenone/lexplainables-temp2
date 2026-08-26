"""Download van BWB-bronbestanden: toestand-XML, WTI, manifest en XSD's.

De ``BwbDownloader`` ontdekt beschikbare toestanden via de SRU-zoekdienst en
haalt de gewenste toestand-XML op, met lokale caching. Een ``requests.Session``
wordt geïnjecteerd zodat de download-laag testbaar is.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from lxml import etree

from app.config import Settings
from app.models import ToestandRef

logger = logging.getLogger(__name__)

# Namespaces in het SRU-antwoord (geverifieerd).
_SRU_NS = {
    "sru": "http://docs.oasis-open.org/ns/search-ws/sruResponse",
    "gzd": "http://standaarden.overheid.nl/sru",
    "dcterms": "http://purl.org/dc/terms/",
    "bwb": "http://standaarden.overheid.nl/bwb/terms/",
}

# XSD-schema-namespace voor het volgen van imports/includes/redefines.
_XSD_NS = "http://www.w3.org/2001/XMLSchema"


class DownloadError(RuntimeError):
    """Een download of discovery is mislukt."""


class BwbDownloader:
    """Haalt BWB-bronbestanden op met lokale caching."""

    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", "bwb-import/0.1 (+legal-tech ETL)")

    # ----------------------------------------------------------------- discovery
    def discover_toestanden(self, bwb_id: str) -> list[ToestandRef]:
        """Vraag alle toestanden (versies) van een regeling op via SRU.

        De lijst is gesorteerd op geldigheidsstartdatum (oudste eerst).
        """
        params = {
            "operation": "searchRetrieve",
            "version": "2.0",
            "x-connection": "BWB",
            "maximumRecords": "1000",
            "query": f"dcterms.identifier={bwb_id}",
        }
        logger.info("SRU-discovery voor %s", bwb_id)
        # De SRU-dienst kan HTTP 406 teruggeven terwijl de body een valide
        # searchRetrieveResponse is; we beoordelen daarom de inhoud, niet de status.
        response = self._session.get(self._settings.sru_base_url, params=params, timeout=60)
        if not response.content:
            raise DownloadError(f"Lege SRU-respons voor {bwb_id} (HTTP {response.status_code})")

        try:
            root = etree.fromstring(response.content)
        except etree.XMLSyntaxError as exc:  # pragma: no cover - defensief
            raise DownloadError(f"Onleesbare SRU-respons voor {bwb_id}: {exc}") from exc

        toestanden: list[ToestandRef] = []
        for record in root.iterfind(".//gzd:gzd", _SRU_NS):
            ref = self._parse_record(record, bwb_id)
            if ref is not None:
                toestanden.append(ref)

        if not toestanden:
            raise DownloadError(f"Geen toestanden gevonden voor {bwb_id}")

        toestanden.sort(key=lambda t: t.geldig_vanaf or "")
        logger.info("%d toestanden gevonden voor %s", len(toestanden), bwb_id)
        return toestanden

    def _parse_record(self, gzd: etree._Element, bwb_id: str) -> ToestandRef | None:
        locatie = gzd.findtext(".//bwb:locatie_toestand", namespaces=_SRU_NS)
        if not locatie:
            return None
        return ToestandRef(
            bwb_id=bwb_id,
            locatie_toestand=locatie,
            geldig_vanaf=gzd.findtext(".//bwb:geldigheidsperiode_startdatum", namespaces=_SRU_NS),
            geldig_tot=gzd.findtext(".//bwb:geldigheidsperiode_einddatum", namespaces=_SRU_NS),
            zicht_vanaf=gzd.findtext(".//bwb:zichtperiode_startdatum", namespaces=_SRU_NS),
            zicht_tot=gzd.findtext(".//bwb:zichtperiode_einddatum", namespaces=_SRU_NS),
            locatie_wti=gzd.findtext(".//bwb:locatie_wti", namespaces=_SRU_NS),
            locatie_manifest=gzd.findtext(".//bwb:locatie_manifest", namespaces=_SRU_NS),
        )

    def latest_toestand(self, bwb_id: str) -> ToestandRef:
        """Geef de meest recente toestand (hoogste geldigheidsstartdatum)."""
        toestanden = self.discover_toestanden(bwb_id)
        latest = toestanden[-1]
        logger.info("Nieuwste toestand %s: geldig vanaf %s", bwb_id, latest.geldig_vanaf or "?")
        return latest

    # ------------------------------------------------------------------ download
    def download_toestand(self, bwb_id: str, ref: ToestandRef | None = None) -> Path:
        """Download (en cache) de toestand-XML. Gebruikt de nieuwste indien geen ref."""
        ref = ref or self.latest_toestand(bwb_id)
        target = self._cache_path(bwb_id, ref.locatie_toestand)
        return self._download_to(ref.locatie_toestand, target)

    def download_wti(self, ref: ToestandRef) -> Path | None:
        if not ref.locatie_wti:
            return None
        target = self._cache_path(ref.bwb_id, ref.locatie_wti)
        return self._download_to(ref.locatie_wti, target)

    def download_manifest(self, ref: ToestandRef) -> Path | None:
        if not ref.locatie_manifest:
            return None
        target = self._cache_path(ref.bwb_id, ref.locatie_manifest)
        return self._download_to(ref.locatie_manifest, target)

    def _cache_path(self, bwb_id: str, url: str) -> Path:
        return self._settings.data_dir / bwb_id / url.rsplit("/", 1)[-1]

    def _download_to(self, url: str, target: Path) -> Path:
        if target.exists() and target.stat().st_size > 0:
            logger.info("Cache-hit: %s", target)
            return target
        logger.info("Download %s -> %s", url, target)
        response = self._session.get(url, timeout=120)
        if response.status_code != 200 or not response.content:
            raise DownloadError(f"Download mislukt ({response.status_code}) voor {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target

    # --------------------------------------------------------------------- XSD's
    def fetch_schemas(self, entry_url: str) -> Path:
        """Download een XSD plus al zijn afhankelijkheden naar de schemas-map.

        Volgt ``xs:import``/``xs:include``/``xs:redefine`` recursief, zodat lxml
        het schema lokaal kan oplossen (de redefine van ``toestand_base`` is
        relatief). Geeft het pad naar het ingangs-XSD terug.
        """
        self._settings.schemas_dir.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        entry_path = self._fetch_schema_recursive(entry_url, seen)
        logger.info("XSD's opgehaald (%d bestanden) in %s", len(seen), self._settings.schemas_dir)
        return entry_path

    def _fetch_schema_recursive(self, url: str, seen: set[str]) -> Path:
        if url in seen:
            return self._settings.schemas_dir / url.rsplit("/", 1)[-1]
        seen.add(url)

        response = self._session.get(url, timeout=60)
        if response.status_code != 200 or not response.content:
            raise DownloadError(f"XSD-download mislukt ({response.status_code}) voor {url}")
        filename = url.rsplit("/", 1)[-1]
        target = self._settings.schemas_dir / filename
        target.write_bytes(response.content)

        base = url.rsplit("/", 1)[0]
        schema = etree.fromstring(response.content)
        for tag in ("import", "include", "redefine"):
            for node in schema.iter(f"{{{_XSD_NS}}}{tag}"):
                location = node.get("schemaLocation")
                if location and not location.startswith("http"):
                    self._fetch_schema_recursive(f"{base}/{location}", seen)
        return target
