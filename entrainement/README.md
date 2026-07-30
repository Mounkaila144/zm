# Corpus vocal zarma — application Android

Application Flutter autonome et hors-ligne pour enregistrer une prise WAV par
consigne, la contrôler, puis partager un ZIP par le menu Android (WhatsApp,
Telegram, Drive, courriel, etc.).

Le projet se trouve dans `entrainement/corpus_recorder/`. Il ne dépend pas de
`apps/mobile` et ne lui importe aucun code.

## Compiler l’APK

Pré-requis :

- Flutter 3.44 ou plus récent ;
- Android SDK installé ;
- Java 17.

Depuis la racine du monorepo :

```sh
cd entrainement/corpus_recorder
flutter pub get
flutter analyze
flutter test
flutter build apk --release
```

L’APK installable est produit ici :

```text
entrainement/corpus_recorder/build/app/outputs/flutter-apk/app-release.apk
```

Pour l’installer sur un téléphone Android relié en USB :

```sh
adb install -r \
  entrainement/corpus_recorder/build/app/outputs/flutter-apk/app-release.apk
```

L’`applicationId` est `ne.zarma.corpus_recorder`. La configuration release du
projet neuf utilise actuellement la clé de développement Flutter afin que
l’APK soit immédiatement installable. Pour une diffusion publique durable,
remplacer cette signature par une clé de publication conservée en lieu sûr.

## Utiliser l’application

1. Ouvrir **Corpus vocal zarma**.
2. Créer un locuteur avec son prénom ou surnom. L’application ajoute un code
   aléatoire de quatre caractères, par exemple `aissata-7f3k`.
3. Garder la liste MVP embarquée, qui possède déjà ses 32 exemples audio, ou
   choisir un CSV externe puis son ZIP d’exemples.
4. Vérifier que la section **Audios d’exemple** indique autant d’exemples que
   de consignes, puis appuyer sur **Commencer**.
5. Pour chaque consigne, appuyer sur **ÉCOUTER L’EXEMPLE**. L’exemple peut être
   réécouté autant de fois que nécessaire.
6. Maintenir ensuite le bouton rond, répéter, puis
   relâcher. Un appui inférieur à 300 ms est ignoré ; la capture continue
   silencieusement 400 ms après le relâchement. Une prise atteint au maximum
   15 secondes.
7. Écouter sa propre prise ou la refaire si nécessaire, puis passer à la
   suivante.
8. Dans **Revue et export**, filtrer les prises douteuses, les réécouter ou les
   refaire.
9. Privilégier **Exporter ce locuteur**, puis choisir WhatsApp ou une autre
   application dans le menu de partage Android.

Une séance reste enregistrée sur le téléphone. Chaque locuteur peut la reprendre
indépendamment. **Recommencer** efface uniquement les prises de ce locuteur,
après confirmation.

## CSV de consignes

La liste embarquée `assets/consignes_mvp.csv` contient les 32 consignes
distinctes du MVP : quatre opérateurs longs, quatre formes courtes et
24 expressions.

Un CSV externe doit être encodé en UTF-8 et avoir exactement cet en-tête :

```csv
id,texte_zarma,affichage
2+3,ihinka kanga itonton ihinza,2 + 3
1500,zambar fo da zangou gou,1500
mot+,kanga itonton,+ (plus)
```

Les identifiants doivent être uniques et ne contenir ni espace, ni antislash,
ni caractère de contrôle.

### ZIP des audios d’exemple

Pour une campagne externe :

1. importer le CSV ;
2. importer le ZIP exporté par cette application après avoir enregistré et
   vérifié une voix de référence ;
3. créer ou recommencer la séance du contributeur.

Le ZIP doit concerner un seul locuteur et contenir son `manifest.csv`. Pour
éviter toute mauvaise association, l’application vérifie avant de l’accepter :

- que chaque identifiant du CSV possède exactement un WAV ;
- que `texte_zarma` est identique dans le CSV et le manifest ;
- qu’il n’existe aucun identifiant supplémentaire ou en double ;
- que chaque exemple est un WAV PCM 16 kHz, mono, 16 bits.

La banque MVP embarquée utilise les 32 prises fournies dans
`mounkaila-tksw.zip`. Elles sont disponibles sans manipulation de fichier et
restent séparées des nouvelles prises : elles ne sont jamais incluses dans le
ZIP exporté par un contributeur.

## Audio et contrôle qualité

Chaque prise est produite directement en :

```text
WAV PCM · 16 000 Hz · mono · 16 bits
```

Il n’y a ni découpage automatique, ni suppression de bruit, ni normalisation,
ni filtre, ni réencodage, ni rééchantillonnage. Le contrôle qualité lit les
échantillons PCM sans les modifier :

- rouge : format invalide, crête supérieure à 0,98 ou RMS inférieur à 0,01 ;
- orange : durée hors de 0,45× à 2,2× la médiane attendue, moins de 150 ms de
  silence final, ou arrêt automatique à 15 secondes ;
- vert : aucun de ces signaux.

La médiane est calculée sur les prises locales ayant le même nombre de mots dès
que trois mesures fiables existent. Avant cela, une estimation prudente par
nombre de mots sert de référence. Une pastille orange ou rouge n’empêche jamais
de poursuivre.

## Export

L’export d’un locuteur s’appelle par exemple `aissata-7f3k.zip`. L’export groupé
s’appelle `zarma_corpus_2026-07-30.zip`. Les deux contiennent :

```text
zarma_corpus/
  aissata-7f3k/
    manifest.csv
    2+3.wav
    ...
```

Le manifest contient :

```text
fichier,identifiant,texte_zarma,affichage,locuteur,code,date,duree_s,rms,crete,qualite
```

Les WAV sont ajoutés au ZIP en mode « stocké » : leurs octets ne sont jamais
réencodés.

## Permissions et fonctionnement hors-ligne

Le manifeste release demande uniquement :

- `RECORD_AUDIO`, pour le microphone ;
- `VIBRATE`, pour le retour haptique.

L’import CSV passe par le sélecteur de documents Android et ne demande aucune
permission générale de stockage. Le manifeste release ne demande pas
`INTERNET`. L’application ne contient aucune API, aucun compte et aucun envoi
automatique.

## Écarts imposés par les sources actuelles

Deux contradictions empêchent de satisfaire littéralement le dernier critère
de la spécification sans modifier des fichiers hors de `entrainement/`.

1. Un identifiant contenant `/` ne peut pas être un nom de fichier plat sous
   Android ni dans un ZIP. L’identifiant machine reste exact dans le CSV et
   dans `manifest.csv`, mais le nom physique échappe ce caractère de façon
   réversible : `10/2` devient `10%2F2.wav` et la colonne `fichier` porte ce
   nom. Aucun audio ni texte zarma n’est changé.
2. La version actuelle de
   `research/zarma-assistant/scripts/build_asr_corpus.py` ne lit pas ces
   manifests. Elle accepte seulement l’ancien corpus `v<N>-<nombre>.wav` et le
   dossier spécial `operation/`; elle rejette les dossiers `nom-code` et les
   expressions comme `2+3`. Le ZIP respecte donc le nouveau contrat documenté,
   mais ce script doit acquérir un lecteur du nouveau manifest avant de pouvoir
   le recevoir « tel quel ».

Enfin, le pré-roll de 200 ms qualifié de « souhaitable » dans la spécification
n’est pas implémenté. Le post-roll obligatoire de 400 ms, lui, est implémenté.
