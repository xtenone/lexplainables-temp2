"""Wetsanalyse API — headless backend voor de werkplek.

Bedient het JAS-annotatiedomein, de chatgeschiedenis, login/gebruikersbeheer en het
LLM-modelprofielbeheer. De agent die de annotaties voorstelt is een aparte dienst
(tools/graph-qa/); deze API bewaart de review-state en het auditspoor.
"""

__version__ = "0.1.0"
