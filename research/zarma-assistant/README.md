# Zarma Assistant — Phase 0 (dé-risquage)

Projet de recherche autonome, séparé de l'app mobile (`apps/mobile`) et de
l'API existante (`services/api`). Objectif : évaluer la faisabilité d'un
assistant conversationnel vocal en zarma avant d'investir dans la
construction (voir `docs/assistant-conversationnel-zarma-strategie.md` à la
racine du repo pour la stratégie complète).

## Question posée par la Phase 0

Un LLM généraliste (GLM, servi via [z.ai](https://z.ai)) peut-il déjà
traduire correctement entre le français et le zarma, dans les deux sens, à
partir du glossaire et de quelques exemples (few-shot) — sans fine-tuning ?
Le script appelle GLM via le point d'accès **compatible Anthropic** de z.ai
(`https://api.z.ai/api/anthropic`), donc avec le SDK Python `anthropic`
standard, juste pointé ailleurs.

Si oui dans le sens zarma→français, le pipeline conversationnel peut sauter
l'étape de traduction dédiée pour cette direction (Amendement A de la
stratégie) : l'ASR alimente directement le LLM, qui comprend le zarma
lui-même.

## Contenu

```
research/zarma-assistant/
├── data/                    # corpus téléchargés (gitignored, sauf échantillons)
├── results/                 # sorties de benchmark (JSON + rapport lisible)
├── scripts/
│   ├── download_feriji.py     # télécharge le corpus Feriji (HF) et isole le split test
│   ├── bench_translation.py   # évalue GLM fr→zarma et zarma→fr sur un échantillon
│   ├── train_m2m100_lora.py     # fine-tuning LoRA local (Mac, sans GPU) — trop lent, abandonné
│   ├── _m2m100_zarma.py         # ajout du zarma comme langue M2M100 (partagé local/cloud)
│   ├── train_m2m100_cloud_gpu.py # fine-tuning complet M2M100 — Kaggle, SageMaker, Colab...
│   ├── translate_interactive.py  # charge le modèle entraîné, traduit des phrases libres (Colab)
│   └── test_asr.py               # compare MMS-1B-all vs Whisper-zarma sur de vrais enregistrements
├── .env.example
└── pyproject.toml
```

## Mise en route

```bash
cd research/zarma-assistant
uv sync
cp .env.example .env
# éditer .env et renseigner ZAI_KEY et HF_TOKEN

uv run python scripts/download_feriji.py
uv run python scripts/bench_translation.py --sample-size 200
```

Si l'API renvoie une erreur liée à `cache_control` (le support du prompt
caching sur le point d'accès z.ai n'est pas documenté avec certitude au
moment de l'écriture), relancer avec `--no-cache-control`.

Le script de benchmark échantillonne (par défaut 200 phrases, seed fixe pour
reproductibilité) le split test de Feriji, demande à GLM de traduire
chaque phrase dans les deux sens avec le glossaire + quelques exemples en
contexte, calcule un score BLEU par direction (`sacrebleu`), et écrit :

- `results/bench_<timestamp>.json` — toutes les traductions produites, pour
  relecture qualitative par un locuteur zarma (l'automatique seul ne suffit
  pas à juger la fluidité orale).
- `results/bench_<timestamp>_summary.md` — scores BLEU + quelques exemples.

## Fine-tuning M2M100 — sur un notebook cloud avec GPU, pas sur le Mac

Reproduit l'approche du papier Feriji (M2M100 fine-tuné, BLEU 30.06 annoncé
en fr→zarma), pour vérifier si un modèle spécialisé fait mieux que GLM
(BLEU 1.0 / 8.7 sans fine-tuning — voir `results/`). Le Mac local (M1, 8 Go
RAM, pas de GPU) s'est révélé beaucoup trop lent — même avec du fine-tuning
allégé (LoRA), un batch de 2 phrases prenait ~27 secondes, ce qui aurait
demandé plusieurs jours pour parcourir le jeu de données complet. Le script
`train_m2m100_lora.py` reste dans le dépôt pour référence mais n'est plus la
voie recommandée.

**À la place : `train_m2m100_cloud_gpu.py`**, un script autonome pensé pour
tourner dans n'importe quel notebook Jupyter avec GPU (Kaggle, Amazon
SageMaker, Google Colab...). Avec un vrai GPU, plus besoin de LoRA ni de
bricolage mémoire : fine-tuning complet du modèle, plus simple et plus
proche de la méthode d'origine du papier.

**Sur Kaggle** (gratuit, 30h GPU/semaine — nécessite un compte avec
téléphone vérifié, sinon les options GPU/Internet restent grisées) :

1. Nouveau notebook → *Settings* → *Accelerator* → **GPU P100** (ou T4 x2)
   → *Internet* → **On**.
2. *Add-ons* → *Secrets* → secret nommé `HF_TOKEN`.
3. Coller le contenu du script dans une ou plusieurs cellules, *Run All*.

**Sur Amazon SageMaker** (via les 300 $ de crédit compte AWS) :

1. Console AWS → chercher **SageMaker** → *Notebook* → *Notebook instances*
   → *Create notebook instance*.
2. Type d'instance : un type GPU — **ml.g4dn.xlarge** est le moins cher
   (GPU T4, largement suffisant).
3. Rôle IAM : laisser AWS en créer un automatiquement (option par défaut).
4. Une fois l'instance "InService", *Open Jupyter* (ou *JupyterLab*), créer
   un notebook avec le kernel `conda_pytorch_p310` (PyTorch pré-installé).
5. Dans une première cellule : `%env HF_TOKEN=hf_votre_token_ici`
6. Coller le contenu du script dans une cellule suivante, l'exécuter.
7. **Important** : une fois terminé, retourner dans la console SageMaker et
   cliquer **Stop** sur la notebook instance — elle facture à l'heure tant
   qu'elle tourne, même si le notebook est inactif ou l'onglet fermé.

Le script détecte automatiquement l'environnement (Kaggle vs autre) pour le
chemin de sortie des résultats. Il est autonome : télécharge et découpe le
corpus Feriji lui-même (même seed que `download_feriji.py`, donc même split
test — comparable au benchmark GLM), fine-tune M2M100 sur les deux sens
(fr→zarma et zarma→fr, le papier n'a évalué que le premier), puis calcule le
BLEU sur le même échantillon de 200 phrases que `bench_translation.py`, pour
une comparaison directe.

## Licence des données

Le dataset Feriji (`27Group/Feriji` sur Hugging Face) est publié en
**CC BY-NC 4.0** (non-commercial). L'application Zarma IA étant entièrement
gratuite et non-commerciale, cet usage est couvert par la licence. Toujours
créditer les auteurs (Keïta, Ibrahim, Alfari, Homan — ACL 2024) dans toute
publication ou usage dérivé.

## Coût estimé

Avec `glm-4.6` (≈0,60 $/1M tokens entrée, 2,20 $/1M sortie — tarifs z.ai à
revérifier avant tout budget précis) et 200 phrases × 2 directions
(glossaire + few-shot idéalement en cache), le coût attendu est de l'ordre
de quelques dizaines de centimes. Le script affiche le nombre de tokens
consommés et une estimation de coût en fin d'exécution.
