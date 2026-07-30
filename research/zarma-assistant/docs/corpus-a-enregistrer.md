# Paroles à enregistrer — calculatrice et assistant vocal

Ce document liste **ce qui manque réellement**, calculé à partir du corpus
existant (`data/asr_corpus/manifest.csv` : 545 clips, 8 personnes, 11,9 min) et
des erreurs mesurées du modèle v1.

Deux parties :

- **Partie A — Calculatrice.** Listes complètes et prêtes à enregistrer : les
  formes zarma sont produites par `zarma_numbers.generate()`, donc exactes.
- **Partie B — Assistant de transfert d'argent.** Structure complète, mais les
  formulations zarma sont **à compléter par toi** : ce sont des phrases
  naturelles, pas des nombres, et aucun générateur ne peut les inventer.

---

# ⚡ MVP DÉMO — le strict minimum

**Si l'objectif immédiat est une démonstration investisseurs, n'enregistre que
cette section.** **32 énoncés distincts** (4 opérateurs longs × 3 répétitions,
4 formes courtes, 24 expressions), soit **5 à 6 minutes par personne**, contre
~90 énoncés pour le corpus complet.

Le reste du document décrit le corpus visé pour une version réelle ; il n'est
pas nécessaire à une démo.

## Ce qui est indispensable, et pourquoi

Sans les mots d'opérateur et au moins quelques expressions complètes, **la
calculatrice ne peut faire aucun calcul** — elle ne sait que reconnaître des
nombres isolés. C'est la fonction que tu vas montrer : elle n'existe pas encore
dans les données.

### ⚠️ Les formes d'opérateur ont été corrigées

Les 16 clips d'opérateur déjà enregistrés portaient de **fausses étiquettes** :
le texte disait `tonton`, l'audio contenait `kanga itonton`. La mesure l'a
prouvé — ces clips durent **1,40 s** de médiane, contre **0,80 s** pour un
nombre d'un mot et **1,35 s** pour un nombre de trois mots. Les quatre
locuteurs avaient tous prononcé la forme longue.

Ce sont donc **ces formes-là** qu'il faut enregistrer, pas les formes courtes
du lexique.

| id | zarma | mots |
|---|---|---|
| `mot+` | kanga itonton | 2 |
| `mot-` | kanga izabou | 2 |
| `mot*` | kalangaybor | 1 |
| `mot/` | kan ifaysor | 2 |

**3 répétitions par personne.** Ces formes n'introduisent aucun caractère ni
digramme nouveau : le vocabulaire du modèle reste à 30 symboles.

> **Enregistrer aussi les formes courtes** (`tonton`, `zabou`, `ingaybor`,
> `inafaysor`), 1 répétition chacune. Elles coûtent 30 secondes et permettront
> de décider plus tard si l'application accepte les deux. Aujourd'hui le modèle
> n'a jamais entendu la forme courte isolée — il ne la reconnaîtrait pas.

### 24 expressions de démonstration

Nombres ronds, résultats simples, les 4 opérateurs à parts égales : ce sont
celles qu'on montre en direct.

| id | zarma | résultat |
|---|---|---|
| `2+3` | ihinka kanga itonton ihinza | 5 |
| `5+10` | igou kanga itonton iwey | 15 |
| `20+5` | waranka kanga itonton igou | 25 |
| `50+50` | waygou kanga itonton waygou | 100 |
| `100+200` | zangou kanga itonton zangou hinka | 300 |
| `1000+500` | zambar fo kanga itonton zangou gou | 1 500 |
| `5-2` | igou kanga izabou ihinka | 3 |
| `10-3` | iwey kanga izabou ihinza | 7 |
| `50-20` | waygou kanga izabou waranka | 30 |
| `100-50` | zangou kanga izabou waygou | 50 |
| `500-100` | zangou gou kanga izabou zangou | 400 |
| `1000-200` | zambar fo kanga izabou zangou hinka | 800 |
| `2*3` | ihinka kalangaybor ihinza | 6 |
| `4*5` | itaci kalangaybor igou | 20 |
| `10*3` | iwey kalangaybor ihinza | 30 |
| `20*5` | waranka kalangaybor igou | 100 |
| `100*2` | zangou kalangaybor ihinka | 200 |
| `1000*3` | zambar fo kalangaybor ihinza | 3 000 |
| `10/2` | iwey kan ifaysor ihinka | 5 |
| `20/4` | waranka kan ifaysor itaci | 5 |
| `50/10` | waygou kan ifaysor iwey | 5 |
| `100/5` | zangou kan ifaysor igou | 20 |
| `500/5` | zangou gou kan ifaysor igou | 100 |
| `1000/2` | zambar fo kan ifaysor ihinka | 500 |

