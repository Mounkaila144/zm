# Optimisation de la latence ASR sur CPU — diagnostic, mesures, décisions

Contexte : VPS Ubuntu 24.04, 4 vCPU AMD EPYC (famille 23, AVX2, **ni AVX-512 ni
VNNI**), 8 Go de RAM, aucun GPU. Modèle `omniASR_CTC_300M_v2` en float32,
décodage contraint à la grammaire des expressions zarma.

Objectif : sur des énoncés réels de 5 à 8 s, p50 ≤ 3 s et p95 ≤ 5 s, sans
dégrader la reconnaissance.

**Résultat : p50 2 571 ms, p95 3 990 ms, maximum 4 717 ms** (55 requêtes par le
service HTTP réel), avec un texte reconnu **identique** sur l'ensemble du corpus.

---

## 1. Le benchmark qui a servi jusqu'ici était trompeur

Le gain de 42 % annoncé après le passage du faisceau de 256 à 64 a été mesuré
sur **8 secondes de silence numérique**. Les journaux de production le montrent
sans ambiguïté :

| moment | audio | décodage |
|---|---|---|
| avant (parole réelle) | 4,6 – 10,0 s | 764 – 6 820 ms |
| après (silence) | 8,0 s | 220 – 408 ms |

Sur du silence, le faisceau ne contient presque aucune hypothèse vivante et le
rescoring exact ne s'exécute quasiment jamais : on mesurait le chemin qui n'est
jamais emprunté en production. La comparaison ne dit donc rien du gain réel —
lequel s'est avéré exister, mais pour d'autres raisons et dans d'autres
proportions.

**Correctif** : `scripts/bench/build_perf_corpus.py` construit un corpus de
15 énoncés à partir des 40 enregistrements de mots zarma réels de
`apps/mobile/assets/voice/words/`, concaténés le long de chemins **valides de la
grammaire** (tirés de l'automate, donc jamais hors grammaire), plus les cas
dégradés : bruit à 15 dB de RSB, silences de bord, parole faible, silence total,
bruit seul.

---

## 2. Profilage : où passe réellement le temps

`scripts/bench/profile_asr.py` ventile chaque étape. Sur la configuration
initialement déployée (4 fils, faisceau 64) :

| étape | part |
|---|---|
| inférence PyTorch | **88 %** |
| décodage (log-softmax + faisceau + rescoring) | 12 % |
| lecture WAV, préparation du lot, sérialisation, HTTP interne | < 1 % |

Deux faits structurent tout le reste :

- **V = 10 288, 50 trames/s**, et le coût du modèle est **linéaire en trames**
  (9,5 / 9,9 / 10,4 ms par trame à 155, 252 et 375 trames). Réduire les trames
  réduit le temps proportionnellement.
- À l'intérieur du décodage, le **rescoring CTC exact** dominait (1 424 ms sur
  `long_2`, contre 296 ms pour la recherche en faisceau).

---

## 3. Ce qui a été changé

### 3.1 Décodeur — 6× plus rapide, **bit à bit identique**

Trois changements, tous vérifiés par égalité exacte des scores, pas par
tolérance (`scripts/bench/decoder_equivalence.py`, 15 énoncés réels ;
`services/asr/tests/test_perf_invariants.py`, entrées aléatoires) :

1. **`np.logaddexp` scalaire → arithmétique Python.** Mesuré à 976 ns contre
   204 ns, soit 4,8×. L'opération est appelée ~150 000 fois par décodage. La
   séquence de branches reproduit `npy_logaddexp` et s'appuie sur les mêmes
   fonctions libm : sortie identique, vérifiée sur 60 000 paires dont les
   infinis.
2. **Forward CTC vectorisé sur l'axe des étiquettes étendues.** La boucle Python
   interne faisait 37 000 itérations par hypothèse sur un énoncé long, pour
   chaque hypothèse acceptante du faisceau.
