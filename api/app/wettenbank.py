"""MCP-client naar de wettenbank — deterministisch ophalen (stap 1), geen LLM-tool-calling.

De MCP geeft per tool één text-content-block terug waarvan de tekst een JSON-string is.
We parsen dat en geven een dict terug. Een lege of fout-respons werpt WettenbankError: de
brongetrouwheidseis verbiedt dat een MCP-mis stil tot lege context (en dus hallucinatie) leidt.
"""

from __future__ import annotations

import asyncio
import json
import re

from .config import Settings


class WettenbankError(RuntimeError):
    """Ophalen mislukte of leverde niets — de job moet stoppen, niet doorgaan.

    `klasse` draagt de MCP-foutklasse (transient/permanent/client/onbekend) zodat de
    aanroeper permanente client-fouten (bv. niet-bestaand artikel) kan onderscheiden
    van tijdelijke haperingen; None als de klasse niet uit de respons te halen was.
    """

    def __init__(self, message: str, *, klasse: str | None = None) -> None:
        super().__init__(message)
        self.klasse = klasse


def _diepste_fout(e: BaseException) -> BaseException:
    """Loop door een (anyio-)ExceptionGroup naar de eigenlijke onderliggende fout."""
    excs = getattr(e, "exceptions", None)
    while excs:
        e = excs[0]
        excs = getattr(e, "exceptions", None)
    return e


class WettenbankClient:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.mcp_url
        self.token = settings.mcp_token
        self.timeout = settings.mcp_timeout_s

    async def call(self, tool: str, args: dict) -> dict:
        try:
            return await asyncio.wait_for(self._call(tool, args), timeout=self.timeout)
        except asyncio.TimeoutError as e:
            raise WettenbankError(f"MCP-timeout op {tool} na {self.timeout}s") from e
        except WettenbankError:
            raise
        except Exception as e:  # noqa: BLE001 — alle transportfouten → WettenbankError
            inner = _diepste_fout(e)
            if isinstance(inner, WettenbankError):
                raise inner from e
            raise WettenbankError(f"MCP-fout op {tool}: {inner}") from e

    async def _call(self, tool: str, args: dict) -> dict:
        # Lazy import: de mcp-client is alleen nodig bij echt ophalen, niet in elke testopzet.
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client

        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        # mcp v2: streamable_http_client neemt geen `headers=` meer; auth loopt via een
        # user-supplied httpx-client. Die entering doen we zelf (streamable_http_client
        # beheert de lifecycle niet als je hem meegeeft) — anders lekken connections.
        async with create_mcp_http_client(headers=headers) as http_client:
            async with streamable_http_client(self.url, http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, args)
        # Parse ná het sluiten van de sessie: zo wordt een WettenbankError niet in de
        # anyio-TaskGroup verpakt en propageert de nette melding (bv. "fetch failed").
        return self._parse(tool, result)

    @staticmethod
    def _parse(tool: str, result) -> dict:
        blocks = getattr(result, "content", None) or []
        teksten = [getattr(b, "text", "") for b in blocks if getattr(b, "type", "") == "text"]
        if not teksten:
            raise WettenbankError(f"MCP gaf geen tekst terug voor {tool}")
        if getattr(result, "is_error", False):
            # De MCP-server stuurt de fout als JSON-payload {"fout", "foutCode"?, "klasse"?};
            # de klasse best-effort meenemen zodat retry/routers client-fouten herkennen.
            klasse = None
            try:
                payload = json.loads(teksten[0])
                if isinstance(payload, dict):
                    k = payload.get("klasse")
                    klasse = k if isinstance(k, str) else None
            except json.JSONDecodeError:
                pass
            raise WettenbankError(f"MCP-fout voor {tool}: {teksten[0]}", klasse=klasse)
        try:
            data = json.loads(teksten[0])
        except json.JSONDecodeError as e:
            raise WettenbankError(f"MCP-respons voor {tool} is geen JSON: {e}") from e
        return data

    # --- convenience ------------------------------------------------------

    async def artikel(self, bwb_id: str, artikel: str, lid: str | None = None) -> dict:
        args = {"bwbId": bwb_id, "artikel": artikel}
        if lid:
            args["lid"] = lid
        return await self.call("wettenbank_artikel", args)

    async def zoek(self, **kwargs) -> dict:
        return await self.call("wettenbank_zoek", kwargs)

    async def structuur(self, bwb_id: str) -> dict:
        return await self.call("wettenbank_structuur", {"bwbId": bwb_id})

    async def zoekterm(self, bwb_id: str, zoekterm: str, **kwargs) -> dict:
        return await self.call("wettenbank_zoekterm", {"bwbId": bwb_id, "zoekterm": zoekterm, **kwargs})


