# Liste d'enregistrement — banque vocale zarma

> ## ✅ La banque vocale est complète (séance `~/Music/voix2`, 2026-07-25)
>
> **40 / 40 mots + 4 consignes.** L'application peut prononcer **les 1 000 001 nombres**
> (0 à 1 000 000), n'importe quel résultat d'opération (reste de division compris), la
> demande de confirmation et le message de refus. Couverture vérifiée : **1001/1001**.
>
> **Il reste un seul lot d'enregistrements**, et il ne sert pas à ce que l'app *parle*
> mais à ce qu'elle *comprenne* : le **groupe E5** (160 énoncés d'opérations complets).
> C'est le dernier point qui bloque la mesure de la story 6.1.
>
> Les groupes A–D ci-dessous sont conservés comme référence — ils redeviennent la liste
> à suivre pour enregistrer une **voix supplémentaire**.

> Liste générée depuis `lexicon.yaml` — **source unique**, rien n'est inventé ici.

## ⚙️ Réglages techniques

| Paramètre | Valeur |
|---|---|
| Format | **WAV** |
| Échantillonnage | **16 000 Hz** (16 kHz) |
| Canaux | **Mono** |
| Profondeur | **16 bits PCM** |
| Nom de fichier | **exactement le mot** — ex. `waranka.wav` |

Dépose tout dans un seul dossier (ex. `~/Music/voix2/`).

## 🎙️ Les 6 règles qui font la différence

Ces mots vont être **collés bout à bout** pour former des phrases. La qualité du résultat
dépend moins du micro que de la **régularité**.

1. **⭐ Intonation PLATE — la règle la plus importante.**
   Prononce chaque mot comme s'il était **au milieu d'une phrase**, pas à la fin.
   Si tu descends la voix à la fin de chaque mot (comme un point final), l'assemblage
   sonnera comme une liste hachée : « vingt. trois. » au lieu de « vingt-trois ».

2. **Ne bouge pas** par rapport au micro pendant toute la séance (distance et angle constants).

3. **Tout en une seule séance.** Le timbre de la voix change d'un jour à l'autre ; mélanger
   deux séances s'entend nettement à la jonction des mots.

4. **Débit régulier**, ni trop lent ni sur-articulé. Un mot isolé a tendance à être exagéré —
   dis-le au rythme naturel d'une phrase.

5. **Laisse ~0,5 s de silence** avant et après chaque mot. Je le couperai automatiquement.

6. **2 ou 3 prises par mot**, garde la meilleure. C'est rapide et ça sauve les ratés.

> 💡 Astuce : enregistre d'abord une phrase test (« waranka cindi hinza »), puis les mots
> `waranka`, `cindi`, `hinza` séparément. En comparant l'assemblage à la vraie phrase, tu
> entendras tout de suite si ton intonation isolée est trop marquée.

---

## GROUPE A — Nombres (35 mots) · **indispensable**

### A1. Zéro (1)

- [ ] `yaamo` — 0

### A2. Unités, forme **isolée** (9) — quand le nombre est dit **seul**

- [ ] `afo` — 1
- [ ] `ihinka` — 2
- [ ] `ihinza` — 3
- [ ] `itaci` — 4
- [ ] `igou` — 5
- [ ] `iddou` — 6
- [ ] `iyye` — 7 ⚠️ *identique à la forme combinée → un seul enregistrement*
- [ ] `ahakou` — 8
- [ ] `iyega` — 9

### A3. Unités, forme **combinée** (8) — à l'**intérieur** d'un nombre composé

> Ce sont des mots **différents** des précédents : `afo` (1 seul) mais `iwey cindi **fo**` (11).

- [ ] `fo` — 1 (composé)
- [ ] `hinka` — 2 (composé)
- [ ] `hinza` — 3 (composé)
- [ ] `taci` — 4 (composé)
- [ ] `gou` — 5 (composé)
- [ ] `iddu` — 6 (composé)
- [ ] `hakou` — 8 (composé)
- [ ] `yega` — 9 (composé)

### A4. Dizaines (10)

- [ ] `iwey` — 10
- [ ] `wey` — 10 après `di` (forme élidée : `zangou di **wey**` = 110)
- [ ] `waranka` — 20
- [ ] `waranza` — 30
- [ ] `waytaci` — 40
- [ ] `waygou` — 50
- [ ] `wayiddu` — 60
- [ ] `wayiyye` — 70
- [ ] `wayhakkou` — 80
- [ ] `wayyegga` — 90