3. **Restriction au sous-vocabulaire de la grammaire.** L'automate n'emploie que
   **21 ids distincts sur 10 288**. Le décodage travaille désormais sur une
   matrice `(T, 22)`. Le log-softmax se normalise toujours sur les 10 288
   colonnes — c'est sa définition — mais par blocs de 16 trames, de sorte que
   les temporaires tiennent dans le cache L3 : la mémoire de pointe du décodage
   passe de ~99 Mo à quelques centaines de Ko et cesse de dépendre de la durée.

### 3.2 Élagage des silences avant inférence (`services/asr/app/vad.py`)

Le coût étant linéaire en trames, une seconde de silence en tête coûte ~500 ms
pour une information nulle. Deux comportements :

- **silence total détecté** → le modèle n'est pas appelé du tout (8 s de silence
  passent de 6 868 ms à 0 ms) ;
- **bords muets élagués** avec une marge de 300 ms, seuil **relatif au bruit
  propre de la prise** — `silences_bord` passe de 402 à 280 trames.

Garde-fous testés : une prise faible n'est jamais déclarée muette (jusqu'à une
amplitude de 0,005), l'intérieur d'un énoncé n'est jamais rogné, et un énoncé
plus court que la marge est laissé intact.

### 3.3 Deux fils de calcul au lieu de quatre

Contre-intuitif, mais c'est le changement qui a le plus d'effet sur la **queue**
de distribution. Trois variantes alternées énoncé par énoncé
(`scripts/bench/latency_report.py`) :

| variante | p50 | p95 | max |
|---|---|---|---|
| 4 fils (déployé) | 3 716 ms | 9 541 ms | 13 892 ms |
| **2 fils** | **2 759 ms** | **3 531 ms** | **4 010 ms** |

Cohérent avec le débit GEMM mesuré séparément : 91 GFLOP/s à 1 fil, 187 à 2,
puis 105 à 3 et 164 à 4, très instable. Au-delà de deux fils, ils se disputent
les 8 Mo de cache L3 et la bande passante mémoire ; le service consommait 237 %
de CPU pour 4 fils, soit 59 % d'efficacité parallèle.

`--threads 2` est passé **en plus** de `OMP_NUM_THREADS=2` : la variable
d'environnement ne dimensionne que le pool OpenMP, alors que
`torch.set_num_threads` gouverne aussi les noyaux qui ne passent pas par OpenMP.

### 3.4 Libération du CPU de la machine

La cause principale de dispersion n'était pas dans le code : **le VPS
n'était pas dédié à Zarma**. Il hébergeait un panel IPTV (xtreamcodes : nginx,
php-fpm, MariaDB, Apache), un démon PM2, Docker et plusieurs services
applicatifs. La file des processus exécutables montait à 3–10 sur 4 vCPU
pendant une inférence, sans aucun vol d'hyperviseur (`st = 0`).

Consommation CPU cumulée sur 5 jours d'uptime, au moment du diagnostic :

| unité | CPU cumulé |
|---|---|
| pm2-root | 882 min |
| rsyslog | 562 min |
| systemd-journald | 300 min |
| containerd + docker | 229 min |
| aflaam + pocketbase + MYTVLYNX | 220 min |
| mariadb | 41 min |
| **php8.3-fpm + apache2** | **2,6 min** |
| zarma-asr | 4 min |

À noter pour la suite : Apache et PHP-FPM, les deux services les plus
naturellement suspects, ne consommaient **rien**. Les arrêter n'aurait rien
donné. C'est PM2, rsyslog et la pile Docker qui pesaient.

Services arrêtés et désactivés au démarrage : `apache2`, `php8.3-fpm`,
`mariadb`, `rsyslog`, `pm2-root`, `docker`, `containerd`, `aflaam`,
`pocketbase`, `MYTVLYNX`, plus la pile xtreamcodes (hors systemd, neutralisée
dans `/etc/crontab` et `/etc/init.d/`).

Résultat : charge moyenne de 2,21 à 0,80, machine à ~90 % inactive au repos.

---

## 4. Avant / après

Médianes par énoncé, variantes alternées dans un même processus
(`scripts/bench/latency_report.py`, 3 passes) :

