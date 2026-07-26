# Déploiement sur un VPS Ubuntu

> Cible : **4 vCPU / 8 Go**, Ubuntu 22.04 ou 24.04. L'API *et* le modèle ASR sur
> la même machine.
>
> ⚠️ Cette procédure **remplace** l'hébergement Modal décrit dans
> `docs/architecture/tech-stack.md`. C'est un écart d'architecture assumé :
> coût fixe et maîtrisé plutôt que GPU serverless facturé à l'usage.

## Ce que tu vas faire tourner

Trois services sur une seule machine, dont **un seul est exposé à Internet** :

```
Internet ──HTTPS──> nginx :443
                      │
                      └──> API FastAPI :8000        (127.0.0.1)
                             │           └──> PostgreSQL
                             └──> service ASR :8001 (127.0.0.1)
                                    └── modèle Omnilingual + décodage contraint
```

Le service ASR n'est **jamais** joignable de l'extérieur. C'est volontaire : il
n'a ni protection contre les abus, ni raison d'être public.

---

## 1. Préparer la machine

```bash
sudo apt update && sudo apt upgrade -y

# libsndfile1 : requis par le binaire natif fairseq2n (sinon l'import échoue
# avec une erreur de bibliothèque partagée peu lisible).
sudo apt install -y git curl build-essential libsndfile1 ffmpeg \
                    nginx certbot python3-certbot-nginx

# Base de données — choisis l'une des deux (voir § 5) :
sudo apt install -y postgresql          # moteur de référence, testé en CI
# sudo apt install -y mysql-server      # pris en charge, non testé en CI

# Utilisateur de service, sans shell de connexion.
sudo useradd --system --create-home --home-dir /opt/zarma --shell /usr/sbin/nologin zarma
```

Pare-feu — n'ouvrir que SSH et HTTPS :

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## 2. Récupérer le projet

```bash
sudo -u zarma git clone <URL_DE_TON_DEPOT> /opt/zarma
cd /opt/zarma
```

## 3. Deux environnements Python, volontairement séparés

Le paquet ASR tire **torch et fairseq2** (~2 Go). Les mêler à l'API rendrait
celle-ci lourde à déployer et à tester. La séparation est une règle du projet.

```bash
# uv, le gestionnaire utilisé par le projet
sudo -u zarma curl -LsSf https://astral.sh/uv/install.sh | sudo -u zarma sh
export PATH="/opt/zarma/.local/bin:$PATH"

# a) Environnement API (léger)
sudo -u zarma uv sync --frozen

# b) Environnement ASR (lourd, isolé)
sudo -u zarma uv venv --python 3.11 /opt/zarma/asrenv
# torch CPU explicite : sans l'index dédié, pip télécharge la version CUDA
# (~2,5 Go inutiles sur une machine sans GPU).
sudo -u zarma /opt/zarma/asrenv/bin/pip install \
    torch --index-url https://download.pytorch.org/whl/cpu
sudo -u zarma /opt/zarma/asrenv/bin/pip install omnilingual-asr
# Le paquet cœur, pour que le décodage contraint dispose de la grammaire.
sudo -u zarma uv pip install --python /opt/zarma/asrenv/bin/python \
    -e packages/zarma_numbers
```

## 4. Télécharger les poids du modèle

Au premier lancement, ~1 à 2 Go sont téléchargés. **Fais-le une fois à la main**
avant de créer le service : sinon `systemd` déclarera un échec de démarrage
pendant le téléchargement.

```bash
sudo -u zarma mkdir -p /opt/zarma/models
sudo -u zarma HF_HOME=/opt/zarma/models /opt/zarma/asrenv/bin/python -c \
  "from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline; \
   ASRInferencePipeline(model_card='omniASR_CTC_300M_v2'); print('poids en cache')"
```

## 5. Base de données

