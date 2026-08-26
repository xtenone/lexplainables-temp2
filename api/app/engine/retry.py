"""Bounded retry met exponentiële backoff op transiënte LLM/MCP-fouten.

De LLM-adapter laat provider-fouten (rate-limit/5xx/timeout) rauw propageren en de MCP-client
verpakt transportfouten in WettenbankError. Beide zijn vaak tijdelijk; één hapering mag niet de
hele (mogelijk half afgeronde) job terminaal naar `fout` duwen. Permanente fouten (onbekende wet,
ongeldige config) zijn niet transiënt en worden niet geretryed.
"""

from __future__ import annotations

import asyncio
import logging
import random

logger = logging.getLogger(__name__)

# LiteLLM-exceptieklassen die een tijdelijke conditie aanduiden. Op naam i.p.v. import,
# zodat de engine niet hard van litellm afhankelijk wordt.
_TRANSIENTE_LLM_NAMEN = {
    "RateLimitError",
    "Timeout",
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
    "ServiceUnavailableError",
}


# HTTP-statuscodes die een tijdelijke conditie aanduiden: 429 (rate-limit) en 5xx (server).
_TRANSIENTE_STATUS = {429, 500, 502, 503, 504}


def is_transient(e: BaseException) -> bool:
    from ..wettenbank import WettenbankError

    if isinstance(e, WettenbankError):
        # Client-/permanente MCP-fouten (bv. niet-bestaand artikel of onbekende wet) worden
        # niet beter van herhalen; alleen zonder of met transiënte klasse retryen.
        return getattr(e, "klasse", None) not in {"client", "permanent"}
    if type(e).__name__ in _TRANSIENTE_LLM_NAMEN:
        return True
    # Robuuster dan alleen de klassenaam (broos bij LiteLLM-versiewissels of doorgelekte
    # httpx-fouten): kijk ook naar een HTTP-status op de fout of de meegeleverde response.
    for status in (
        getattr(e, "status_code", None),
        getattr(getattr(e, "response", None), "status_code", None),
    ):
        if isinstance(status, int) and status in _TRANSIENTE_STATUS:
            return True
    return False


def retry_after_seconds(e: BaseException) -> float | None:
    """Lees een door de provider voorgestelde wachttijd (Retry-After) uit een rate-limit-fout.

    Defensief en zonder harde litellm-afhankelijkheid: kijk naar een direct attribuut én naar de
    `Retry-After`-header op een eventueel meegeleverde httpx-response. De HTTP-date-vorm (zeldzaam
    bij rate-limits) negeren we — dan valt de aanroeper terug op exponentiële backoff.
    """
    for attr in ("retry_after", "retry_after_seconds"):
        v = getattr(e, attr, None)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    headers = getattr(getattr(e, "response", None), "headers", None)
    if headers:
        ra = headers.get("retry-after") or headers.get("Retry-After")
        if ra:
            try:
                return float(ra)
            except (TypeError, ValueError):
                return None
    return None


async def met_retry(maak, *, max_retries: int, backoff: float, max_backoff: float = 30.0):
    """Roep de coroutine-factory `maak` aan; herhaal bij een transiënte fout.

    Wachttijd = de door de provider voorgestelde `Retry-After` (indien aanwezig, bv. bij een 429),
    anders exponentiële backoff. Begrensd op `max_backoff` en met jitter, zodat veel gelijktijdige
    jobs die tegelijk een 429 krijgen niet als kudde op hetzelfde moment opnieuw aankloppen.
    """
    poging = 0
    while True:
        try:
            return await maak()
        except Exception as e:  # noqa: BLE001 — niet-transiënt wordt direct doorgegooid
            if poging >= max_retries or not is_transient(e):
                raise
            voorstel = retry_after_seconds(e)
            basis = voorstel if voorstel is not None else backoff * (2 ** poging)
            wacht = min(basis, max_backoff)
            wacht += random.uniform(0, min(wacht, max_backoff) * 0.25)  # jitter (geen thundering herd)
            logger.warning(
                "Transiënte fout (%s%s); retry %d/%d na %.1fs",
                type(e).__name__,
                f", Retry-After={voorstel:.0f}s" if voorstel is not None else "",
                poging + 1, max_retries, wacht,
            )
            await asyncio.sleep(wacht)
            poging += 1
