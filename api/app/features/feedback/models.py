"""De ene bron voor het feedback-domein (werkwijze-ADR-0011).

Gebruikersfeedback vanuit de webapp. Elke rij is onwijzigbaar; beheerders lezen via
/v1/admin/feedback.
"""

from __future__ import annotations

from sqlalchemy import Column, Index, Integer, String, Table, Text

from ...shared.db import DATETIME_TZ, metadata

user_feedback = Table(
    "user_feedback",
    metadata,
    Column("id",        Integer, primary_key=True, autoincrement=True),
    Column("client_id", String(128), nullable=False),
    Column("userid",    String(128), nullable=False),
    Column("categorie", String(32),  nullable=False),
    Column("tekst",     Text,        nullable=False),
    # Pad waar de feedback vandaan kwam, zodat een melding te plaatsen is.
    Column("pagina",    Text,        nullable=True),
    Column("created",   DATETIME_TZ, nullable=False),
    Index("ix_user_feedback_created", "created"),
)
