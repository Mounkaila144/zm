# Numération zarma — Spécification v1

> **Statut du document : PROVISOIRE — en attente de validation locuteurs natifs.**
> Toutes les formes ci-dessous sont marquées `unresolved` tant que le protocole
> de validation (§3) n'a pas été appliqué avec ≥ 3 locuteurs natifs. Aucune
> forme ne doit être considérée comme `validé` sans preuve de validation
> consignée dans le tableau de résultats (§7).

Ce document fige — **avant** le codage de la grammaire (stories 1.3 → 1.6) — le
système numérique zarma pour l'intervalle `0`–`999 999`, plus le traitement
prioritaire des grandes échelles `10 000` / `100 000` / `1 000 000`. Il constitue
le dérisquage linguistique du cœur produit.

---

## 1. Règle de décision (à lire en premier)

Le statut de chaque forme est déterminé par la règle de décision suivante,
appliquée aux réponses des locuteurs natifs interrogés séparément (§3) :

| Situation observée chez les locuteurs | Décision | Statut |
|---|---|---|
| **Unanimité** sur une forme | cette forme devient la **forme canonique** | `validé` |
| **Majorité 2 sur 3** | la forme majoritaire devient **canonique** ; l'autre forme est **conservée comme variante** | `validé` (avec variante) |
| **Désaccord complet** (aucune majorité) | aucune forme n'est figée | `unresolved` |
| Variante reconnue **correcte** par les locuteurs | **ne jamais la supprimer** | conservée |
| Variante **douteuse ou inventée** | **ne jamais l'ajouter** | rejetée |

**Gouvernance des variantes.** Aucune variante n'est ajoutée sans **au moins
l'une** des trois justifications : (1) validation par les locuteurs, (2) présence
dans une ressource linguistique fiable, ou (3) observation répétée dans les
transcriptions réelles. On n'invente jamais une variante ; on ne supprime jamais
arbitrairement une variante reconnue.

**Variantes ≠ corrections ASR.** Ce document ne recense que des **variantes
linguistiques** (formes réellement dites par des locuteurs). Il ne contient
**aucune** correction d'erreur ASR (confusions phonétiques du modèle vocal) —
notion distincte qui sera gérée séparément en aval. Ne pas mélanger les deux.

---

## 2. Vocabulaire numéral (PROVISOIRE — à valider)

> ⚠️ Toutes les formes de cette section sont **provisoires** (« à valider »).
> Elles proviennent de la spécification source et ne sont **pas** définitives.

### 2.1 Unités (0–9)

| Nombre | Forme isolée | Forme combinée | Statut |
|---:|---|---|---|
| 0 | yaamo | yaamo | `unresolved` |
| 1 | afo | fo | `unresolved` |
| 2 | ihinka | hinka | `unresolved` |
| 3 | ihinza | hinza | `unresolved` |
| 4 | itaci | taci | `unresolved` |
| 5 | igou | gou | `unresolved` |
| 6 | iddou | iddu | `unresolved` |
| 7 | iyye | iyye | `unresolved` |
| 8 | ahakou | hakou | `unresolved` |
| 9 | iyega | yega | `unresolved` |

**Observation** : plusieurs unités perdent leur voyelle initiale en forme
combinée (`afo`→`fo`, `ihinka`→`hinka`, `ahakou`→`hakou`, `iyega`→`yega`), mais
pas toutes (`iyye`, `yaamo`). Ce comportement des **voyelles initiales** est une
question ouverte à confirmer (voir §6).

### 2.2 Dizaines (10, 20, …, 90)

| Nombre | Forme proposée | Statut |
|---:|---|---|
| 10 | iwey | `unresolved` |
| 20 | waranka | `unresolved` |
| 30 | waranza | `unresolved` |
| 40 | waytaci | `unresolved` |
| 50 | waygou | `unresolved` |
| 60 | wayiddu | `unresolved` |
| 70 | wayiyye | `unresolved` |
| 80 | wayhakkou | `unresolved` |
| 90 | wayyegga | `unresolved` |

