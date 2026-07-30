# Distribution iOS bêta avec TestFlight

Cette application iOS est distribuée aux testeurs uniquement par TestFlight :

`Xcode → Archive → Distribute App → TestFlight & App Store → Upload`

Dans les versions de Xcode qui affichent l’ancien assistant, le chemin
équivalent est :

`Distribute App → App Store Connect → Upload`

Ne pas choisir `TestFlight Internal Only`, car cette option interdit ensuite
l’ajout de testeurs externes.

## Identité de la build

- Nom affiché : `Zarma IA`
- Bundle Identifier : `ne.zarma.zarmaMobile`
- Version : `1.1.0`
- Build : `2`
- API de production : `https://ia.ptrniger.com/api/v1`
- Politique de confidentialité : `https://ia.ptrniger.com/privacy`
- Contact : `mail@ptrniger.com`

Le numéro après `+` dans `apps/mobile/pubspec.yaml` doit être augmenté avant
chaque nouvel envoi d’une build de la même version. Le même numéro doit rester
cohérent avec `AppConfig.buildNumber`.

## Préparation locale

Depuis `apps/mobile` :

```bash
flutter clean
flutter pub get
cd ios
pod install
cd ..
flutter analyze
flutter test
flutter build ios --release
open ios/Runner.xcworkspace
```

La dernière commande de build nécessite une équipe Apple Developer payante
sélectionnée dans le target `Runner`. Pour valider la compilation avant que la
signature soit disponible, utiliser temporairement :

```bash
flutter build ios --release --no-codesign \
  --dart-define=API_BASE_URL=https://ia.ptrniger.com/api/v1
```

## Signature

Dans Xcode :

1. ouvrir le navigateur de projet avec `⌘1` ;
2. cliquer sur le projet bleu `Runner` ;
3. sous `TARGETS`, cliquer sur `Runner` ;
4. ouvrir `Signing & Capabilities` ;
5. laisser `Automatically manage signing` activé ;
6. sélectionner l’équipe Apple Developer qui possède
   `ne.zarma.zarmaMobile`.

Une `Personal Team` n’est pas valable pour TestFlight. Aucun certificat ou
profil ne doit être créé pour les testeurs : Xcode gère la signature App Store
et Apple distribue la build avec TestFlight.

## Archivage et envoi

1. choisir le scheme `Runner` ;
2. choisir `Any iOS Device (arm64)` ou `Any iOS Device` ;
3. ouvrir `Product → Archive` ;
4. dans l’Organizer, sélectionner l’archive ;
5. cliquer sur `Distribute App` ;
6. choisir `TestFlight & App Store` ou, dans l’ancien assistant,
   `App Store Connect → Upload` ;
7. conserver la signature automatique et l’envoi des symboles ;
8. ne pas activer `TestFlight Internal Only` ;
9. valider puis envoyer la build.

L’upload ne publie pas l’application sur l’App Store. Une publication publique
nécessite une soumission App Review distincte, qui n’entre pas dans ce
processus.

## Informations de bêta recommandées

### Description

Zarma IA permet de prononcer un nombre ou un calcul en zarma, de confirmer la
reconnaissance et d’écouter le résultat. Avec le consentement de la personne,
les enregistrements contribuent aussi à l’amélioration de la reconnaissance
vocale en zarma.

### Fonctionnalités à tester

- consentement initial et accès à l’application ;
- demande d’autorisation du microphone ;
- enregistrement et arrêt automatique ;
- reconnaissance d’un nombre ou d’un calcul en zarma ;
- confirmation ou correction du résultat ;
- lecture vocale du résultat ;
- historique ;
- retrait du consentement depuis l’écran Confidentialité.

### Accès pour la Beta App Review

Aucun compte et aucun mot de passe ne sont nécessaires.

1. ouvrir l’application avec une connexion Internet ;
2. accepter la note de confidentialité ;
3. autoriser le microphone ;
4. prononcer par exemple `waranka cindi hinza` pour le nombre 23 ;
5. suivre l’écran de confirmation.

### Contact et remarques

- Contact : `mail@ptrniger.com`
- Politique de confidentialité :
  `https://ia.ptrniger.com/privacy`
- Remarque : l’application cible la langue zarma et envoie l’audio à un
  service HTTPS de reconnaissance. Elle n’utilise pas la reconnaissance vocale
  Apple et ne demande aucun compte utilisateur.

## Testeurs externes

Dans App Store Connect :

1. ouvrir `Zarma IA`, puis `TestFlight` ;
2. attendre la fin du traitement de la build ;
3. compléter la conformité d’exportation si Apple la demande ;
4. renseigner les informations de test et le contact ;
5. créer d’abord un groupe de test interne si App Store Connect l’exige ;
6. créer un groupe sous `External Testing` ;
7. ajouter la build et remplir `What to Test` ;
8. soumettre la build à la Beta App Review ;
9. après approbation, ajouter les testeurs par adresse e-mail et envoyer les
   invitations.

Les testeurs installent l’app TestFlight depuis l’App Store, acceptent
l’invitation et installent Zarma IA depuis TestFlight. Aucun UDID, profil,
certificat manuel ou fichier IPA n’est nécessaire.