## Deux précautions pour le jour de la démo

**Enregistre les phrases que tu montreras, et fais-les dire par les 8
personnes.** Une expression enregistrée par tous sera reconnue de façon très
fiable ; une expression jamais enregistrée ne le sera pas du tout.

**Sache lire ton propre chiffre.** Si c'est toi qui fais la démonstration, le
modèle aura entendu ta voix à l'entraînement : le taux réel sera proche de
100 %, bien au-dessus des 95,1 % mesurés sur voix inconnue. C'est légitime pour
une démonstration, mais si un investisseur essaie lui-même, il retombe dans la
plage 89,6 %–100 % mesurée. Annonce le chiffre en voix inconnue plutôt que
celui de la démo : c'est celui qui tiendra en production, et c'est déjà très
bon face aux 66,2 % d'Omnilingual.

---

## Règles d'enregistrement (valables partout)

Ces règles viennent d'erreurs constatées, pas de principes généraux.

1. **Les mêmes 8 personnes que le corpus actuel, plus les nouvelles.** Les
   nouvelles voix valent plus que les nouvelles phrases : l'écart mesuré entre
   la meilleure et la pire voix est de 10 points (89,6 % à 100 %).
2. **Une phrase par fichier**, nommé exactement comme l'identifiant de la
   ligne. Le découpage automatique d'un enregistrement continu a déjà produit
   un jeu de données entièrement mal étiqueté — ne pas recommencer.
3. **Débit naturel, pas de sur-articulation.** Le modèle sera utilisé sur de la
   parole ordinaire.
4. **Ne pas couper les fins de mots.** Deux des trois causes d'erreur
   principales sont des mots courts avalés en fin d'énoncé (`gou`, `dala`).
5. **Varier les conditions** entre les séances : intérieur, extérieur, un peu
   de bruit. Le modèle a des fonds sonores pour l'augmentation, mais rien ne
   remplace du bruit réel.
6. **16 kHz mono minimum**, format WAV de préférence.

---

# PARTIE A — Calculatrice

## A1. Les 4 opérateurs — PRIORITÉ ABSOLUE

**État : dits par 4 personnes sur 8, isolément — et mal étiquetés.** C'est le
manque le plus grave du projet : la calculatrice ne peut pas fonctionner sans
eux.

Formes réelles, telles que prononcées par les 4 locuteurs (voir l'encadré de la
section MVP pour la preuve par la mesure) :

| id | zarma | mots | sens |
|---|---|---|---|
| `mot+` | kanga itonton | 2 | plus |
| `mot-` | kanga izabou | 2 | moins |
| `mot*` | kalangaybor | 1 | fois |
| `mot/` | kan ifaysor | 2 | divisé par |

Formes courtes, à enregistrer **en plus**, 1 répétition — pour pouvoir décider
plus tard si l'application accepte les deux :

| id | zarma |
|---|---|
| `court+` | tonton |
| `court-` | zabou |
| `court*` | ingaybor |
| `court/` | inafaysor |

**Toutes les personnes, 3 répétitions des formes longues.**

## A2. Expressions complètes — JAMAIS ENREGISTRÉES

**État : zéro enregistrement.** Le modèle n'a jamais entendu un opérateur au
milieu d'une phrase. Or un mot prononcé dans un flux continu sonne très
différemment du même mot dit seul — c'est exactement ce que la calculatrice
doit reconnaître.