### 2.3 Échelles et connecteurs

| Élément | Forme | Rôle | Statut |
|---|---|---|---|
| Cent (100) | `zangou` | échelle 100 | `unresolved` |
| Mille (1 000) | `zambar` | échelle 1 000 | `unresolved` |
| Million (1 000 000) | `zambar yagga` / `miliyo` / autre | échelle 1 000 000 | **`unresolved` — non résolu / bloquant** |
| Liaison dizaine+unité | `cindi` | relie une dizaine et une unité (ex. `iwey cindi fo` = 11) | `unresolved` |
| « et » | `nda` / `da` | relie des groupes (centaines, milliers…) | `unresolved` |

---

## 3. Règles de composition + exemples (0–999 999)

Les formes composées suivent ces principes (à confirmer par la validation) :

1. **Dizaine + unité** → `<dizaine> cindi <unité combinée>` (ex. `24 = waranka cindi taci`).
2. **Centaines** → `zangou <multiplicateur>` (ex. `200 = zangou hinka`), le reste relié par `nda`.
3. **Milliers** → `zambar <valeur>` (ex. `1 000 = zambar fo`, `2 000 = zambar hinka`), le reste relié par `nda`.
4. **Groupes reliés** par `nda` (« et »).

### Exemples fournis (à reprendre tels quels, provisoires)

```text
# Dizaines composées (cindi)
11 = iwey cindi fo          13 = iwey cindi hinza        16 = iwey cindi iddu
19 = iwey cindi yega        24 = waranka cindi taci      56 = waygou cindi iddu
99 = wayyegga cindi yega

# Centaines (zangou … nda …)
100 = zangou                101 = zangou nda fo          156 = zangou nda waygou cindi iddu
200 = zangou hinka          250 = zangou hinka nda waygou
372 = zangou hinza nda wayiyye cindi hinka
999 = zangou yega nda wayyegga cindi yega

# Milliers (zambar … nda …)
1 000 = zambar fo           2 000 = zambar hinka
12 345 = zambar iwey cindi hinka nda zangou hinza nda waytaci cindi gou
45 678 = zambar waytaci cindi gou nda zangou iddu nda wayiyye cindi hakou
888 888 = zambar zangou hakou nda wayhakkou cindi hakou nda zangou hakou nda wayhakkou cindi hakou
999 999 = zambar zangou yega nda wayyegga cindi yega nda zangou yega nda wayyegga cindi yega
```

> Couverture : unités (0–9), dizaines simples et composées (`cindi`), centaines
> (`zangou`), milliers (`zambar`), groupes reliés (`nda`) — l'intervalle
> `0`–`999 999` est couvert par les règles ci-dessus. **Statut global :
> `unresolved`** jusqu'à validation.

---

## 4. Formes bloquantes prioritaires — grandes échelles

Ces trois formes sont traitées **en priorité** car elles conditionnent la
grammaire au-delà de `999 999`. Chacune est soit résolue (forme canonique
consignée), soit explicitement marquée **bloquante**.

| Nombre | Forme(s) candidate(s) | Statut | Question ouverte |
|---:|---|---|---|
| **10 000** | `zambar iwey` (= « mille dix » ? à confirmer) | **`unresolved` / bloquant** | 10 000 se dit-il `zambar iwey`, ou existe-t-il une échelle dédiée ? |
| **100 000** | `zambar zangou` (= « mille cent » ? à confirmer) | **`unresolved` / bloquant** | 100 000 = `zambar zangou`, ou forme spécifique ? |
| **1 000 000** | `zambar yagga` / `miliyo` / autre | **`unresolved` / bloquant** | Forme million **non résolue** : `zambar yagga` vs emprunt `miliyo` vs autre. |

