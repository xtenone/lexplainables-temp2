"""Service-laag over de LLM-modelprofielen in de database.

Verantwoordelijkheden:
  - CRUD + default-beheer voor `LlmProfile` (gebruikt door de admin-router).
  - `resolve_config`: zet een profielnaam om in een `LlmConfig` (ontsleutelt de API-key en valt
    voor lege velden terug op de env-config), die de engine aan de LLM-adapter geeft.
  - `ensure_seeded`: seedt bij de allereerste start één default-profiel uit de env-waarden,
    zodat bestaande deploys zonder ingreep blijven werken.

De plaintext-API-key blijft binnen deze laag (en de adapter); admin-responses tonen 'm nooit.
"""

from __future__ import annotations

from sqlalchemy import delete, func, insert, select, update

from . import db
from .config import Settings, get_settings
from .llm.base import LlmConfig
from .llm_profile import LlmProfile, _utcnow
from .secrets_crypto import decrypt, encrypt


class ProfileError(ValueError):
    """Ongeldige profiel-operatie (onbekend profiel, laatste/default verwijderen, e.d.)."""


def _row_to_profile(row) -> LlmProfile:
    m = dict(row)
    return LlmProfile(
        name=m["name"],
        provider=m["provider"],
        model=m["model"] or "",
        api_base=m["api_base"] or "",
        api_version=m["api_version"],
        output_strategy=m["output_strategy"],
        temperature=m["temperature"],
        enc_api_key=m["enc_api_key"],
        is_default=m["is_default"],
        updated_by=m["updated_by"] or "",
        created=db.aware(m["created"]),
        updated=db.aware(m["updated"]),
    )


# --- lezen ---------------------------------------------------------------------

async def list_profiles() -> list[LlmProfile]:
    async with db.get_engine().connect() as conn:
        rows = (await conn.execute(
            select(db.llm_profiles).order_by(db.llm_profiles.c.name)
        )).mappings().all()
    return [_row_to_profile(r) for r in rows]


async def get_profile(name: str) -> LlmProfile | None:
    async with db.get_engine().connect() as conn:
        row = (await conn.execute(
            select(db.llm_profiles).where(db.llm_profiles.c.name == name)
        )).mappings().first()
    return _row_to_profile(row) if row is not None else None


async def get_default() -> LlmProfile | None:
    async with db.get_engine().connect() as conn:
        row = (await conn.execute(
            select(db.llm_profiles).where(db.llm_profiles.c.is_default.is_(True))
        )).mappings().first()
    return _row_to_profile(row) if row is not None else None


async def ensure_exists(name: str) -> None:
    """Werp ProfileError als het profiel niet bestaat (voor request-validatie → 400)."""
    if await get_profile(name) is None:
        raise ProfileError(f"Onbekend model_profile: {name!r}")


async def _count() -> int:
    async with db.get_engine().connect() as conn:
        return (await conn.execute(select(func.count()).select_from(db.llm_profiles))).scalar() or 0


# --- resolutie naar een LlmConfig ----------------------------------------------

def _config_uit_env(s: Settings) -> LlmConfig:
    return LlmConfig(
        provider=s.llm_provider,
        model=s.llm_model,
        api_base=s.llm_api_base,
        api_key=s.llm_api_key,
        api_version=s.llm_api_version,
        output_strategy=s.llm_output_strategy,
        temperature=s.llm_temperature,
        timeout=s.llm_timeout_s,
        max_prompt_tokens=s.llm_max_prompt_tokens,
        prompt_caching=s.llm_prompt_caching,
    )


async def resolve_config(name: str | None, settings: Settings | None = None) -> LlmConfig:
    """Profielnaam → `LlmConfig`. Onbekend/None profiel → env-fallback (faalt niet hard hier;
    de bestaanscheck gebeurt bij het aanmaken van de analyse)."""
    s = settings or get_settings()
    profile = await get_profile(name) if name else await get_default()
    if profile is None:
        return _config_uit_env(s)
    api_key = decrypt(profile.enc_api_key) if profile.enc_api_key else s.llm_api_key
    return LlmConfig(
        provider=profile.provider,
        model=profile.model,
        api_base=profile.api_base,
        api_key=api_key,
        api_version=profile.api_version,
        output_strategy=profile.output_strategy,
        temperature=profile.temperature,
        timeout=s.llm_timeout_s,
        max_prompt_tokens=s.llm_max_prompt_tokens,
        prompt_caching=s.llm_prompt_caching,
    )


