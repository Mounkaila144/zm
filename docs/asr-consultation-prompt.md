

## CONTEXTE

Je développe une application mobile de **reconnaissance vocale de nombres en zarma**
(langue songhaï parlée au Niger, code ISO `dje`, écriture latine → `dje_Latn`).

L'utilisateur prononce un nombre à voix haute, l'application doit afficher **le
nombre en chiffres**. C'est le cœur du produit : commerce, prix, quantités.


---

## 1. COMMENT FONCTIONNE LA NUMÉRATION ZARMA

C'est le point important : **le système est petit, fermé et très régulier.**

### 1.1 Le vocabulaire complet (≈ 30 mots seulement)

**Zéro**
- `yaamo` = 0

**Unités 1–9** — deux formes : *isolée* (seule) et *combinée* (dans un nombre composé)

| Valeur | Isolée | Combinée |
|---|---|---|
| 1 | afo | fo |
| 2 | ihinka | hinka |
| 3 | ihinza | hinza |
| 4 | itaci | taci |
| 5 | igou | gou |
| 6 | iddou | iddu |
| 7 | iyye | iyye |
| 8 | ahakou | hakou |
| 9 | iyega | yega |

**Dizaines 10–90**

| Valeur | Mot |
|---|---|
| 10 | iwey |
| 20 | waranka |
| 30 | waranza |
| 40 | waytaci |
| 50 | waygou |
| 60 | wayiddu |
| 70 | wayiyye |
| 80 | wayhakkou |
| 90 | wayyegga |

**Connecteurs**
- `cindi` = lie une dizaine à une unité (« et »)
- `nda` (variantes : `da`, `di`) = lie deux groupes d'ordre différent
- `dala` = marqueur de reste-unité aux grandes échelles

**Échelles**
- `zangou` = 100
- `zambar` = 1000
- `million` = 1 000 000
- (10 000 et 100 000 n'ont pas de mot propre : ils se composent, voir plus bas)

### 1.2 Les règles de composition

La construction est **strictement compositionnelle et régulière** :

- **Dizaine + unité** → `<dizaine> cindi <unité combinée>`
- **Multiple d'échelle** → `<échelle> <unité combinée>` (le multiplicateur SUIT l'échelle)
- **Assemblage de groupes** → reliés par `nda`, du plus grand au plus petit

### 1.3 Exemples réels (générés par mon moteur déterministe)

```
        0 : yaamo
        1 : afo
        5 : igou
       10 : iwey
       11 : iwey cindi fo
       15 : iwey cindi gou
       19 : iwey cindi yega
       20 : waranka
       21 : waranka cindi fo
       42 : waytaci cindi hinka
       88 : wayhakkou cindi hakou
       99 : wayyegga cindi yega
      100 : zangou
      101 : zangou nda fo
      110 : zangou nda iwey
      111 : zangou nda iwey cindi fo
      200 : zangou hinka          (littéralement « cent deux » = 2×100)
      372 : zangou hinza nda wayiyye cindi hinka
      999 : zangou yega nda wayyegga cindi yega
     1000 : zambar fo
     1234 : zambar fo nda zangou hinka nda waranza cindi taci
     2000 : zambar hinka
    10000 : zambar iwey            (= 1000 × 10)
   100000 : zambar zangou          (= 1000 × 100)
   100005 : zambar zangou nda dala gou
   999999 : zambar zangou yega nda wayyegga cindi yega nda zangou yega nda wayyegga cindi yega
  1000000 : million
```

### 1.4 Propriétés déterminantes pour le choix technique

1. **Vocabulaire fermé et minuscule** : environ **30 tokens** au total. Aucun mot
   hors de cette liste n'apparaît jamais dans un nombre.
2. **Plage bornée** : **0 à 1 000 000**. Pas de nombres arbitrairement grands.
3. **Grammaire régulière et non ambiguë** : la composition suit des règles fixes.
4. **Énoncés courts** : la plupart des nombres se disent en **0,5 à 2 secondes**.
5. **Un moteur déterministe texte↔nombre existe déjà et fonctionne parfaitement.**
   J'ai un parseur/générateur exhaustivement testé : l'invariant
   `parse(generate(n)) == n` est vérifié sur **tous** les entiers de 0 à 1 000 000.
   → **Le problème n'est PAS la conversion texte→nombre. Elle est résolue.**
   → **Le seul maillon défaillant est la transcription audio→texte (l'ASR).**

---

## 2. LE PROBLÈME QUE JE RENCONTRE

J'utilise **Omnilingual ASR de Meta** (paquet `omnilingual-asr`, basé sur
`fairseq2`), qui annonce le support de 1600+ langues, dont le zarma (`dje_Latn`
est bien dans la liste des langues supportées — vérifié).

Deux variantes existent, et j'ai testé les deux sur de vrais enregistrements.

### Protocole de test
- **18 fichiers WAV**, mono 16 kHz, **1 locuteur natif**, environnement calme.
- Contenu : les nombres **0 à 20** dits isolément (un nombre par fichier),
  durées 0,5–2 s.
