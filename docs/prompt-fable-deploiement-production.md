# Prompt — mise en production de l'ASR zarma au moindre coût

> À copier tel quel dans une conversation avec Fable 5. Autonome : ne suppose
> aucun accès au dépôt.

---

## Qui je suis, ce que je construis

Je développe une **calculatrice vocale en zarma** (langue du Niger, ~4 M de
locuteurs) destinée à des **commerçants qui ne savent ni lire ni écrire**.
L'utilisateur énonce une opération à voix haute (« vingt-trois plus quinze ») ;
l'application reconnaît l'opération, calcule, affiche **et prononce** le
résultat. Tout ce que l'application « dit » doit être audible : l'écran seul
n'apprend rien à la cible.

Le produit fonctionne aujourd'hui de bout en bout en développement. Je veux le
**mettre en production pour ~200 utilisateurs**, avec un budget serré (contexte
ouest-africain, projet non financé par un grand acteur).

**Ma question : quelle est l'architecture de production la moins coûteuse et la
plus adaptée à ce cas ?**

---

## Architecture actuelle

| Composant | Technologie |
|---|---|
| Mobile | Flutter/Dart (Android), Riverpod, dio |
| API | FastAPI (Python 3.11), PostgreSQL, nginx |
| Moteur linguistique | Paquet Python maison, déterministe, sans ML |
| ASR | **Meta Omnilingual `omniASR_CTC_300M_v2`** (326 M paramètres, bfloat16, Apache 2.0) |

Le flux : le téléphone enregistre un WAV PCM16 mono 16 kHz → `POST /recognize`
sur l'API → l'API appelle un service ASR via une interface abstraite
(`SpeechRecognizer`, échangeable **par configuration seulement**) → le service
ASR produit les logits CTC et les décode.

### Le décodage est contraint à une grammaire

Point important pour comprendre les coûts : je ne fais **pas** d'`argmax` trame
par trame. Les logits CTC alimentent une **recherche en faisceau restreinte à un
automate fini** décrivant exactement la langue des nombres zarma (ou des
expressions arithmétiques). C'est indispensable : en décodage libre, ce modèle
transcrit du zarma en caractères chinois. La contrainte est ce qui ramène la
sortie dans la langue.

- Implémentation : **numpy pur, mono-fil**, ~500 lignes, aucune dépendance torch.
- Automate « expressions » : 8 870 états, 39 mots. « nombres » : 4 435 états, 35 mots.
- Largeur de faisceau : 256.
- Garantie recherchée : toute sortie appartient à la grammaire, **ou le système
  s'abstient**. Jamais de nombre inventé — c'est une exigence produit absolue,
  un résultat faux étant indétectable par un utilisateur qui ne lit pas.

---

## Le problème concret qui m'amène

En essai sur téléphone réel, l'application affichait **« Le traitement a pris
trop de temps »** : un énoncé de 10 secondes demandait **35 secondes** de calcul,
au-delà du délai de 30 s de l'API.

J'ai diagnostiqué et corrigé la cause principale (détail plus bas), mais la
question de fond reste entière : **sur quelle infrastructure faire tourner ce
modèle en production, au coût le plus bas ?**

---

## Mesures déjà faites (à ne pas refaire, mais à challenger)

Machine de mesure : **MacBook Apple M1, 8 cœurs**. Toutes les mesures portent sur
le même modèle et les mêmes fichiers audio.

### 1. Le piège bfloat16 sur CPU — cause du dépassement de délai

Le modèle est livré en **bfloat16**. Un CPU sans instruction bfloat16 l'émule
opération par opération :

| Placement | 10 s d'audio (inférence seule) |
|---|---|
| `cpu` / bfloat16 *(état initial)* | **32,7 s** |
| `cpu` / float32 | 1,5 s |
| `mps` / float32 | 0,76 s |
| `mps` / float16 | 0,63 s |

**Sorties identiques** dans tous les cas : 12/12 transcriptions inchangées sur
mes enregistrements réels. Seul le format de calcul change. Corrigé → **35 s
ramenés à 2,2 s** de bout en bout.

### 2. Répartition du temps (avant correction)

| Audio | Modèle | Décodage contraint | Part du décodage |
|---|---|---|---|
| 3 s | 7,85 s | 0,29 s | 4 % |
| 10 s | 32,7 s | 1,56 s | 5 % |

Après correction du format, les deux postes pèsent **du même ordre**.

### 3. Simulation VPS — CPU seul, float32, 2 fils

| Audio | Modèle | Décodage | Total | ×temps-réel |
|---|---|---|---|---|
| 3,0 s | 0,77 s | 0,28 s | **1,05 s** | ×0,35 |
| 3,7 s | 0,65 s | 1,18 s | **1,83 s** | ×0,49 |
| 10,0 s | 2,03 s | 1,81 s | **3,84 s** | ×0,38 |

**Mémoire : 1,9 Go** de RSS pour le processus ASR (modèle float32 = 1,3 Go de
poids + activations + runtime).

### 4. Quantification int8 dynamique — **écartée**