### A5. Échelles (3)

- [ ] `zangou` — 100
- [ ] `zambar` — 1 000
- [ ] `million` — 1 000 000

### A6. Connecteurs (4)

> ⚠️ `da` et `di` ne sont **pas** interchangeables (correction locuteur) :
> `di` devant 2, 3, 4, 5 et 10 (avec `wey`), `da` partout ailleurs.
> L'ancien enregistrement `nda.wav` ne suffit plus.

- [ ] `cindi` — lie une dizaine à une unité (`iwey cindi fo` = 11)
- [ ] `da` — connecteur général (`zangou da fo` = 101, `zangou da waranka` = 120)
- [ ] `di` — connecteur devant 2, 3, 4, 5, 10 (`zangou di gou` = 105, `zangou di wey` = 110)
- [ ] `dala` — marqueur de reste aux grandes échelles (`zambar zangou da dala gou` = 100 005)

---

## GROUPE B — Division avec reste (1 mot) · **nouveau**

- [ ] `ga` — marqueur du reste : `waranka **ga** cindi hinza` = « 20 reste 3 »

> ⚠️ À ne pas confondre avec `dala` (groupe A6) : ce sont **deux marqueurs différents**.

---

## GROUPE C — Opérateurs (4 mots) · ✅ **complet**

- [x] `tonton` — addition `+` ✅ *validé par le locuteur*
- [x] `zabou` — soustraction `−` ✅ *validé par le locuteur*
- [x] `ingaybor` — multiplication `×` ✅ *validé le 2026-07-25*
- [x] `inafaysor` — division `÷` ✅ *validé le 2026-07-25*

> Les quatre formes sont **intégrées au lexique** (`grammar_version` 1.4.0) : les quatre
> opérations sont désormais reconnues, évaluées et prononçables.

> ⚠️ **Ces mots servent aussi à ce que l'app parle**, pas seulement à ce qu'elle comprenne :
> pour demander « c'est bien vingt-trois plus quinze ? », elle doit **relire l'opération**.
> Sans `tonton` et `zabou` dans la banque, aucune confirmation d'opération n'est prononçable.
> Enregistre-les avec l'**intonation plate** du groupe A (ce sont des briques à assembler),
> même si tu les redis autrement dans les phrases du groupe E.

---

## GROUPE D — Phrases de dialogue · **à formuler d'abord**

L'utilisateur cible **ne lit pas** : tout ce que l'application « dit » doit être audible.
Ces phrases doivent d'abord être **formulées par ton locuteur natif**, puis enregistrées
d'un seul tenant (ce sont des phrases, pas des mots à assembler).

| Rôle | Nom de fichier | Quand l'app le dit | ✍️ Formulation zarma |
|---|---|---|---|
| **Confirmation** | `confirm.wav` | « C'est bien … ? » avant de valider | |
| **Impossible** | `cannot_answer.wav` | Résultat négatif ou hors limites | |
| **Répéter** | `repeat.wav` | Quand elle n'a pas compris (`repeat`) | |
| **Résultat** | `result.wav` | « ça fait … » (si une amorce est nécessaire) | |

