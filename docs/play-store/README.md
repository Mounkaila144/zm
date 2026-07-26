# Publication Android de Zarma IA sur Google Play

Ce dossier contient les textes, déclarations et visuels préparés pour la fiche
Google Play. Il ne contient aucune clé privée.

## Livrables

- `assets/app-icon-512.png` : icône Play, PNG RGBA 512×512.
- `assets/feature-graphic-1024x500.jpg` : bannière Play 1024×500.
- `store-listing-fr.md` : nom et descriptions.
- `release-notes-1.1.0-fr.txt` : notes de version.
- `data-safety-fr.md` : réponses préparatoires « Sécurité des données ».
- `privacy-policy.html` : page publique à servir sur
  `https://ia.ptrniger.com/privacy`.

Les captures de téléphone doivent représenter la version réellement publiée.
Google Play exige au moins deux captures et recommande quatre captures portrait
de 1080×1920 ou plus. Elles seront placées dans `assets/screenshots-phone/`
après validation sur l’appareil.

## 1. Compte développeur

PTR Niger étant une entreprise, utiliser de préférence un compte Play Console
de type **Organisation**. Google exige alors les informations légales cohérentes
avec le profil de paiement et un numéro D‑U‑N‑S.

Pour un compte personnel créé après le 13 novembre 2023, Google exige
actuellement un test fermé avec au moins 12 testeurs inscrits pendant 14 jours
consécutifs avant la demande d’accès à la production. La vérification d’un
téléphone Android réel peut également être demandée.

## 2. Clé d’envoi

La clé locale a été créée par :

```bash
cd apps/mobile
./tool/create_play_upload_key.sh
```

Fichiers secrets, tous deux ignorés par Git :

- `android/upload-keystore.jks`
- `android/key.properties`

Les sauvegarder ensemble dans un coffre-fort chiffré. La perte de la clé ou de
son mot de passe bloque les prochains envois jusqu’à une procédure de
réinitialisation auprès de Google. Pour une nouvelle application, activer
**Play App Signing** : Google conserve la clé de signature de distribution et
le fichier local reste la clé d’envoi.

## 3. Préparer le serveur avant publication

Le build Play refuse de démarrer si `GET /api/v1/mobile/config` n’est pas
disponible. Avant tout test Play :

1. pousser les changements Git puis faire `git pull --ff-only` sur le VPS ;
2. exécuter `uv sync --frozen` et les migrations Alembic ;
3. ajouter les variables `MOBILE_*` et `REQUIRE_TRAINING_CONSENT=true` dans
   `.env.api` ;
4. copier/recharger la configuration nginx pour exposer `/privacy` ;
5. redémarrer `zarma-api` ;
6. vérifier :

```bash
curl -f https://ia.ptrniger.com/api/v1/mobile/config
curl -f https://ia.ptrniger.com/api/v1/consent
curl -f https://ia.ptrniger.com/privacy
```

Ne pas publier tant que ces trois commandes n’aboutissent pas.

## 4. Version

Chaque envoi doit avoir un `versionCode` inédit. Mettre à jour ensemble :

- `version: 1.1.0+2` dans `apps/mobile/pubspec.yaml` ;
- `AppConfig.buildNumber` dans `lib/config/app_config.dart` ;
- `MOBILE_LATEST_BUILD` sur le serveur.

Ne relever `MOBILE_MIN_SUPPORTED_BUILD` qu’après la disponibilité du nouveau
build sur Google Play.

## 5. Construire le bundle signé

```bash
cd apps/mobile
flutter pub get
flutter analyze
flutter test
flutter build appbundle --release \
  --dart-define=API_BASE_URL=https://ia.ptrniger.com/api/v1
```

Sortie :

`build/app/outputs/bundle/release/app-release.aab`

Le bundle doit être signé par l’alias `zarma-upload`, cibler l’API 36 et ne
contenir aucune URL HTTP.

## 6. Play Console

1. Créer l’application avec le package immuable
   `ne.zarma.zarma_mobile`.
2. Choisir le français comme langue par défaut, « Application » et « Gratuite ».
3. Activer Play App Signing.
4. Remplir la fiche avec `store-listing-fr.md` et les fichiers `assets/`.
5. Renseigner `https://ia.ptrniger.com/privacy`.
6. Compléter « Sécurité des données » à partir de `data-safety-fr.md`.
7. Compléter Accès à l’application, Public cible, Classification du contenu,
   Annonces et les autres déclarations de contenu.
8. Créer d’abord une version **Test interne**, téléverser le `.aab`, installer
   depuis Google Play et tester le micro, le consentement, le calcul, le retrait
   et la mise à jour immédiate.
9. Passer ensuite au test fermé ou à la production selon les exigences du
   compte.

## 7. Build signé avec GitHub Actions

Le workflow `Android release bundle` construit un `.aab` téléchargeable sans le
publier. Ajouter dans les secrets GitHub :

- `ANDROID_UPLOAD_KEYSTORE_BASE64`
- `ANDROID_UPLOAD_STORE_PASSWORD`
- `ANDROID_UPLOAD_KEY_PASSWORD`
- `ANDROID_UPLOAD_KEY_ALIAS` (`zarma-upload`)

Sur macOS, la valeur Base64 est obtenue sans modifier le fichier :

```bash
base64 -i apps/mobile/android/upload-keystore.jks | pbcopy
```

Les mots de passe restent dans le `android/key.properties` local et doivent
être copiés séparément dans les secrets GitHub.
