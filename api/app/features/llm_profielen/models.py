"""De ene bron voor het llm_profielen-domein (werkwijze-ADR-0011).

Benoemde LLM-modelprofielen: vervangen de vroegere hardcoded model-config, leven in de database
en zijn beheerbaar via /v1/admin/profiles (geen redeploy nodig). De client kiest een profiel op
naam (governance: geen vrije model-string). De API-key staat versleuteld in `enc_api_key` (Fernet,
zie shared.secrets_crypto). De plaintext-key verlaat de server nooit via de API — admin-responses
tonen alleen `api_key_set: bool`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, Float, String, Table, Text

from ...shared.db import DATETIME_TZ, metadata, utcnow

llm_profiles = Table(
    "llm_profiles",
    metadata,
    Column("name", String(128), primary_key=True),
    Column("provider", String(64), nullable=False, default="azure_ai"),
    Column("model", String(128), nullable=False, default=""),
    Column("api_base", String(512), nullable=False, default=""),
    Column("api_version", String(64), nullable=True),
    Column("output_strategy", String(64), nullable=False, default="prompt_and_parse"),
    Column("temperature", Float, nullable=False, default=0.0),
    Column("enc_api_key", Text, nullable=True),
    Column("is_default", Boolean, nullable=False, default=False),
    Column("updated_by", String(128), nullable=False, default=""),
    Column("created", DATETIME_TZ, nullable=False),
    Column("updated", DATETIME_TZ, nullable=False),
)


class LlmProfile(BaseModel):
    name: str
    provider: str = "azure_ai"
    model: str = ""
    api_base: str = ""
    api_version: str | None = None
    output_strategy: str = "prompt_and_parse"
    temperature: float = 0.0
    # Versleutelde API-key (Fernet-token). Leeg ⇒ val terug op de env-LLM_API_KEY.
    enc_api_key: str | None = None
    is_default: bool = False

    updated_by: str = ""
    created: datetime = Field(default_factory=utcnow)
    updated: datetime = Field(default_factory=utcnow)

    def touch(self) -> None:
        self.updated = utcnow()
