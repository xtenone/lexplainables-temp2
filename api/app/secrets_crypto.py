"""Versleuteling-at-rest voor secrets die via de admin-UI in de database belanden (de LLM-API-key).

Symmetrisch (Fernet/AES-128-CBC + HMAC) met één master key uit een Docker-secret —
hetzelfde *_FILE-patroon als de rest van de config (zie `config._read_secret`). De master key
zelf staat dus nooit in de database, alleen op de host. Ontbreekt de master key, dan kan er
geen key opgeslagen worden: de admin-laag faalt expliciet (fail-closed) i.p.v. plaintext te
bewaren.

De master key moet een geldige Fernet-key zijn (32 url-safe base64-bytes). Genereer er één met
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
"""

from __future__ import annotations

from functools import lru_cache

from .config import get_settings


class SecretsCryptoError(RuntimeError):
    """Versleutelen/ontsleutelen kan niet — meestal: master key niet (juist) geconfigureerd."""


@lru_cache
def _fernet():
    from cryptography.fernet import Fernet

    key = get_settings().llm_config_secret
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as e:
        raise SecretsCryptoError(
            "LLM_CONFIG_SECRET is geen geldige Fernet-key (32 url-safe base64-bytes)."
        ) from e


def crypto_beschikbaar() -> bool:
    """True als er een (geldige) master key is en we dus secrets kunnen op-/ontsleutelen."""
    return _fernet() is not None


def encrypt(plain: str) -> str:
    f = _fernet()
    if f is None:
        raise SecretsCryptoError(
            "Geen LLM_CONFIG_SECRET geconfigureerd; kan geen API-key versleuteld opslaan."
        )
    return f.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    f = _fernet()
    if f is None:
        raise SecretsCryptoError(
            "Geen LLM_CONFIG_SECRET geconfigureerd; kan opgeslagen API-key niet ontsleutelen."
        )
    from cryptography.fernet import InvalidToken

    try:
        return f.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise SecretsCryptoError(
            "Kan opgeslagen API-key niet ontsleutelen (verkeerde of geroteerde master key?)."
        ) from e


def decrypt_ttl(token: str, ttl: int) -> str | None:
    """Ontsleutel een Fernet-token dat maximaal `ttl` seconden oud mag zijn (Fernet stempelt zelf
    een timestamp). Geeft None bij een ongeldig, gemanipuleerd of verlopen token — bedoeld voor
    kortlevende auth-tokens (login-ticket, trusted-device) i.p.v. een exception. Zonder master key
    ook None (fail-closed: geen token te vertrouwen)."""
    f = _fernet()
    if f is None:
        return None
    from cryptography.fernet import InvalidToken

    try:
        return f.decrypt(token.encode("ascii"), ttl=ttl).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None
