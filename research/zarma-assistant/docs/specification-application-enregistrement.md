# Application d'enregistrement de corpus vocal zarma — spécification

> Document à remettre tel quel à un développeur ou à un agent de codage.
> Il décrit une application Android autonome, distribuable à des contributeurs
> distants, qui produit un corpus **directement exploitable** par
> `research/zarma-assistant/scripts/build_asr_corpus.py`, sans aucune retouche
> manuelle.

---

## 1. Le problème à résoudre

Aujourd'hui, enregistrer un locuteur suppose : enregistrer un fichier continu,
l'ouvrir dans un éditeur audio, découper chaque phrase à la main, renommer
chaque extrait. C'est plusieurs heures de travail par personne, et c'est la
principale raison pour laquelle le corpus stagne à 8 locuteurs et 12 minutes.

L'application doit ramener ce travail à **zéro** : une prise = un appui = un
fichier correctement nommé.

Elle doit aussi permettre à des personnes éloignées, non techniciennes, de
contribuer depuis leur propre téléphone et de renvoyer leurs enregistrements
par WhatsApp.

---

## 2. Contraintes techniques non négociables

### Format audio

```
WAV PCM · 16 000 Hz · mono · 16 bits
```

Toute autre valeur rend les fichiers inutilisables : le modèle et tout le
pipeline sont construits sur ce format. L'application existante le produit déjà
— voir `apps/mobile/lib/recording/audio_recording_service.dart` :

```dart
static const RecordConfig recordingConfig = RecordConfig(
  encoder: AudioEncoder.wav,
  sampleRate: 16000,
  numChannels: 1,
);
```

Paquets Flutter déjà présents et suffisants : `record` 5.2.1, `path_provider`,
`permission_handler`.

### Nommage des fichiers

Le nom du fichier **est** l'étiquette. Il doit valoir exactement l'identifiant
de la consigne, sans transformation :

```
2+3.wav          1500.wav         mot+.wav         100005.wav
```

Aucun horodatage, aucun compteur, aucun suffixe dans le nom. Les métadonnées
vont dans le manifest, jamais dans le nom de fichier.

---

## 3. Écrans

### 3.1 Séance

- Choisir un locuteur existant ou en créer un nouveau.
- À la création : prénom ou surnom (libre), et **génération automatique d'un
  code court unique** (voir §6).
- Choisir la liste de consignes : liste embarquée par défaut, ou import d'un
  CSV.
- Si la personne a déjà une séance en cours, proposer **Reprendre** ou
  **Recommencer**.

### 3.2 Enregistrement

```
┌─────────────────────────────┐
│  Aïssata          12 / 32   │
│  ▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░   │
│                             │
│                             │
│          2 + 3              │  ← très grand
│                             │
│   ihinka kanga itonton      │  ← petit, gris
│         ihinza              │
│                             │
│       ┌─────────┐           │
│       │    ●    │           │  ← maintenir pour parler
│       │ PARLER  │           │
│       └─────────┘           │
│                             │
│   ▶ Écouter    ↻ Refaire    │
│                  Suivant →  │
└─────────────────────────────┘
```

**Ce qui est affiché en grand est le SENS, pas le zarma.** `2 + 3`, `1500`,
`50 − 20`. Le texte zarma reste visible en petit, à titre indicatif.

Raison : le zarma n'a pas d'orthographe standardisée. Quelqu'un qui lit une
transcription approximative produit une *voix de lecture* — syllabes détachées,
débit artificiel — au lieu de sa parole naturelle. Le texte zarma est
l'étiquette destinée à la machine, pas la consigne destinée à l'humain.

### 3.3 Revue et export

- Liste des consignes de la séance avec leur pastille qualité (§5).
- Écoute et réenregistrement depuis cette liste.
- Filtre « ne montrer que les prises douteuses ».
- Boutons d'export (§7).

