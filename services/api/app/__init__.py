"""Service API FastAPI Zarma.

Serveur traditionnel conteneurisé **sans GPU** : expose le moteur linguistique
déterministe (paquet ``zarma_numbers``) via HTTP. Dépend de ``zarma_numbers`` ;
l'inverse est interdit (le paquet linguistique n'importe jamais FastAPI).
"""

__version__ = "0.1.0"