`torch.quantization.quantize_dynamic` sur les couches `Linear` :
**4,07 s contre 2,25 s** en float32, soit *plus lent*, pour 10/10 transcriptions
identiques. Sur cette architecture et cet ARM, c'est une perte. (Testé, pas
supposé — mais une quantification **statique** ou via un autre runtime n'a pas
été essayée.)

### 5. Autres chiffres

- Chargement du modèle : ~3 s. Échauffement première inférence : ~0,5 s.
- De bout en bout via l'API, avec le vrai modèle : **2,2 s** pour 3,7 s d'audio.

---

## ⚠️ Ce qui n'est PAS vérifié

Ne bâtis pas de raisonnement sur ces points sans les faire confirmer :

1. **Le passage de 2 à 4 fils n'a montré aucun gain net** dans une mesure
   préliminaire (3,84 s vs 3,89 s sur 10 s d'audio) — mais cette mesure incluait
   l'échauffement et était bruitée. **La vérification propre n'a pas été faite.**
   Si c'est confirmé, la conséquence est majeure : il vaudrait mieux **2 workers
   à 2 fils** qu'1 worker à 4 fils.
2. **Le rapport de vitesse entre un vCPU de VPS et un cœur M1** est une
   estimation (×1,5 à ×2,5 plus lent), jamais mesurée.
3. Le décodage contraint est **mono-fil numpy** : il ne profitera d'aucun cœur
   supplémentaire au sein d'une même requête.

---

## Contraintes non négociables

- **Jamais de résultat inventé.** Sous le seuil de confiance, le système
  s'abstient et demande de répéter. Toute solution qui « devine » est exclue.
- **Le décodage contraint doit rester** : sans lui la sortie n'est pas du zarma.
  Une API ASR tierce en boîte noire (qui ne rend que du texte, pas les logits)
  est donc **inutilisable** — il me faut les logits CTC.
- **La restitution vocale est déjà hors ligne** : banque de 40 mots enregistrés
  embarquée dans l'APK, assemblés sur le téléphone. Ce point est réglé.
- HTTPS obligatoire, aucun secret embarqué dans le mobile.
- L'ASR doit rester remplaçable **par configuration** (interface abstraite).
- Python 3.11, modèle sous licence Apache 2.0.

## Ce dont je dispose

- Un **VPS : 4 vCPU, 8 Go de RAM** (déjà payé).
- Pas de GPU. Pas de budget cloud significatif.
- ~200 utilisateurs attendus, usage concentré aux heures de marché.
- Volumétrie estimée : entre 5 et 20 calculs par personne et par jour — soit
  **1 000 à 4 000 requêtes/jour**, avec des pointes à ~3× la moyenne.

---

## Une piste que j'ai identifiée mais pas implémentée

Mes enregistrements de test durent **10 secondes pour ~3 secondes de parole
utile** : l'utilisateur appuie sur « démarrer », parle, puis met un moment à
appuyer sur « arrêter ». Le modèle paie les 10 secondes.

Un découpage des silences côté serveur (VAD) avant l'inférence diviserait la
charge par **3 à 4**. J'ai déjà du code de détourage par seuil relatif au pic
dans mon outillage. **Est-ce le bon levier, et suffit-il ?**

---

## Ce que j'attends de toi

1. **Une recommandation d'architecture de production chiffrée**, adaptée à 200
   utilisateurs et au budget le plus bas. VPS CPU seul ? GPU loué à l'heure ?
   Serverless GPU (Modal, RunPod…) ? Hybride ? Tranche la question et justifie.
2. **Une réponse nette : mes 4 vCPU / 8 Go suffisent-ils ?** Avec le raisonnement
   de capacité (files d'attente, concurrence, pointes), pas seulement un avis.
3. **Les optimisations d'inférence CPU que je n'ai pas essayées** et leur gain
   réaliste sur cette architecture (modèle CTC de type wav2vec/conformer,
   326 M paramètres) : export ONNX Runtime, OpenVINO, CTranslate2,
   `torch.compile`, quantification statique, mise en lots, découpage en
   fenêtres… Lesquelles valent l'effort, lesquelles sont des impasses, et
   pourquoi. **Dis-moi comment vérifier**, ne te contente pas d'affirmer.
4. **Le coût du décodage contraint** : il pèse désormais autant que le modèle et
   il est mono-fil en numpy. Faut-il l'optimiser, le réécrire, réduire le
   faisceau ? Rappel : sa correction est une garantie produit, je ne peux pas
   l'affaiblir sans mesure.
5. **Ce qu'il manque à mon service ASR pour être production-ready** : il tourne
   aujourd'hui en `ThreadingHTTPServer` mono-processus, sans authentification ni
   file d'attente bornée. Quelle est la mise en production minimale et robuste ?
6. **Les risques que je n'ai pas vus.** Démarrage à froid, saturation, montée en
   charge, coupure réseau côté terrain, coût caché.

**Sois direct et quantitatif.** Si une piste est mauvaise, dis-le et explique
pourquoi. Si une réponse dépend d'une mesure que je n'ai pas faite, dis-moi
laquelle faire et comment l'interpréter — je préfère une inconnue nommée à une
certitude inventée.
