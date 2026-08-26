"""
JAS-klassen-referentie — de dertien klassen van het Juridisch Analyseschema.

Vers afgeleid uit de brondocumentatie (`docs/wetsanalyse/wetsanalyse-rijk/H2-JAS.md`): per klasse een
omschrijving, een herken-vraag (à la zinsontleding) en de uitdrukkingswijze in wetgeving. Deze
referentie voedt de annotatie-prompt (`agent/annotatie_prompt.py`).

De klasse-*namen* zijn de canonieke JAS-namen (dezelfde weergave-volgorde als `docs/wetsanalyse/wa-table.png`),
zodat annotaties niet driften t.o.v. de rest van het systeem. Alléén de namen zijn gedeeld; de
inhoudelijke duiding hieronder komt vers uit de bron, niet uit de skill-prompts.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JasKlasse:
    naam: str
    omschrijving: str
    vraag: str
    uitdrukkingswijze: str


JAS_KLASSEN: tuple[JasKlasse, ...] = (
    JasKlasse(
        naam="Rechtssubject",
        omschrijving="De drager van rechten en plichten; een partij in een rechtsbetrekking.",
        vraag="Wie heeft het recht? Wie heeft de plicht? Van wie is een rechtsobject?",
        uitdrukkingswijze=(
            "Een zelfstandig naamwoord voor een persoon of entiteit, of een (persoonlijk, onbepaald, "
            "betrekkelijk) voornaamwoord zoals 'hij', 'zij', 'iemand', 'een ieder', 'degene'."
        ),
    ),
    JasKlasse(
        naam="Rechtsobject",
        omschrijving=(
            "Het voorwerp van een rechtsbetrekking en/of rechtsfeit; fysiek (auto, huis) of niet-fysiek "
            "(medische zorg)."
        ),
        vraag="Wat is het voorwerp van een recht of plicht? Waarvan is het subject eigenaar/houder?",
        uitdrukkingswijze=(
            "Een zelfstandig naamwoord voor het voorwerp van een recht/plicht (een studie, een woning), "
            "of een aanwijzend/betrekkelijk voornaamwoord zoals 'dat', 'hetgeen', 'welk(e)'."
        ),
    ),
    JasKlasse(
        naam="Rechtsbetrekking",
        omschrijving=(
            "Een juridische relatie tussen twee rechtssubjecten: de een heeft een plicht, de ander het "
            "bijbehorende recht."
        ),
        vraag="Hoe verhouden twee rechtssubjecten zich tot elkaar? Welke relatie hebben zij?",
        uitdrukkingswijze=(
            "Een of meer werkwoorden — recht: 'kan verzoeken', 'mag wijzigen', 'heeft recht op'; "
            "plicht: 'stelt vast', 'moet informeren', 'is verplicht', 'dient te voldoen', 'draagt de last om'."
        ),
    ),
    JasKlasse(
        naam="Rechtsfeit",
        omschrijving=(
            "Een handeling, gebeurtenis of tijdsverloop die een wijziging in de juridische toestand "
            "teweegbrengt (een rechtsbetrekking creëert, wijzigt of beëindigt)."
        ),
        vraag="Welke gebeurtenis, handeling of welk tijdsverloop heeft gevolgen voor de rechtsbetrekking?",
        uitdrukkingswijze=(
            "Een actieve werkwoordsvorm, vaak met een zelfstandig naamwoord: 'indienen van een "
            "bezwaarschrift', 'toekennen van een subsidie', 'horen van belanghebbende'."
        ),
    ),
    JasKlasse(
        naam="Voorwaarde",
        omschrijving=(
            "Een conditie die beschrijft aan welke omstandigheid voldaan moet zijn voor een rechtsgevolg. "
            "Kan enkelvoudig of samengesteld zijn (cumulatief EN / alternatief OF)."
        ),
        vraag="Welke eis wordt gesteld aan een subject, object, rechtsbetrekking of rechtsfeit?",
        uitdrukkingswijze=(
            "Een voorwaardelijke bijzin, meestal ingeleid door 'indien', 'als', 'tenzij', 'mits', 'met "
            "dien verstande dat', 'met uitzondering van'; soms een bijwoord zoals 'schriftelijk'."
        ),
    ),
    JasKlasse(
        naam="Afleidingsregel",
        omschrijving=(
            "Een regel die nieuwe feiten of waarden afleidt uit bestaande (beslisregel: ja/nee; rekenregel: "
            "een bedrag/duur). De vastgestelde variabele is de uitvoervariabele; de gebruikte de invoer."
        ),
        vraag="Hoe wordt een variabele berekend of afgeleid? Hoe wordt een specifiek subject/object bepaald?",
        uitdrukkingswijze=(
            "Woorden die op berekening/afleiding duiden: 'is verminderd met', 'bedraagt vermeerderd met', "
            "'wordt gesteld op', 'is het gezamenlijke bedrag van', of eenvoudigweg 'en'."
        ),
    ),
    JasKlasse(
        naam="Variabele en variabelewaarde",
        omschrijving=(
            "Een variabele is een kenmerk van een subject/object/rechtsbetrekking/rechtsfeit dat per "
            "instantie kan verschillen; een variabelewaarde is de waarde die die variabele kan hebben."
        ),
        vraag="Welk kenmerk/eigenschap wordt genoemd? Welke waarde (bedrag, duur, hoogte) hoort erbij?",
        uitdrukkingswijze=(
            "Een getal of datum, een tekst (bv. 'naam van de werkgever'), een enumeratiewaarde (limitatieve "
            "opsomming) of een booleaanse waarde (ja/nee)."
        ),
    ),
    JasKlasse(
        naam="Parameter en parameterwaarde",
        omschrijving=(
            "Een parameter is een waarde die gelijk is voor alle subjecten/objecten (een constante), meestal "
            "voor een periode; de parameterwaarde is de concrete waarde in die periode."
        ),
        vraag="Is er een waarde die gedurende een periode een vaste hoogte heeft voor iedereen?",
        uitdrukkingswijze=(
            "Een tarief, (drempel)bedrag, maximum/minimum of vrijstelling; de waarde als bedrag, percentage "
            "of datum, geldig over een periode."
        ),
    ),
    JasKlasse(
        naam="Operator",
        omschrijving=(
            "Een woord, woordcombinatie of teken dat een rekenkundige bewerking, vergelijking, gelijkstelling "
            "of logische verbinding tussen waarden/voorwaarden uitdrukt."
        ),
        vraag="Hoe worden variabelen/parameters verbonden in een berekening? In welke verhouding staan voorwaarden?",
        uitdrukkingswijze=(
            "Rekenkundig: 'de som van', 'vermeerderd/verminderd met', 'percentage van'. Vergelijking: 'groter "
            "dan', 'kleiner dan', 'is gelijk aan'. Logisch: 'en', 'of', 'niet', 'ten minste'."
        ),
    ),
    JasKlasse(
        naam="Tijdsaanduiding",
        omschrijving=(
            "Een omschrijving van een tijdstip of tijdvak — nodig voor de geldigheid van een rechtsbetrekking, "
            "een tijdsverloop met rechtsgevolg, of als variabele/parameter(waarde). Kies bij twijfel de meest "
            "specifieke klasse (tijdsaanduiding boven variabele/parameter)."
        ),
        vraag="Wanneer, op welk moment? Sinds/tot wanneer, vanaf/tot welk moment?",
        uitdrukkingswijze=(
            "Een concrete datum ('1 september 2009') of omschrijving ('de eerste maandag van de maand'); "
            "tijdvakken met 'jaar', 'maand', 'week', 'dag' of specialisaties zoals 'kalenderjaar'."
        ),
    ),
    JasKlasse(
        naam="Plaatsaanduiding",
        omschrijving=(
            "Een plaats of gebied waarop wetgeving betrekking heeft; bepaalt het toepassingsbereik. Kies bij "
            "twijfel de meest specifieke klasse (plaatsaanduiding boven variabele/parameter)."
        ),
        vraag="Waar (voor welk gebied of welke plaats) geldt de wettelijke regel (niet)?",
        uitdrukkingswijze=(
            "Een algemene gebiedsbeschrijving ('een lidstaat van de EU') of een specifieke naam ('de gemeente "
            "Amsterdam', 'Nederland')."
        ),
    ),
    JasKlasse(
        naam="Delegatiebevoegdheid en delegatie-invulling",
        omschrijving=(
            "Een delegatiebevoegdheid maakt mogelijk of schrijft voor dat nadere regels worden gesteld over een "
            "rechtsbetrekking/rechtsfeit/afleidingsregel; de delegatie-invulling is de lagere regeling die dat "
            "invult. Verplicht of facultatief; subdelegatie mogelijk bij 'bij of krachtens'."
        ),
        vraag="Geeft een artikel de opdracht om (nadere) regels te stellen? Verwijst een lagere regeling terug?",
        uitdrukkingswijze=(
            "Verplicht: 'bij (of krachtens) algemene maatregel van bestuur / bij ministeriële regeling worden "
            "regels gesteld'. Facultatief: 'kunnen regels worden gesteld'."
        ),
    ),
    JasKlasse(
        naam="Brondefinitie",
        omschrijving=(
            "Een begripsomschrijving die expliciet in de wetgeving is opgenomen en een in de wet gebruikte term "
            "eenduidig definieert. Te onderscheiden van de analyse-begrippen die pas bij de Wetsanalyse ontstaan."
        ),
        vraag="Is deze term uitdrukkelijk omschreven in de wetgeving?",
        uitdrukkingswijze=(
            "Een definitieartikel (vaak aan het begin van een regeling) met een aanhef en onderdelen, bij "
            "voorkeur alfabetisch; soms geldend voor een specifiek hoofdstuk of artikel."
        ),
    ),
)

# Canonieke weergave-volgorde + naamlijst (drift-guard: gelijk aan validation.JAS_KLASSEN_VOLGORDE).
JAS_KLASSEN_VOLGORDE: tuple[str, ...] = tuple(k.naam for k in JAS_KLASSEN)
GELDIGE_JAS_KLASSEN: frozenset[str] = frozenset(JAS_KLASSEN_VOLGORDE)