| id | zarma |
|---|---|
| `5-1` | igou kanga izabou afo |
| `1+5` | afo kanga itonton igou |
| `5+1` | igou kanga itonton afo |
| `5-4` | igou kanga izabou itaci |
| `5-0` | igou kanga izabou yaamo |
| `0+5` | yaamo kanga itonton igou |
| `2+3` | ihinka kanga itonton ihinza |
| `3-2` | ihinza kanga izabou ihinka |
| `8+3` | ahakou kanga itonton ihinza |
| `8-3` | ahakou kanga izabou ihinza |
| `0*4` | yaamo kalangaybor itaci |
| `0*6` | yaamo kalangaybor iddou |
| `0*9` | yaamo kalangaybor iyega |
| `4*0` | itaci kalangaybor yaamo |
| `4*6` | itaci kalangaybor iddou |
| `4*9` | itaci kalangaybor iyega |
| `2*3` | ihinka kalangaybor ihinza |
| `0/4` | yaamo kan ifaysor itaci |
| `6/9` | iddou kan ifaysor iyega |
| `9/6` | iyega kan ifaysor iddou |
| `2/6` | ihinka kan ifaysor iddou |
| `2/9` | ihinka kan ifaysor iyega |
| `3/6` | ihinza kan ifaysor iddou |
| `20-8` | waranka kanga izabou ahakou |
| `30-20` | waranza kanga izabou waranka |
| `115-1` | zangou di wey cindi gou kanga izabou afo |
| `1+115` | afo kanga itonton zangou di wey cindi gou |
| `250-115` | zangou hinka da waygou kanga izabou zangou di wey cindi gou |

## A3. `dala` — le mot le plus dangereux du lexique

**État : 12 occurrences, 1 à 2 par personne.** Le perdre ne casse pas la
phrase, il **rebracketise le nombre entier** : `100099` devient `199000`,
`900099` devient `999000`. Le modèle et Omnilingual échouent tous les deux
dessus (0/2 chacun).

| id | zarma |
|---|---|
| `100005` | zambar zangou da dala gou |
| `200007` | zambar zangou hinka da dala iyye |
| `300002` | zambar zangou hinza da dala hinka |
| `500009` | zambar zangou gou da dala yega |
| `100099` | zambar zangou da dala wayyegga cindi yega |
| `400099` | zambar zangou taci da dala wayyegga cindi yega |
| `900099` | zambar zangou yega da dala wayyegga cindi yega |

**Insister sur `dala` sans le sur-articuler** — il doit rester audible dans un
débit naturel.

## A4. `gou` final — deuxième cause d'erreur

**État : perdu 4 fois sur les erreurs analysées.** `zambar fo da zangou gou`
(1500) devient `zambar fo da zangou` (1100). Un mot court, en fin d'énoncé,
donc avalé.

| id | zarma |
|---|---|
| `500` | zangou gou |
| `1500` | zambar fo da zangou gou |
| `2500` | zambar hinka da zangou gou |
| `3500` | zambar hinza da zangou gou |
| `4500` | zambar taci da zangou gou |
| `7500` | zambar iyye da zangou gou |
| `10500` | zambar iwey da zangou gou |
| `1500000` | million da zambar zangou gou |
| `2500000` | million hinka da zambar zangou gou |

## A5. Décades en `way-` — confusions mutuelles

**État : `waygou` / `wayyegga` / `wayiddu` confondus entre eux.** 53 lu 93,
63 lu 53, 199 lu 159.

| id | zarma |
|---|---|
| `50` | waygou |
| `60` | wayiddu |
| `70` | wayiyye |
| `90` | wayyegga |
| `53` | waygou cindi hinza |
| `63` | wayiddu cindi hinza |
| `73` | wayiyye cindi hinza |
| `93` | wayyegga cindi hinza |
| `153` | zangou da waygou cindi hinza |
| `163` | zangou da wayiddu cindi hinza |
| `193` | zangou da wayyegga cindi hinza |

**Enregistrer ces 11 à la suite, dans cet ordre**, pour que le contraste soit
présent dans la même séance et la même voix.

## A6. Construction `di` — sous-couverte

**État : 12 occurrences, dont 5 chez une seule personne.** Quand cette
personne est écartée du test, le modèle échoue sur 103, 104 et 110.

| id | zarma |
|---|---|
| `101` | zangou da fo |
| `102` | zangou di hinka |
| `103` | zangou di hinza |
| `104` | zangou di taci |
| `110` | zangou di wey |
| `115` | zangou di wey cindi gou |
| `604` | zangou iddu di taci |

## A7. Montants du MVP absents du corpus

**État : 15 des 24 montants de la spécification n'ont jamais été enregistrés.**
Ce sont les montants d'usage réel en Mobile Money.