> ⚠️ Tant qu'elles ne sont pas tranchées par les locuteurs, ces trois formes
> restent **bloquantes** : la grammaire (story 1.3+) ne pourra pas encoder de
> manière fiable les valeurs ≥ 10 000 sans cette décision.

---

## 5. Variantes régionales / orthographiques recensées

Variantes et incohérences **conservées** (jamais inventées, jamais supprimées
arbitrairement) — à trancher via le protocole §3 :

| Forme concernée | Variantes observées | Type | Note |
|---|---|---|---|
| 6 | `iddou` / `iddu` | orthographique | isolée vs combinée ? |
| 9 | `iyega` / `yega` / `yegga` | orthographique/régionale | dont `wayyegga` (90) |
| 8 | `ahakou` / `hakou` / `hakkou` | orthographique | dont `wayhakkou` (80) |
| 80 | `wayhakkou` | orthographique | gémination `kk` à confirmer |
| « et » | `nda` / `da` | phonologique/régionale | forme pleine vs réduite |
| 10 | `iwey` | variante ? | forme unique ou variantes régionales ? |
| 100 | `zangou` / `zangu` | orthographique | voyelle finale |
| 1 000 | usage de `fo` après `zambar` | composition | dit-on `zambar` seul ou `zambar fo` pour 1 000 ? |
| unités combinées | voyelles initiales | phonologique | quelles unités perdent leur voyelle initiale, et quand ? |
| régional | plusieurs variantes correctes possibles | régionale | Niamey / Dosso / autres — noter la région, pas l'identité |

**Rappel gouvernance** (cf. §1) : une variante n'est ajoutée que si validée par
les locuteurs, attestée dans une ressource fiable, ou observée de façon répétée
dans les transcriptions réelles.

---

## 6. Protocole de validation par locuteurs natifs

> Ce protocole est un **processus humain** hors du contrôle de l'outillage. Cette
> section décrit **comment** valider ; le tableau §7 sert à **consigner** les
> résultats. Tant que la validation réelle n'a pas eu lieu, tout reste
> `unresolved`.

### 6.1 Participants

- **≥ 3 locuteurs natifs** interrogés **séparément** (viser **5–10**).
- Tranches d'âge et **régions variées** (Niamey, Dosso, autres).
- La **région déclarée** est notée ; **l'identité n'est jamais publiée**.

### 6.2 Méthode (par nombre)

1. Montrer **les chiffres seuls** (ex. `156`).
2. Demander la **prononciation naturelle** (sans suggérer de forme).
3. **Écrire la réponse exacte** telle que prononcée.
4. Faire **répéter** pour confirmer.
5. Montrer **la proposition** du document.
6. Demander si elle est **correcte / naturelle / régionale**.

### 6.3 Liste minimale des nombres à vérifier

```text
0, 1, 2, 3, 4, 5, 6, 7, 8, 9,
10, 11, 12, 13, 16, 18, 19,
20, 24, 30, 35, 40, 50, 56, 60, 67, 70, 80, 90, 91, 99,
100, 101, 110, 111, 156, 200, 250, 372, 999,
1 000, 1 001, 1 010, 1 100, 2 000,
10 000, 12 345, 45 678, 100 000, 888 888, 999 999,
1 000 000
```

### 6.4 Questions à poser explicitement

- Dit-on **`nda`** ou **`da`** pour « et » ? Contexte de chaque forme ?
- **`zangou`** ou **`zangu`** pour 100 ?
- La forme **`iwey`** (10) est-elle unique, ou a-t-elle des variantes régionales ?
- Quelles sont les **formes exactes de 10 000 / 100 000 / 1 000 000** ?
- Dit-on **`zambar`** seul ou **`zambar fo`** pour 1 000 ?
- Quelles unités perdent leur **voyelle initiale** en forme combinée, et dans quels contextes ?
- Variantes `iddou`/`iddu`, `iyega`/`yega`/`yegga`, `ahakou`/`hakou`/`hakkou` : lesquelles sont naturelles / régionales ?

