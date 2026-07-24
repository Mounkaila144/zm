# Requirements

## Functional

- **FR1 :** Le système enregistre un audio contraint au format WAV PCM 16 bits, mono, 16 kHz, d'une durée idéale de 1 à 8 s (10 s maximum), pour un seul locuteur prononçant un seul nombre entier.
- **FR2 :** L'application applique des contrôles locaux d'enregistrement : demande de permission micro, bornes de durée min/max, contrôle de taille, annulation en cours, et suppression du fichier temporaire après traitement.
- **FR3 :** Le moteur linguistique génère la forme zarma canonique d'un nombre entier (`generate(n)`) sur la plage `0`–`1 000 000`.
- **FR4 :** Le moteur linguistique analyse un texte zarma normalisé et retourne le nombre entier correspondant (`parse(texte)`), ou une absence de résultat si le texte n'est pas un nombre valide.
- **FR5 :** Le système normalise le texte brut issu de l'ASR (casse, orthographes alternatives connues, connecteurs, espaces) avant analyse grammaticale.
- **FR6 :** Le moteur linguistique satisfait l'invariant `parse(generate(n)) == n` sur toute la plage `0`–`1 000 000` une fois la grammaire gelée.
- **FR7 :** Le lexique est versionné et chaque élément porte un statut (`validé` ou `unresolved`), la version du lexique/grammaire étant exposée par le système.
- **FR8 :** Le système maintient deux tables distinctes — variantes linguistiques reconnues d'une part, corrections d'erreurs ASR d'autre part — et ne corrige jamais aveuglément un mot vers le plus proche.
- **FR9 :** Le service de reconnaissance vocale expose une interface abstraite `SpeechRecognizer` avec au moins trois implémentations : CTC (`omniASR_CTC_300M_v2`, sans `lang`), LLM (`omniASR_LLM_300M_v2`, avec `lang=["dje_Latn"]`) et Mock.
- **FR10 :** L'endpoint `/api/v1/recognize` (multipart/form-data) retourne le nombre compris, le texte zarma normalisé, un score de confiance, une liste d'alternatives candidates, ainsi que `model_version` et `grammar_version`.
- **FR11 :** L'API expose les endpoints `/health`, `/api/v1/models`, `/api/v1/grammar/version`, `/api/v1/recognize`, `/api/v1/feedback`, `/api/v1/recordings`, `/api/v1/history`.
- **FR12 :** Le système calcule un score de confiance composite intégrant les signaux acoustique, grammatical, variante connue, marge entre candidats, et historique de confusions.
- **FR13 :** Selon la confiance, le système applique une politique explicite : **accepter**, **demander confirmation**, ou **demander répétition**.
- **FR14 :** L'application Flutter fournit les écrans Accueil, Enregistrement, Traitement, Résultat, Confirmation, Correction et Historique, avec gestion complète des erreurs.
- **FR15 :** En cas d'ambiguïté, le système demande confirmation à l'utilisateur en présentant le(s) candidat(s) plutôt que de forcer un résultat.
- **FR16 :** L'utilisateur peut corriger un résultat via un clavier numérique, l'application affichant automatiquement la forme zarma canonique correspondant au nombre corrigé.
- **FR17 :** Le système conserve et affiche un historique des reconnaissances de l'utilisateur.
- **FR18 :** Les feedbacks et corrections utilisateur sont stockés pour alimenter les métriques et l'amélioration continue.
- **FR19 :** La collecte vocale consentie couvre : consentement explicite (versionné), génération de prompts, métadonnées, upload, possibilité de retrait, et validation avant intégration au dataset.
- **FR20 :** L'audio ordinaire est supprimé après traitement par défaut ; seul l'audio explicitement consenti est conservé.
- **FR21 :** Le système ne doit jamais inventer un nombre à partir d'une phrase non numérique : il rejette ou demande une répétition.
- **FR22 :** La persistance utilise SQLite en développement et PostgreSQL en production avec migrations Alembic ; l'audio n'est jamais stocké en base (stockage objet/répertoire sécurisé).
- **FR23 :** Chaque réponse de reconnaissance ambiguë inclut les alternatives candidates ordonnées pour permettre la confirmation.

## Non Functional

- **NFR1 :** L'expérience est réactive ; la latence totale et la latence ASR sont mesurées séparément et exposées comme signaux de qualité.
- **NFR2 :** Objectif de qualité (Exact Number Accuracy, à ajuster après benchmark) : **≥ 95 %** sur nouveaux locuteurs en environnement calme, **≥ 90 %** sur nouveaux locuteurs en bruit modéré.
- **NFR3 :** Sécurité : HTTPS obligatoire, aucun secret ou clé embarqué dans Flutter, fichiers `.env` hors Git.
- **NFR4 :** L'API applique un rate limiting et des timeouts sur les endpoints sensibles.
- **NFR5 :** Contrôles serveur stricts sur l'audio : vérification du MIME réel, décodage, taille ≤ ~2 Mo, conversion mono 16 kHz, refus des fichiers corrompus, aucune exécution du fichier.
- **NFR6 :** Les logs ne contiennent aucune donnée sensible ni identifiante.
- **NFR7 :** Les contributions utilisent des identifiants anonymes ; l'anonymisation et le retrait des contributions sont possibles.
- **NFR8 :** Le moteur linguistique est entièrement développable et testable **sans** modèle ASR installé, indépendamment de FastAPI.
- **NFR9 :** L'architecture ASR est remplaçable : changer de modèle (CTC, LLM, futur fine-tuné) ne doit pas nécessiter de réécrire l'application ni l'API.
- **NFR10 :** Les jeux de données sont séparés **par locuteur** : aucune voix présente dans le jeu de test ne figure dans l'entraînement/la calibration.
- **NFR11 :** L'application fonctionne sur les téléphones Android courants en Afrique de l'Ouest et gère robustement les permissions micro et les connexions lentes (indicateurs clairs, annulation possible).
- **NFR12 :** Chaque reconnaissance persistée conserve au minimum `model_version` et `grammar_version` pour la traçabilité et la reproductibilité.
- **NFR13 :** Le déploiement s'appuie sur Docker avec images séparées (API légère / ASR lourde), reverse proxy nginx, monitoring, sauvegardes, et environnements local / staging / production distincts.
- **NFR14 :** Aucun fuzzy matching décisionnel (ex. distance de Levenshtein aveugle) n'est utilisé pour trancher un nombre.
- **NFR15 :** Contraintes de runtime : backend Python 3.11 (FastAPI, Pydantic) ; service ASR compatible Python `>= 3.10, < 3.14`.

---
