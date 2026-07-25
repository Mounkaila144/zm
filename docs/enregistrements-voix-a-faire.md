# Liste d'enregistrement — banque vocale zarma

> **40 mots + quelques phrases.** Une fois enregistrés, l'application peut prononcer
> **les 1 000 001 nombres** (0 à 1 000 000) et le résultat de n'importe quelle opération.
>
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

## GROUPE C — Opérateurs (4 mots)

- [ ] `tonton` — addition `+` ✅ *validé par le locuteur*
- [ ] `zabou` — soustraction `−` ✅ *validé par le locuteur*
- [ ] `______________` — multiplication `×` ⏳ **forme à confirmer**
- [ ] `______________` — division `÷` ⏳ **forme à confirmer**

> Les formes de `×` et `÷` ne sont pas encore fixées (cf. `docs/lexique-operateurs-a-valider.md`).
> Enregistre-les dès que ton locuteur les aura arrêtées.

---

## GROUPE D — Phrases de dialogue · **à formuler d'abord**

L'utilisateur cible **ne lit pas** : tout ce que l'application « dit » doit être audible.
Ces phrases doivent d'abord être **formulées par ton locuteur natif**, puis enregistrées
d'un seul tenant (ce sont des phrases, pas des mots à assembler).

| Rôle | Quand l'app le dit | ✍️ Formulation zarma |
|---|---|---|
| **Confirmation** | « C'est bien … ? » avant de valider | |
| **Répéter** | Quand elle n'a pas compris (`repeat`) | |
| **Impossible** | Résultat négatif ou hors limites | |
| **Résultat** | « ça fait … » (si une amorce est nécessaire) | |

> ⚠️ La confirmation est le cas le **plus fréquent** : la mesure de la story 5.6 montre que
> l'application demande confirmation dans la grande majorité des cas. Sans cette phrase
> enregistrée, l'app reste inutilisable pour un non-lecteur.

---

## ✅ Récapitulatif

| Groupe | Nombre | Statut |
|---|---|---|
| A — Nombres | **35** | prêt à enregistrer |
| B — Reste de division | **1** | prêt à enregistrer |
| C — Opérateurs | **4** | 2 prêts, 2 en attente du locuteur |
| D — Phrases | ~4 | à formuler d'abord |
| **Total mots** | **40** | |

> Les 35 mots du groupe A sont **exactement** l'alphabet de l'automate de la grammaire
> (vérifié) : ni un de plus, ni un de moins. En retirer un rend certains nombres
> imprononçables ; en ajouter un ne sert à rien.

---

## GROUPE E — Corpus de reconnaissance · **autre besoin, même séance**

> ⚠️ Les groupes A–D servent à ce que l'app **parle**. Le groupe E sert à ce qu'elle
> **comprenne** : ce sont des enregistrements de *test*, pas des briques à assembler.
> Profite de la séance et du bon micro pour les faire aussi.
>
> Ici, **pas d'intonation plate** : parle naturellement, comme un utilisateur réel.
> Nom de fichier : `<locuteur>-<nombre>.wav` (ex. `v4-372.wav`), même format WAV 16 kHz mono.

### E1. Ré-enregistrer 4 fichiers devenus faux (locuteur v2)

Ces quatre-là avaient été dits avec l'ancien connecteur `nda`, qui n'existe plus :

| Fichier | Nombre | Ancienne forme (périmée) | **Forme correcte à dire** |
|---|---|---|---|
| `v2-102.wav` | 102 | ~~zangou nda hinka~~ | **zangou di hinka** |
| `v2-103.wav` | 103 | ~~zangou nda hinza~~ | **zangou di hinza** |
| `v2-104.wav` | 104 | ~~zangou nda taci~~ | **zangou di taci** |
| `v2-110.wav` | 110 | ~~zangou nda iwey~~ | **zangou di wey** |

Tant qu'ils ne sont pas refaits, la mesure de performance est faussée sur ces 4 cas.

### E2. Un **4ᵉ locuteur** (le plus important)

Le corpus compte 3 locuteurs, et le tirage les a **tous** placés dans le jeu de test. Il
n'existe donc **aucun jeu de réglage** distinct, ce qui bloque le calibrage du refus.
Un 4ᵉ locuteur (idéalement une voix différente : autre sexe, autre âge, autre région)
débloque ça. Même liste de nombres que les autres, ~35 fichiers.

### E3. Enregistrements **non numériques** de contrôle

Sans eux, impossible de régler le seuil à partir duquel l'app doit dire « je n'ai pas
compris » plutôt que d'inventer un nombre. **~15 fichiers courts** suffisent :

- [ ] 5 phrases zarma quelconques **sans aucun nombre** (« il fait chaud aujourd'hui »…)
- [ ] 4 enregistrements de **bruit ambiant** seul (marché, rue, ventilateur)
- [ ] 3 enregistrements de **silence** (micro ouvert, personne ne parle)
- [ ] 3 enregistrements de **musique** ou de radio

Nomme-les `nonum-01.wav`, `nonum-02.wav`, etc.

### E4. Condition **bruit** (objectif de qualité non mesuré à ce jour)

Tout le corpus actuel est en condition calme. L'objectif « ≥ 90 % en bruit modéré » n'a
donc **jamais** été mesuré. Réenregistrer **~20 nombres** avec un bruit de fond réaliste
(marché, radio) suffirait à le chiffrer. Nomme-les `<locuteur>-bruit-<nombre>.wav`.

| Sous-groupe | Fichiers | Débloque |
|---|---|---|
| E1 — les 4 périmés | 4 | mesure juste sur ces cas |
| E2 — 4ᵉ locuteur | ~35 | jeu de réglage + validité statistique |
| E3 — non numériques | ~15 | le refus « je n'ai pas compris » |
| E4 — condition bruit | ~20 | l'objectif de qualité en bruit |

---

## Après l'enregistrement

```bash
# Vérifier qu'il ne manque rien
uv run python scripts/speech/say_number.py --voice v1 --bank-dir ~/Music/voix2 --list-missing

# Vérifier la couverture (attendu : 1001/1001)
uv run python scripts/speech/say_number.py --voice v1 --bank-dir ~/Music/voix2 --coverage

# Écouter un nombre difficile
uv run python scripts/speech/say_number.py --voice v1 --bank-dir ~/Music/voix2 \
    --number 372 --out /tmp/372.wav
```
