# Project Agents

This file provides guidance and memory for Codex CLI.

<!-- BEGIN: BMAD-AGENTS -->
# BMAD-METHOD Agents (bloc réduit)

Les personas et tâches BMAD complètes vivent dans `.bmad-core/` :

- **Agents** : `.bmad-core/agents/<id>.md` — analyst, pm, architect, po, sm, dev, qa,
  ux-expert, bmad-master, bmad-orchestrator.
- **Tâches** : `.bmad-core/tasks/<name>.md`
- **Templates / checklists / data** : `.bmad-core/{templates,checklists,data}/`
- **Config projet** : `.bmad-core/core-config.yaml`

Pour agir en tant qu'agent, lire le fichier `.bmad-core/agents/<id>.md` correspondant et
suivre ses `activation-instructions`.

> ⚠️ Le bloc complet (personas inline, ~205 KB) a été réduit manuellement pour éviter de
> renvoyer ~51 000 tokens à chaque requête quand le cache de prompt n'est pas actif.
> Version complète sauvegardée dans `AGENTS.md.full.bak`.
> Régénérer : `npx bmad-method install -f -i codex` (ou `npm run bmad:refresh`).
<!-- END: BMAD-AGENTS -->
