# Application mobile Zarma

Socle Flutter Android de l'application Zarma. Cette fondation utilise Material 3,
Riverpod pour l'injection de dépendances et Dio pour le futur accès à l'API.

## Prérequis

- Flutter 3.24.5 stable
- Dart 3.5.x (fourni par Flutter 3.24.x)
- Android SDK et un émulateur ou appareil Android

La CI est figée sur Flutter 3.24.5. Le projet accepte Dart à partir de 3.5 afin de
rester compatible avec la baseline d'architecture.

## Configuration non secrète

`API_BASE_URL` est fournie à la compilation avec `--dart-define`. Sa valeur par
défaut cible l'API locale depuis l'émulateur Android :
`http://10.0.2.2:8000/api/v1`.

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

Pour un appareil physique, remplacer `10.0.2.2` par l'adresse IP locale de la
machine qui exécute l'API. Cette configuration ne doit contenir aucun token,
aucune clé ASR et aucun autre secret. Les secrets restent exclusivement côté
serveur ; aucun fichier `.env` mobile n'est requis ou versionné.

### Appareil branché en USB (recommandé)

`adb reverse` fait passer l'API par le **câble** : rien ne sort sur le réseau, et
aucune adresse IP à retrouver à chaque changement de Wi-Fi.

```bash
# 1) API locale (sans GPU ; ASR_MOCK_TEXT force une transcription — DÉV uniquement)
ASR_MODE=mock ASR_MOCK_TEXT="waranka cindi hinza tonton iwey cindi gou" \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir services/api

# 2) Rediriger le port 8000 du téléphone vers celui de la machine
adb reverse tcp:8000 tcp:8000

# 3) Lancer l'app
flutter run --dart-define=API_BASE_URL=http://localhost:8000/api/v1
```

Le HTTP en clair n'est autorisé que par le manifeste **debug**
(`android/app/src/debug/AndroidManifest.xml`) : un build release reste en HTTPS
obligatoire (NFR3).

## Parcours vocal simplifié

L'accueil ne présente qu'une action principale. Un appui sur le grand micro
ouvre l'écran d'enregistrement et démarre immédiatement la capture. La personne
arrête avec le même geste explicite sur le bouton d'arrêt, ou laisse
l'application s'arrêter automatiquement à dix secondes. Un audio valide est
envoyé au traitement sans bouton « Continuer ».

Toute opération reconnue est relue à voix haute pour confirmation, y compris
lorsque le serveur l'a classée `accept`. Tant que la personne n'a choisi ni
« Oui » ni « Non », l'application attend trois secondes après la fin de la
lecture puis répète la demande. « Oui » ouvre le calcul et prononce
automatiquement la réponse ; « Non » revient à l'enregistrement et relance le
micro. L'écran de résultat ne conserve qu'une action pour dire une nouvelle
opération.

⚠️ **Chaîne de build.** Flutter ≥ 3.27 exige Gradle ≥ 8.7 alors que le wrapper du
projet est en 8.3 (aligné sur Flutter 3.24.5, la version du tech-stack). Avec un
SDK plus récent, ajouter `--android-skip-build-dependency-validation` à
`flutter build` / `flutter run`, ou installer la version pinnée.

## Commandes

