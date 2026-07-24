# Epic 3 — Application mobile Android (parcours complet)

**Objectif étendu :** livrer l'application Flutter Android offrant le parcours utilisateur complet, connectée à l'API. À la fin de cet epic, un locuteur zarma peut enregistrer un nombre, voir ce que le système a compris, confirmer en cas d'ambiguïté, corriger simplement, et consulter son historique — avec une gestion robuste des permissions, des erreurs et des réseaux lents. Cet epic peut fonctionner contre l'API branchée sur `MockRecognizer` tant que l'ASR réel n'est pas déployé.

## Story 3.1 — Fondation de l'app Flutter et navigation

En tant que développeur,
je veux une app Flutter initialisée avec navigation et configuration API,
afin d'avoir un socle mobile prêt à accueillir les écrans.

### Acceptance Criteria

1. `apps/mobile` est un projet Flutter Android buildable avec la solution de gestion d'état retenue par l'Architect (Riverpod ou Bloc).
2. La navigation entre les écrans principaux (Accueil, Enregistrement, Traitement, Résultat, Confirmation, Correction, Historique) est en place.
3. L'URL de l'API et la configuration proviennent d'une config non secrète ; aucun secret n'est embarqué.
4. Un client HTTP (`dio`) est configuré avec gestion des timeouts et des erreurs réseau.
5. L'app démarre sur l'écran Accueil avec le bouton micro visible.

## Story 3.2 — Enregistrement audio contraint

En tant qu'utilisateur,
je veux enregistrer ma voix simplement et proprement,
afin de fournir un audio exploitable par le système.

### Acceptance Criteria

1. L'app demande et gère la permission micro (accord, refus, refus permanent) avec messages clairs.
2. L'enregistrement produit du WAV PCM 16 bits mono 16 kHz, borné (idéal 1–8 s, max 10 s) avec retour visuel (niveau, minuterie).
3. L'utilisateur peut annuler l'enregistrement ; le fichier temporaire est supprimé après envoi ou annulation.
4. Un contrôle de taille/durée empêche l'envoi d'audios hors limites.
5. Des tests/vérifications manuelles sur device confirment le format et la suppression du fichier temporaire.

## Story 3.3 — Traitement et écran Résultat

En tant qu'utilisateur,
je veux voir clairement le nombre compris,
afin d'obtenir rapidement mon résultat.

### Acceptance Criteria

1. Après enregistrement, l'app appelle `/recognize` et affiche un état de traitement avec possibilité d'annuler la requête.
2. En cas de haute confiance, l'écran Résultat affiche le nombre en chiffres et la forme zarma.
3. Les erreurs (réseau lent, timeout, échec serveur) affichent des messages clairs et des options de reprise.
4. La latence perçue est gérée (indicateur d'activité, pas de blocage de l'UI).

## Story 3.4 — Confirmation en cas d'ambiguïté

En tant qu'utilisateur,
je veux confirmer parmi des propositions quand le système hésite,
afin d'éviter une erreur sans avoir à tout ressaisir.

### Acceptance Criteria

1. Quand la réponse demande confirmation, l'app présente le(s) candidat(s) ordonné(s).
2. L'utilisateur peut sélectionner un candidat, demander à répéter, ou passer en correction manuelle.
3. Le choix de l'utilisateur est renvoyé comme feedback à l'API.
4. Quand la réponse demande répétition (phrase non numérique / trop incertaine), l'app invite à réenregistrer avec un message compréhensible.

## Story 3.5 — Correction manuelle avec forme zarma

En tant qu'utilisateur,
je veux corriger facilement un nombre erroné,
afin de garder le contrôle et de renforcer la fiabilité.

### Acceptance Criteria

1. L'écran Correction propose un clavier numérique pour saisir le bon nombre.
2. À la saisie, l'app affiche automatiquement la forme zarma canonique (via le générateur, exposé par l'API ou embarqué).
3. La correction est envoyée à `/feedback` avec le contexte (nombre proposé vs corrigé, versions).
4. Les nombres hors plage sont refusés avec un message clair.

## Story 3.6 — Historique

En tant qu'utilisateur,
je veux consulter mes reconnaissances passées,
afin de retrouver et vérifier mes résultats.

### Acceptance Criteria

1. L'écran Historique liste les reconnaissances récentes (nombre, forme zarma, date) via `/history`.
2. La liste gère les états vide, chargement et erreur.
3. L'affichage fonctionne en connexion lente (chargement progressif / réessai).

---