| énoncé | audio | gardé | réf modèle | réf décod. | réf total | opt modèle | opt décod. | opt total | gain | texte identique |
|---|---|---|---|---|---|---|---|---|---|---|
| court_1 | 2,54 s | 2,54 s | 1 239 | 116 | 1 354 | 1 168 | 32 | 1 200 | 1,13× | oui |
| court_2 | 3,11 s | 3,10 s | 1 574 | 121 | 1 679 | 985 | 36 | 1 022 | 1,64× | oui |
| court_3 | 3,25 s | 3,24 s | 1 528 | 169 | 1 697 | 1 272 | 46 | 1 319 | 1,29× | oui |
| moyen_1 | 4,33 s | 4,32 s | 3 409 | 513 | 3 926 | 1 738 | 79 | 1 802 | 2,18× | oui |
| moyen_2 | 5,00 s | 5,00 s | 1 622 | 757 | 2 379 | 2 079 | 88 | 2 213 | 1,08× | oui |
| moyen_3 | 5,05 s | 5,04 s | 4 153 | 502 | 4 672 | 2 328 | 106 | 2 493 | 1,87× | oui |
| moyen_4 | 6,32 s | 6,30 s | 8 570 | 950 | 9 488 | 2 900 | 167 | 3 068 | 3,09× | oui |
| long_1 | 6,54 s | 6,54 s | 3 403 | 597 | 4 000 | 2 632 | 138 | 2 770 | 1,44× | oui |
| long_2 | 7,51 s | 7,50 s | 5 350 | 1 310 | 6 518 | 2 670 | 162 | 2 867 | 2,27× | oui |
| long_3 | 7,55 s | 7,54 s | 4 879 | 1 626 | 7 235 | 3 040 | 171 | 3 278 | 2,21× | oui |
| bruit_15db | 5,05 s | 5,04 s | 2 319 | 368 | 2 713 | 2 911 | 105 | 3 027 | 0,90× | oui |
| silences_bord | 8,05 s | **5,62 s** | 5 252 | 813 | 6 026 | 3 012 | 94 | 3 189 | 1,89× | oui |
| parole_faible | 5,05 s | 5,04 s | 6 721 | 485 | 7 224 | 2 590 | 109 | 2 666 | 2,71× | oui |
| silence_total | 8,00 s | — | 6 437 | 272 | 6 868 | **0** | **0** | **0** | — | oui |
| bruit_seul | 6,00 s | 6,00 s | 3 951 | 198 | 4 115 | 3 073 | 90 | 3 163 | 1,30× | oui |

RSS maximal du processus : **2 303 Mo** (inchangé ; le modèle domine).

Mesure finale **par le service HTTP réel**, machine libérée, 55 requêtes :

| | p50 | p95 | max |
|---|---|---|---|
| énoncés 5–8 s | **2 571 ms** | **3 990 ms** | 4 717 ms |
| tous énoncés | 2 414 ms | 3 988 ms | 4 717 ms |

---

## 5. Pistes évaluées et écartées (pour l'instant)

### Quantification dynamique INT8 — **prometteuse, non déployée**

`scripts/bench/try_int8.py`. `fairseq2.nn.Linear` n'hérite pas de
`torch.nn.Linear`, donc `quantize_dynamic` ne voit rien et ne fait rien si on
l'appelle naïvement. Le script substitue d'abord les 146 couches (substitution
vérifiée **bit à bit** sur les logits avant de quantifier quoi que ce soit),
puis quantifie.

- gain : **1,32×** sur l'inférence (modeste, ce CPU n'a pas VNNI) ;
- fidélité : **14/15 textes identiques**. La seule divergence est en faveur
  d'INT8 — sur `long_2`, float32 se trompait (`waygou`) et INT8 donnait la
  bonne réponse (`wayiddu`).

**Non déployée** : 15 énoncés ne suffisent pas à conclure sur une divergence
unique, fût-elle favorable. À reprendre sur un jeu étiqueté plus large avant
mise en production.

### Non retenues

- **torch.compile / TorchScript** : non évalués — le gain attendu sur un
  encodeur transformeur CPU est de l'ordre de 10–20 %, à comparer au coût de
  compilation au démarrage et au risque de divergence numérique. À reconsidérer
  seulement si les cibles se durcissent.
