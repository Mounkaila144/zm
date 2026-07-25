# services/api

Service API **FastAPI** du système Zarma — serveur traditionnel conteneurisé,
**sans GPU**. Expose le moteur linguistique déterministe (`zarma_numbers`) via HTTP.

## Endpoints

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/health` | Sonde de santé → `{ "status": "ok" }` |
| GET | `/api/v1/models` | Recognizers ASR : `{ active, available }` |
| GET | `/api/v1/grammar/version` | Version de grammaire (issue du lexique) : `{ grammar_version, validated_count, unresolved_items }` |
| POST | `/api/v1/recognize` | Reconnaissance audio sécurisée, persistée avec son `id` |
| GET | `/api/v1/history?anon_id=…` | Historique isolé d'un identifiant anonyme |
| POST | `/api/v1/feedback` | Confirmation ou correction liée à une reconnaissance |
| GET / POST | `/api/v1/consent` | Texte courant et acceptation versionnée du consentement |
| POST | `/api/v1/recordings` | Contribution WAV consentie, stockée avec le statut `pending` |
| POST | `/api/v1/recordings/withdraw` | Retrait et anonymisation des contributions d'un `anon_id` |
| GET | `/docs`, `/openapi.json` | Documentation OpenAPI (native FastAPI) |

## Configuration

Toute la config passe par l'objet `Settings` (`app/config.py`, pydantic-settings),
lu depuis l'environnement / un `.env` **hors Git**. Aucun secret en dur. Voir
`.env.example` racine pour la liste des variables backend.

La base utilise SQLite en développement et PostgreSQL en production via
`DATABASE_URL`. Les mêmes modèles SQLAlchemy et migrations Alembic sont utilisés
sur les deux moteurs. Aucune colonne audio n'est persistée.

### Stockage des contributions audio

`AUDIO_STORAGE_DIR` désigne la racine dédiée aux seuls WAV explicitement
consentis. L'API crée des fichiers PCM16 mono 16 kHz avec des noms UUID opaques :
elle ignore le nom envoyé par le client, conserve uniquement la référence
relative en base et ne l'expose jamais dans le reçu. Le répertoire et les
fichiers sont créés avec des permissions restrictives (`0700`/`0600`) lorsque
le système les prend en charge.

En staging et production, l'exploitant doit fournir un volume privé, chiffré au
repos et inaccessible au serveur web statique. La sauvegarde et la restauration
doivent couvrir ensemble ce volume et la base afin de préserver les références
fichier↔métadonnées. Les sauvegardes suivent la même politique d'accès, de
chiffrement, de rétention et de retrait que les données actives. Une
implémentation objet future peut remplacer le filesystem via l'interface
`AudioStore`.

La migration `20260724_0003` crée uniquement les métadonnées et index de
`contributions`. L'appliquer avant de recevoir des uploads :

```bash
uv run alembic -c services/api/alembic.ini upgrade head
uv run alembic -c services/api/alembic.ini check
```

Le contrat MVP n'a pas de clé d'idempotence : si le serveur accepte un upload
mais que le reçu réseau est perdu, une nouvelle tentative peut créer une
contribution distincte.

### Retrait et exclusion des exports

`POST /api/v1/recordings/withdraw` reçoit uniquement l'UUID anonyme de
l'appareil. La commande est idempotente et renvoie toujours le même reçu
générique après succès, qu'elle ait trouvé ou non des données actives.

Le traitement révoque d'abord les consentements afin de bloquer immédiatement
les nouveaux uploads, puis supprime les WAV du stockage actif et anonymise les
tombstones SQL. Une réponse `503 WITHDRAWAL_INCOMPLETE` indique un état partiel
sûr : les consentements sont déjà révoqués et la même commande doit être
réessayée jusqu'au succès. Un fichier déjà absent n'empêche pas le retry.

Toute construction de manifest, dataset ou benchmark doit utiliser le prédicat
central de `ContributionRepo.dataset_candidates` : uniquement
`status=validated` avec `audio_ref` non nul. Une ligne `withdrawn` est terminale
et ne doit jamais être restaurée ni exportée ; la séparation des locuteurs
éligibles continue de reposer sur `speaker_key`.

Le code supprime les données du stockage actif. La politique de purge des
sauvegardes chiffrées n'est pas définie par l'architecture actuelle : une
procédure d'exploitation distincte doit être approuvée avant la production pour
appliquer les retraits aux sauvegardes selon leur rétention.

## Sécurité et anonymat

Le MVP n'utilise ni compte utilisateur ni identifiant personnel : le client
transmet uniquement un `anon_id` (UUID généré sur l'appareil). Les endpoints
sensibles sont limités par `anon_id` lorsqu'il est disponible dans la requête,
sinon par IP. Cette clé de quota est volatile : l'IP n'est ni persistée ni
journalisée.

Les erreurs partagent une enveloppe sûre avec un `request_id` anonyme, également
renvoyé dans `X-Request-ID`. Les logs JSON ne contiennent que cet identifiant de
corrélation et des métadonnées techniques non sensibles — jamais l'audio, le
texte reçu, un secret, l'`anon_id` ou l'IP.

En staging et production, **HTTPS obligatoire** et **CORS restreint aux origines
attendues** sont appliqués par nginx/la couche de déploiement. Ils ne sont pas
ouverts par défaut dans le code applicatif du MVP.

## Développement

```bash
uv sync                                                  # installe le workspace
uv run alembic -c services/api/alembic.ini upgrade head # applique les migrations
uv run uvicorn app.main:app --app-dir services/api --reload   # démarrage local
uv run pytest services/api                               # tests d'intégration
```