Depuis `apps/mobile` :

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
flutter analyze
flutter test
flutter build apk --debug
```

## Organisation

- `lib/config/` : configuration non secrète injectable.
- `lib/network/` : client Dio central et classification des erreurs réseau.
- `lib/navigation/` : noms et graphe des routes Flutter.
- `lib/recording/` : permission, capture WAV, contraintes, état et nettoyage.
- `lib/screens/` : sept écrans fonctionnels sans comportement métier.
- `test/` : tests unitaires et widget tests sans appel Internet.

Les timeouts Dio sont de 10 secondes pour la connexion et de 30 secondes pour
l'envoi et la réception. La connexion échoue rapidement lorsque l'API est
injoignable, tandis que les durées d'envoi/réception laissent une marge aux
futurs transferts audio sans bloquer indéfiniment l'interface.

## Enregistrement audio

Android demande `android.permission.RECORD_AUDIO` au premier enregistrement.
En cas de refus, l'écran permet de réessayer. Après un refus permanent, il
propose d'ouvrir les réglages de l'application et recontrôle la permission au
retour.

Chaque prise est créée dans le répertoire temporaire de l'application avec les
contraintes suivantes :

- conteneur WAV, PCM 16 bits, mono, 16 kHz ;
- minimum accepté : 1 seconde ;
- zone idéale : 1 à 8 secondes ;
- avertissement après 8 secondes et arrêt automatique à 10 secondes ;
- taille maximale : 2 Mo.

Une prise invalide, annulée ou remplacée est supprimée. Une prise valide reste
temporaire jusqu'au handoff à la story 3.3 ; celle-ci devra appeler
`RecordingController.deleteHandoff()` dans un `finally` après l'envoi, quel que
soit son résultat. Aucun audio n'est déplacé vers un stockage permanent.

## Vérification sur appareil Android

1. Lancer `flutter run -d <device-id>`.
2. Refuser puis redemander le micro ; répéter jusqu'au refus permanent et
   vérifier le lien vers les réglages, puis autoriser le micro.
3. Enregistrer une prise de 2 à 5 secondes et une prise laissée jusqu'à l'arrêt
   automatique à 10 secondes.
4. Pendant l'écran « Audio prêt », inspecter le fichier temporaire avec un outil
   tel que `ffprobe` et confirmer WAV/PCM16/mono/16 kHz, durée et taille.
5. Annuler une prise, simuler la suppression post-envoi, puis confirmer avec
   `adb shell run-as ne.zarma.zarma_mobile` qu'aucun
   `zarma_recording_*.wav` ne reste dans le cache.

Le format produit par la chaîne Android et le comportement des réglages de
permission doivent être revérifiés sur chaque famille d'appareil ciblée. Les
tests automatisés utilisent des doubles et ne remplacent pas ce contrôle.

## Reconnaissance et écran Résultat

Après validation, l'écran Enregistrement transmet le chemin temporaire à
Traitement. L'application envoie une seule requête `POST /recognize` en
`multipart/form-data`, avec la part `audio` explicitement typée `audio/wav` et
un `anon_id` UUID. Aucun retry automatique n'est effectué : le serveur peut
avoir persisté une reconnaissance avant une coupure de réponse.

Traitement affiche immédiatement un indicateur et reste annulable. Le fichier
WAV est supprimé dans un `finally` après succès, erreur ou annulation. En cas
d'erreur, la seule reprise proposée est donc un nouvel enregistrement. Une
décision serveur `accept` ouvre Résultat ; `confirm` et `repeat` sont transmis
à Confirmation pour la story 3.4.

Les timeouts restent ceux de la fondation : connexion 10 secondes, envoi et
réception 30 secondes. Le serveur possède également une limite de traitement
de 30 secondes ; à cette frontière, le timeout transport peut arriver avant le
`504` serveur, mais les deux affichent le même message sûr.

Pour tester sur un appareil physique contre l'API locale :

```bash
# API, depuis la racine du dépôt
ASR_MODE=mock docker compose up api

# Mobile, avec l'adresse LAN de la machine
flutter run -d <device-id> \
  --dart-define=API_BASE_URL=http://<ip-lan>:8000/api/v1
```

Vérifier successivement un succès accepté, Annuler pendant Traitement, l'API
arrêtée et un timeout simulé. Dans chaque cas, contrôler le cache privé avec
`adb shell run-as ne.zarma.zarma_mobile` sans extraire ni journaliser l'audio.

## Confirmation en cas d'ambiguïté

Quand la décision serveur est `confirm`, l'écran Confirmation présente la
proposition principale puis les alternatives **dans l'ordre exact reçu** — aucun
tri, aucun recalcul de confiance ou de forme zarma côté mobile. Les scores,
seuils et versions ne sont jamais affichés. La proposition principale n'est pas
répétée si elle réapparaît dans les alternatives, et toute alternative sans
nombre ou sans forme zarma est ignorée. Si aucune proposition numérique
exploitable n'existe, l'écran bascule sur l'invite de répétition plutôt que
d'inventer un nombre.

Quand la décision est `repeat` (ou un `confirm` sans candidat exploitable),
aucun nombre n'est présenté comme résultat : l'écran explique qu'aucun nombre
n'a pu être identifié avec assez de certitude et propose de réenregistrer.

Chaque action explicite envoie un `POST /feedback` en JSON, avec l'`anon_id` du
même provider que `/recognize` :

| Action | `feedback_type` | `proposed_number` | `corrected_number` |
|--------|-----------------|-------------------|--------------------|
| Choix d'une proposition (principale ou alternative) | `confirmed` | nombre choisi | `null` |
| « Réenregistrer » depuis `confirm` ou `repeat` | `repeat_requested` | `recognizedNumber` (nullable) | `null` |
| « Saisir moi-même » | aucun envoi en 3.4 | — | — |

La requête ne porte jamais les versions : `model_version` et `grammar_version`
sont hérités par le backend depuis la reconnaissance persistée. Le receipt `201`
est validé côté client (identifiants, type, nombres et versions) et rejeté s'il
est incohérent. La navigation vers Résultat n'a lieu qu'après un receipt validé,
sans transformer une décision `confirm` en faux `accept`. Un `repeat_requested`
confirmé revient à l'écran Enregistrement s'il est encore dans la pile, sinon à
l'Accueil, sans repasser par Traitement ni Confirmation.

Limites connues : l'API feedback **n'est pas idempotente** (ni clé
d'idempotence, ni contrainte d'unicité). Aucun retry automatique n'est effectué
et les contrôles sont verrouillés pendant l'envoi pour neutraliser le double
tap ; en cas d'échec, seule une action « Réessayer » explicite renvoie le même
choix. Un `anon_id` divergent produit un `404` indifférenciable d'un identifiant
inconnu ; la persistance durable de l'`anon_id` reste une story de fondation.
La saisie manuelle (`corrected`), la génération zarma et l'historique sont hors
périmètre de cette story.
