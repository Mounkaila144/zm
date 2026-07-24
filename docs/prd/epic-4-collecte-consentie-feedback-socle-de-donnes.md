# Epic 4 — Collecte consentie, feedback & socle de données

**Objectif étendu :** transformer l'usage en ressource durable et éthique. À la fin de cet epic, les utilisateurs consentants peuvent contribuer leur voix via des prompts générés, avec consentement explicite versionné, anonymat, upload, et possibilité de retrait ; les contributions sont validées avant intégration au dataset ; et les corrections/feedbacks alimentent des métriques exploitables. Cet epic constitue le socle de données consenties réutilisable pour le benchmark (Epic 5) et l'amélioration continue.

## Story 4.1 — Consentement explicite versionné

En tant que contributeur,
je veux comprendre et accepter clairement comment ma voix sera utilisée,
afin de contribuer en confiance et de pouvoir me rétracter.

### Acceptance Criteria

1. Un écran de consentement présente un texte versionné (usage, anonymat, conservation, retrait) avant toute contribution.
2. Le consentement (version acceptée, horodatage, identifiant anonyme) est enregistré.
3. Aucune collecte conservée n'a lieu sans consentement explicite ; l'audio ordinaire reste supprimé par défaut.
4. Le texte et la version du consentement sont traçables côté serveur.

## Story 4.2 — Prompts de contribution et enregistrement consenti

En tant que contributeur,
je veux qu'on me propose quoi prononcer,
afin de fournir des contributions utiles et variées.

### Acceptance Criteria

1. Le système génère des prompts (nombres à prononcer) couvrant la plage et les cas utiles (paires de confusion, échelles).
2. Le flux de contribution réutilise l'enregistrement contraint (WAV PCM 16 bits mono 16 kHz).
3. Chaque contribution attache des métadonnées (prompt attendu, identifiant anonyme, device/région si fournis, versions).
4. Le consentement valide est requis pour lancer la contribution.

## Story 4.3 — Upload, endpoint `recordings` et stockage sécurisé

En tant que responsable données,
je veux recevoir et stocker les contributions de façon sûre,
afin d'alimenter le dataset sans exposer de données sensibles.

### Acceptance Criteria

1. `/api/v1/recordings` reçoit les contributions consenties (audio + métadonnées) avec les mêmes contrôles de sécurité audio que `/recognize`.
2. L'audio consenti est stocké en stockage objet/répertoire sécurisé (jamais en base) ; seules les métadonnées vont en base.
3. Les contributions sont marquées « en attente de validation » avant toute intégration au dataset.
4. Les logs ne contiennent aucune donnée sensible.

## Story 4.4 — Retrait des contributions

En tant que contributeur,
je veux pouvoir retirer mes contributions,
afin d'exercer mon droit de rétractation.

### Acceptance Criteria

1. Un mécanisme permet de demander le retrait des contributions liées à un identifiant anonyme.
2. Le retrait supprime l'audio consenti et marque les métadonnées comme retirées/anonymisées.
3. Les données retirées sont exclues du dataset et des évaluations futures.

## Story 4.5 — Validation avant intégration au dataset

En tant que responsable données,
je veux valider les contributions avant de les intégrer,
afin de préserver la qualité et la représentativité du corpus.

### Acceptance Criteria

1. Un outil/flux (script ou back-office minimal) permet de revoir les contributions en attente et de les accepter/rejeter.
2. Seules les contributions validées entrent dans le dataset, avec séparation **par locuteur** préservée.
3. Le statut (en attente / validé / rejeté / retiré) est traçable.

## Story 4.6 — Métriques de qualité issues du feedback

En tant que responsable produit,
je veux voir les métriques de production,
afin de piloter la qualité et cibler les améliorations.

### Acceptance Criteria

1. Les taux de confirmation et de correction sont calculés à partir des feedbacks stockés.
2. Les latences totale et ASR sont mesurées et consultables.
3. La couverture linguistique (éléments `validé` vs `unresolved`) est visible.
4. Les métriques sont exposées de façon lisible (endpoint, log structuré ou tableau de bord minimal).

---