Le projet tourne sur **PostgreSQL** (moteur de référence, couvert par la CI) ou
sur **MySQL/MariaDB**. Le schéma est portable : ses colonnes indexées ont une
longueur bornée, et un test (`test_schema_portability.py`) compile le DDL pour
les trois moteurs à chaque exécution de la suite.

### Option A — PostgreSQL *(recommandé)*

```bash
sudo -u postgres psql -c "CREATE USER zarma WITH PASSWORD 'CHANGE_MOI';"
sudo -u postgres psql -c "CREATE DATABASE zarma OWNER zarma;"
```

`DATABASE_URL=postgresql+asyncpg://zarma:CHANGE_MOI@127.0.0.1/zarma`

### Option B — MySQL / MariaDB

⚠️ **MySQL 8.0.16 minimum.** En deçà, les `CHECK` sont *analysés puis ignorés
silencieusement* : les colonnes `decision`, `feedback_type` et `status`
accepteraient alors n'importe quelle valeur, et une donnée invalide passerait
sans erreur. MariaDB applique les `CHECK` depuis la 10.2.

```bash
mysql --version   # doit afficher ≥ 8.0.16 (ou MariaDB ≥ 10.2)

sudo mysql -e "CREATE DATABASE zarma CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -e "CREATE USER 'zarma'@'127.0.0.1' IDENTIFIED BY 'CHANGE_MOI';"
sudo mysql -e "GRANT ALL PRIVILEGES ON zarma.* TO 'zarma'@'127.0.0.1'; FLUSH PRIVILEGES;"
```

`utf8mb4` n'est pas optionnel : le lexique zarma contient des caractères comme
`ŋ` et `ɔ`, que l'ancien `utf8` de MySQL (3 octets) ne sait pas stocker.

Installe le pilote asynchrone — il n'est pas dans les dépendances par défaut :

```bash
sudo -u zarma uv sync --frozen --extra mysql
```

`DATABASE_URL=mysql+asyncmy://zarma:CHANGE_MOI@127.0.0.1/zarma`

> **Pourquoi PostgreSQL reste recommandé** : c'est le moteur que la CI exerce à
> chaque commit, celui que décrit l'architecture, et le seul sur lequel les
> migrations ont réellement tourné. MySQL fonctionne — le schéma est vérifié —
> mais tu serais le premier à l'éprouver en conditions réelles. Si tu utilises
> déjà MySQL pour autre chose sur ce VPS, faire tourner PostgreSQL à côté ne
> coûte que ~200 Mo de RAM.

## 6. Configuration (hors Git)

Deux fichiers, lisibles du seul utilisateur `zarma`.

```bash
# Secret partagé API ↔ ASR
TOKEN=$(openssl rand -hex 32)

sudo -u zarma tee /opt/zarma/.env.api >/dev/null <<EOF
APP_ENV=production
# PostgreSQL : postgresql+asyncpg://zarma:CHANGE_MOI@127.0.0.1/zarma
# MySQL      : mysql+asyncmy://zarma:CHANGE_MOI@127.0.0.1/zarma
DATABASE_URL=postgresql+asyncpg://zarma:CHANGE_MOI@127.0.0.1/zarma
ASR_MODE=ctc
ASR_ENDPOINT_URL=http://127.0.0.1:8001
ASR_ENDPOINT_TOKEN=$TOKEN
ASR_TIMEOUT_SECONDS=30
AUDIO_STORAGE_DIR=/opt/zarma/storage/audio
MOBILE_MIN_SUPPORTED_BUILD=2
MOBILE_LATEST_BUILD=2
MOBILE_ENFORCE_MIN_BUILD=true
REQUIRE_TRAINING_CONSENT=true
MOBILE_PLAY_STORE_URL=https://play.google.com/store/apps/details?id=ne.zarma.zarma_mobile
RATE_LIMIT_RECOGNIZE=10/minute
LOG_LEVEL=INFO
EOF

sudo -u zarma tee /opt/zarma/.env.asr >/dev/null <<EOF
ASR_ENDPOINT_TOKEN=$TOKEN
EOF

sudo chmod 600 /opt/zarma/.env.api /opt/zarma/.env.asr
sudo -u zarma mkdir -p /opt/zarma/storage/audio
```

