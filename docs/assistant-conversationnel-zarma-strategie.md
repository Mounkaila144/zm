# Assistant conversationnel vocal en zarma — Stratégie et faisabilité

> Analyse produite en réponse à une consultation sur l'extension de "Zarma IA"
> (calculateur vocal zarma existant) vers un assistant conversationnel vocal
> libre, s'appuyant sur un LLM cloud. Document de travail — à mettre à jour au
> fil des vérifications (licences, benchmarks de la Phase 0, etc.).

## Contexte

**Zarma IA** est une application mobile Flutter (Android) pour des locuteurs
zarma au Niger, en grande partie analphabètes. La version en production
reconnaît des nombres prononcés en zarma (vocabulaire fermé, grammaire
contrainte) et fait des calculs, avec une sortie vocale par concaténation de
mots pré-enregistrés. Elle fonctionne hors-ligne.

**Nouvel objectif** : un assistant conversationnel vocal en zarma — voix libre
en entrée, réponse pertinente via un LLM généraliste, voix en sortie —
acceptant une dépendance à Internet (contrairement au calculateur).

**Pipeline envisagé (à valider)** :

1. Voix zarma → texte zarma (ASR)
2. Texte zarma → texte français (traduction)
3. Texte français → réponse française (LLM)
4. Réponse française → texte zarma (traduction retour)
5. Texte zarma → voix zarma (TTS)

## Verdict

**Oui, c'est faisable** — mais pas exactement comme prévu. Deux choses
changent le plan de départ :

1. **Bonne nouvelle** : l'écosystème zarma est plus riche que prévu. Le dendi
   (`ddn`), le koyraboro senni (`ses`) et le koyra chiini (`khq`) — trois
   langues songhay très proches du zarma — ont des **modèles MMS-TTS déjà
   entraînés** (base de transfer learning idéale), et l'équipe Feriji a
   continué : il existe déjà un Whisper fine-tuné zarma, des TTS SpeechT5
   zarma expérimentaux, et des datasets POS/NER/correction orthographique.