| id | zarma |
|---|---|
| `2500` | zambar hinka da zangou gou |
| `5000` | zambar gou |
| `7500` | zambar iyye da zangou gou |
| `15000` | zambar iwey cindi gou |
| `20000` | zambar waranka |
| `25000` | zambar waranka cindi gou |
| `30000` | zambar waranza |
| `40000` | zambar waytaci |
| `50000` | zambar waygou |
| `75000` | zambar wayiyye cindi gou |
| `100000` | zambar zangou |
| `150000` | zambar zangou da waygou |
| `200000` | zambar zangou hinka |
| `250000` | zambar zangou hinka da waygou |
| `500000` | zambar zangou gou |

Également faibles (moins de 4 voix) : `500` (zangou gou), `3000` (zambar
hinza), `10000` (zambar iwey).

## A8. Paires de contraste critiques

**État : aucune des 7 paires n'a le moindre enregistrement.** Ce sont les
confusions qui coûteraient le plus cher dans une application d'argent.

| id | zarma | à ne pas confondre avec |
|---|---|---|
| `15000` | zambar iwey cindi gou | `50000` zambar waygou |
| `16000` | zambar iwey cindi iddu | `60000` zambar wayiddu |
| `17000` | zambar iwey cindi iyye | `70000` zambar wayiyye |
| `18000` | zambar iwey cindi hakou | `80000` zambar wayhakkou |
| `19000` | zambar iwey cindi yega | `90000` zambar wayyegga |
| `25000` | zambar waranka cindi gou | `250000` zambar zangou hinka da waygou |
| `100000` | zambar zangou | `110000` zambar zangou di wey |

**Enregistrer chaque paire l'une après l'autre**, dans la même séance.

## Récapitulatif Partie A

| section | énoncés |
|---|---|
| A1 mots d'opérateur | 4 |
| A2 expressions complètes | 28 |
| A3 `dala` | 7 |
| A4 `gou` final | 9 |
| A5 décades `way-` | 11 |
| A6 construction `di` | 7 |
| A7 montants MVP | 18 |
| A8 contrastes | 14 |
| **total (après dédoublonnage)** | **~90** |

Environ **12 à 15 minutes par personne**. Sur 8 personnes : ~2 heures d'audio,
soit **dix fois le corpus actuel**.

---

# PARTIE B — Assistant de transfert d'argent

> **À compléter par toi.** Les colonnes « zarma » sont vides à dessein : ce
> sont des phrases naturelles, et tu es le seul locuteur natif du projet. Pour
> chaque intention, donne **2 à 3 formulations différentes** — les gens ne
> disent jamais la même phrase.
>
> Une règle technique à respecter en les choisissant : les mots de commande ne
> doivent **pas** réutiliser les connecteurs de nombres (`da`, `di`, `cindi`,
> `dala`). Sinon une même suite de sons serait à la fois un nombre et une
> commande, et le décodage n'aurait plus de chemin unique. Le constructeur de
> grammaire vérifie cette disjonction mécaniquement, mais autant l'éviter dès
> la conception.

## B1. Intentions principales

### `CHECK_BALANCE` — consulter le solde

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `bal_1` | Dis-moi mon solde. | |
| `bal_2` | Combien ai-je dans mon compte ? | |
| `bal_3` | Combien me reste-t-il ? | |
| `bal_4` | Vérifie mon argent. | |

### `SEND_MONEY` — transférer

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `snd_1` | Je veux envoyer de l'argent. | |
| `snd_2` | Je veux faire un transfert. | |
| `snd_3` | Envoie de l'argent à [BÉNÉFICIAIRE]. | |
| `snd_4` | Envoie [MONTANT] à [BÉNÉFICIAIRE]. | |
| `snd_5` | Transfère [MONTANT] à [BÉNÉFICIAIRE]. | |
| `snd_6` | Ce n'est pas la bonne personne. | |
| `snd_7` | Change le bénéficiaire. | |
| `snd_8` | Corrige le nom. | |

### `BUY_AIRTIME` — crédit téléphonique

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `air_1` | Achète-moi du crédit. | |
| `air_2` | Recharge mon téléphone. | |
| `air_3` | Mets [MONTANT] de crédit sur mon numéro. | |
| `air_4` | Achète du crédit pour [ALIAS]. | |

