# Fiche de transcription — opérateurs arithmétiques zarma

> ## ✅ FICHE CLOSE — D1 résolue le 2026-07-25
>
> Les quatre formes courtes sont validées et **intégrées au lexique** (`lexicon.yaml`,
> `grammar_version` **1.4.0**) :
>
> | Opération | Forme canonique | Variantes | Enregistré |
> |---|---|---|---|
> | Addition `+` | `tonton` | `itonton` | ✅ `tonton.wav` |
> | Soustraction `−` | `zabou` | `izabou` | ✅ `zabou.wav` |
> | Multiplication `×` | `ingaybor` | — | ✅ `ingaybor.wav` |
> | Division `÷` | `inafaysor` | — | ✅ `inafaysor.wav` |
>
> Conséquence : les 4 opérations sont reconnues, évaluées et prononçables de bout en
> bout. Le plan de corpus est passé de 84 à **160 consignes**.
>
> La suite du document est conservée comme **trace de la session** de transcription.

> **À faire remplir par un locuteur natif zarmaphone.** Story 6.1, Task 0 (décision D1).
>
> ⚠️ Les colonnes « brouillon » ci-dessous sont ce que le **modèle de reconnaissance** a cru
> entendre. **Ce ne sont PAS des transcriptions validées** — elles servent uniquement à éviter
> de partir d'une page blanche. Corrige librement, y compris entièrement.

## Comment procéder

Écoute chaque fichier dans `~/Music/operation/` et complète la colonne « forme correcte ».

Fichiers : `v1`…`v4` = les 4 locuteurs · `+` `-` `*` `:` = les 4 opérations.

## 1. Transcription par locuteur

### Addition (`+`) — fichiers `v1+.wav` … `v4+.wav`

| Locuteur | Brouillon machine | ✍️ Forme correcte |
|---|---|---|
| v1 | `kan ga i tonton` | | `kan ga i tonton`
| v2 | `kanga i tonton` | | `kanga i tonton` 
| v3 | `kan ga i tontan` | | `kan ga i tontan`
| v4 | `kaŋ ga i tonton` | | `kaŋ ga i tonton`

### Soustraction (`−`) — fichiers `v1-.wav` … `v4-.wav`

| Locuteur | Brouillon machine | ✍️ Forme correcte |
|---|---|---|
| v1 | `kan ga i jabu` | |`kan ga i jabu` |
| v2 | `kaŋ ga izabu` | |`kaŋ ga izabu` | 
| v3 | `kan ga yi zabu` | |`kan ga yi zabu` 
| v4 | `kaŋ ga izabu` | |`kaŋ ga izabu` | 

### Multiplication (`×`) — fichiers `v1*.wav` … `v4*.wav`

| Locuteur | Brouillon machine | ✍️ Forme correcte |
|---|---|---|
| v1 | `kali m gay bor` | | `kali m gay bor` |
| v2 | `ka len ngay boor` | | `ka len ngay boor`
| v3 | `kalin goy bor` | | `kalin goy bor` | 
| v4 | `kali ngay boor` | | `kali ngay boor` |

### Division (`÷`) — fichiers `v1:.wav` … `v4:.wav`

| Locuteur | Brouillon machine | ✍️ Forme correcte |
|---|---|---|
| v1 | `kaŋ i foyi sor` | | `kaŋ i foyi sor` 
| v2 | `kan i fay sor` | | `kan i fay sor` 
| v3 | `ka yi fa yi sor` | | `ka yi fa yi sor`
| v4 | `kaŋ i fa i sɔrɔ` | | `kaŋ i fa i sɔrɔ`

## 2. Formes canoniques à retenir (le plus important)

Pour chaque opération, **une** forme de référence + les variantes légitimes.

| Opération | ✍️ Forme canonique | ✍️ Variantes acceptables |
|---|--------------------|--------------------------|
| Addition `+` | tonton             | itonton                  |
| Soustraction `−` | zabou              | izabou                   |
| Multiplication `×` | ingaybor          |                          |
| Division `÷` | inafaysor          |                          |

