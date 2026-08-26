"""De ene bron voor het annotatie-domein (werkwijze-ADR-0011).

Eén rij per bron-document; de elementen (met hun review-levenscyclus + beslissingen) staan als
JSON — het document draagt de HUIDIGE staat. `annotatie_audit` is de append-only geschiedenis
(alleen inserts) ernaast.
"""

from __future__ import annotations

from sqlalchemy import Column, Index, Integer, String, Table, Text

from ...shared.db import DATETIME_TZ, JSON_TYPE, metadata

annotatie_documenten = Table(
    "annotatie_documenten",
    metadata,
    Column("slug", String(255), primary_key=True),
    # Eigenaar = de ingelogde gebruiker (per-gebruiker gescopet, zoals de gesprekken). `client_id`
    # blijft de bearer-client als herkomst-/tenant-veld, maar de zichtbaarheid gaat op `user_id`.
    Column("user_id", String(64), nullable=False, default=""),
    Column("client_id", String(128), nullable=False, default=""),
    Column("citeertitel", Text, nullable=False, default=""),
    Column("werkgebied", Text, nullable=False, default=""),
    Column("bwbId", String(64), nullable=False, default=""),
    Column("artikel", String(32), nullable=False, default=""),
    Column("lid", String(32), nullable=False, default=""),
    Column("status", String(24), nullable=False, default="in_review"),
    Column("elementen", JSON_TYPE, nullable=False, default=list),
    # Het productiespoor: per agent-ronde welk model/agentversie de voorstellen maakte.
    Column("runs", JSON_TYPE, nullable=False, default=list),
    Column("created", DATETIME_TZ, nullable=False),
    Column("updated", DATETIME_TZ, nullable=False),
    Index("ix_annotatie_docs_user_updated", "user_id", "updated"),
)

# Append-only audit trail: de onwijzigbare geschiedenis (event-log) náást de huidige documentstaat.
# Alleen inserts; nooit update/delete. De tijdlijn = ORDER BY id.
annotatie_audit = Table(
    "annotatie_audit",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("document_slug", String(255), nullable=False),
    Column("client_id", String(128), nullable=False, default=""),
    Column("actor", String(128), nullable=False, default=""),
    Column("actie", String(64), nullable=False, default=""),
    Column("element_id", String(64), nullable=True),
    Column("detail", JSON_TYPE, nullable=True),
    Column("tijdstip", DATETIME_TZ, nullable=False),
    Index("ix_annotatie_audit_doc_id", "document_slug", "id"),
)