C'est l'écran qu'on oublie et qui sauve : il permet de voir d'un coup les cinq
prises suspectes sur quatre-vingt-dix, au lieu de découvrir le problème des
semaines plus tard à l'entraînement.

---

## 4. Comportement du bouton d'enregistrement

**Maintien-relâchement, comme WhatsApp** : on appuie et on garde le doigt
pendant qu'on parle, on relâche à la fin.

### Post-roll obligatoire — 400 ms

À la fin de l'appui, **continuer d'enregistrer 400 ms avant de fermer le
fichier**. L'utilisateur ne voit rien.

Ce n'est pas un raffinement. Les gens relâchent au moment exact où ils
finissent de parler, ce qui rogne le dernier phonème. Or les deux causes
d'erreur dominantes du modèle actuel sont précisément des fins d'énoncé
avalées : `gou` final (`zambar fo da zangou gou` reconnu 1100 au lieu de 1500)
et `dala` (100099 reconnu 199000). Un bouton qui coupe net fabriquerait
industriellement le défaut qu'on cherche à corriger.

### Pre-roll — 200 ms, souhaitable

Démarrer la capture dans un tampon circulaire dès l'affichage de la consigne,
et conserver les 200 ms précédant l'appui. Protège les débuts de mots. Plus
délicat à implémenter — à faire si le temps le permet, sans bloquer le reste.

### Garde-fous

- Appui de moins de 300 ms : ignoré, pas de fichier créé (appui accidentel).
- Appui de plus de 15 s : arrêt automatique, prise marquée douteuse.
- Retour haptique court à l'appui et au relâchement.

---

## 5. Contrôle qualité immédiat

Après chaque prise, calculer et afficher une pastille **verte / orange /
rouge** :

| contrôle | seuil | signification |
|---|---|---|
| niveau crête | > 0,98 | saturation — inutilisable |
| niveau moyen (RMS) | < 0,01 | trop faible ou micro couvert |
| durée vs longueur du texte | hors de 0,45× à 2,2× la médiane attendue | probablement tronqué ou mauvaise consigne |
| silence en fin | < 150 ms | fin de mot probablement coupée |

Le contrôle de durée est le plus précieux. C'est lui qui a démasqué les deux
pires accidents de ce projet : un découpage automatique produisant `999999` en
0,48 s, et 16 clips d'opérateur étiquetés `tonton` alors qu'ils duraient
1,40 s — trois fois la durée d'un mot isolé.

Une pastille rouge **n'empêche pas** de continuer : elle propose « Refaire »,
et l'information est consignée dans le manifest. C'est à l'humain de décider.

---

## 6. Locuteurs — nombre illimité sur un même téléphone

Un même téléphone doit pouvoir servir à un nombre quelconque de locuteurs, les
séances se poursuivant indépendamment.

### Code unique — indispensable en collecte distribuée

À la création d'un locuteur, générer un **code court aléatoire** de 4
caractères, accolé au nom :

```
aissata-7f3k
moussa-x29p
```

Sans cela, deux contributrices prénommées Aïssata sur deux téléphones
différents produiraient des dossiers homonymes qui s'écraseraient à la fusion.
Avec le code, on peut fusionner les envois de vingt contributeurs sans jamais
vérifier quoi que ce soit à la main.

### Ordre des consignes mélangé par locuteur

Chaque locuteur reçoit les consignes dans un ordre différent, tiré à partir de
son code (donc reproductible).

Si tout le monde enregistre dans le même ordre, la fatigue tombe toujours sur
les mêmes consignes : les dernières sont bâclées chez **tous** les locuteurs à
la fois, et ces mots-là restent durablement mal appris. Mélanger répartit la
fatigue sur l'ensemble du vocabulaire.

---

## 7. Export

### Arborescence

```
zarma_corpus/
  aissata-7f3k/
    manifest.csv
    2+3.wav
    1500.wav
    ...
  moussa-x29p/
    manifest.csv
    ...
```