- Vérité terrain connue (le locuteur a annoncé ce qu'il disait).
- Métrique : **exactitude du nombre final** (le nombre reconnu est-il le bon ?).

### Résultat A — modèle CTC (`omniASR_CTC_300M_v2`, checkpoint 1,24 Go)

**Problème majeur : il transcrit dans le mauvais système d'écriture.**

Sur les nombres courts (chiffres isolés < 1 s), il produit du **chinois** ou de
l'**arabe** au lieu du latin :

| Nombre attendu | Ce que le CTC écrit |
|---|---|
| 1 | `二夫` (chinois) |
| 2 | `你经刚` (chinois) |
| 4 | `إتاجي` (arabe) |
| 8 | `هكو` (arabe) |
| 11 | `iwaycinda fo` (latin, correct-ish) |
| 20 | `waranka` (latin, correct) |

**Fait vérifié empiriquement** : passer le paramètre `lang=["dje_Latn"]` au modèle
CTC **ne change strictement rien** à sa sortie — il ignore l'indication de langue
et auto-détecte l'écriture. Sur des extraits courts, il se trompe souvent.

→ **Exactitude : 1 nombre correct sur 18.**

Note : le CTC s'en sort mieux sur les énoncés plus longs (11–20), où il a plus de
contexte acoustique pour identifier la langue.

### Résultat B — modèle LLM (`omniASR_LLM_300M_v2`, checkpoint 6,2 Go)

Celui-ci **accepte** l'indication de langue `lang=["dje_Latn"]`.

**Le problème d'écriture est massivement résolu : 16 sorties sur 18 sont en
alphabet latin.** Le modèle entend manifestement bien la voix.

**Mais l'exactitude reste faible : 2 nombres corrects sur 18.**

La raison est instructive : **les erreurs ne sont pas acoustiques, elles sont
orthographiques.** Le modèle entend juste mais écrit selon d'autres conventions
que mon lexique :

| Nombre | Le LLM écrit | Ma forme canonique | Nature de l'écart |
|---|---|---|---|
| 10 | `i wey` | `iwey` | **une espace** |
| 0 | `yamo` | `yaamo` | voyelle longue |
| 1 | `afu` | `afo` | u / o |
| 5 | `i gu` | `igou` | espace + u/ou |
| 3 | `ihinzo` | `ihinza` | o / a final |
| 12 | `i way cindi hinka` | `iwey cindi hinka` | way / wey |
| 16 | `i woycindi iddu` | `iwey cindi iddu` | segmentation |
| 19 | `i way cindi yagga` | `iwey cindi yega` | way/wey, yagga/yega |

**Mesure de proximité : 13 transcriptions sur 18 sont à ≥ 70 % de similarité**
avec la forme canonique attendue. Autrement dit, le signal acoustique est bon ;
c'est la **normalisation orthographique** qui bloque.

### Contraintes matérielles

- Mon poste : **MacBook Pro M1, 8 Go de RAM**.
- Le **CTC (1,24 Go)** tourne en local sans problème (pic ~1,75 Go de RAM,
  ~0,6 s par clip en CPU).
- Le **LLM (6,2 Go)** ne tient pas confortablement en 8 Go → j'ai dû le faire
  tourner sur un GPU cloud (Google Colab T4, ~150–370 ms par clip).
- Pour la production, je vise un hébergement **peu coûteux** (faible trafic au
  lancement) — idéalement du serverless *scale-to-zero*, voire de l'embarqué.

---

## 3. MA QUESTION

J'hésite entre plusieurs directions, et j'aimerais un avis argumenté.

### Question principale

**Puis-je m'appuyer sur un modèle de transcription « universel » — c'est-à-dire un
reconnaisseur de phonèmes indépendant de toute langue (type Allosaurus, ou un
Wav2Vec2 phonétique/IPA), qui écoute un son et le transcrit en symboles latins
sans jamais choisir de langue — ou bien suis-je obligé de passer par le LLM
d'Omnilingual/Meta (6,2 Go, GPU requis) ?**

Ce qui m'attire dans l'option « universelle » :
- **très léger** (dizaines de Mo), tournerait sur mon M1 voire sur le téléphone ;
- **aucune détection de langue** → le problème du chinois/arabe disparaît par
  construction ;
- pas de dépendance à un gros modèle hébergé et coûteux.

Ce qui m'inquiète :
- il sortirait des **phonèmes**, pas des mots zarma. Il faudrait ensuite une étape
  qui rapproche cette suite de sons du mot-nombre correspondant. 
- est-ce que cette étape peut être rendue **rigoureuse** plutôt qu'approximative,
  étant donné que mon vocabulaire est **fermé et ne compte que ~30 mots** ?
  (ex. dictionnaire de prononciations + décodage contraint sur un automate des
  formes valides ?)

### Questions secondaires

1. **Compte tenu du vocabulaire fermé (~30 mots) et de la plage bornée (0 à
   1 000 000), quelle architecture recommandez-vous ?** Un ASR généraliste
   est-il seulement le bon outil, ou devrais-je viser un système de type
   *reconnaissance de mots-clés / vocabulaire fermé* (keyword spotting,
   décodage CTC contraint à une grammaire) ?

2. **Le fine-tuning d'un petit modèle sur mes propres enregistrements** (avec les
   formes canoniques comme étiquettes) résoudrait-il d'un coup **les deux**
   problèmes — mauvais système d'écriture ET variantes orthographiques ?
   Si oui : **combien de locuteurs et combien d'enregistrements** faut-il
   réalistement pour un tel vocabulaire fermé ? (J'ai actuellement 1 locuteur, je
   peux en mobiliser quelques-uns.)

3. **Le problème orthographique** (`i wey` vs `iwey`, `way` vs `wey`, `u` vs `ou`)
   se traite-t-il mieux : (a) en enrichissant une table de variantes en aval du
   modèle, (b) par fine-tuning en amont, ou (c) par un décodage contraint au
   vocabulaire valide ? Quels sont les risques de chaque option vis-à-vis de ma
   contrainte « jamais de nombre inventé » ?

4. **Existe-t-il des approches spécifiquement adaptées aux langues peu dotées**
   (low-resource) pour ce type de tâche fermée, que je devrais considérer ?

Merci de me donner une recommandation claire et argumentée, avec les compromis
(précision / poids / coût / risque d'erreur), plutôt qu'un catalogue d'options.
