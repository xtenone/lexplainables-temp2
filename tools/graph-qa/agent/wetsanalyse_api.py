"""
Client naar de wetsanalyse-API: hier legt graph-qa de uitkomst van een beurt vast.

Waarom deze richting bestaat. Tot nu toe schreef de **browser** het resultaat weg, ná afloop van de
stream. Dat betekende: wie zijn tabblad sloot voordat de agent klaar was, verloor het werk — ook als
de agent zijn beurt keurig had afgemaakt. Bij een annotatie is dat 60 tot 90 seconden werk. Met deze
client hoeft er aan het eind niemand meer te kijken.

Drie dingen om te weten:

- **Namens wie.** De API kent twee lagen: een client-bearer (wie ben je, `WETSANALYSE_API_TOKENS`) en
  de header `X-User-Id` (namens wie handel je). graph-qa krijgt een eigen client-id; de userid komt
  per beurt mee in het verzoek. Daarmee is dit token een schrijfprimitief op elk gebruikersgesprek —
  vandaar dat graph-qa intern-only blijft en zijn eigen endpoint een token móét hebben
  (`Settings.require_api`).
- **Idempotent waar het telt.** Het `run_id` reist mee met de chatbeurt; de API weigert een tweede
  bericht met datzelfde id. Zo levert opnieuw proberen geen dubbel antwoord op.
- **Falen mag de beurt niet opeten.** Kan er niet geschreven worden, dan is dat een fout in het log
  en een `error`-event richting de werkplek — nooit een stilzwijgend verlies.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger("graph_qa.api")

# Ruim genoeg voor een PUT met tientallen elementen, krap genoeg dat een hangende api de run niet
# eindeloos ophoudt.
TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)


#: Velden waar de agent en de api een ándere opvatting van "geen waarde" hebben: de agent gebruikt de
#: lege string (`aandacht: str = ""`), de api een enum met `None` (`Aandacht | None`). Zo'n lege
#: string is voor de api geen geldige waarde maar een 422 — en omdat de PUT alles-of-niets is, sleurt
#: één zo'n veld de complete annotatie mee. Dat is op dev gebeurd: agent klaar en gegrond, jurist een
#: leeg document.
#:
#: De vertaling hoort hier, op de grens, en niet bij elke aanroeper: dit is de enige plek waar de
#: agent-representatie het contract van een ánder proces binnengaat. `tests/test_contract_drift.py`
#: bewaakt dat er geen vierde veld bijkomt zonder dat iemand het merkt.
def _leeg_is_niets(waarde: dict[str, Any], veld: str = "aandacht") -> dict[str, Any]:
    return waarde if waarde.get(veld) else {**waarde, veld: None}


def naar_contract(element: dict[str, Any]) -> dict[str, Any]:
    """Eén element in de vorm die `ElementInvoer` accepteert. Zie `_leeg_is_niets`."""
    uit = _leeg_is_niets(element)
    rondes = uit.get("critic_rondes")
    if rondes:
        uit = {**uit, "critic_rondes": [_leeg_is_niets(r) for r in rondes]}
    return uit


class WetsanalyseApiFout(Exception):
    """De uitkomst kon niet worden vastgelegd. Expliciet, want stil verliezen is het ergste."""

    def __init__(self, melding: str, status: int = 0) -> None:
        super().__init__(melding)
        self.status = status


class GesprekVerdwenen(WetsanalyseApiFout):
    """Het gesprek bestaat niet meer — meestal omdat de jurist het verwijderde terwijl de beurt liep.

    Geen storing, maar een gevolg van een bewuste handeling. De api weigert terecht: erin schrijven
    zou een verwijderd gesprek half laten herrijzen. De aanroeper hoort hier stil te eindigen in
    plaats van alarm te slaan over iets wat de gebruiker zelf deed."""


class WetsanalyseApi:
    """Dunne HTTP-client. Eén instantie per beurt; sluit hem met `aclose()`."""

    def __init__(self, settings: Settings, user_id: str) -> None:
        self._basis = settings.wetsanalyse_api_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.wetsanalyse_api_token}",
            # Namens wie we schrijven. De api vertrouwt deze header van een geldige client.
            "X-User-Id": user_id,
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(timeout=TIMEOUT)
        #: Hoeveel markeringen de api liet vallen bij de laatste `zet_elementen`. Zie daar.
        self.verworpen = 0
        self._laatste_headers: dict[str, str] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, pad: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._verstuur("POST", pad, payload)

    async def _put(self, pad: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._verstuur("PUT", pad, payload)

    async def _verstuur(self, methode: str, pad: str, payload: dict[str, Any]) -> dict[str, Any]:
        antwoord = await self._client.request(
            methode, f"{self._basis}{pad}", json=payload, headers=self._headers,
        )
        self._laatste_headers = dict(antwoord.headers)
        if antwoord.status_code == 404 and "/gesprekken/" in pad:
            raise GesprekVerdwenen(f"{methode} {pad} → 404", 404)
        if antwoord.status_code >= 400:
            # De ruwe body kan gebruikersinhoud bevatten; log de status en het pad, niet de payload.
            logger.error(
                "api-schrijffout",
                extra={"categorie": "technisch", "http_status": antwoord.status_code, "http_path": pad},
            )
            raise WetsanalyseApiFout(f"{methode} {pad} → {antwoord.status_code}", antwoord.status_code)
        return antwoord.json() if antwoord.content else {}

    # -- annotatie-domein ------------------------------------------------------------------------

    async def maak_document(self, *, bwb_id: str, artikel: str, lid: str, citeertitel: str) -> str:
        """Maak het annotatiedocument en geef de slug terug.

        Bewust pas hier, aan het eind van de beurt, en niet zodra het doel bekend is: `emit_node` is
        terminaal, dus een run die eerder sneuvelt heeft nul elementen. Een document dat dan al
        bestond zou als leeg skelet in de werkvoorraad van de jurist blijven staan.
        """
        doc = await self._post("/v1/annotatie/documenten", {
            "bwbId": bwb_id,
            "artikel": artikel,
            "lid": lid or None,
            # De wetnaam hoort in `citeertitel`; `werkgebied` blijft leeg tot de jurist er zelf een
            # kennisdomein van maakt.
            "citeertitel": citeertitel,
        })
        return str(doc.get("slug", ""))

    async def zet_elementen(
        self,
        slug: str,
        *,
        elementen: list[dict[str, Any]],
        suggesties: list[dict[str, Any]],
        run: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """De uitkomst van deze agent-ronde. De api merget op id/tekst+lid en bevriest wat de jurist
        al beoordeeld heeft — die semantiek zit daar, niet hier."""
        self.verworpen = 0
        payload: dict[str, Any] = {
            "elementen": [naar_contract(e) for e in elementen],
            "suggesties": [_leeg_is_niets(s) for s in suggesties],
            "ronde": 0,
        }
        if run:
            # `tijd` is bij ons optioneel en bij de api verplicht mét default. Hem als `None`
            # meesturen is dus géén "laat maar leeg" maar een validatiefout; weglaten wél.
            payload["run"] = {k: v for k, v in run.items() if not (k == "tijd" and v is None)}
        uit = await self._put(f"/v1/annotatie/documenten/{slug}/elementen", payload)
        # De api laat een element dat zijn schema niet haalt vallen in plaats van de hele ronde te
        # weigeren — beter, maar daarmee wordt een lúíde fout een stille. Daarom telt hij ze in
        # `X-Verworpen` en zeggen wij het tegen de jurist.
        self.verworpen = int(self._laatste_headers.get("X-Verworpen", 0) or 0)
        return uit

    # -- gesprekken-domein -----------------------------------------------------------------------

    async def voeg_bericht_toe(self, gesprek_id: str, bericht: dict[str, Any]) -> dict[str, Any]:
        """De assistent-beurt in de chatgeschiedenis. `run_id` in de payload maakt dit idempotent."""
        return await self._post(f"/v1/gesprekken/{gesprek_id}/berichten", bericht)