> Les deux premières sont **attendues par le code** (`--prompt-dir`) : sans elles, la
> confirmation et le refus restent muets — donc inutilisables (le code refuse de
> prononcer un énoncé incomplet plutôt que d'en dire la moitié). Les deux autres sont
> facultatives à ce stade.

> ⚠️ La confirmation est le cas le **plus fréquent** : la mesure de la story 5.6 montre que
> l'application demande confirmation dans la grande majorité des cas. Sans cette phrase
> enregistrée, l'app reste inutilisable pour un non-lecteur.

---

## ✅ Récapitulatif

| Groupe | Nombre | Statut |
|---|---|---|
| A — Nombres | **35** | ✅ enregistré (séance `voix2`) |
| B — Reste de division | **1** | ✅ enregistré |
| C — Opérateurs | **4** | ✅ enregistré, les 4 formes validées |
| D — Phrases | 4 | ✅ enregistré (`confirm`, `cannot_answer`, `repeat`, `result`) |
| **Total mots** | **40** | ✅ **40 / 40** |

> Les 35 mots du groupe A sont **exactement** l'alphabet de l'automate de la grammaire
> (vérifié) : ni un de plus, ni un de moins. En retirer un rend certains nombres
> imprononçables ; en ajouter un ne sert à rien.
>
> La commande `--list-missing` ci-dessous est **la référence** : elle est calculée depuis
> le lexique, donc elle ne peut pas être en retard sur ce document.

---

## GROUPE E — Corpus de reconnaissance · **autre besoin, même séance**

> ⚠️ Les groupes A–D servent à ce que l'app **parle**. Le groupe E sert à ce qu'elle
> **comprenne** : ce sont des enregistrements de *test*, pas des briques à assembler.
> Profite de la séance et du bon micro pour les faire aussi.
>
> Ici, **pas d'intonation plate** : parle naturellement, comme un utilisateur réel.
> Nom de fichier : `<locuteur>-<nombre>.wav` (ex. `v4-372.wav`), même format WAV 16 kHz mono.

### E1. ~~Ré-enregistrer 4 fichiers devenus faux (locuteur v2)~~ — ❌ **demande annulée**

**Rien à refaire.** Ces quatre fichiers ont été écoutés par le locuteur : ils sont
**corrects**. La demande précédente était une erreur d'analyse, corrigée ici.

| Fichier | Nombre | Statut |
|---|---|---|
| `v2-102.wav` | 102 | ✅ à conserver |
| `v2-103.wav` | 103 | ✅ à conserver |
| `v2-104.wav` | 104 | ✅ à conserver |
| `v2-110.wav` | 110 | ✅ à conserver |

**Pourquoi c'était une erreur.** `nda` n'a jamais cessé d'exister : le lexique le
déclare comme **variante linguistique** de `da` (`connectors.groups.variants`).
Ce que 1.2.0 a changé, c'est la forme que le générateur *produit*, pas celles que
le système *accepte*. Vérifié sur le code :

```
normalize("zangou nda hinka")  →  "zangou da hinka"
parse("zangou nda hinka")      →  102          ✅
grammar.canonical_token("nda") →  "da"         ✅ (le décodeur contraint la connaît)
```

La vérité terrain de ces 4 audios est donc **exacte**, et la mesure n'est pas
faussée. Un énoncé prononcé avec la variante est simplement un cas un peu plus
exigeant pour le décodage — c'est-à-dire exactement ce qu'un corpus d'évaluation
doit contenir, pas ce qu'il faut en retirer.

### E2. Un **4ᵉ locuteur** (le plus important)

Le corpus compte 3 locuteurs, et le tirage les a **tous** placés dans le jeu de test. Il
n'existe donc **aucun jeu de réglage** distinct, ce qui bloque le calibrage du refus.
Un 4ᵉ locuteur (idéalement une voix différente : autre sexe, autre âge, autre région)
débloque ça. Même liste de nombres que les autres, ~35 fichiers.

### E3. Enregistrements **non numériques** de contrôle · 🟡 **matière fournie**

Sans eux, impossible de régler le seuil à partir duquel l'app doit dire « je n'ai pas
compris » plutôt que d'inventer un nombre. **~15 fichiers courts** suffisent :

- [x] 5 phrases zarma quelconques **sans aucun nombre** (`phrase quelqconque1..5.wav`)
- [x] 4 enregistrements de **bruit ambiant** seul (`bruit ambiant1..5.wav`)
- [x] 3 enregistrements de **silence** (`silence1..2.wav`)
- [x] 3 enregistrements de **musique** ou de radio (`music1..2.wav`)

Ces fichiers sont dans `~/Music/voix2`. ⚠️ **Bruit, silence et musique durent 3 min 23
chacun** : ce sont de longues prises, pas des extraits courts. Il faudra les découper
en segments de quelques secondes avant calibration — sinon un seul fichier pèse autant
que tout le reste du corpus de contrôle. Les 5 phrases, elles (1,4 s à 6,6 s), sont
directement exploitables.

### E4. Condition **bruit** (objectif de qualité non mesuré à ce jour)

Tout le corpus actuel est en condition calme. L'objectif « ≥ 90 % en bruit modéré » n'a
donc **jamais** été mesuré. Réenregistrer **~20 nombres** avec un bruit de fond réaliste
(marché, radio) suffirait à le chiffrer. Nomme-les `<locuteur>-bruit-<nombre>.wav`.

### E5. **Énoncés d'opérations complets** (story 6.1)

> ⚠️ **Les 16 fichiers de `~/Music/operation/` ne servent PAS ici.** Un opérateur
> prononcé seul ne sonne pas comme le même opérateur au milieu d'une phrase
> (coarticulation) : ils servent à fixer le lexique, pas à mesurer.

La liste exacte est **générée**, pas écrite à la main :

```bash
uv run python scripts/bench/build_benchmark_corpus.py plan-expressions \
    --speakers v1 v2 v3 v4 \
    --out dataset/benchmark/expression_recording_plan.jsonl
```

Chaque ligne donne la phrase à dire (`expected_prompt`). Depuis la validation de
`×` et `÷` : **160 consignes** pour 4 locuteurs, couvrant les **quatre** opérations,
dont **20 cas volontairement impossibles** (résultat négatif, dépassement) qui
servent à mesurer que l'application refuse au lieu d'inventer, et **20 divisions
avec reste**.

C'est désormais **le seul enregistrement qui bloque encore la story 6.1** : sans
lui, aucun chiffre de performance de la calculatrice vocale ne peut être publié.

| Sous-groupe | Fichiers | Débloque |
|---|---|---|
| ~~E1 — les 4 périmés~~ | ~~4~~ | ❌ annulé : les fichiers sont corrects |
| E2 — 4ᵉ locuteur | ~35 | jeu de réglage + validité statistique |
| E3 — non numériques | ~15 | le refus « je n'ai pas compris » |
| E4 — condition bruit | ~20 | l'objectif de qualité en bruit |
| E5 — opérations complètes | **160** | **toute la mesure de la calculatrice vocale** |

---

## Après l'enregistrement

**Tu n'as pas à te soucier du format ni des fautes de frappe** : un outil convertit
les prises brutes (n'importe quel taux d'échantillonnage, mono ou stéréo), coupe les
silences promis au début et à la fin de chaque mot, corrige les noms évidents, et dit
ce qui manque encore.

```bash
# 1) Bilan sans rien écrire
uv run python scripts/speech/prepare_bank.py --source ~/Music/voix2 --dry-run

# 2) Préparer la banque (les sources ne sont jamais modifiées)
uv run python scripts/speech/prepare_bank.py \
    --source ~/Music/voix2 --out dataset/voice/v4

# 3) Vérifier la couverture (attendu : 1001/1001)
uv run python scripts/speech/say_number.py --voice v4 \
    --bank-dir dataset/voice/v4/words --prompt-dir dataset/voice/v4/prompts --coverage

# 4) Écouter — un nombre difficile, un reste de division, une confirmation
uv run python scripts/speech/say_number.py --voice v4 \
    --bank-dir dataset/voice/v4/words --number 372 --out /tmp/372.wav
uv run python scripts/speech/say_number.py --voice v4 \
    --bank-dir dataset/voice/v4/words --expression "103 / 5" --out /tmp/reste.wav
uv run python scripts/speech/say_number.py --voice v4 \
    --bank-dir dataset/voice/v4/words --prompt-dir dataset/voice/v4/prompts \
    --number 42 --confirm --out /tmp/confirm.wav
```

### ✅ État mesuré au 2026-07-25 — séance `~/Music/voix2`

| Mesure | Valeur |
|---|---|
| Mots préparés | **40 / 40** |
| Consignes préparées | **4** (`confirm`, `cannot_answer`, `repeat`, `result`) |
| **Couverture 0–1000** | **1001 / 1001** |
| Grandes échelles | `1 234`, `100 005`, `999 999`, `1 000 000` ✅ |
| Format des prises | 44,1 kHz mono 16 bits → converti automatiquement en 16 kHz |
| Noms corrigés automatiquement | `igouwav`, `taciwav`, `waytaciwav`, `zongou` |

**La banque vocale est complète.** Plus rien à enregistrer pour que l'application
parle : n'importe quel nombre de 0 à 1 000 000, n'importe quel résultat d'opération
(reste de division compris), la demande de confirmation et le message de refus.

**Sur `zongou` / `zangou`** — décision : *les deux se disent*. `zangou` reste la forme
que le système **produit** (une seule forme de surface par nombre, c'est ce qui rend
le décodage déterministe), et `zongou` est déclarée **variante linguistique** :
elle est acceptée à la reconnaissance, et l'outil de préparation range
automatiquement `zongou.wav` sous `zangou.wav`. Aucun réenregistrement.

> Les 1001/1001 annoncés en D3 avaient été mesurés **avant** la correction du
> connecteur (`nda` → `da`/`di`) et avant l'ajout de `ga`. Cette séance couvre tout :
> la promesse est de nouveau tenue, cette fois vérifiée sur les vrais fichiers.