---

## 7. Tableau de résultats (à remplir lors de la validation)

Chaque forme documentée porte les champs :
`nombre` · `forme canonique` · `formes combinées` · `variantes acceptées` ·
`région éventuelle` · `nombre de validations` · `statut` · `notes`.

Le vocabulaire de statut (`validé` / `unresolved`) est **identique** à celui du
futur `lexicon.yaml` (story 1.3), pour cohérence aval.

| Nombre | Forme canonique | Formes combinées | Variantes acceptées | Région | Nb validations | Statut | Notes |
|---:|---|---|---|---|---:|---|---|
| 0 | yaamo | yaamo | — | — | 0 | `unresolved` | à valider |
| 1 | afo | fo | — | — | 0 | `unresolved` | à valider |
| 2 | ihinka | hinka | — | — | 0 | `unresolved` | à valider |
| 3 | ihinza | hinza | — | — | 0 | `unresolved` | à valider |
| 4 | itaci | taci | — | — | 0 | `unresolved` | à valider |
| 5 | igou | gou | — | — | 0 | `unresolved` | à valider |
| 6 | iddou | iddu | iddou / iddu | — | 0 | `unresolved` | variante orthographique |
| 7 | iyye | iyye | — | — | 0 | `unresolved` | à valider |
| 8 | ahakou | hakou | ahakou / hakou / hakkou | — | 0 | `unresolved` | variante orthographique |
| 9 | iyega | yega | iyega / yega / yegga | — | 0 | `unresolved` | variante orthographique |
| 10 | iwey | iwey | — | — | 0 | `unresolved` | variantes régionales ? |
| 20 | waranka | waranka | — | — | 0 | `unresolved` | à valider |
| 30 | waranza | waranza | — | — | 0 | `unresolved` | à valider |
| 40 | waytaci | waytaci | — | — | 0 | `unresolved` | à valider |
| 50 | waygou | waygou | — | — | 0 | `unresolved` | à valider |
| 60 | wayiddu | wayiddu | — | — | 0 | `unresolved` | à valider |
| 70 | wayiyye | wayiyye | — | — | 0 | `unresolved` | à valider |
| 80 | wayhakkou | wayhakkou | — | — | 0 | `unresolved` | gémination kk ? |
| 90 | wayyegga | wayyegga | — | — | 0 | `unresolved` | à valider |
| 100 | zangou | zangou | zangou / zangu | — | 0 | `unresolved` | voyelle finale |
| 1 000 | zambar | zambar (fo ?) | — | — | 0 | `unresolved` | `fo` après `zambar` ? |
| 10 000 | — | — | — | — | 0 | `unresolved` **bloquant** | forme exacte à trancher |
| 100 000 | — | — | — | — | 0 | `unresolved` **bloquant** | forme exacte à trancher |
| 1 000 000 | — | — | zambar yagga / miliyo / autre | — | 0 | `unresolved` **bloquant** | forme million non résolue |

**Connecteurs** : `cindi` (liaison dizaine+unité), `nda`/`da` (« et ») —
statut `unresolved`, à confirmer avec les questions §6.4.

---

## 7bis. Validation — Session 1 (1 locuteur natif)

- **Locuteur** : 1 locuteur natif (région non précisée ; identité non publiée).
- **Date** : 2026-07-24.
- **Statut de gouvernance** : ⚠️ **1 seul locuteur** — la règle de décision (§1)
  exige **unanimité** ou **majorité 2 sur 3** sur **≥ 3 locuteurs** avant de
  passer une forme en `validé`. Les résultats ci-dessous sont donc **confirmés
  Session 1** (candidats forts), mais restent formellement `unresolved` tant que
  2 locuteurs supplémentaires n'ont pas confirmé.

### Grammaire 0–999 — **confirmée** (structure)

Règle des **centaines multiplicative** confirmée : `zangou <unité combinée>` =
unité × 100 ; reste relié par `nda`/`da`.