### `BUY_DATA_BUNDLE` — forfait Internet

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `dat_1` | Je veux acheter un forfait Internet. | |
| `dat_2` | Achète-moi un forfait. | |
| `dat_3` | Je veux un forfait d'un jour. | |
| `dat_4` | Je veux un forfait d'un mois. | |

### `RECHARGE_ELECTRICITY` — compteur

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `ele_1` | Je veux recharger mon compteur. | |
| `ele_2` | Recharge le compteur de [ALIAS]. | |
| `ele_3` | Mets [MONTANT] sur le compteur [ALIAS]. | |
| `ele_4` | Achète [MONTANT] d'électricité. | |

### `CHECK_ELECTRICITY_BILL` / `PAY_ELECTRICITY_BILL`

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `ebc_1` | Vérifie ma facture d'électricité. | |
| `ebc_2` | Combien dois-je payer pour l'électricité ? | |
| `ebp_1` | Je veux payer ma facture d'électricité. | |
| `ebp_2` | Paie l'électricité de [ALIAS]. | |

### `CHECK_WATER_BILL` / `PAY_WATER_BILL`

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `wbc_1` | Vérifie ma facture d'eau. | |
| `wbc_2` | Combien dois-je payer pour l'eau ? | |
| `wbp_1` | Je veux payer ma facture d'eau. | |
| `wbp_2` | Paie l'eau de [ALIAS]. | |

### `CHECK_RECENT_TRANSACTIONS` / `CHECK_FEES`

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `hst_1` | Dis-moi mes dernières opérations. | |
| `hst_2` | Est-ce que mon dernier transfert a réussi ? | |
| `fee_1` | Combien coûtent les frais ? | |
| `fee_2` | Quel sera le montant total ? | |

## B2. Commandes de navigation — LES PLUS FRÉQUENTES

Elles seront prononcées à chaque opération, bien plus souvent que les
intentions. **Prévoir 5 répétitions par personne**, et plusieurs formulations :
un « oui » se dit de vingt façons.

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `yes_1` | Oui. | |
| `yes_2` | C'est correct. | |
| `yes_3` | Je confirme. | |
| `yes_4` | D'accord. | |
| `no_1` | Non. | |
| `no_2` | Ce n'est pas correct. | |
| `no_3` | Ce n'est pas cela. | |
| `rep_1` | Répète. | |
| `rep_2` | Je n'ai pas compris. | |
| `rep_3` | Répète le montant. | |
| `rep_4` | Répète le nom. | |
| `slw_1` | Parle lentement. | |
| `slw_2` | Dis-le mot par mot. | |
| `bck_1` | Retour. | |
| `bck_2` | Reviens en arrière. | |
| `can_1` | Annule. | |
| `can_2` | Arrête l'opération. | |
| `can_3` | Ne fais rien. | |
| `rst_1` | Recommence. | |
| `rst_2` | Nouvelle opération. | |
| `hlp_1` | Aide-moi. | |
| `hlp_2` | Que dois-je dire ? | |
| `agt_1` | Appelle un agent. | |
| `stp_1` | Arrête d'écouter. | |

> **`oui` et `non` sont critiques.** Ce sont eux qui valident un transfert
> d'argent. Une confusion entre les deux coûte de l'argent réel. Enregistre-les
> aussi **prononcés vite, à mi-voix, et dans le bruit** — c'est ainsi qu'ils
> seront dits en vrai.

## B3. Alias de bénéficiaires — relations

Ces alias-là sont communs à tous les utilisateurs et doivent être dans le
corpus général.

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `rel_1` | ma fille | |
| `rel_2` | mon fils | |
| `rel_3` | ma mère | |
| `rel_4` | mon père | |
| `rel_5` | mon mari | |
| `rel_6` | ma femme | |
| `rel_7` | mon frère | |
| `rel_8` | ma sœur | |
| `rel_9` | mon fournisseur | |
| `rel_10` | mon employé | |
| `rel_11` | mon patron | |
| `rel_12` | ma boutique | |
| `rel_13` | mon associé | |

## B4. Prénoms courants

Prononcés **en zarma**, pas à la française. À enregistrer par plusieurs
personnes, car un prénom varie beaucoup d'un locuteur à l'autre.

```
Aïssata   Moussa    Amadou    Mariama
Fatouma   Abdou     Issa      Hadiza
```

