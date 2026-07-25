# Prompt pour Fable 5 — correction du connecteur `da`/`di` et de l'automate

> Copier tout ce qui suit dans une nouvelle session Fable 5, à la racine du dépôt.

---

## Contexte

Ce dépôt (`/Users/pc/project/zarma`) est une application de reconnaissance vocale de
**nombres en zarma** (langue songhaï du Niger) destinée à des commerçants **ne sachant ni
lire ni écrire**. Le cœur du produit est un moteur linguistique déterministe
(`packages/zarma_numbers`) et un **décodage CTC contraint à la grammaire des nombres**
(story 5.6, livrée et mesurée à **89,6 %** d'Exact Number Accuracy sur 96 audios / 3 locuteurs).

Un locuteur natif vient de corriger une **erreur linguistique de fond** dans le lexique.
La correction est faite au niveau du générateur et du parseur, **mais elle casse l'automate
de la grammaire**. C'est ce que je te demande de réparer.

## La correction linguistique (déjà appliquée, ne pas la remettre en cause)

Le lexique traitait `nda` / `da` / `di` comme des **variantes libres** du connecteur de
groupes. C'est faux. Le locuteur a établi qu'elles sont en **distribution complémentaire** :

- **`di`** devant les valeurs de tête **2, 3, 4, 5 et 10** — et le **`i` initial du mot
  suivant s'élide** (`iwey` → `wey`)
- **`da`** partout ailleurs (1, 6, 7, 8, 9, les dizaines 20–90, les centaines)

La « valeur de tête » est celle du **premier mot du groupe qui suit** : dans
`115 = zongou di wey cindi gou`, le groupe commence par 10 → `di` ; dans
`199 = zongou da wayyegga cindi yega`, il commence par 90 → `da`.

Exemples validés par le locuteur (référence à respecter) :

```
101  zongou da fo                 110  zongou di wey
102  zongou di hinka              115  zongou di wey cindi gou
103  zongou di hinza              120  zongou da waranka
104  zongou di taci               130  zongou da waranza
105  zongou di gou                150  zongou da weygou
106  zongou da iddou              199  zongou da wey yega cindi yega
107  zongou da iyye              1001  zambar fo da fo
108  zongou da hakou             1002  zambar fo di hinka
109  zongou da yega              1100  zambar fo da zongou
                                 1500  zambar fo da zongou gou
```

> Notes : `zongou`/`zangou` et `wey`/`way` sont des graphies équivalentes — le locuteur a
> demandé de **ne pas y toucher**. Le seul écart connu et non tranché est `iddu` (lexique)
> vs `iddou` (locuteur) pour 6 ; les deux sont listés comme variantes.

**Aucune règle phonétique n'a été devinée** : `da hakou` et `di hinka` commencent tous deux
par « h », la sélection ne se déduit donc pas du son. C'est une **table explicite** de 5 valeurs.

## Ce qui est déjà fait et fonctionne

- `lexicon.yaml` : `groups` = `da` (variantes `da`, `nda`) et nouveau `groups_elided` = `di` ;
  `wey` ajouté comme variante de `iwey` ; `version` 1.1.0 → **1.2.0**
- `generator.py` : sélection du connecteur + élision (`_ELIDED_CONNECTOR_HEADS`,
  `_leading_value`, `_elide_initial_i`, `_join_group`)
- `parser.py` : accepte indifféremment `da` et `di` à l'analyse
- ✅ **Invariant vérifié : `parse(generate(n)) == n` sur les 1 000 001 nombres, 0 violation**
- ✅ Conformité aux exemples du locuteur : 20/21

## Le problème à résoudre

`packages/zarma_numbers/src/zarma_numbers/grammar.py` dérive un **automate/trie des formes
valides** en observant la sortie du générateur et en **retirant un préfixe fixe** contenant le
connecteur. Cette hypothèse ne tient plus. Erreur actuelle :

```
GrammarDerivationError: Structure inattendue du générateur pour reste 2 :
('zambar', 'fo', 'di', 'hinka') ne commence pas par ('zambar', 'fo', 'da').
```

**La difficulté réelle** n'est pas le message d'erreur : c'est que **l'arête du connecteur
dans l'automate dépend désormais de l'état suivant**. Un `da` et un `di` ne mènent pas aux
mêmes continuations. L'automate doit encoder cette dépendance **sans devenir ambigu** et
**sans accepter de formes invalides** (par exemple `zongou di waranka`, qui n'existe pas).

C'est une modification de **structure**, pas un chercher-remplacer.

## Ce que je te demande

Rendre le système cohérent de bout en bout avec la nouvelle règle :

1. **L'automate** accepte exactement l'ensemble des formes que le générateur produit — ni
   plus (pas de forme invalide acceptée), ni moins.
2. **Le décodage contraint** (`services/asr/app/decoding.py`, story 5.6) refonctionne sur ce
   nouvel automate.
3. **Les tests** reflètent la nouvelle vérité. Certains asserts portent sur l'ancienne forme
   (`nda`) ou l'ancienne version (1.1.0) : ils doivent être **mis à jour**, pas contournés.
4. **L'invariant reste vérifié** sur les 1 000 001 nombres.

### État actuel des tests (à ramener au vert)

```
61 ERROR  packages/zarma_numbers/tests/test_grammar.py      ← l'automate ne se construit plus
30 ERROR  services/asr/tests/test_decoding.py               ← dépend de l'automate
20 ERROR  services/asr/tests/test_rejection.py              ← idem
10 ERROR  services/asr/tests/test_decoder_properties.py     ← idem
10 FAILED packages/zarma_numbers/tests/test_generator.py    ← asserts sur l'ancienne forme
 4 FAILED packages/zarma_numbers/tests/test_normalizer.py   ← canonique changé (nda → da)
 3 FAILED packages/zarma_numbers/tests/test_loader.py       ← version 1.1.0 → 1.2.0
```

Avant la correction linguistique, la suite complète était à **517 tests au vert**.

## Contraintes non négociables

- **Source unique** : la grammaire se **dérive** du lexique et du générateur. Aucune forme,
  aucune règle ne doit être réécrite en dur dans `grammar.py` ou ailleurs.
- **Jamais de forme inventée** : si une brique manque au lexique, échouer explicitement
  (`GrammarDerivationError`) plutôt que deviner — c'est déjà le principe du module.
- **Aucun fuzzy matching décisionnel** (NFR14) : la sélection d'un nombre reste un score
  acoustique sur un espace de sorties valides, jamais une distance d'édition textuelle.
- **Ne pas modifier** : l'interface `SpeechRecognizer` (`services/api/app/asr/base.py`),
  l'API publique, ni `apps/mobile/`.
- **CI sans GPU** : les tests tournent sur des logits en fixtures
  (`services/asr/tests/fixtures/`). Ne pas introduire de dépendance à un modèle.
- **Ne pas « corriger »** `zangou`→`zongou` ni `way`→`wey` : décision explicite du locuteur.

## Vérifications attendues

```bash
# 1. Invariant exhaustif — doit rester à 0 violation
uv run python -c "import sys; from zarma_numbers.validator import main; sys.exit(main())"

# 2. Suite complète — doit repasser au vert
uv run pytest -q

# 3. Lint
uv run ruff check . && uv run black --check .

# 4. Conformité aux exemples du locuteur (le tableau ci-dessus)
```

## Attendu en sortie

- Le code corrigé, avec les tests à jour.
- Une note courte expliquant **comment tu as encodé la dépendance du connecteur dans
  l'automate**, et pourquoi elle ne crée pas d'ambiguïté.
- Le signalement de tout impact que je n'aurais pas anticipé — en particulier :
  - la **vérité terrain du benchmark** (`docs/qa/benchmarks/decoding-greedy-vs-constrained-v1.*`)
    a été mesurée avec l'ancien connecteur : elle est à re-mesurer, mais la passe exige
    l'environnement ASR lourd (hors périmètre de cette tâche — signale-le, ne le lance pas) ;
  - la **banque vocale** (`scripts/speech/say_number.py`) : `nda.wav` doit devenir
    `da.wav` + `di.wav`, et `wey.wav` s'ajoute.

Si tu estimes qu'une partie de la demande est mal posée ou risquée, dis-le et propose mieux
plutôt que de l'appliquer telle quelle.