| Nombre | Forme donnée (S1) | Cohérent avec le moteur ? |
|---:|---|---|
| 200 | `zangou hinka` | ✅ identique |
| 300 | `zangou hinza` | ✅ identique |
| 500 | `zangou gou` | ✅ identique |
| 150 | `zangou nda weygou` | ✅ (`weygou`≈`waygou`) |
| 250 | `zangou hinka da waygou` | ✅ (`da`=`nda`) |
| 102 | `zangou nda ihinka` | ✅ (parseur accepte `ihinka` **et** `hinka`) |
| 24 | `waranka cindi taci` | ✅ identique |

→ **Le générateur/parseur `zarma_numbers` est linguistiquement validé pour
`0`–`999 999` (structure + formes canoniques).** Le parseur accepte déjà la
forme **isolée et combinée** des unités (`ihinka`/`hinka`) et le connecteur
`nda`/`da`/`di`.

**⚠️ Gap de robustesse (entrée réelle, à traiter en Epic 2) :** les variantes
de **graphie/région des échelles et dizaines** ne sont **pas encore** reconnues
par le parseur : `zongou`/`zangu` (100), `weygou` (50). Aujourd'hui seul
`zangou`/`waygou` (formes canoniques) sont acceptées. À ajouter comme variantes
reconnues (lexique + parseur/normaliseur) pour absorber l'entrée ASR/native.

### Connecteurs

- `nda` / `da` / **`di`** = même connecteur « et » (variation libre selon
  locuteur). → **ajouter `di`** aux variantes du connecteur `groups`.

### Reste après échelle (séries 1001–1009, S1)

`1001 zambar fo da fo` · `1002 zambar fo di ihinka` · `1003 …ihinza` ·
`1004 …itaci` · `1005 …igou` · `1006 da iddou` · `1007 da iyye` ·
`1008 da hakou` · `1009 da yega`. Le reste emploie **tantôt la forme longue
(isolée) tantôt la courte (combinée)** — variation libre confirmée par le
locuteur. L'invariant reste garanti (le parseur accepte les deux formes).
Corrections de coquilles : `1010 = zambar fo di iwey`, `1011 = zambar fo di
iwey cindi fo`.

### Grandes échelles — candidats Session 1 (⚠️ toujours à confirmer ≥3)

| Nombre | Candidat S1 | Statut | Note |
|---:|---|---|---|
| 10 000 | `zambar wey` | `unresolved` (candidat) | 10 en composition = `wey` (≠ `iwey`) |
| 20 000 / 30 000 | `zambar waranka` / `zambar waranza` | `unresolved` (candidat) | multiplicatif |
| 100 000 | `zambar zongou` | `unresolved` (candidat) | |
| 1 000 000 | `million` (ou `million fo`) | `unresolved` (candidat fort) | emprunt ; 2 M = `million hinka` |

### 🔑 Désambiguïsation ≥ 100 000 — mécanisme identifié (S1, à confirmer ≥3)

**Mécanisme de désambiguïsation confirmé pour les multiplicateurs à dizaines**
(plage 10 000–99 999) : `cindi` = **lié** (dans le multiplicateur) vs
`nda`/`da`/`di` = **séparé** (reste).

| Nombre | Forme (S1) | Décodage |
|---:|---|---|
| 15 000 | `zambar wey cindi gou` | multiplicateur 15 (`wey cindi gou`), lié par `cindi` |
| 10 005 | `zambar wey di gou` | 10 000 **+ reste 5**, séparé par `di` |

→ **déjà implémenté** : `generate(15000)="zambar iwey cindi gou"`,
`generate(10005)="zambar iwey nda gou"` — identiques (roundtrip OK).

**Pour les multiplicateurs à centaines** (plage ≥ 100 000), un **marqueur de
reste spécial `dala`** (« da dala ») lève l'ambiguïté :