**À compléter :** ajoute les prénoms réellement fréquents autour de toi — cette
liste doit refléter les vrais carnets d'adresses, pas une liste générique.

```
À COMPLÉTER : ______________________________________________
```

## B5. Alias de compteurs, eau et téléphones

| id | sens (français) | zarma — À COMPLÉTER |
|---|---|---|
| `mtr_1` | compteur maison | |
| `mtr_2` | compteur boutique | |
| `mtr_3` | compteur bureau | |
| `wtr_1` | eau maison | |
| `wtr_2` | eau boutique | |
| `phn_1` | mon numéro | |
| `phn_2` | mon téléphone | |
| `phn_3` | téléphone de la boutique | |

## B6. Montants en contexte

Les montants de la **partie A7** doivent aussi être enregistrés **à l'intérieur
d'une phrase**, pas seulement isolés. Un nombre en fin de phrase se prononce
autrement qu'un nombre seul — c'est la même cause que les erreurs sur `gou`.

Pour chaque montant, au moins deux de ces gabarits :

```
Envoie [MONTANT] à [BÉNÉFICIAIRE].
Achète [MONTANT] de crédit.
Recharge le compteur avec [MONTANT].
J'ai dit [MONTANT].
Non, je voulais dire [MONTANT].
```

Gabarits à traduire :

```
À COMPLÉTER : ______________________________________________
```

## B7. Exemples négatifs — indispensables

Le système doit savoir **refuser**. Sans ces enregistrements, il tentera de
comprendre n'importe quel bruit comme un ordre de transfert.

| catégorie | à enregistrer | quantité |
|---|---|---|
| `OUT_OF_SCOPE` | conversation ordinaire, sans rapport | 20 par personne |
| `AMBIGUOUS` | phrase commencée puis coupée, hésitation | 10 par personne |
| `UNKNOWN` | nom de personne non enregistrée | 10 par personne |
| `NOISE` | marché, radio, télévision, plusieurs voix | 10 min continu |
| `SILENCE` | pièce vide, micro ouvert | 5 min continu |
| — | mots ressemblant à « oui » / « non » sans l'être | 10 par personne |

> Le corpus contient déjà 9 fonds sonores (`asr_corpus/noise/`) et 5 phrases
> quelconques. C'est un début, très insuffisant pour cette catégorie.

## B8. Voix de sortie de l'application — PROJET SÉPARÉ

Les messages `SYS_*` de ta spécification (section 13) ne servent **pas** à
entraîner le modèle : ce sont les phrases que l'application **dit**. Ils
relèvent de la banque vocale, pas du corpus ASR.

Ne les mélange pas aux enregistrements d'entraînement — le dossier
`pour le tts/` existe déjà pour ça.

---

## Ordre de priorité recommandé

1. **A1 + A2** — les opérateurs et les expressions. Sans eux la calculatrice
   n'existe pas, et c'est une heure de travail.
2. **A3 + A4** — `dala` et `gou` final. Ce sont les erreurs qui produisent un
   nombre faux et **indétectable**.
3. **B2** — `oui` / `non` / `annule` / `répète`. Les plus fréquentes de tout le
   système, et celles qui valident de l'argent.
4. **A7 + A8** — montants réels et paires de contraste.
5. **A5 + A6** — décades et construction `di`.
6. **B1** — les intentions.
7. **B3 à B6** — alias, prénoms, montants en contexte.
8. **B7** — exemples négatifs.

## Suivi

| partie | énoncés/personne | fait ? |
|---|---|---|
| A1 mots d'opérateur | 4 × 3 rép. | ☐ |
| A2 expressions | 28 | ☐ |
| A3 `dala` | 7 | ☐ |
| A4 `gou` final | 9 | ☐ |
| A5 décades `way-` | 11 | ☐ |
| A6 construction `di` | 7 | ☐ |
| A7 montants MVP | 18 | ☐ |
| A8 contrastes | 14 | ☐ |
| B1 intentions | ~35 | ☐ |
| B2 navigation | 24 × 5 rép. | ☐ |
| B3 relations | 13 | ☐ |
| B4 prénoms | ~10 | ☐ |
| B5 alias | 8 | ☐ |
| B6 montants en contexte | ~30 | ☐ |
| B7 négatifs | ~50 + bruit | ☐ |
