"""
Supervisor van de juridische agent (vervangt de vroegere QA-router).

De supervisor bepaalt per vraag WELKE worker-agents nodig zijn en in welke volgorde: `antwoord`
(vraag beantwoorden/duiden/definiëren, gegrond op de graaf) of `annotatie` (een artikel/lid volgens
het JAS markeren). Hij mag ketenen (bv. eerst annoteren, dan samenvatten). Retrieval (get_lid/
get_artikel) is een gedeelde tool die de gekozen worker zelf aanroept.

Backward-compatible met het oude router-formaat: een respons met alleen `SPECIALIST:`/`PLAN:` (zonder
`WORKERS:`) wordt gelezen als één `antwoord`-worker met die specialist — zo blijven de bestaande
QA-flows/tests ongewijzigd.
"""
from __future__ import annotations

SUPERVISOR_SYSTEM = (
    "Je bent de supervisor van een juridische agent over een kennisgraaf met Nederlandse wet- en "
    "regelgeving (invordering/belastingen). Bepaal welke agent(s) de vraag nodig heeft en in welke "
    "volgorde. Antwoord in EXACT dit formaat, drie regels:\n"
    "WORKERS: <komma-gescheiden uit: antwoord, annotatie>\n"
    "SPECIALIST: <definitie|duiding|algemeen>\n"
    "PLAN: <1-2 zinnen aanpak, of AFWIJZEN als de vraag niet over Nederlandse wet- en regelgeving "
    "gaat>\n"
    "AFWIJZEN is alleen voor vragen die BUITEN de wetgeving vallen: het weer, actualiteit, "
    "programmeren, rekensommen, meningen. Gaat de vraag wél over een wet, een bepaling of een "
    "juridisch begrip, dan kies je 'antwoord' — óók als je de genoemde regeling niet kent of denkt "
    "dat ze niet in de graaf zit. Dat is niet aan jou om te weten: je hebt geen tools en je hebt niet "
    "gekeken. De worker zoekt het op en zegt zelf dat het niet in de kennisgraaf staat als hij niets "
    "vindt — en vindt hij iets aangrenzends, dan is dat een beter antwoord dan een afwijzing.\n"
    "Kies 'annotatie' als de gebruiker vraagt een ARTIKEL of LID te ANNOTEREN volgens het JAS (de "
    "juridische elementen markeren en classificeren). Kies anders 'antwoord' (een vraag beantwoorden, "
    "duiden of een begrip definiëren) met de passende SPECIALIST: 'definitie' voor begrip-/definitie"
    "vragen, 'duiding' voor betekenis/structuur/samenhang van een bepaling, anders 'algemeen'. "
    "SPECIALIST geldt alleen voor 'antwoord'."
)

_QA_SPECIALISTS = ("definitie", "duiding", "algemeen")

# De enige twee workers die bestaan. Alles daarbuiten is een verzinsel van het model en telt niet
# mee: eerder werd élke onbekende naam stilzwijgend een extra ANTWOORD-worker, zodat "WORKERS:
# antwoord, samenvatten" dezelfde vraag twee keer beantwoordde — dubbele kosten, twee antwoorden.
_WORKERS = ("antwoord", "annotatie")

# Meer dan twee schakels heeft geen enkele vraag nodig (annoteren en dan samenvatten is de langste
# zinnige keten). Zonder plafond kan één supervisor-respons de beurt willekeurig lang maken.
_MAX_WORKERS = 2


def parse_supervisor(text: str) -> tuple[list[str], str, bool]:
    """(worker_plan, plan, afwijzen).

    `worker_plan` is een geordende lijst specialist-namen die de agent-node draait: een
    `antwoord`-worker wordt de gekozen QA-specialist, een `annotatie`-worker wordt 'annotatie'.

    `afwijzen` betekent dat de supervisor de vraag buiten de scope plaatste. Dat stond al in het
    promptformaat maar werd nergens gelezen: het woord "AFWIJZEN" ging als plan de systeemprompt van
    de specialist in, waarna een tweede modelbeslissing bepaalde wat er gebeurde. Nu is het een
    besluit dat de orkestrator uitvoert — de vraag eindigt vóór de eerste tool-call.
    """
    workers_raw, qa_specialist, plan = "", "algemeen", ""
    for line in text.splitlines():
        low = line.strip()
        up = low.upper()
        if up.startswith("WORKERS:"):
            workers_raw = low.split(":", 1)[1].strip().lower()
        elif up.startswith("SPECIALIST:"):
            val = low.split(":", 1)[1].strip().lower()
            if val in _QA_SPECIALISTS:
                qa_specialist = val
        elif up.startswith("PLAN:"):
            plan = low.split(":", 1)[1].strip()
    if not plan:
        plan = text.strip()

    # Alleen bekende workers, en nooit meer dan het plafond. Blijft er niets over, dan is
    # 'antwoord' de veilige terugval — een beurt zonder worker zou niets doen.
    workers = [w.strip() for w in workers_raw.split(",") if w.strip() in _WORKERS][:_MAX_WORKERS]
    plan_spec = ["annotatie" if w == "annotatie" else qa_specialist for w in workers or ["antwoord"]]
    return plan_spec, plan, plan.strip().upper().startswith("AFWIJZEN")
