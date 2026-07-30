# Synthèse vocale neuronale zarma — décisions validées

Document préparatoire à la campagne d'enregistrement.

> **Statut (2026-07-30) : validé par le locuteur.**
> Décision 1 : le locuteur demande « la meilleure méthode » et se dit prêt à
> enregistrer autant qu'il faut → voie recommandée retenue : **Piper fine-tuné,
> entrée graphèmes** (plan B `mms-tts-ses` conservé).
> Décision 2 : **capture 48 kHz master** validée.
> Décision 3 : **structure 4 blocs** validée ; sources du bloc A confirmées :
> phrases du quotidien **et** proverbes/récits **et** textes zarma existants.

Toutes les affirmations sur les modèles ont été vérifiées le 2026-07-30 **dans
les fichiers des dépôts publiés**, pas dans leur documentation (leçon MMS-ASR).
Les commandes de vérification sont en annexe.

---

## Décision 1 — Modèle de base : Piper (VITS), fine-tuné, entrée graphèmes

### Ce que la vérification a éliminé

| Option | Verdict | Preuve (fichiers, pas docs) |
|---|---|---|
| **MMS-TTS zarma** | ❌ n'existe pas | `facebook/mms-tts-dje` est absent de HuggingFace (l'API renvoie l'erreur servie pour les dépôts inexistants, là où `mms-tts-eng` répond normalement). Même piège que MMS-ASR : la langue est annoncée, le checkpoint n'est pas publié. |
| **MMS-TTS songhaï voisin** | ⚠️ existe mais plafonné | `facebook/mms-tts-ses` (Koyraboro Senni) et `mms-tts-khq` (Koyra Chiini) existent — langues sœurs du zarma. Mais leur `config.json` dit `sampling_rate: 16000` : sortie 16 kHz, exactement le plafond de matité que le projet s'interdit. Gardé comme plan B (voir plus bas). |
| **XTTS-v2** | ❌ éliminé | Son `config.json` liste 17 langues, zarma absent. Licence CPML non commerciale (incompatible avec une application de transfert d'argent). ~900 Mo à 2 Go, irréaliste sur téléphone d'entrée de gamme ou VPS 4 vCPU. |

### Pourquoi Piper

- **Sortie 22,05 kHz** (qualité `medium`) : au-dessus du plancher exigé, voix
  brillante.
- **Entrée graphèmes sans phonétiseur** : `--data.phoneme_type text` est
  documenté et supporté dans l'entraînement officiel. espeak-ng ne connaît pas
  le zarma, mais on n'en a pas besoin : l'orthographe « au son » du projet
  (correspondance lettre/son régulière) est exactement le cas où l'entrée
  caractères fonctionne. C'est aussi l'approche des checkpoints MMS (vocabulaire
  = caractères), validée à l'échelle de 1100 langues.
- **Fine-tuning inter-langue officiellement recommandé** : « recommended since
  it will speed up training a lot, even if the checkpoint is from a different
  language ». Avec 30–60 min de parole, partir d'un checkpoint est la seule
  voie réaliste ; c'est aussi ce qu'a fait le travail publié sur l'efik
  (TTS mono-locuteur, langue africaine peu dotée, arXiv:2607.04515).
- **Checkpoints de départ vérifiés disponibles** :
  `datasets/rhasspy/piper-checkpoints` contient `fr/fr_FR/siwis/medium`
  (~846 Mo, voix féminine) et `fr/fr_FR/upmc/medium` (voix masculine et
  féminine). Le français est un bon départ : l'orthographe projet en est
  proche (« ou » = /u/, accents). Le choix exact du checkpoint (voix masculine
  ou féminine selon ta voix, siwis vs upmc) se fera par un petit essai
  comparatif au début de l'entraînement — pas une décision à prendre
  aujourd'hui.
- **Cible d'exécution réaliste** : Piper tourne en temps réel sur Raspberry
  Pi ; sur Android, l'export ONNX s'exécute via `onnxruntime` /
  `sherpa-onnx` (bindings Flutter existants — notre app mobile est Flutter).
  Modèle final ~60–80 Mo. Le VPS 4 vCPU est large.
- **Entraînable sur Colab T4** : le fine-tuning tient dans 8 Go de VRAM
  (rapports d'utilisateurs) ; la T4 en a 16.

### Plan B (coût nul, décidé d'avance)

Si le fine-tuning graphème de Piper déçoit à l'écoute, repli sur un
fine-tuning de `facebook/mms-tts-ses` (même famille de langues, architecture
VITS, entrée caractères) — en acceptant alors ses 16 kHz. Le corpus enregistré
en 48 kHz sert tel quel aux deux options (on sous-échantillonne, jamais
l'inverse). C'est le pendant exact des deux backends ASR de
`services/asr/local_server.py`.

---

## Décision 2 — Fréquence : capter à 48 kHz, entraîner à 22,05 kHz

Le brief fixe un minimum de 24 kHz. Proposition : **capter au-dessus du
minimum, à 48 kHz mono 16 bits**, et dériver les fréquences d'entraînement
hors ligne.

- 48 kHz est la fréquence **native** des chaînes audio Android : demander
  24 kHz force un rééchantillonnage embarqué de qualité inconnue, alors qu'un
  rééchantillonnage hors ligne (`sox`/`ffmpeg`, sur le Mac) est propre et
  reproductible.
- Le master 48 kHz est **archivé une fois pour toutes** : on en dérive
  22,05 kHz pour Piper aujourd'hui, 16 kHz si le plan B MMS sert un jour, et
  n'importe quelle fréquence pour un futur modèle. C'est l'assurance contre
  « réenregistrer 60 minutes ».
- La règle du brief reste entière : **aucune séance avant d'avoir mesuré, sur
  un fichier réellement produit par l'application modifiée**, la fréquence, le
  nombre de canaux et la profondeur réels (`wav_analysis.dart` valide
  aujourd'hui 16 kHz **en dur**, lignes 71–74 : deux endroits à changer, pas
  un). Si le téléphone de la campagne ne fournit pas un vrai 48 kHz, repli
  mesuré sur 44,1 kHz, jamais en dessous de 24.

---

## Décision 3 — Structure du script d'enregistrement

Volume : **500 à 700 énoncés** (~40–55 min effectives), en plusieurs séances,
mêmes conditions (pièce, micro, distance), débit naturel — jamais dicté.

Quatre blocs. Les proportions sont indicatives et se discutent :

### Bloc A — Texte zarma ordinaire (~350 phrases, le cœur du corpus)
Phrases du quotidien, proverbes, mini-récits, salutations, phrases sur le
marché, la famille, le temps qu'il fait. Longueurs variées (2 à 12 mots).
**Un quart de questions** — l'intonation montante ne s'apprend que si elle est
dans le corpus — et quelques impératifs/exclamations.
C'est ce bloc qui donne la couverture phonétique que le corpus ASR n'a pas
(45 mots distincts). **Sources à choisir avec toi** : ce que tu dirais
naturellement, pas des traductions du français.

### Bloc B — Vocabulaire applicatif (~150 phrases)
Ce que l'application dira réellement, pour que ces énoncés soient les mieux
rendus :
- nombres et montants générés par `zarma_numbers.generate()` (**jamais écrits
  à la main**), isolés et en phrase (« le résultat est… », « tu envoies… ») ;
- opérateurs, formes longues (`kanga itonton`…) et courtes, cf.
  `corpus-a-enregistrer.md` ;
- messages système existants (`confirm`, `repeat`, `cannot_answer`…) et
  messages de l'assistant de transfert — formulations zarma à écrire par toi ;
- questions de confirmation (« veux-tu envoyer X à Y ? »).

### Bloc C — Noms de personnes (~100 énoncés)
La raison d'être du TTS neuronal. Prénoms et noms réellement portés au Niger
(zarma, haoussa, arabes, peuls, français), seuls et dans des phrases
porteuses de type transfert (« … envoie 5 000 francs à Aïssa »). C'est toi
qui établis la liste — elle doit refléter les bénéficiaires réels de
l'application.

### Bloc D — Complément de couverture (~50 phrases, généré en dernier)
Après rédaction des blocs A–C, un script comptera les caractères, digrammes et
structures syllabiques couverts et signalera les trous ; des phrases ciblées
(écrites par toi) les combleront.

### Convention orthographique (condition de réussite)
Le zarma s'écrit « au son », mais le modèle exige que **le même son s'écrive
toujours pareil**. Avant la rédaction : fixer par écrit la liste fermée des
caractères et digrammes (alignée sur `lexicon.yaml` : « ou » = /u/, etc.), et
valider chaque phrase du script contre cette liste. Le document servira ensuite
tel quel au module texte→modèle.

---

## Après validation (ordre, pour mémoire)

1. Modifier `entrainement/corpus_recorder` : fréquence (capture **et**
   validation `wav_analysis.dart`), seuils qualité recalibrés TTS (plus
   stricts que l'ASR : saturation zéro, plancher de bruit, souffle/plosives),
   affichage de phrases longues, reprise de séance — sans casser le mode ASR.
2. Vérifier sur fichier produit réel, puis séance pilote de 20 phrases →
   écoute critique avant la campagne complète.
3. Campagne (plusieurs séances) avec contrôle qualité au fil de l'eau.
4. Pipeline Colab T4 (préparation des données sur le M1, entraînement sur
   Colab, checkpoints sauvés sur Drive à intervalle court — reprise après
   coupure).
5. Évaluation : écoute par toi, A/B contre la concaténation sur les mêmes
   phrases — l'étalon à battre.
6. Intégration : la concaténation reste le chemin par défaut jusqu'à preuve
   du contraire, repli automatique comme côté ASR.

---

## Annexe — commandes de vérification (rejouables)

```bash
# MMS-TTS : dje absent, eng/ses/khq présents (200 = existe, 401 = inexistant)
for l in dje eng ses khq; do
  printf "mms-tts-%s : " "$l"
  curl -s -o /dev/null -w "%{http_code}\n" \
    https://huggingface.co/api/models/facebook/mms-tts-$l
done

# MMS-TTS ses : sortie 16 kHz, entrée caractères
curl -sL https://huggingface.co/facebook/mms-tts-ses/raw/main/config.json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['sampling_rate'])"

# XTTS-v2 : 17 langues, pas de zarma
curl -sL https://huggingface.co/coqui/XTTS-v2/raw/main/config.json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['languages'])"

# Checkpoints Piper français disponibles pour le fine-tuning
curl -s "https://huggingface.co/api/datasets/rhasspy/piper-checkpoints/tree/main/fr/fr_FR/siwis/medium"
```

Support graphèmes et recommandation de fine-tuning : `docs/TRAINING.md` du
dépôt officiel `OHF-Voice/piper1-gpl`.
