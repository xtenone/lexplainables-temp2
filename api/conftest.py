"""Test-bootstrap: zet de projectroot op sys.path zodat `import app.*` werkt.

De brede engine-/durability-fixtures (FakeLLM/FakeWettenbank/store/engine) zijn met de
analyse-pijplijn verwijderd; de resterende suites (annotatie, auth, admin, wet-info,
validation, observability) brengen hun eigen fixtures mee."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Elke feature registreert zijn Table(s) op de gedeelde `shared.db.metadata` als bijwerking van het
# importeren van zijn `models.py` (via `store.py`/`router.py`). In productie gebeurt dat vanzelf
# doordat main.py bij het opstarten alle routers importeert vóór de lifespan `create_all()` aanroept.
# Een geïsoleerde feature-test die zijn eigen `db`-fixture heeft (init_engine + create_all) zonder
# zelf via app.main te lopen, zou zonder deze import alleen de tabellen van features zien die
# eerder in dezelfde pytest-run toevallig al geïmporteerd zijn — importeer daarom hier, eenmalig bij
# het opstarten van de testsessie, alle feature-modules zodat elke test-DB altijd het volledige
# schema aanmaakt, ongeacht de collectie-/uitvoervolgorde van tests.
from app.features.annotatie import models as _annotatie_models  # noqa: E402,F401
from app.features.api_tokens import models as _api_tokens_models  # noqa: E402,F401
from app.features.berichten import models as _berichten_models  # noqa: E402,F401
from app.features.feedback import models as _feedback_models  # noqa: E402,F401
from app.features.gesprekken import models as _gesprekken_models  # noqa: E402,F401
from app.features.identiteit_toegang import models as _identiteit_toegang_models  # noqa: E402,F401
from app.features.llm_profielen import models as _llm_profielen_models  # noqa: E402,F401


async def maak_testgebruikers(*userids: str) -> None:
    """Zet de gegeven userids als actieve accounts in de (test-)DB.

    Nodig sinds de gescopete endpoints via `actieve_userid` controleren of het account bestaat en
    actief is: een verzonnen X-User-Id levert nu 401 in plaats van stilzwijgend door te lopen.
    """
    from app.features.identiteit_toegang import store as users

    for i, uid in enumerate(userids):
        if i == 0 and await users.needs_setup():
            await users.bootstrap_admin(uid, f"{uid}@example.test", "testwachtwoord123")
        else:
            await users.create_user(uid, f"{uid}@example.test")
