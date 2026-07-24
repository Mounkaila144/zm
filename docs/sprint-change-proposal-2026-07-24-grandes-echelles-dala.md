# Sprint Change Proposal — Grandes échelles & marqueur `dala`

- **Date :** 2026-07-24
- **Déclenché par :** session de validation avec un locuteur natif (pendant/après l'Epic 1)
- **Auteur :** James (Dev) via `/correct-course`
- **Statut :** proposé — en attente d'approbation

---

## 1. Résumé du problème (Trigger & Context)

**Story déclenchante :** Story 1.6 (parseur + invariant). En écrivant le parseur, une **ambiguïté** du système numérique a été détectée pour `n ≥ 100 000` : `generate(100 005)` et `generate(105 000)` produisaient la même chaîne `zambar zangou nda gou`. Décision prise en 1.6 : prouver l'invariant sur la plage résolue `0–99 999` et **tracer** `100 000–1 000 000` comme non résolu.

**Nouvelle information (session locuteur natif) :** l'ambiguïté **n'en est pas une** en zarma réel. Le locuteur a fourni :
- **Mécanisme de désambiguïsation** : `cindi` = lié (multiplicateur) vs `nda`/`da`/`di` = séparé (reste), pour les multiplicateurs à **dizaines** — *déjà implémenté* (`generate(15000)="zambar iwey cindi gou"`, `generate(10005)="zambar iwey nda gou"`).
- **Marqueur `dala`** (= « une unité ») qui lève l'ambiguïté aux **grandes échelles** :
  - `105 000 = zambar zongou di gou` (5 dans le multiplicateur 105) ;
  - `100 005 = zambar zangou da dala gou` (`dala` → 5 = reste-unité).
- **Forme million résolue** : `1 000 000 = million` (ou `million fo`) ; `2 000 000 = million hinka`.
- **Variantes régionales d'entrée** : `zongou`/`zangu` (100), `weygou` (50), `wey` (10 en composition), connecteur `di`.

**Nature du changement :** exigence nouvellement découverte + correction d'une hypothèse erronée (ambiguïté irréductible). **Pas** un échec technique : le moteur `0–999 999` est **confirmé linguistiquement correct** par le locuteur.

**Impact immédiat observé :** aucune régression. Le moteur reste valide sur `0–99 999`. Le changement **étend** la portée résoluble (potentiellement jusqu'à `1 000 000`) au prix d'une évolution de grammaire.

**Preuve :** échanges de validation consignés dans `docs/numeration-zarma-v1.md` §7bis (Session 1).

**Réserve de gouvernance :** **1 seul locuteur** à ce jour ; la règle de décision (numeration §1) exige **≥ 3 locuteurs** (unanimité / majorité 2-sur-3) avant de figer une forme en `validé`.

---

## 2. Impact sur les Epics

- **Epic 1 (Fondations & moteur linguistique) — TERMINÉ, non invalidé.**
  - Le moteur `0–999 999` est confirmé correct. Aucune story 1.1–1.6 n'est à annuler ni rollback.
  - **Ajout** : une nouvelle story **1.7 — « Grandes échelles ≥ 100 000 (marqueur `dala`) & million »** étend l'Epic 1. Elle est **gatée** sur la validation ≥ 3 locuteurs.
- **Epic 2 (API)** — impact mineur : l'endpoint `/grammar/version` bumpera `grammar_version` quand `dala`/`million` seront intégrés ; les variantes d'entrée (`zongou`/`zangu`/`weygou`) améliorent la robustesse ASR → une petite story « variantes d'entrée » peut être ajoutée à l'Epic 2 (ou incluse en 1.7).
- **Epics 3, 4, 5** — pas d'impact structurel. (Epic 5 calibrera de toute façon les confusions ASR séparément.)

**Synthèse :** structure des epics **préservée** ; une story ajoutée en fin d'Epic 1, un léger enrichissement possible en Epic 2.

---

## 3. Conflits & impacts sur les artefacts

| Artefact | Impact | Nature |
|---|---|---|
| `docs/numeration-zarma-v1.md` | ✅ déjà mis à jour | §7bis Session 1 (mécanisme `cindi`/`di`, `dala`, million, variantes) |
| `docs/prd/epic-1-*.md` | à modifier | ajouter la story 1.7 à la liste des stories de l'Epic 1 |
| `docs/stories/1.7.story.md` | à créer | nouvelle story (draft) |
| `packages/.../lexicon.yaml` | à modifier (story 1.7) | ajouter `dala`, `million` (échelle), variantes `zongou`/`zangu`/`weygou`/`wey` ; bump `grammar_version` |
| `packages/.../generator.py` | à modifier (story 1.7) | émettre `da dala <unité>` sur reste-unité à grande échelle ; million |
| `packages/.../parser.py` | à modifier (story 1.7) | reconnaître `dala`, `million`, variantes d'échelle/dizaine |
| `packages/.../validator.py` | à modifier (story 1.7) | étendre `RESOLVED_MAX` (jusqu'à 1 000 000 si validé) |
| `docs/architecture.md` | vérifier | `grammar_version` / `GrammarVersionInfo` — bump documenté |
| PRD (goals/requirements) | **pas de conflit** | les objectifs MVP restent valides |

**Note :** aucune décision architecturale n'est invalidée. Le paquet reste autonome (stdlib + PyYAML). Le changement est **additif**.

---

## 4. Évaluation du chemin (Path Forward)

### Option 1 — Ajustement direct / intégration (✅ RECOMMANDÉ)
Créer **story 1.7** (extension Epic 1) pour spécifier + implémenter `dala`/`million`/variantes, **gatée** sur validation ≥ 3 locuteurs. Le code `0–999 999` reste tel quel.
- **Effort :** modéré (grammaire generator/parser + tests + invariant étendu).
- **Travail jeté :** aucun.
- **Risques :** faible côté code ; **risque linguistique** = 1 seul locuteur → mitigé par le gating ≥ 3 locuteurs.
- **Timeline :** implémentable dès validation ; n'empêche pas de démarrer l'Epic 2 en parallèle.

### Option 2 — Rollback
Revenir sur des stories 1.x. **Rejeté** : rien à annuler, le moteur est correct.

### Option 3 — Re-scoping du MVP
Réduire/modifier le périmètre MVP. **Rejeté** : le MVP reste atteignable ; c'est une extension, pas une remise en cause.

**Chemin retenu : Option 1.**

---

## 5. Édits proposés (concrets)

### 5.1 `docs/prd/epic-1-*.md` — ajouter à la liste des stories

> **Story 1.7 — Grandes échelles ≥ 100 000 (marqueur `dala`) & forme million**
> Étendre le moteur linguistique pour générer/parser sans ambiguïté la plage
> `0`–`1 000 000`, en intégrant le marqueur de reste `dala` (« une unité ») et
> la forme `million`, après validation par ≥ 3 locuteurs natifs.

### 5.2 Nouvelle story `docs/stories/1.7.story.md` (draft) — critères d'acceptation proposés

1. Le lexique intègre `dala` (marqueur de reste-unité), l'échelle `million` (canonical `million`, variantes `million fo`/`miliyo`), et les variantes d'entrée `zongou`/`zangu` (100), `weygou` (50), `wey` (10) ; `grammar_version` est bumpé (ex. `1.1.0`).
2. Le **générateur** produit la forme désambiguïsée à grande échelle : reste-unité après échelle marqué `da dala <unité>` (ex. `100 005 = zambar zangou da dala gou`), multiplicateur lié sans `dala` (ex. `105 000 = zambar zongou di gou`), et `1 000 000 = million`.
3. Le **parseur** reconnaît `dala`, `million` et les variantes d'entrée ; `parse` reste l'inverse exact du générateur.
4. L'**invariant** `parse(normalize(generate(n))) == n` est étendu et **prouvé sur `0`–`1 000 000`** (plus aucune plage tracée `ambiguous` ; seules d'éventuelles formes encore `unresolved` sont tracées).
5. **Gating :** la story n'est marquée `validé` (statuts lexique) qu'après confirmation par **≥ 3 locuteurs natifs** (règle de décision, numeration §1) ; à défaut, les formes restent `unresolved` et l'implémentation est livrée derrière ce gate.
6. Tests : cas `dala` (100 005 vs 105 000, 100 015, 200 007, 1 000 005), million, variantes d'entrée ; invariant complet en CI (`make invariant`).

### 5.3 `packages/zarma_numbers/src/zarma_numbers/lexicon.yaml`
- Ajouter une section connecteur/marqueur `dala` ; résoudre `scales.million` (canonical `million`) ; enrichir variantes `hundred`/`tens` ; bump `version`.

### 5.4 `generator.py` / `parser.py` / `validator.py`
- Grammaire : règle `dala` sur reste-unité à grande échelle ; support `million` ; `RESOLVED_MAX` → `1 000 000` (sous réserve validation).

---

## 6. Impact MVP & plan d'action

- **PRD MVP :** inchangé. Extension additive, pas de changement de portée ni de but.
- **Plan d'action :**
  1. **[Bloquant linguistique]** Compléter la validation : Session 2/3 avec ≥ 2 locuteurs supplémentaires ; recueillir `1 000 005`, `100 015`, `200 007` et confirmer la portée de `dala`.
  2. Créer `docs/stories/1.7.story.md` (SM `/sm`) + l'ajouter à l'Epic 1.
  3. Implémenter 1.7 (Dev `/dev`) une fois approuvée/validée.
  4. Enrichir l'Epic 2 (variantes d'entrée) si non couvert par 1.7.

- **Critère de succès :** invariant `parse(generate(n)) == n` **vert sur `0`–`1 000 000`** en CI, formes clés confirmées par ≥ 3 locuteurs.

---

## 7. Plan de handoff (agents)

| Rôle | Action |
|---|---|
| **PO / porteur produit** | Piloter la validation ≥ 3 locuteurs (processus humain) ; approuver ce proposal |
| **SM (`/sm`)** | Rédiger `docs/stories/1.7.story.md` à partir du §5.2 ; l'ajouter à l'Epic 1 |
| **Dev (`/dev`)** | Implémenter 1.7 après approbation + validation locuteurs |
| **Architect (`/architect`)** | (léger) valider le bump `grammar_version` / `GrammarVersionInfo` |

**Pas de replan fondamental requis** — pas de handoff PM pour une PRD v2.

---

## 8. Décision demandée

Approuver ce proposal pour :
1. acter que le moteur `0–999 999` est validé et conservé ;
2. créer la **story 1.7** (grandes échelles + `dala` + million), gatée ≥ 3 locuteurs ;
3. planifier la validation Session 2/3 comme prérequis linguistique.