- **ONNX Runtime / OpenVINO** : coût d'export et de validation élevé pour un
  modèle qui utilise des membres privés du pipeline `omnilingual_asr` ; le
  chemin INT8 est plus court et déjà instrumenté.
- **Réduction du faisceau sous 64** : le décodage ne pèse plus que 3–5 % du
  temps. Il n'y a plus rien à y gagner, et réduire le faisceau est le seul de
  ces leviers qui touche directement la qualité.

---

## 6. Risques restants

1. **Co-location.** Les services arrêtés peuvent être redémarrés ; la latence se
   dégradera d'autant. `CPUWeight=1000` et `Nice=-5` sur `zarma-asr` limitent
   l'effet, mais l'effet mesuré était dans le bruit (médiane 4 894 → 4 220 ms
   sur 12 requêtes par variante) : c'est retenu parce que le risque est nul, pas
   parce que le gain est démontré. Le correctif franc reste l'isolation de Zarma
   sur sa propre machine, ou un `CPUQuota` sur les unités co-hébergées.
2. **Corpus synthétique.** Les énoncés sont des mots réels concaténés : il leur
   manque la coarticulation d'une élocution continue. Les temps de calcul sont
   représentatifs (l'inférence ne dépend que du nombre de trames), la
   reconnaissance l'est moins. Un corpus d'enregistrements continus reste
   souhaitable pour juger de la qualité.
3. **Seuil de silence.** `_SILENCE_PEAK_DBFS = -65` est volontairement très bas.
   Un micro exceptionnellement bruyant pourrait faire passer un vrai silence au
   modèle : le coût est alors le temps de calcul habituel, puis une abstention
   par le décodeur — jamais un nombre inventé.
4. **Redis** n'est plus démarré. Zarma ne l'utilise pas (`Limiter` sans
   `storage_uri` : stockage en mémoire, vérifié), mais un autre projet de la
   machine en dépendait peut-être.

---

## 7. Commandes

```bash
# Corpus de performance (à refaire si la grammaire change)
asrenv/bin/python scripts/bench/build_perf_corpus.py

# Profilage par étapes + capture des logits pour le travail hors ligne
asrenv/bin/python scripts/bench/profile_asr.py --repeats 3 \
    --dump-logits /tmp/logits --out /tmp/profil.json

# Équivalence bit à bit du décodeur contre une référence
asrenv/bin/python scripts/bench/decoder_equivalence.py \
    --lexicon /tmp/lexicon.json --logits /tmp/logits --reference /chemin/decoding.py

# Tableau avant/après, variantes alternées
asrenv/bin/python scripts/bench/latency_report.py \
    --reference-decoder /chemin/decoding.py --repeats 3

# Quantification INT8 (évaluation)
asrenv/bin/python scripts/bench/try_int8.py --threads 2

# Non-régression (sans modèle ni GPU)
.venv/bin/python -m pytest services/asr/tests -q
```

## 8. Retour arrière

```bash
# 1. Code (sauvegarde horodatée créée avant déploiement)
cd /opt/zarma && git checkout -- services/asr/app/decoding.py \
    services/asr/local_server.py services/asr/tests/conftest.py \
    infrastructure/systemd/zarma-asr.service
rm -f services/asr/app/vad.py

# 2. Unité systemd d'origine
sudo cp /opt/zarma/.rollback-<horodatage>/zarma-asr.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl restart zarma-asr

# 3. Redémarrer les services arrêtés
for s in apache2 php8.3-fpm mariadb rsyslog pm2-root docker containerd \
         aflaam pocketbase MYTVLYNX; do
  sudo systemctl enable --now $s
done

# 4. Panel xtreamcodes
sudo sed -i 's/^#DESACTIVE-ZARMA //' /etc/crontab
sudo chmod +x /etc/init.d/xtreamcodes
sudo /home/xtreamcodes/iptv_xtream_codes/start_services.sh
```

Chaque optimisation est indépendante : on peut revenir sur les threads sans
toucher au décodeur, ou désactiver la VAD (`analyse_silence` dans
`local_server.py`) sans rien changer d'autre.