## 3. ❓ Questions structurelles (déterminent la faisabilité)

### Q1 — Mot court ou phrase entière ?

Les enregistrements semblent contenir des **phrases** (ex. `kaŋ ga i tonton`), pas des mots
isolés. Or les quatre commencent par le même début (`kaŋ` / `kan`).

**Existe-t-il un mot court désignant l'opération elle-même** (comme « plus », « moins » en
français) ?

- Addition : ✍️tonton  (`tonton` seul  )
- Soustraction : ✍️ zabou  (`zabu` seul )
- Multiplication : ✍️ ingaybor
- Division : ✍️ inafaysor

> ✅ **Réponse : oui, un mot court existe pour les quatre.** C'était la meilleure issue
> possible : la machine distingue les opérations sur un mot entier, et non sur la
> dernière syllabe d'une phrase de quatre mots dont trois seraient communs.
>
> ⚠️ La contradiction relevée plus haut sur `kalin gay boor` (donné pour `×` dans le
> tableau par locuteur, pour `÷` dans l'exemple Q2) est **tranchée par les formes
> courtes** : `ingaybor` = `×`, `inafaysor` = `÷`. L'exemple Q2 « 40 ÷ 8 » contenait
> donc bien une erreur.

> **Pourquoi ça compte :** si l'opérateur est une phrase de 4 mots dont 3 sont **communs aux
> quatre opérations**, la machine ne distingue l'opération que sur **le dernier mot**. C'est plus
> fragile — et ça allonge chaque énoncé. Un mot court, s'il existe, est nettement préférable.

### Q2 — Dans quel ordre dit-on une opération complète ?

Comment dit-on **« 23 + 15 »** en zarma, en une seule phrase naturelle ?

✍️ waranka cindi hinza kanga itonton iwey cindi gou

Et **« 40 ÷ 8 »** ?

✍️ weytachi kalin gay boor hakou

> **Pourquoi ça compte :** l'opérateur est-il **entre** les deux nombres (comme en français), ou
> oui comme en francais .

### Q3 — Risque de confusion avec `nda` ⚠️

Le mot **`nda`** sert déjà à composer les nombres : `zangou nda gou` = **105**.

**Le mot de l'addition peut-il être confondu avec `nda` ?** Autrement dit, `zangou nda gou`
peut-il vouloir dire à la fois « 105 » et « 100 plus 5 » ?

✍️ Oui / Non — précisions : non 

> **Pourquoi ça compte :** si oui, la machine ne peut pas trancher entre « un nombre » et « une
> opération ». Il faudrait alors une règle claire (marqueur, pause) pour lever l'ambiguïté.

### Q4 — Comment dit-on l'impossible ?

Le système ne sait manipuler que les entiers de 0 à 1 000 000. Que dire quand :

- le résultat est **négatif** (`3 − 5`) ? ✍️ impossible
- le résultat n'est **pas entier** (`7 ÷ 2`) ? ✍️ tu pronconce l'entier suivie de 'cindi' les rest 
- existe-t-il une façon zarma de dire **« 3, reste 1 »** (division avec reste) ?
  ✍️ 3 cindi 1

## 4. Note technique (pour l'équipe, pas pour le locuteur)

🐛 **Renommer les fichiers de division.** Le caractère `:` dans un nom de fichier **casse le
pipeline ASR** (fairseq2 l'interprète comme un séparateur d'offset : `v1:.wav` échoue). Renommer
`v1:.wav` → `v1div.wav`, etc.

✅ Point positif mesuré : les **16 fichiers ont été transcrits en alphabet latin**, sans dérive
vers d'autres écritures — contrairement aux chiffres isolés. Confirmé : plus l'énoncé est long,
plus la détection de langue du modèle est fiable.
