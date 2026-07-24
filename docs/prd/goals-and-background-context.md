# Goals and Background Context

## Goals

- Livrer une bêta Android où le parcours complet **enregistrer → reconnaître → confirmer/corriger** fonctionne de bout en bout, évaluée sur des locuteurs non vus.
- Fournir un **moteur linguistique déterministe** zarma (texte ↔ nombre) passant l'invariant `parse(generate(n)) == n` sur toute la plage `0`–`1 000 000`.
- Publier un **lexique numérique zarma v1 validé** par des locuteurs natifs, avec les formes de 10 000 / 100 000 / 1 000 000 résolues ou explicitement marquées bloquantes.
- Choisir le **modèle ASR du MVP sur des données** (benchmark reproductible, métrique Exact Number Accuracy), et jamais sur une démonstration manuelle.
- Garantir un système **prudent** qui préfère demander confirmation ou rejeter plutôt qu'inventer un nombre, sans jamais passer par le français.
- Constituer un **socle de données consenties et anonymisées** réutilisable pour l'amélioration continue et de futures applications vocales zarma.

## Background Context

Le zarma (`dje_Latn`), parlé par plusieurs millions de personnes en Afrique de l'Ouest (principalement au Niger), est quasi absent des technologies vocales. Les moteurs grand public ne le supportent pas directement et le font transiter par le français, ce qui confond des formes acoustiquement proches mais numériquement très différentes (`hinka`/`hinza`, `iyye`/`yega`, `iddu`/`iyye`) et produit des erreurs graves et silencieuses. Pour une langue à forte tradition orale, saisir un nombre par la voix est un cas d'usage à forte valeur (commerce, comptage, éducation, accessibilité) et un point d'entrée réaliste pour bâtir un écosystème vocal zarma.

La publication récente de Meta Omnilingual ASR (Apache 2.0), qui annonce le support de `dje_Latn`, ouvre une fenêtre d'opportunité : construire un moteur zarma sérieux sans entraîner de modèle depuis zéro. L'approche retenue sépare strictement le **moteur linguistique** (texte → nombre, déterministe, testable sans GPU) du **moteur vocal** (audio → texte, remplaçable), et s'appuie sur une grammaire formalisée, un lexique versionné validé par des locuteurs, une table de corrections ASR distincte des variantes linguistiques, et une gestion prudente de l'ambiguïté. Le maillon critique — la validation linguistique — est débloquable immédiatement grâce à 3+ locuteurs natifs disponibles.

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-07-23 | 1.0 | Création initiale du PRD à partir du brief (mode YOLO) | John (PM) |

---
