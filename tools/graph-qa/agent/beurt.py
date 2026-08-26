"""
De beurt-driver: vangt de eventstroom op en legt de uitkomst vast.

Dit is het spiegelbeeld van wat de werkplek vroeger deed. Daar verzamelde `verstuur()` de events in
closure-variabelen en schreef ná de stream het document, de elementen en het chatbericht weg — met
als gevolg dat een gesloten tabblad al dat werk kostte. Diezelfde logica staat nu hier, achter de
run, waar geen browser bij nodig is.

Bewust **buiten** de LangGraph-code: de driver leest alleen de eventstroom van `answer_stream`, dus
`orchestrator.py` blijft ongemoeid. Dat scheelt risico op de plek waar het duurst is.

Twee volgorde-eisen die je niet mag omdraaien:

1. **`done` gaat er pas uit als er is weggeschreven.** Anders ziet een client die precies op dat
   moment herlaadt noch de lopende run, noch het bericht — en dan lijkt de beurt verdampt.
2. **Het document wordt pas aan het eind gemaakt.** `emit_node` is terminaal: vóór dat punt zijn er
   geen elementen. Een document dat al bij het `doel`-event ontstond, zou bij elke afgebroken run als
   leeg skelet in de werkvoorraad blijven staan.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from .annotatie import sleutel_van
from .config import Settings
from .wetsanalyse_api import GesprekVerdwenen, WetsanalyseApi, WetsanalyseApiFout

logger = logging.getLogger("graph_qa.beurt")


def _titel(doel: dict[str, Any]) -> str:
    """Het leesbare label van de annotatie, zoals de werkplek het toont.

    Reist mee met het bericht zodat de kaart in het gesprek zichzelf kan benoemen als het document
    later verwijderd wordt — er is geen foreign key die dat afdwingt."""
    naam = doel.get("citeertitel") or doel.get("bwbId") or ""
    lid = doel.get("lid") or ""
    return f"{naam} — art. {doel.get('artikel', '')}" + (f" lid {lid}" if lid else "")


class BeurtSchrijver:
    """Verzamelt wat er in één beurt binnenkomt en legt het aan het eind vast."""

    def __init__(self) -> None:
        self.doel: dict[str, Any] | None = None
        self.elementen: list[dict[str, Any]] = []
        self.suggesties: list[dict[str, Any]] = []
        self.ontbrekend: list[dict[str, Any]] = []
        self.run: dict[str, Any] | None = None
        self.kandidaten: list[dict[str, Any]] = []
        self.tekst = ""
        self.denk = ""
        self.bronnen: list[dict[str, Any]] = []

    def verwerk(self, event: dict[str, Any]) -> None:
        """Eén event bijhouden. Dezelfde toewijzing als de handlers in de werkplek."""
        soort = event.get("type")
        if soort == "token":
            self.tekst += event.get("content", "")
        elif soort == "status":
            self.denk += ("\n" if self.denk else "") + "· " + event.get("message", "")
        elif soort == "reason":
            self.denk += event.get("content", "")
        elif soort == "sources":
            self.bronnen = event.get("sources") or []
        elif soort == "doel":
            self.doel = event.get("doel") or {}
        elif soort == "element":
            self._voeg_element_toe(event.get("element") or {})
        elif soort == "run":
            self.run = event.get("run") or {}
        elif soort == "ontbrekend":
            self.ontbrekend.extend(event.get("items") or [])
        elif soort == "suggestie":
            self.suggesties.append(event.get("suggestie") or {})
        elif soort == "kandidaten":
            self.kandidaten = event.get("kandidaten") or []

    def _voeg_element_toe(self, element: dict[str, Any]) -> None:
        """Ontdubbeld verzamelen: de annoteerder ⇄ Critic-lus kan hetzelfde element opnieuw sturen,
        en dan wint de laatste versie.

        Dezelfde regel als `mergeVoorstellen` in de werkplek en als de merge in de api: eerst op
        `id`, anders op de canonieke inhoudssleutel (`sleutel_van` — genormaliseerde tekst + lid).
        Dat laatste stond hier eerder als rúwe tekst in één tuple mét het id, waardoor een
        witruimteverschil een tweede kaart opleverde en een herziening zonder id nooit matchte.
        """
        if not element:
            return

        def zelfde(bestaand: dict[str, Any]) -> bool:
            eigen_id, ander_id = element.get("id") or "", bestaand.get("id") or ""
            if eigen_id and ander_id:
                return eigen_id == ander_id
            return sleutel_van(element.get("tekst") or "", element.get("lid") or "") == sleutel_van(
                bestaand.get("tekst") or "", bestaand.get("lid") or ""
            )

        for i, bestaand in enumerate(self.elementen):
            if zelfde(bestaand):
                self.elementen[i] = element
                return
        self.elementen.append(element)

    @property
    def is_annotatie(self) -> bool:
        return bool(self.doel and self.doel.get("bwbId") and self.elementen)


async def voer_beurt_uit(
    stroom: AsyncIterator[dict[str, Any]],
    *,
    settings: Settings,
    run,
    gesprek_id: str,
    user_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """Draai één beurt: stuur de events door, en leg aan het eind de uitkomst vast.

    `run` is het run-object uit het register; we lezen er het stopverzoek en het `run_id` uit.

    Kan graph-qa niet zelf wegschrijven (geen api geconfigureerd, of geen gesprek/gebruiker bekend),
    dan is dit puur een doorgeefluik. Leverde de beurt wél markeringen op, dan **zeggen we dat**:
    de werkplek nam dat vroeger stilzwijgend over met een eigen schrijfpad, en dat tweede pad is
    weg. Zwijgen zou nu betekenen dat een annotatie van anderhalve minuut spoorloos verdwijnt.
    """
    schrijver = BeurtSchrijver()
    async for event in stroom:
        if event.get("type") == "done":
            # Vasthouden: `done` is voor de client het teken dat de beurt vastligt.
            break
        schrijver.verwerk(event)
        yield event

    # Is er om stoppen gevraagd, dan is de graaf er zelf op een nodegrens uitgestapt (`stop_check` →
    # `BeurtGestopt`). We breken hier dus NIET af: dan zouden we de generator halverwege dichtgooien
    # en het lopende werk alsnog weggooien — precies wat we wilden afschaffen. De prijs is dat
    # stoppen tijd kost; dat hoort de UI te tonen.
    gestopt = bool(run.stop_gevraagd)

    mag_vastleggen = settings.legt_zelf_vast and bool(gesprek_id) and bool(user_id)
    if mag_vastleggen:
        async for na in _leg_vast(schrijver, settings=settings, run=run,
                                  gesprek_id=gesprek_id, gestopt=gestopt, user_id=user_id):
            yield na
    elif schrijver.is_annotatie:
        logger.warning(
            "beurt: markeringen niet vastgelegd (geen schrijfpad)",
            extra={"categorie": "functioneel", "run_id": run.run_id,
                   "elementen": len(schrijver.elementen)},
        )
        yield {
            "type": "error",
            "message": ("Deze markeringen zijn niet vastgelegd: deze agent heeft geen verbinding "
                        "met de wetsanalyse-API."),
        }
    yield {"type": "done"}


async def _leg_vast(
    schrijver: BeurtSchrijver,
    *,
    settings: Settings,
    run,
    gesprek_id: str,
    gestopt: bool,
    user_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """Schrijf document, elementen en het chatbericht weg; meld de uitkomst aan de client."""
    api = WetsanalyseApi(settings, user_id)
    try:
        bericht: dict[str, Any] = {"rol": "assistant", "run_id": run.run_id}
        slug = ""
        elementen_bewaard = False

        if schrijver.is_annotatie:
            # Vanaf hier kan een deel geslaagd zijn: het document en zijn elementen staan er dan al
            # terwijl het chatbericht nog moet. Wat er wél is bewaard hoort in de foutmelding —
            # anders leest de jurist "niet opgeslagen", draait hij de beurt van 60-90 seconden
            # opnieuw, en heeft hij een tweede annotatiedocument.
            doel = schrijver.doel or {}
            slug = await api.maak_document(
                bwb_id=str(doel.get("bwbId", "")),
                artikel=str(doel.get("artikel", "")),
                lid=str(doel.get("lid") or ""),
                citeertitel=str(doel.get("citeertitel") or ""),
            )
            await api.zet_elementen(
                slug,
                elementen=schrijver.elementen,
                suggesties=schrijver.suggesties,
                run=schrijver.run,
            )
            elementen_bewaard = True
            if getattr(api, "verworpen", 0):
                # Niet als `error`: de beurt is geslaagd en de rest staat er. Maar wél zeggen —
                # anders ziet de jurist dertien markeringen en weet hij niet dat het er vijftien
                # hadden moeten zijn. Een stil verlies is erger dan een luide fout.
                aantal = api.verworpen
                yield {
                    "type": "waarschuwing",
                    "message": (f"{aantal} markering{'en' if aantal > 1 else ''} kon niet worden "
                                f"opgeslagen en {'staan' if aantal > 1 else 'staat'} niet in de "
                                f"annotatie. Wat er wél is, vind je hieronder."),
                }
            bericht |= {
                "annotatie_slug": slug,
                "annotatie_titel": _titel(doel),
                "ontbrekend": schrijver.ontbrekend,
                "denk": schrijver.denk,
            }
        else:
            tekst = schrijver.tekst.strip()
            if gestopt:
                # Weggooien wat de agent al schreef is niet wat "stoppen" betekent. Maar beloof ook
                # geen half resultaat dat er niet is: `emit_node` is terminaal, dus stoppen vóór dat
                # punt levert écht nul voorstellen op — dan is dat wat er staat.
                tekst = f"{tekst}\n\n_(gestopt)_" if tekst else "_Gestopt — er waren nog geen voorstellen._"
            bericht |= {
                "tekst": tekst or "(geen antwoord)",
                "denk": schrijver.denk,
                "bronnen": schrijver.bronnen,
            }

        await api.voeg_bericht_toe(gesprek_id, bericht)
        logger.info(
            "beurt vastgelegd",
            extra={"categorie": "functioneel", "run_id": run.run_id,
                   "chat_session_id": gesprek_id, "annotatie_slug": slug},
        )
        # De client hoeft de inhoud niet mee te krijgen: hij haalt het document bij de api op. Zo
        # blijft er één bron van waarheid en groeit het SSE-contract niet mee met het datamodel.
        yield {"type": "opgeslagen", "annotatie_slug": slug, "run_id": run.run_id}
    except GesprekVerdwenen:
        # De jurist verwijderde het gesprek terwijl de beurt liep. Dat is geen fout om over te
        # klagen — alarm slaan over iemands eigen handeling leert mensen meldingen negeren.
        #
        # Het annotatiedocument blijft wél staan: annotaties zijn eersteklas objecten die los van
        # hun gesprek bestaan (zie /annotaties), dus dat is bewaard werk, geen wees.
        logger.info(
            "gesprek verdwenen tijdens de beurt",
            extra={"categorie": "functioneel", "run_id": run.run_id, "chat_session_id": gesprek_id},
        )
    except (WetsanalyseApiFout, Exception):
        logger.exception(
            "beurt niet vastgelegd",
            extra={"categorie": "technisch", "run_id": run.run_id, "chat_session_id": gesprek_id,
                   "annotatie_slug": slug},
        )
        # Zichtbaar falen: de jurist moet weten dat dit werk niet bewaard is, niet later ontdekken
        # dat het gesprek een gat heeft. Wél eerlijk zijn over wat er al staat: "probeer opnieuw" is
        # een slecht advies als de annotatie er al is — dat levert een tweede document op.
        if slug and elementen_bewaard:
            yield {
                "type": "error",
                "message": ("De annotatie is bewaard, alleen het bericht in dit gesprek niet. "
                            "Je vindt hem terug bij Annotaties; de vraag opnieuw stellen maakt een "
                            "tweede annotatie."),
                "annotatie_slug": slug,
            }
        elif slug:
            # Het document bestaat, de markeringen niet. Zeggen dat de annotatie bewaard is, is dan
            # onwaar — en het advies "niet opnieuw proberen" is precies verkeerd: er valt niets terug
            # te vinden. Op dev liep een run hierop stuk en hield de jurist een leeg document over.
            yield {
                "type": "error",
                "message": ("De markeringen konden niet worden opgeslagen; bij Annotaties staat een "
                            "leeg document. Stel de vraag opnieuw."),
                "annotatie_slug": slug,
            }
        else:
            yield {
                "type": "error",
                "message": "Het antwoord is gemaakt, maar niet opgeslagen. Probeer de vraag opnieuw.",
            }
    finally:
        await api.aclose()