Puis les migrations. Alembic lit `DATABASE_URL` via l'objet `Settings` de
l'API : il faut donc charger `.env.api` dans l'environnement du processus.

```bash
cd /opt/zarma
sudo -u zarma bash -c 'set -a; . /opt/zarma/.env.api; set +a; \
    uv run alembic -c services/api/alembic.ini upgrade head'
```

## 7. Lancer les services

```bash
sudo cp infrastructure/systemd/zarma-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zarma-asr zarma-api

# Le chargement du modèle prend quelques secondes.
sudo systemctl status zarma-asr zarma-api
curl -s http://127.0.0.1:8001/health   # {"status": "ok", ...}
curl -s http://127.0.0.1:8000/health   # {"status": "ok"}
```

## 8. Exposer en HTTPS

```bash
sudo cp infrastructure/nginx/zarma.conf /etc/nginx/sites-available/zarma
sudo sed -i 's/api.exemple.ne/TON_DOMAINE/' /etc/nginx/sites-available/zarma
sudo ln -sf /etc/nginx/sites-available/zarma /etc/nginx/sites-enabled/
sudo certbot --nginx -d TON_DOMAINE
sudo nginx -t && sudo systemctl reload nginx
```

## 9. Reconstruire l'application mobile

L'URL de l'API est figée **à la compilation** :

```bash
cd apps/mobile
flutter build apk --release \
    --dart-define=API_BASE_URL=https://TON_DOMAINE/api/v1
```

Le `versionCode` du build (`+2`, `+3`, etc. dans `pubspec.yaml`) doit
correspondre aux valeurs `MOBILE_*_BUILD`. Publier d'abord la nouvelle version
sur Google Play, attendre qu'elle soit disponible, puis augmenter
`MOBILE_MIN_SUPPORTED_BUILD` et redémarrer `zarma-api`. L'augmenter avant la
publication bloquerait tous les anciens clients sans issue.

---

## Vérifier que ça marche

```bash
# Accepter d'abord le consentement courant pour cet identifiant de test.
ANON_ID=00000000-0000-4000-8000-000000000001
CONSENT_ID=$(curl -s https://TON_DOMAINE/api/v1/consent \
  -H 'Content-Type: application/json' \
  -d "{\"anon_id\":\"$ANON_ID\",\"consent_version\":\"2.0.0\"}" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

# Une reconnaissance réelle, de bout en bout.
curl -F "audio=@un_enregistrement.wav;type=audio/wav" \
     -F "anon_id=$ANON_ID" \
     -F "consent_id=$CONSENT_ID" \
     -H "X-App-Build: 2" \
     https://TON_DOMAINE/api/v1/recognize

# Les temps, ventilés (modèle vs décodage)
sudo journalctl -u zarma-asr -f
```

Chaque requête journalise sa décomposition :

```
→ « waranka cindi hinza tonton iwey cindi gou » (confiance 0.87)
  · audio 3.7s · modèle 1101 ms · décodage 1074 ms · total 2179 ms
```

C'est **la** ligne à surveiller : si le total dérive vers 30 s, l'application
affichera « Le traitement a pris trop de temps ».

## Régler la charge

| Symptôme | Cause probable | Réglage |
|---|---|---|
| Réponses en 30 s+ | Modèle mal placé | Vérifier `--device cpu` (jamais bfloat16 émulé) |
| Erreurs 503 fréquentes | File saturée | Augmenter `--workers`, ou réduire la durée d'audio |
| RAM saturée | Trop de workers | Chaque worker ≈ 2 Go ; sur 8 Go, ne pas dépasser 2 |
| Lenteur générale | Silences facturés | Découper les silences avant l'inférence (non implémenté) |

Sur 4 vCPU / 8 Go, le point de départ raisonnable est **2 workers × 2 fils**.

---
