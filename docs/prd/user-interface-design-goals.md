# User Interface Design Goals

## Overall UX Vision

Une application **minimaliste, orale-first et rassurante**, conçue pour des utilisateurs aux niveaux d'alphabétisation variés. Le geste central est unique et évident : appuyer sur un gros bouton micro, parler, obtenir un nombre. L'UX privilégie la **confiance et le contrôle** : le système montre clairement ce qu'il a compris, demande confirmation quand il hésite, et rend la correction triviale. Aucun jargon technique n'est exposé à l'utilisateur final ; les scores et versions restent en coulisses (utiles au diagnostic, pas à l'écran principal).

## Key Interaction Paradigms

- **Un seul geste principal** : bouton micro proéminent (press-to-record ou tap-to-start/stop) avec retour visuel d'enregistrement (niveau audio, minuterie, limite 10 s).
- **Boucle de confirmation** : Résultat → soit accepté immédiatement (haute confiance), soit écran de confirmation présentant le(s) candidat(s), soit invitation à répéter.
- **Correction directe** : clavier numérique pour saisir le bon nombre, avec affichage immédiat de la forme zarma canonique (renforce l'apprentissage et la confiance).
- **Feedback non intrusif** : indicateurs d'état clairs (enregistrement, traitement, réseau lent, erreur) via icônes et couleurs plutôt que texte dense.

## Core Screens and Views

- **Écran Accueil** (point d'entrée, bouton micro, accès historique)
- **Écran Enregistrement** (retour audio, minuterie, annulation)
- **Écran Traitement** (état de la reconnaissance, annulation possible)
- **Écran Résultat** (nombre en chiffres + forme zarma)
- **Écran Confirmation** (candidats en cas d'ambiguïté)
- **Écran Correction** (clavier numérique + forme zarma canonique)
- **Écran Historique** (reconnaissances passées)
- **Écran/Flux Contribution & Consentement** (collecte vocale consentie, prompts, retrait)

## Accessibility: WCAG AA

Cible **WCAG AA** adaptée au mobile : contrastes suffisants, cibles tactiles larges, dépendance minimale au texte (icônes + couleurs + éventuels repères audio), compatibilité lecteurs d'écran Android. Pertinent pour une audience à alphabétisation variable.

## Branding

Aucune charte graphique imposée à ce stade. Recommandation : identité sobre et culturellement respectueuse, valorisant la langue zarma (affichage systématique de la forme zarma à côté des chiffres). À préciser avec l'UX Expert.

## Target Device and Platforms: Mobile Only (Android d'abord)

**Android en priorité** pour le MVP (téléphones courants d'Afrique de l'Ouest). iOS repoussé post-MVP. Pas de version web ni desktop dans le périmètre MVP.

---