2. **Mauvaise nouvelle** : le dataset Feriji est publié sous **CC BY-NC 4.0 —
   non commercial** — sur Hugging Face
   ([27Group/Feriji](https://huggingface.co/datasets/27Group/Feriji)). Si
   l'app est commerciale (Play Store payant, pub, etc.), il n'est pas
   possible d'entraîner dessus sans accord des auteurs. C'est le risque n°1,
   et il se résout par un e-mail, pas par de la technique.

## 1. Vérification des faits "à re-vérifier"

| Fait | Statut vérifié |
|---|---|
| MMS ASR supporte le zarma (`dje`) | ✅ Confirmé — ASR uniquement |
| MMS TTS/LID pour `dje` | ❌ Confirmé absent — **mais `ddn` (dendi), `ses` et `khq` ont ASR + TTS + LID** ([tableau MMS](https://dl.fbaipublicfiles.com/mms/misc/language_coverage_mms.html)) |
| Licence Feriji | ⚠️ **CC BY-NC 4.0** sur le dépôt HF officiel (le CC BY 4.0 de la page ACL ne couvre que le papier). Les datasets annexes du même groupe (`Zarma_POS`, `Zarma_NER`, `ZarmaLanguageRules`) sont en CC BY 4.0, `noisy_zarma` en CC BY-SA 4.0 |
| Corpus monolingue zarma séparé | Pas confirmé dans le papier, mais il existe `abdouaziz/bible_zarma` et `27Group/noisy_zarma` sur HF |
| "Rien d'autre n'existe en TTS zarma" | ❌ Faux : [Birma/zarma_tts_data](https://huggingface.co/datasets/Birma/zarma_tts_data) (322 échantillons, 4 locuteurs, ~1 h — trop petit mais preuve de faisabilité) + plusieurs `speecht5_finetuned_zarma` et des essais Orpheus-LoRA |

**Autre point licence à vérifier avant engagement** : les checkpoints MMS de
Meta (ASR et TTS) sont, à confirmer, publiés en **CC BY-NC 4.0** également —
même problème potentiel que Feriji pour un usage commercial. À vérifier sur
le dépôt fairseq/MMS. En revanche **M2M100 est sous licence MIT** (et NLLB
est CC BY-NC) — coup de chance : le meilleur modèle du papier Feriji est
aussi le seul librement commercialisable.

**Action immédiate (coût : un e-mail)** : contacter Mamadou K. Keita et
l'équipe Feriji/27Group. Ils sont nigériens, travaillent exactement sur ce
problème (leur compte HF `Mamadou2727` héberge un `whisper-medium-zarma` et
un `m2m100-correction-zarma`), et le papier appelle explicitement à résoudre
la TTS pour les analphabètes — cette app est leur cas d'usage rêvé. Une
licence commerciale négociée, voire une collaboration, est plausible.

## 2. Architecture : le pipeline en 5 étapes est le bon, avec deux amendements

Le pipeline 5 étapes est la bonne architecture de départ. Les alternatives
"tout-en-un" ne tiennent pas aujourd'hui :

- **LLM raisonnant nativement en zarma** : aucun LLM frontière n'a assez de
  zarma dans son pré-entraînement pour générer du zarma fiable (la langue est
  quasi absente du web). Les fine-tunes Gemma-270M zarma communautaires sont
  des expériences, pas des produits.
- **Speech-to-speech direct** : hors de portée sans des centaines d'heures de
  données.

Deux corrections :

### Amendement A — tester si le LLM peut absorber les étapes 2 et/ou 4

Avant d'entraîner quoi que ce soit, benchmarker un LLM frontière sur le split
test de Feriji, en lui donnant le glossaire (4 062 paires) + 10-20 exemples
en contexte. Hypothèse : le LLM sera correct en **zarma→français
(compréhension)** — cette direction tolère le bruit, le français cible est
sa langue forte — et médiocre en **français→zarma (génération)**. Si ça se
confirme, l'architecture optimale devient :

```
Voix → ASR zarma → [LLM : comprend le zarma directement + répond en français simple] → MT fr→zarma (M2M100) → TTS
```

soit **un seul appel LLM au lieu de MT + LLM + MT**, ce qui supprime un étage
de latence et un modèle à entraîner (la direction z→fr, justement celle que
Feriji n'a pas évaluée). Ce test coûte une journée et quelques euros.

### Amendement B — contraindre le style de la réponse LLM

Le maillon faible du pipeline, c'est la traduction fr→zarma d'un texte de LLM
typique (listes, subordonnées, vocabulaire abstrait). Imposer dans le prompt
système : phrases courtes (< 15 mots), vocabulaire concret du quotidien, pas
de markdown/listes/chiffres en notation, ton oral, 2-4 phrases max. Une
réponse écrite "pour être traduite puis dite à voix haute" traverse le
pipeline dix fois mieux. C'est gratuit et c'est le levier qualité n°1.

## 3. Les briques, concrètement

### ASR zarma

- **Point de départ** : MMS-1B (`dje`) en zero-shot, et le
  `Mamadou2727/whisper-medium-zarma-model1` communautaire. **S'attendre à un
  WER élevé** : MMS-`dje` a appris sur du Nouveau Testament *lu* ; la cible
  est de la parole conversationnelle sur micro de téléphone, avec
  code-switching français/haoussa.
- **Étape 1 (obligatoire)** : enregistrer 30-60 min d'audio test
  représentatif (questions réelles, téléphones réels, bruit de marché) et
  mesurer. Sans ce chiffre, tout le reste est spéculation.
- **Étape 2** : fine-tuning de MMS (adaptateurs par langue, recette
  documentée) ou de Whisper avec 20-50 h d'audio zarma transcrit. Coût GPU :
  dizaines d'euros en location (RTX 4090/A100 quelques heures à quelques
  jours).
- **Servir** : sur serveur (GPU modeste ou CPU quantifié) ; audio envoyé en
  Opus 16 kHz (~1 min ≈ 100 Ko, OK en 3G).

### Traduction fr↔zarma

- **fr→zarma** : refaire le fine-tuning **M2M100-418M** de Feriji (BLEU 30,
  MIT, recette dans le papier). Entraînement : quelques heures de GPU loué.
- **zarma→fr** : soit le LLM directement (Amendement A), soit le même
  M2M100 fine-tuné dans l'autre sens — à évaluer soi-même puisque le papier
  ne l'a pas fait ; le corpus le permet.
- **Servir** : M2M100-418M passe très bien sur **CPU avec CTranslate2
  quantifié int8** (< 200 ms/phrase) — pas de GPU serveur nécessaire.

### LLM (étape 3)

- API Claude : `claude-opus-5` par défaut ($5/$25 par MTok) ; pour maîtriser
  le coût à l'échelle, `claude-haiku-4-5` ($1/$5) suffit largement pour des
  réponses courtes grand public. Un tour de conversation ≈ 500 tokens in /
  150 out → moins de 0,5 centime par question même sur Opus. Mettre le
  prompt système + glossaire zarma derrière un point de **prompt caching**
  (~90 % d'économie sur ce préfixe).
- Le LLM sert aussi d'**usine à données** : augmentation du corpus
  parallèle, génération de phrases de couverture phonétique pour le TTS,
  post-édition — avec validation humaine systématique (c'est déjà la
  méthode Feriji).

### TTS zarma — le vrai chantier, mais plus court que prévu

Le chemin réaliste n'est **pas** un entraînement from scratch :

1. **Transfer learning depuis MMS-TTS dendi (`ddn`)** — VITS léger, langue
   sœur du zarma (sud-songhay, phonologie très proche), ou `ses`/`khq` en
   secours. Fine-tuner un VITS existant sur une langue apparentée demande
   typiquement **3 à 10 h d'un seul locuteur en studio**, pas des centaines.
   (Sous réserve de la licence MMS — sinon, VITS from scratch avec les
   mêmes données : ~2× plus de données/temps, mais faisable.)
2. Les `speecht5_finetuned_zarma` communautaires prouvent que ça "sort" déjà
   avec 1 h de données — la qualité produit exigera un corpus propre dédié.
3. Bonus : VITS est assez léger pour tourner **sur le téléphone** à terme
   (cohérent avec la philosophie hors-ligne du reste de l'app).

## 4. Stratégie de collecte de données (sans équipe de recherche)

Principe clé : **un seul chantier d'enregistrement nourrit deux briques**.
De l'audio lu + son texte = corpus TTS **et** corpus ASR aligné.

1. **Studio, 1 locuteur "voix de l'app"** (2-4 semaines) : sélectionner
   ~5 000 phrases zarma (Feriji + phrases propres au domaine : commerce,
   santé, agriculture, salutations) maximisant la couverture phonétique ;
   les faire lire par un locuteur natif à voix claire, payé, avec **contrat
   cédant les droits voix** (critique — c'est la voix permanente du
   produit). 10-15 h utiles. Coût : studio local + cachet, de l'ordre de
   quelques milliers d'euros au Niger. → TTS + 15 h d'ASR lu.
2. **Terrain, multi-locuteurs** (en continu) : via l'app existante (opt-in
   explicite, consentement **vocal** en zarma, petit dédommagement crédit
   téléphonique), collecte des questions parlées réelles. Transcription par
   2-3 locuteurs zarma lettrés recrutés localement (étudiants) avec un outil
   simple (Label Studio). Objectif : 20-50 h conversationnelles. C'est la
   donnée qui fera vraiment baisser le WER.
3. **Partenariat 27Group/Feriji** : licence + éval humaine + peut-être leurs
   données ASR non publiées.
4. **Boucle produit** : chaque requête de l'assistant (avec consentement)
   devient de la donnée d'entraînement future ; ajouter un bouton feedback
   vocal "👍/👎".

## 5. Phasage

### Phase 0 — Dé-risquage (3-4 semaines, coût ≈ 0)

Benchmarks : WER de MMS-`dje` et whisper-zarma sur audio test ; BLEU/éval
humaine de Claude sur Feriji-test dans les deux directions ; reproduction du
M2M100 fr→zarma. E-mail licence aux auteurs Feriji.

**Livrable** : un rapport chiffré go/no-go par brique + réponse licence.

### Phase 1 — Prototype texte bout-en-bout (1-2 mois)

Pipeline complet sans TTS neural : voix → texte zarma → réponse zarma
**affichée**, testée en interne avec des locuteurs lettrés (les testeurs
savent lire — pas les utilisateurs finaux). En parallèle, mode "magicien
d'Oz" avec 3-5 utilisateurs analphabètes : un humain lit la réponse à voix
haute, pour valider que la *compréhension* et le *contenu* fonctionnent
avant d'investir dans le TTS.

**Livrable** : démo + taux de réponses jugées correctes/compréhensibles sur
100 questions types.

### Phase 2 — Données + modèles (2-4 mois, en partie parallèle à la phase 1)

Enregistrements studio ; fine-tuning TTS (transfert `ddn`→zarma) ;
fine-tuning ASR ; collecte terrain lancée.

**Livrable** : TTS v1 écoutable (test MOS informel avec 10 locuteurs) + ASR
v1 avec WER mesuré < seuil fixé en phase 0.

### Phase 3 — Intégration + pilote (2-3 mois)

Intégration Flutter (streaming par phrase à chaque étage : l'utilisateur
entend le début de la réponse pendant que la fin se traduit — viser < 4-6 s
avant le premier mot parlé) ; pilote terrain 20-50 utilisateurs ; boucle de
correction.

**Livrable** : version bêta fermée sur le Play Store.

### Long terme

Élargissement des domaines, TTS/ASR embarqués hors-ligne (VITS + MMS
quantifiés sur mobile), éventuellement un modèle de génération zarma natif
par distillation quand la donnée sera 10× plus abondante.

## 6. Risques et pièges

1. **Licence Feriji NC** (et probablement MMS NC) — bloquant commercial, à
   résoudre en premier. Plan B : corpus Bible/Peace Corps aux licences
   propres + génération de données synthétiques validées par des locuteurs.
2. **Direction zarma→fr jamais évaluée** — ne pas supposer la symétrie ;
   mesurer en phase 0.
3. **Biais du corpus** : registre religieux (Bible, NT) + histoires ChatGPT
   traduites → le vocabulaire commercial/quotidien des utilisateurs (prix,
   unités, mobile money, agriculture) est sous-représenté. Prévoir
   d'augmenter le corpus dans le domaine cible, et réutiliser le moteur de
   nombres existant : les montants et calculs doivent passer par la
   grammaire déterministe (`zarma_numbers`), pas par la traduction
   neuronale (les nombres sont là où la MT hallucine le plus, et c'est le
   point fort déjà construit).
4. **Orthographe non standardisée** : Feriji, MMS, Peace Corps et le lexique
   du projet n'écrivent pas le zarma pareil (ny/ɲ, gn, tons, élisions). Il
   faut une **couche de normalisation orthographique** entre ASR→MT et
   MT→TTS — le `normalizer.py` du moteur de nombres existant est un bon
   point de départ à généraliser. Le dataset `noisy_zarma` (correction
   orthographique) est fait pour ça.
5. **Code-switching** : le zarma urbain réel est truffé de français et de
   haoussa. Un ASR mono-langue va souffrir ; collecte du terrain réel
   rapidement recommandée.
6. **Hallucinations LLM sur public vulnérable** : des utilisateurs
   analphabètes ne peuvent pas recouper une réponse écrite. Pour
   santé/finance/légal : réponses prudentes imposées par prompt, renvoi
   vers un humain, disclaimer **vocal** en zarma. Autant éthique que
   produit.
7. **Latence et coût data** : 5 étages séquentiels = 8-15 s si naïf.
   Streaming ASR + réponse LLM en streaming découpée par phrase + TTS
   phrase par phrase ramènent le premier son sous ~5 s. Audio compressé
   (Opus), jamais de WAV.
8. **Évaluation sans lecteurs** : les métriques finales sont orales —
   panels d'écoute ("la réponse était-elle compréhensible ? utile ?"), pas
   BLEU. Budget quelques sessions par itération.
9. **Voix et consentement** : les enregistrements de voix sont des données
   personnelles ; consentement vocal enregistré, stockage sécurisé, contrat
   clair avec la voix studio.

## 7. La voie la plus efficace, en une phrase

**Phase 0 de mesure (presque gratuite) → e-mail licence aux auteurs Feriji →
un seul chantier d'enregistrement studio qui nourrit TTS et ASR → transfer
learning systématique (MMS-`dje` pour l'ASR, M2M100-Feriji pour fr→zarma,
MMS-TTS-dendi pour la voix, LLM pour la compréhension zarma→fr) — rien n'est
entraîné from scratch, quatre modèles existants sont spécialisés avec 10-50 h
de données réellement productibles.**

C'est un projet à la portée d'un développeur indépendant motivé : la
première démo interne est à ~2 mois, une bêta crédible à ~6-9 mois, pour un
budget matériel/API de l'ordre de quelques milliers d'euros — le poste
principal étant l'humain (locuteurs, transcripteurs, panels), pas le GPU.

## Sources

- [Couverture langues MMS (ASR/TTS/LID)](https://dl.fbaipublicfiles.com/mms/misc/language_coverage_mms.html)
- [Feriji (ACL 2024, ACL Anthology)](https://aclanthology.org/2024.acl-srw.1/)
- [27Group/Feriji sur Hugging Face (licence CC BY-NC 4.0)](https://huggingface.co/datasets/27Group/Feriji)
- [Birma/zarma_tts_data](https://huggingface.co/datasets/Birma/zarma_tts_data)
- Recherches Hugging Face datasets/models "zarma" (POS, NER, correction
  orthographique, Whisper, SpeechT5, Orpheus-LoRA)

## Prochaine étape suggérée

Script de benchmark de la Phase 0 : évaluation de Claude sur le split test
Feriji dans les deux directions (fr→zarma et zarma→fr) + calcul du WER de
MMS-`dje` sur un échantillon d'audio réel.
