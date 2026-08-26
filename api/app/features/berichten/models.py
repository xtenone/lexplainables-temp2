"""De ene bron voor het berichten-domein (werkwijze-ADR-0011).

Release notes en aankondigingen: beheerders schrijven berichten (concept → gepubliceerd),
analisten lezen ze. Leesbewijzen zijn (bericht, user)-paren.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import Boolean, Column, Index, Integer, PrimaryKeyConstraint, String, Table, Text

from ...shared.db import DATETIME_TZ, metadata

GELDIGE_TYPES = Literal["info", "update", "waarschuwing", "kritiek"]

berichten = Table(
    "berichten",
    metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("titel",           Text, nullable=False, default=""),
    Column("inhoud",          Text, nullable=False, default=""),
    Column("type",            String(16), nullable=False, default="info"),
    Column("versie",          String(32), nullable=True),
    Column("gepubliceerd",    Boolean, nullable=False, default=False),
    Column("gepubliceerd_op", DATETIME_TZ, nullable=True),
    Column("aangemaakt_door", String(128), nullable=False, default=""),
    Column("created",         DATETIME_TZ, nullable=False),
    Column("updated",         DATETIME_TZ, nullable=False),
    Index("ix_berichten_gepubliceerd_created", "gepubliceerd", "created"),
)

bericht_leesbewijzen = Table(
    "bericht_leesbewijzen",
    metadata,
    Column("bericht_id", Integer, nullable=False),
    Column("userid",     String(64), nullable=False),
    Column("gelezen_op", DATETIME_TZ, nullable=False),
    PrimaryKeyConstraint("bericht_id", "userid"),
)
