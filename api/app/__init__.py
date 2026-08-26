"""Wetsanalyse API — headless orchestratie van de JAS-wetsanalyse.

De engine bezit de review-lus en de state; het LLM doet per stap één begrensde taak.
De bestaande skill-artefacten (analyses/<id>/werk/.../ronde-N/) zijn de jobstore, zodat
API en lokale Claude Code-skill interoperabel blijven.
"""

__version__ = "0.1.0"
