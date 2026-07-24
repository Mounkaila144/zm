# Epic List

- **Epic 1 — Fondations & Moteur linguistique déterministe :** établir le monorepo, l'outillage (Git, CI, lint, tests), valider et geler le lexique numérique zarma v1, et livrer le paquet `zarma_numbers` (générateur, normaliseur, parseur, validateur) passant l'invariant exhaustif — un moteur texte↔nombre entièrement testable, sans GPU ni mobile.
- **Epic 2 — API de reconnaissance & Service ASR remplaçable :** exposer l'API FastAPI (health, models, grammar/version, recognize, feedback, recordings, history) branchée sur le moteur linguistique via un `SpeechRecognizer` abstrait (Mock + CTC + LLM), avec confiance composite, politique d'ambiguïté, persistance et sécurité — un parcours de reconnaissance de bout en bout démontrable avec `MockRecognizer`.
- **Epic 3 — Application mobile Android (parcours complet) :** livrer l'app Flutter (enregistrement contraint, traitement, résultat, confirmation, correction, historique) connectée à l'API, avec gestion des erreurs et des réseaux lents — le parcours utilisateur complet enregistrer → reconnaître → confirmer/corriger.
- **Epic 4 — Collecte consentie, feedback & socle de données :** implémenter le consentement versionné, la génération de prompts, l'upload et le retrait des contributions, la validation avant intégration au dataset, et le stockage des corrections/feedbacks pour les métriques — le socle de données consenties et anonymisées.
- **Epic 5 — Benchmark ASR, sélection du modèle & calibration :** constituer le corpus de benchmark (≥ 100 audios, split par locuteur), comparer CTC vs LLM sur l'Exact Number Accuracy, produire la matrice de confusions, sélectionner le modèle du MVP et calibrer les poids/seuils de la confiance composite — la décision ASR fondée sur les données et la qualité de bêta mesurée.

---
