# Zarma

Projet piloté avec BMAD-METHOD 4.44.3.

## Méthode BMAD

Les commandes Claude Code sont dans `.claude/commands/BMad`. Les mêmes agents sont
disponibles pour Codex via `AGENTS.md`.

Flux classique : `/analyst` → `/pm` → `/architect` → `/po` → `/sm` → `/dev` → `/qa`.

Commandes de maintenance :

```bash
npm run bmad:list
npm run bmad:validate
npm run bmad:refresh
```
