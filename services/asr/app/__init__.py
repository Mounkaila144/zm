"""Service ASR serverless GPU (Modal) — chargement CTC/LLM + endpoint /transcribe.

Ce paquet est **isolé** de ``services/api`` : image lourde (torch + Omnilingual
ASR), déployée et redémarrée indépendamment (``modal deploy services/asr/app``).
Il n'est pas membre du workspace uv racine afin de **garder la CI sans GPU**.
"""
