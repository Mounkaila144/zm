# Enregistrement du corpus de synthèse vocale — nombres zarma

Liste prête à enregistrer : **`data/tts_prompts.csv`** — 400 énoncés,
**environ 18 minutes de parole**, une séance.

Régénérable par `scripts/generate_tts_prompts.py`.

---

## ⚠️ À faire AVANT la première prise

**Passer l'application de collecte en 24 kHz.**
`entrainement/corpus_recorder/lib/audio_service.dart` enregistre aujourd'hui en
16 kHz — la fréquence dont l'ASR a besoin. C'est un **plafond définitif** pour la
synthèse : les modèles TTS travaillent en 22,05 ou 24 kHz, et une voix apprise
sur du 16 kHz reste sourde, quel que soit le modèle et quelle que soit la durée
enregistrée.

Après modification, **vérifier sur un fichier réellement produit** :

```bash
ffprobe -v error -show_entries stream=sample_rate,channels -of csv=p=0 <fichier>.wav
# doit afficher : 24000,1
```

Le réglage demandé n'est pas toujours celui que le matériel applique. Refaire
seize minutes pour cette raison serait évitable.

**Revoir aussi les seuils qualité.** Ceux de l'application ont été calibrés pour
l'ASR, qui tolère beaucoup de bruit. La synthèse non : elle apprendrait le
souffle et le ronflement de la pièce en même temps que la voix.

---

## Protocole

**Une seule voix**, du début à la fin. Un modèle de synthèse produit un timbre ;
mélanger deux locuteurs le rend impossible à apprendre.

**Conditions constantes** : même pièce, même micro, même distance, si possible la
même séance. Une voix change entre le matin et le soir, et un changement de
timbre au milieu du corpus s'entend davantage qu'une erreur de modèle.

**Débit naturel, jamais sur-articulé.** C'est le réflexe qui gâche le plus de
corpus de synthèse : le modèle apprendrait à parler comme quelqu'un qui dicte
lentement, et c'est exactement ce qu'on cherche à éviter.

**Silence propre avant et après** chaque prise — une demi-seconde suffit, sans
bruit de bouche ni de doigt sur l'écran.

**Pauses régulières.** 400 prises fatiguent la voix, et la fatigue s'entend. Trois
ou quatre séries d'une centaine d'énoncés valent mieux qu'une traite.

---

## Ce que contient la liste, et pourquoi

Elle n'est pas tirée au hasard : elle est construite pour la **couverture**, car
un modèle de synthèse apprend des transitions sonores et non des mots.
Enregistrer 400 nombres au hasard donnerait cinquante fois `zangou` et jamais
`dala`.

| | couverture obtenue |
|---|---|
| mots du vocabulaire | 41, chacun **au moins 4 fois** |
| couples (mot, position) | 104 — début, milieu, fin, seul |
| jonctions entre deux mots | 263 |

**Pourquoi la position compte.** Un mot en fin d'énoncé porte une mélodie
descendante ; au milieu, il enchaîne. Ce sont deux réalisations différentes du
même mot, et un corpus qui n'en contient qu'une produit une voix qui récite.

**Pourquoi les jonctions comptent.** C'est là que la synthèse par concaténation
s'entend. C'est donc précisément ce que le modèle neuronal doit apprendre à
faire mieux.

Répartition des longueurs :

```
 1 mot   :  21 énoncés   ← les résultats que la calculatrice prononce seuls
 2 mots  :   8
 3 mots  : 295           ← les expressions
 4 mots+ :  76           ← les grands nombres
```

Les 21 énoncés d'un seul mot sont essentiels et n'étaient pas venus seuls : un
choix purement glouton les écarte tous, puisqu'une expression de trois mots
couvre davantage par prise. Or la calculatrice énonce ses **résultats**, qui sont
souvent un mot unique — `igou` pour 5, `zangou` pour 100.

---

## Les opérateurs sont en forme LONGUE

```
+   kanga itonton
−   kanga izabou
×   kalangaybor
÷   kan ifaysor
```

C'est ce que les gens disent, donc ce que l'application doit prononcer quand
elle répète ce qu'elle a compris. Un utilisateur qui ne peut vérifier qu'à
l'oreille doit entendre une formulation qu'il emploie lui-même.

Les formes courtes (`tonton`, `zabou`, `ingaybor`, `inafaysor`) ne figurent
donc pas dans cette liste. Elles restent dans la banque vocale existante — rien
n'est perdu si l'on veut revenir en arrière.

> **Conséquence à traiter avant la mise en service.** `render_expression()`
> produit aujourd'hui la forme **courte** : c'est elle que l'application
> reçoit. Enregistrer les formes longues ne suffit donc pas, il faut aussi que
> la couche de synthèse les demande.
>
> Deux voies. Changer `canonical` dans `lexicon.yaml` — mais cela modifie
> l'identité des expressions dans toute la pile, avec le retentissement sur les
> tests que la correction précédente a déjà montré. Ou, plus simple et mieux
> séparé : laisser la grammaire garder la forme courte comme **identité** (pour
> l'analyse, la comparaison, le stockage) et faire traduire par la couche
> vocale, dont c'est le rôle. `tonton` reste ce que le système *pense* ;
> `kanga itonton` devient ce qu'il *dit*.

**Les 3 phrases fixes** (`cannot_answer`, `confirm`, `repeat`) restent des
enregistrements. Leur texte ne change jamais : les jouer telles quelles donne
une vraie voix humaine, sans risque et sans coût. Ne demande au modèle que ce
qu'il est seul à pouvoir faire.

---

## Après l'enregistrement

**Valider avant d'entraîner.** Écouter un échantillon, vérifier la fréquence,
le niveau, l'absence de saturation. Un corpus défectueux découvert après
l'entraînement coûte les deux.

**Puis vérifier le modèle presque exhaustivement** — c'est le luxe d'un domaine
fermé. Générer quelques centaines de nombres avec `zarma_numbers`, les faire
prononcer, et écouter. Si le modèle reste juste sur des nombres jamais entendus
à l'entraînement, il est sûr. Cette garantie est impossible à obtenir pour une
synthèse générale, et elle compte : sur une application d'argent dont les
utilisateurs ne vérifient qu'à l'oreille, un nombre mal prononcé ne se rattrape
pas.

**Étalon de comparaison** : la synthèse par concaténation actuelle. Le modèle
neuronal ne doit être adopté que s'il fait mieux, jugé à l'oreille sur les mêmes
phrases. Une vraie voix humaine assemblée reste un adversaire sérieux.