| Nombre | Forme (S1) | Décodage |
|---:|---|---|
| 105 000 | `zambar zongou di gou` | multiplicateur 105 (`zongou di gou`), lié |
| 100 005 | `zambar zangou **da dala** gou` | 100 000 **+ reste 5**, marqué par **`dala`** |

→ **Conséquence majeure : les grandes échelles `≥ 100 000` sont RÉSOLUBLES**
(le zarma désambiguïse via `dala`), contrairement à l'hypothèse initiale
d'ambiguïté irréductible. **MAIS** : (a) `dala` est un **nouveau lexème/règle**
absent de la spec et du moteur actuels ; (b) 1 seul locuteur (réponses passées
partiellement contradictoires) → **≥ 3 locuteurs requis** ; (c) implémenter
`dala` demande une **évolution de la grammaire** (générateur + parseur).

→ **Décision** : conserver `≥ 100 000` en `unresolved` dans le code actuel
(invariant prouvé sur `0`–`99 999`) ; ouvrir une **story dédiée** (via
`/correct-course`) pour spécifier et implémenter la règle `dala` après
validation ≥ 3 locuteurs.

**Sens de `dala` (S1) :** `dala` = **« une unité »** en zarma. C'est un
**marqueur de reste explicite** : `da dala <unité>` force la lecture « + unité
isolée » (reste), par opposition à `di <unité>` qui rattache l'unité au nombre
composé (multiplicateur). Utilisable dès les centaines :
`102 = zangou da dala hinka` **ou** `zangou di hinka` (les deux, à petite
échelle) ; le `dala` devient **discriminant** à grande échelle :

| Nombre | Forme (S1) | Rôle de `dala` |
|---:|---|---|
| 105 000 | `zambar zongou di gou` | pas de `dala` → `5` dans le multiplicateur (105) |
| 100 005 | `zambar zangou da dala gou` | `dala` → `5` = reste-unité (+5) |

→ **Règle de désambiguïsation ≥ 100 000 identifiée et cohérente.** La grammaire
peut donc, à terme, générer/parser toute la plage `0`–`1 000 000` sans ambiguïté.

**Reste à confirmer (Session 2/3, ≥3 locuteurs) :**
- Portée exacte de `dala` : uniquement devant une **unité** (1–9), ou aussi
  devant dizaines/centaines de reste ? (ex. 100 015, 200 070 ?)
- Formes complètes de `1 000 005`, `100 015`, `200 007` pour figer la règle.
- Stabilité `di`/`nda`/`da dala` selon les locuteurs et régions.

---

## 8. Synthèse des statuts

- **Formes documentées :** unités 0–9, dizaines 10–90, centaine, millier,
  connecteurs → **toutes `unresolved`** (provisoires, en attente de validation).
- **Formes bloquantes prioritaires :** `10 000`, `100 000`, `1 000 000` →
  **`unresolved` / bloquantes**, chacune avec sa question ouverte (§4).
- **Variantes recensées :** conservées et non inventées (§5).
- **Règle de décision :** documentée en tête (§1) et appliquée au tableau (§7).

**Prochaine étape :** appliquer le protocole §6 avec ≥ 3 locuteurs natifs, puis
mettre à jour les statuts (`validé` / `unresolved`) et le nombre de validations
dans le tableau §7. Ce document alimentera ensuite le `lexicon.yaml` de la
story 1.3.

---

## Références sources

- `docs/specification-complete-application-nombres-zarma.md` §7 (7.1 Unités,
  7.2 Dizaines, 7.3 Échelles et connecteurs, 7.4 Exemples, 7.5 Variantes) et §8
  (8.1–8.6 protocole, règle de décision, fichier de résultat).
- `docs/architecture.md` — Décisions clés & risques résiduels ; Coding Standards
  (« Variantes ≠ corrections ASR ») ; GrammarVersionInfo.
- `docs/prd/epic-1-*.md` — Stories 1.2 et 1.3.
