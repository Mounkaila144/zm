# Déclaration « Sécurité des données » — Zarma IA

Réponses préparatoires pour Play Console. Elles doivent être revérifiées après
toute modification de l’application, de l’API ou d’un SDK.

## Collecte et sécurité

- L’application collecte-t-elle ou partage-t-elle des données utilisateur ?
  **Oui, elle collecte des données.**
- Données chiffrées en transit : **Oui**, pour le build Play en HTTPS.
- Suppression des données : **Oui**, depuis l’icône Confidentialité de
  l’application ou par demande à `mail@ptrniger.com`.
- Création de compte : **Non**.
- Partage avec des tiers : **Non**.

## Types de données à déclarer

### Audio — Enregistrements vocaux ou sonores

- Collecté : **Oui**.
- Partagé : **Non**.
- Traitement éphémère : **Non**, les enregistrements consentis sont conservés.
- Collecte obligatoire : **Oui** pour utiliser l’application.
- Finalités : **Fonctionnalité de l’application** et **Analyses** (entraînement,
  test et amélioration des modèles de reconnaissance).

### Identifiants — Identifiants d'appareil ou autres identifiants

- Collecté : **Oui** (`anon_id`, identifiant aléatoire de l’installation).
- Partagé : **Non**.
- Traitement éphémère : **Non**.
- Collecte obligatoire : **Oui**.
- Finalités : **Fonctionnalité de l’application**, **Sécurité/prévention des
  abus** et gestion du consentement/retrait.

## Données non collectées par l’application

Pas de nom, adresse e-mail, numéro de téléphone, contacts, localisation,
photos, vidéos, données financières, santé, messages, fichiers personnels,
historique de navigation, identifiant publicitaire ni compte utilisateur.

## URL à renseigner

- Politique de confidentialité : `https://ia.ptrniger.com/privacy`
- Demande de suppression : la même page indique l’accès dans l’application et
  l’adresse `mail@ptrniger.com`.