def map_artikel_naar_analyse_basis(artikel_data: dict) -> dict:
    """Map de MCP-artikelrespons naar de brongetrouwe basisvelden van analyse.json.

    Deze velden komen UIT de MCP en mogen niet door het LLM verzonnen worden.
    `mcp_verwijzingen` is de door de MCP getagde intref/extref-lijst per lid —
    kandidaten voor de verwijzing-inventaris (activiteit 2a).
    """
    leden = []
    mcp_verwijzingen: list[dict] = []
    for l in (artikel_data.get("leden") or []):
        lidnr = str(l.get("lid", ""))
        leden.append({
            "lid": lidnr,
            "tekst": l.get("tekst", ""),
            **({"bronreferentie": l["bronreferentie"]} if l.get("bronreferentie") else {}),
        })
        for v in (l.get("verwijzingen") or []):
            mcp_verwijzingen.append({"bron_lid": f"lid {lidnr}" if lidnr else "", **v})
    return {
        "wet": artikel_data.get("citeertitel", ""),
        "bwbId": artikel_data.get("bwbId", ""),
        "artikel": str(artikel_data.get("artikel", "")),
        "versiedatum": artikel_data.get("versiedatum", ""),
        "bronreferentie": artikel_data.get("bronreferentie", ""),
        "pad": artikel_data.get("pad", ""),
        "leden": leden,
        "mcp_verwijzingen": mcp_verwijzingen,
    }


def map_artikel_naar_bron_basis(
    artikel_data: dict, bron_id: str, lid: str | None = None, label: str = ""
) -> dict:
    """Als map_artikel_naar_analyse_basis, maar voor één **bron** in het werkgebied: voegt
    `bron_id`, `label` en `lid` toe. Het `label` is leesbaar (bv. "Zvw art. 43 lid 2"); valt
    terug op een afleiding uit citeertitel/artikel/lid."""
    basis = map_artikel_naar_analyse_basis(artikel_data)
    if not label:
        wet = basis["wet"] or basis["bwbId"]
        lid_str = f" lid {lid}" if lid else ""
        label = f"{wet} art. {basis['artikel']}{lid_str}".strip()
    return {"bron_id": bron_id, "label": label, "lid": lid, **basis}


def parse_jci(target: str) -> tuple[str, str, str | None] | None:
    """Haal (bwbId, artikel, lid?) uit een JCI/BWB-verwijzing-target, zodat de orchestrator
    het verwezen artikel via wettenbank_artikel kan ophalen. Heterogeen formaat: een volledige
    JCI (`jci1.3:c:BWBR...&artikel=..&lid=..`), of een kale BWB-id. Geeft None als er geen
    artikel uit te halen is (dan valt er niets te fetchen).
    """
    if not target:
        return None
    m_bwb = re.search(r"BWB[RVW]\d+", target, re.IGNORECASE)
    if not m_bwb:
        return None
    bwb = m_bwb.group(0)
    m_art = re.search(r"[&?]artikel=([^&]+)", target)
    if not m_art:
        return None
    m_lid = re.search(r"[&?]lid=([^&]+)", target)
    return bwb, m_art.group(1), (m_lid.group(1) if m_lid else None)
