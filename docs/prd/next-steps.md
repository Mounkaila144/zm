# Next Steps

## UX Expert Prompt

Concevoir l'UX/UI mobile Android de « Zarma — reconnaissance des nombres » à partir de ce PRD. Cible : utilisateurs zarma à alphabétisation variable, geste micro unique, boucle confirmation/correction rassurante, WCAG AA, affichage systématique de la forme zarma à côté des chiffres. Livrer les spécifications des écrans Accueil, Enregistrement, Traitement, Résultat, Confirmation, Correction, Historique et flux Contribution/Consentement.

## Architect Prompt

Concevoir l'architecture technique à partir de ce PRD. Décisions attendues : **Riverpod vs Bloc** (une seule solution) ; découpage monorepo (Flutter / API FastAPI / service ASR / paquet `zarma_numbers`) ; contrats API et schéma de données (audio hors base) ; interface `SpeechRecognizer` (Mock/CTC/LLM) ; **stratégie de déploiement GPU pour l'ASR** (cloud vs local — risque n°1) ; Docker (images API légère / ASR lourde), nginx, HTTPS, environnements local/staging/prod ; et garantie que le moteur linguistique et l'API (via Mock) restent développables sans GPU.