# --- muteren -------------------------------------------------------------------

async def upsert_profile(
    name: str,
    *,
    updated_by: str,
    provider: str | None = None,
    model: str | None = None,
    api_base: str | None = None,
    api_version: str | None = None,
    output_strategy: str | None = None,
    temperature: float | None = None,
    api_key: str | None = None,
    is_default: bool | None = None,
) -> LlmProfile:
    """Maak of werk een profiel bij. Een veld dat `None` is blijft ongewijzigd (PATCH-semantiek).
    Een leeg/None `api_key` laat de bestaande versleutelde key staan; vullen vervangt 'm
    (versleuteld). Het allereerste profiel wordt automatisch default."""
    profile = await get_profile(name)
    is_new = profile is None
    if profile is None:
        profile = LlmProfile(name=name)

    if provider is not None:
        profile.provider = provider
    if model is not None:
        profile.model = model
    if api_base is not None:
        profile.api_base = api_base
    if api_version is not None:
        profile.api_version = api_version or None
    if output_strategy is not None:
        profile.output_strategy = output_strategy
    if temperature is not None:
        profile.temperature = temperature
    if api_key:
        profile.enc_api_key = encrypt(api_key)

    profile.updated_by = updated_by
    profile.updated = _utcnow()

    # Eerste profiel is altijd default; expliciet default zetten wist eerst elke andere default.
    geen_profielen = is_new and await _count() == 0
    if is_default or geen_profielen:
        profile.is_default = True

    async with db.get_engine().begin() as conn:
        if profile.is_default:
            await conn.execute(
                update(db.llm_profiles).where(db.llm_profiles.c.is_default.is_(True))
                .values(is_default=False)
            )
        waarden = dict(
            provider=profile.provider, model=profile.model, api_base=profile.api_base,
            api_version=profile.api_version, output_strategy=profile.output_strategy,
            temperature=profile.temperature, enc_api_key=profile.enc_api_key,
            is_default=profile.is_default, updated_by=profile.updated_by, updated=profile.updated,
        )
        if is_new:
            await conn.execute(insert(db.llm_profiles).values(
                name=profile.name, created=profile.created, **waarden
            ))
        else:
            await conn.execute(
                update(db.llm_profiles).where(db.llm_profiles.c.name == name).values(**waarden)
            )
    return profile


async def set_default(name: str) -> LlmProfile:
    profile = await get_profile(name)
    if profile is None:
        raise ProfileError(f"Onbekend model_profile: {name!r}")
    async with db.get_engine().begin() as conn:
        await conn.execute(
            update(db.llm_profiles).where(db.llm_profiles.c.is_default.is_(True))
            .values(is_default=False)
        )
        await conn.execute(
            update(db.llm_profiles).where(db.llm_profiles.c.name == name)
            .values(is_default=True, updated=_utcnow())
        )
    profile.is_default = True
    return profile


async def delete_profile(name: str) -> None:
    profile = await get_profile(name)
    if profile is None:
        raise ProfileError(f"Onbekend model_profile: {name!r}")
    if profile.is_default:
        raise ProfileError("Kan het default-profiel niet verwijderen; wijs eerst een ander aan.")
    async with db.get_engine().begin() as conn:
        await conn.execute(delete(db.llm_profiles).where(db.llm_profiles.c.name == name))


# --- seeding -------------------------------------------------------------------

async def ensure_seeded(settings: Settings | None = None) -> None:
    """Seed bij de eerste start één default-profiel uit de env-waarden (idempotent)."""
    if await _count() > 0:
        return
    s = settings or get_settings()
    now = _utcnow()
    async with db.get_engine().begin() as conn:
        await conn.execute(insert(db.llm_profiles).values(
            name=s.default_model_profile,
            provider=s.llm_provider,
            model=s.llm_model,
            api_base=s.llm_api_base,
            api_version=s.llm_api_version,
            output_strategy=s.llm_output_strategy,
            temperature=s.llm_temperature,
            # Geen enc_api_key: resolve_config valt terug op de env/secret-key.
            is_default=True,
            updated_by="seed",
            created=now,
            updated=now,
        ))
