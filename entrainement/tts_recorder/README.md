# Studio vocal zarma TTS

Application Android Flutter indépendante pour enregistrer la voix unique d’un
modèle Piper zarma à vocabulaire fermé.

Elle embarque une copie de
`research/zarma-assistant/data/tts_prompts.csv` : **400 consignes exactes**,
de 1 à 17 mots. Le collecteur ASR `corpus_recorder` n’est ni importé ni
modifié.

## Format master

Chaque appui produit directement :

```text
WAV PCM · 48 000 Hz · mono · 16 bits
```

Le gain automatique, l’annulation d’écho et la suppression de bruit sont
explicitement désactivés. Il n’y a aucun découpage, filtre, réencodage,
rééchantillonnage ou envoi réseau dans l’application.

Les masters 48 kHz sont archivés. La dérivation Piper à 22,05 kHz sera produite
plus tard, hors ligne, avec une commande reproductible.

## Compiler

```sh
cd entrainement/tts_recorder
flutter pub get
flutter analyze
flutter test
flutter build apk --release
```

APK :

```text
entrainement/tts_recorder/build/app/outputs/flutter-apk/app-release.apk
```

Paquet Android : `ne.zarma.tts_recorder`.

## Enregistrer

1. Créer une voix, par exemple `Mounkaila`.
2. Utiliser toujours la même personne, le même téléphone ou microphone, la
   même distance et la même pièce calme.
3. Les exemples audio sont facultatifs. Un ZIP complet peut être importé si la
   personne a besoin d’entendre chaque phrase.
4. Lire exactement le texte zarma affiché en grand, avec un ton naturel.
5. Maintenir le bouton pendant toute la phrase puis relâcher. Le post-roll
   conserve 400 ms après le relâchement.
6. Écouter et refaire immédiatement les prises signalées.
7. S’arrêter après 20 prises pour le premier pilote et faire contrôler ce ZIP
   avant d’enregistrer les 380 autres.

Une prise rouge ou orange reste exportable afin que l’humain garde la décision,
mais la revue permet de les filtrer.

## Contrôles TTS

Rouge :

- format différent de WAV PCM 48 kHz mono 16 bits ;
- saturation à partir de 0,98 ;
- RMS inférieur à 0,015 ;
- durée inférieure à 0,35 s ou supérieure à 12 s.

Orange :

- début ou fin possiblement coupés ;
- silence de début ou de fin supérieur à 1 s ;
- bruit de fond final RMS supérieur à 0,02 ;
- niveau moyen très élevé, décalage continu ou durée incohérente ;
- arrêt automatique à 15 s.

Ces mesures n’altèrent jamais les échantillons.

## Export Piper

Le ZIP d’une voix contient :

```text
zarma_tts/
  mounkaila-ab12/
    metadata.csv
    manifest.csv
    wavs/
      tts_1.wav
      tts_1%2F5.wav
      ...
```

`metadata.csv` suit le format mono-locuteur Piper :

```text
tts_1.wav|afo
tts_1%2F5.wav|afo inafaysor igou
```

`manifest.csv` conserve les identifiants originaux, dates et mesures de qualité.
Le caractère `/`, impossible dans un nom de fichier plat, est échappé en
`%2F`, tandis que l’identifiant original reste intact dans le manifest.

Documentation Piper :
<https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/TRAINING.md>.

## Limite volontaire

Cette campagne vise uniquement les 400 textes embarqués. Le modèle pourra être
évalué et utilisé sur ce vocabulaire fermé ; aucune qualité n’est promise sur
une phrase extérieure à cette liste.