### Deux boutons

- **Exporter ce locuteur** → `aissata-7f3k.zip` (~4 Mo pour 90 énoncés)
- **Exporter tous les locuteurs** → `zarma_corpus_<date>.zip`

### Envoi

Partage Android natif (`share_plus`), qui ouvre WhatsApp, Telegram, Drive ou
courriel indifféremment. **Ne pas coder d'intégration WhatsApp spécifique** :
le partage système couvre tout et ne casse pas quand WhatsApp change.

**Privilégier l'export par locuteur.** Un ZIP de 4 Mo part sur un réseau
médiocre ; un ZIP de 60 Mo échoue et doit être renvoyé entièrement. Le bouton
« tous » sert au collecteur qui rapatrie son propre téléphone, pas aux
contributeurs distants.

### Manifest exporté

Le CSV accompagne les fichiers dans chaque dossier. C'est lui qui rend l'envoi
autonome — sans lui, le destinataire ne peut pas savoir ce que contient chaque
fichier.

```csv
fichier,identifiant,texte_zarma,affichage,locuteur,code,date,duree_s,rms,crete,qualite
2+3.wav,2+3,ihinka kanga itonton ihinza,2 + 3,aissata,7f3k,2026-07-30T10:12:03Z,1.83,0.061,0.42,ok
```

---

## 8. Format du CSV de consignes en entrée

Liste embarquée par défaut dans l'application, **et** import possible d'un
fichier.

```csv
id,texte_zarma,affichage
2+3,ihinka kanga itonton ihinza,2 + 3
1500,zambar fo da zangou gou,1500
mot+,kanga itonton,+ (plus)
```

- `id` — devient le nom du fichier. Sans espace ni accent.
- `texte_zarma` — l'étiquette pour l'entraînement.
- `affichage` — ce que voit le locuteur, en grand.

**La liste embarquée est essentielle** : un contributeur distant ne manipulera
jamais un fichier CSV. L'import sert au collecteur qui prépare une campagne
particulière.

---

## 9. Ce qu'il ne faut PAS faire

- **Aucun découpage automatique.** Une prise = un appui = un fichier. Toute la
  fiabilité vient de là. Une tentative de découpage automatique par détection
  de silence a déjà produit un jeu de données entièrement mal étiqueté, sans
  aucun signe d'erreur visible.
- **Aucune suppression de bruit, aucune normalisation, aucun filtre.** Le bruit
  ambiant fait partie des conditions réelles d'usage et sert à l'entraînement.
- **Aucun réencodage.** Ni MP3, ni AAC, ni rééchantillonnage.
- **Aucun envoi automatique vers un serveur** dans cette version. Export
  manuel, contrôlé.
- **Aucune connexion réseau requise** pour enregistrer. Tout doit fonctionner
  hors-ligne, l'envoi se faisant plus tard.

---

## 10. Points à trancher avant de coder

**Écoute d'un exemple.** Pour un locuteur qui ne lit pas, entendre la prise
d'un autre aide à comprendre la consigne — mais il risque d'imiter l'accent et
le débit entendus, ce qui réduit la diversité recherchée. Suggestion : bouton
présent mais discret, à utiliser seulement en cas d'incompréhension, jamais
systématiquement.

**Consentement.** La spécification MVP du projet stipule « ne pas réutiliser
les voix sans consentement ». Si l'application dépasse le cercle des proches,
prévoir un écran de consentement à la première séance de chaque locuteur, dont
la trace est consignée dans le manifest.

---

## 11. Critère de réussite

L'application est réussie si, après une séance de 90 énoncés avec un locuteur,
le fichier ZIP reçu par WhatsApp peut être décompressé et donné tel quel à
`build_asr_corpus.py` — **sans ouvrir un seul fichier audio, sans renommer quoi
que ce soit, sans corriger une seule étiquette**.
