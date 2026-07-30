# Zarma Voice Access — Corpus vocal et spécification du MVP

## 1. Objectif

Créer une couche vocale en zarma, intégrable dans une application Mobile Money, afin qu’une personne ne sachant ni lire ni écrire puisse :

- consulter son solde ;
- transférer de l’argent à un bénéficiaire enregistré ;
- acheter du crédit ou un forfait ;
- recharger un compteur enregistré ;
- consulter et payer une facture ;
- écouter chaque étape ;
- corriger, répéter ou annuler oralement.

Le système utilise un **vocabulaire fermé et contrôlé**. Il ne doit jamais deviner un montant, un bénéficiaire ou une intention.

---

## 2. État actuel

Le projet possède déjà :

- un modèle entraîné avec plus de huit locuteurs ;
- la reconnaissance des chiffres, nombres et montants en zarma ;
- un algorithme déterministe de conversion zarma vers valeur numérique ;
- une couverture allant approximativement jusqu’à un million.

L’algorithme numérique existant doit être conservé et intégré au pipeline final.

---

## 3. Deux modes de l’application

### 3.1 Configuration accompagnée

Réalisée par un agent ou un proche de confiance :

- création du compte ;
- vérification d’identité ;
- activation du mode vocal zarma ;
- configuration de la biométrie ou du PIN ;
- enregistrement des bénéficiaires ;
- enregistrement des compteurs d’eau et d’électricité ;
- enregistrement des numéros à recharger ;
- choix de la vitesse de la voix ;
- formation de l’utilisateur.

Le PIN ne doit jamais être prononcé ni enregistré.

### 3.2 Utilisation quotidienne

L’utilisateur dispose principalement de :

- un grand bouton microphone ;
- un bouton Répéter ;
- un bouton Annuler ;
- des réponses vocales ;
- des vibrations et sons simples.

---

## 4. Intentions du MVP

### Intentions principales

```text
CHECK_BALANCE
SEND_MONEY
BUY_AIRTIME
BUY_DATA_BUNDLE
RECHARGE_ELECTRICITY
CHECK_ELECTRICITY_BILL
PAY_ELECTRICITY_BILL
CHECK_WATER_BILL
PAY_WATER_BILL
CHECK_RECENT_TRANSACTIONS
CHECK_FEES
CALCULATE
```

### Navigation

```text
CONFIRM_YES
CONFIRM_NO
REPEAT
SPEAK_SLOWLY
GO_BACK
CANCEL
RESTART
HELP
CORRECT_AMOUNT
CORRECT_BENEFICIARY
CALL_AGENT
STOP_LISTENING
```

### Cas techniques

```text
UNKNOWN
SILENCE
NOISE
OUT_OF_SCOPE
AMBIGUOUS
```

---

## 5. Informations à extraire

```text
amount
beneficiary_alias
phone_alias
meter_alias
service_account_alias
bundle_type
operator
operand_1
operand_2
```

Exemple :

```json
{
  "intent": "SEND_MONEY",
  "slots": {
    "amount": 20000,
    "beneficiary_alias": "ma fille"
  }
}
```

---

# 6. Corpus à enregistrer — paroles de l’utilisateur

Les phrases françaises ci-dessous décrivent le sens. Chaque locuteur doit les produire **naturellement en zarma**, sans traduction mot à mot. Prévoir plusieurs formulations zarma pour chaque intention.

## 6.1 Consultation du solde — `CHECK_BALANCE`

1. Dis-moi mon solde.
2. Combien ai-je dans mon compte ?
3. Combien me reste-t-il ?
4. Vérifie mon argent.
5. Je veux connaître mon argent.
6. Quel est mon solde ?
7. Vérifie l’argent disponible.
8. Combien puis-je utiliser ?
9. Lis-moi mon solde.
10. Dis-moi ce que je possède.

## 6.2 Transfert — `SEND_MONEY`

1. Je veux envoyer de l’argent.
2. Je veux faire un transfert.
3. Envoie de l’argent.
4. Commence un transfert.
5. Envoie de l’argent à ma fille.
6. Envoie vingt mille francs à ma fille.
7. Transfère dix mille francs à Moussa.
8. Donne cinq mille francs à mon fournisseur.
9. Envoie quinze mille francs à mon fils.
10. Transfère l’argent à Aïssata.
11. Ce n’est pas la bonne personne.
12. Change le bénéficiaire.
13. Je veux choisir une autre personne.
14. Corrige le nom.
15. Annule ce bénéficiaire.

## 6.3 Crédit téléphonique — `BUY_AIRTIME`

1. Achète-moi du crédit.
2. Recharge mon téléphone.
3. Mets mille francs de crédit sur mon numéro.
4. Achète deux mille francs de crédit.
5. Je veux du crédit téléphonique.
6. Recharge mon propre numéro.
7. Achète du crédit pour ma fille.
8. Recharge le téléphone de mon fils.
9. Achète du crédit pour la boutique.
10. Je veux recharger un numéro enregistré.

## 6.4 Forfait Internet — `BUY_DATA_BUNDLE`

1. Je veux acheter un forfait Internet.
2. Achète-moi un forfait.
3. Je veux un forfait d’un jour.
4. Achète un forfait d’une semaine.
5. Je veux un forfait d’un mois.
6. Achète un forfait pour mon numéro.
7. Achète un forfait pour ma fille.
8. Mets Internet sur mon téléphone.
9. Je veux renouveler mon forfait.
10. Dis-moi les forfaits disponibles.

## 6.5 Compteur électrique — `RECHARGE_ELECTRICITY`

1. Je veux recharger mon compteur.
2. Recharge le compteur de la maison.
3. Recharge le compteur de la boutique.
4. Mets dix mille francs sur le compteur maison.
5. Achète cinq mille francs d’électricité.
6. Je veux acheter du crédit d’électricité.
7. Recharge mon compteur avec vingt mille francs.
8. Recharge le compteur enregistré.
9. Aide-moi à recharger l’électricité.
10. Je veux alimenter le compteur maison.

## 6.6 Facture d’électricité

### Consultation — `CHECK_ELECTRICITY_BILL`

1. Vérifie ma facture d’électricité.
2. Combien dois-je payer pour l’électricité ?
3. Dis-moi le montant de ma facture.
4. Vérifie la facture de la maison.
5. Quelle est ma dette d’électricité ?
6. Lis-moi la facture d’électricité.

### Paiement — `PAY_ELECTRICITY_BILL`

1. Je veux payer ma facture d’électricité.
2. Paie l’électricité de la maison.
3. Paie ma facture.
4. Je veux régler l’électricité.
5. Paie l’électricité de la boutique.
6. Aide-moi à payer l’électricité.

## 6.7 Facture d’eau

### Consultation — `CHECK_WATER_BILL`

1. Vérifie ma facture d’eau.
2. Combien dois-je payer pour l’eau ?
3. Dis-moi le montant de ma facture d’eau.
4. Vérifie l’eau de la maison.
5. Lis-moi la facture d’eau.
6. Quelle est ma dette d’eau ?

### Paiement — `PAY_WATER_BILL`

1. Je veux payer ma facture d’eau.
2. Paie l’eau de la maison.
3. Paie ma facture d’eau.
4. Je veux régler l’eau.
5. Aide-moi à payer l’eau.
6. Paie le compte d’eau enregistré.

## 6.8 Historique — `CHECK_RECENT_TRANSACTIONS`

1. Dis-moi mes dernières opérations.
2. Qu’est-ce que j’ai fait récemment ?
3. Lis-moi mes derniers transferts.
4. Vérifie mes dernières transactions.
5. Dis-moi le dernier paiement.
6. Est-ce que mon dernier transfert a réussi ?

## 6.9 Frais — `CHECK_FEES`

1. Combien coûtent les frais ?
2. Dis-moi les frais.
3. Quels sont les frais du transfert ?
4. Combien vais-je payer ?
5. Quel sera le montant total ?
6. Combien sera retiré de mon compte ?

---

# 7. Commandes globales à enregistrer

## `CONFIRM_YES`

- Oui.
- C’est correct.
- Je confirme.
- Continue.
- C’est bien cela.
- D’accord.

## `CONFIRM_NO`

- Non.
- Ce n’est pas correct.
- Je ne confirme pas.
- Ne continue pas.
- Arrête.
- Ce n’est pas cela.

## `REPEAT`

- Répète.
- Redis-moi.
- Dis-le encore.
- Je n’ai pas entendu.
- Je n’ai pas compris.
- Répète le montant.
- Répète le nom.

## `SPEAK_SLOWLY`

- Parle lentement.
- Parle moins vite.
- Répète doucement.
- Dis-le mot par mot.
- Lis le nombre lentement.

## `GO_BACK`

- Retour.
- Reviens en arrière.
- Retourne au menu.
- Reviens à la question précédente.
- Retour au début.

## `CANCEL`

- Annule.
- Annule tout.
- Arrête l’opération.
- Je ne veux plus continuer.
- Abandonne.
- Ne fais rien.

## `RESTART`

- Recommence.
- Recommence depuis le début.
- Je veux refaire l’opération.
- Efface tout et recommence.
- Nouvelle opération.

## `HELP`

- Aide-moi.
- Que puis-je faire ?
- Dis-moi les commandes.
- Explique-moi.
- Je suis perdu.
- Que dois-je dire ?

## `CALL_AGENT`

- Appelle un agent.
- Je veux parler à quelqu’un.
- J’ai besoin d’une personne.
- Appelle le service client.
- Je veux de l’aide humaine.

## `STOP_LISTENING`

- Arrête d’écouter.
- Ferme le microphone.
- Coupe la voix.
- Arrête l’assistant.
- Termine la session.

---

# 8. Bénéficiaires personnalisés

Les transferts du MVP sont autorisés uniquement vers des bénéficiaires enregistrés.

## Exemples d’alias

- ma fille ;
- mon fils ;
- ma mère ;
- mon père ;
- mon mari ;
- ma femme ;
- mon frère ;
- ma sœur ;
- mon fournisseur ;
- mon employé ;
- mon patron ;
- ma boutique ;
- mon associé ;
- Aïssata ;
- Moussa ;
- Amadou ;
- Mariama ;
- Fatouma ;
- Abdou ;
- Issa ;
- Hadiza.

## Enregistrement individuel

Pour chaque bénéficiaire, enregistrer au minimum :

```text
le surnom seul
le nom seul
la relation seule
le nom avec la relation
trois répétitions naturelles du propriétaire
```

Exemple :

```text
ma fille
Aïssata
ma fille Aïssata
Aïssata ma fille
```

## Règles

- interdire deux alias identiques ;
- signaler les alias trop proches ;
- ne jamais choisir approximativement ;
- confirmer le nom ;
- annoncer les quatre derniers chiffres du numéro ;
- demander de répéter en cas d’ambiguïté.

---

# 9. Compteurs, services et téléphones enregistrés

## Alias de compteurs

```text
compteur maison
compteur boutique
compteur bureau
compteur de ma mère
électricité maison
électricité boutique
```

## Alias d’eau

```text
eau maison
eau boutique
compte d’eau
eau de ma mère
```

## Alias téléphoniques

```text
mon numéro
mon téléphone
téléphone de ma fille
téléphone de mon fils
téléphone de la boutique
téléphone du fournisseur
```

Chaque alias personnel doit être enregistré trois fois par son propriétaire.

---

# 10. Nombres, montants et contrastes critiques

Conserver le corpus numérique existant et enregistrer particulièrement :

```text
100
200
500
1 000
1 500
2 000
2 500
3 000
5 000
7 500
10 000
15 000
20 000
25 000
30 000
40 000
50 000
75 000
100 000
150 000
200 000
250 000
500 000
1 000 000
```

Enregistrer chaque montant dans plusieurs contextes :

```text
Envoie [montant] à ma fille.
Achète [montant] de crédit.
Recharge le compteur avec [montant].
J’ai dit [montant].
Corrige le montant en [montant].
Non, je voulais dire [montant].
```

Contrastes critiques :

```text
15 000 / 50 000
16 000 / 60 000
17 000 / 70 000
18 000 / 80 000
19 000 / 90 000
25 000 / 250 000
100 000 / 110 000
```

---

# 11. Calculatrice vocale

Intent : `CALCULATE`

## Addition

- Vingt mille plus cinq mille.
- Ajoute cinq mille à vingt mille.
- Calcule dix mille plus trois mille.

## Soustraction

- Cinquante mille moins dix mille.
- Retire dix mille de cinquante mille.
- Calcule vingt mille moins cinq mille.

## Multiplication

- Deux mille multiplié par cinq.
- Multiplie deux mille par cinq.
- Combien font cinq fois deux mille ?

## Division

- Vingt mille divisé par quatre.
- Divise vingt mille par quatre.
- Partage vingt mille entre quatre personnes.

Structure attendue :

```json
{
  "intent": "CALCULATE",
  "slots": {
    "operand_1": 20000,
    "operator": "ADD",
    "operand_2": 5000
  }
}
```

Le résultat est calculé par un moteur déterministe.

---

# 12. Exemples négatifs à enregistrer

Le modèle doit reconnaître les cas à rejeter :

- conversations ordinaires ;
- phrases sans rapport avec l’application ;
- noms inconnus ;
- nombres incomplets ;
- hésitations ;
- phrases coupées ;
- silence ;
- bruit de marché ;
- radio ou télévision ;
- plusieurs personnes parlant ;
- enfant parlant à proximité ;
- voix trop éloignée ;
- mots ressemblant à « oui » ou « non ».

Étiquettes :

```text
UNKNOWN
SILENCE
NOISE
OUT_OF_SCOPE
AMBIGUOUS
```

---

# 13. Messages vocaux de sortie de l’application

Ces phrases doivent être enregistrées séparément avec une voix zarma claire.

## Accueil

```text
SYS_WELCOME
Bienvenue. Appuyez sur le grand bouton et dites ce que vous voulez faire.
```

```text
SYS_MAIN_HELP
Vous pouvez consulter votre solde, envoyer de l’argent, acheter du crédit, acheter un forfait, payer une facture ou recharger un compteur.
```

```text
SYS_LISTENING
Je vous écoute.
```

## Connexion

```text
SYS_LOGIN_FINGERPRINT
Posez votre doigt sur le capteur.
```

```text
SYS_LOGIN_PIN
Saisissez votre code secret. Ne prononcez jamais votre code à haute voix.
```

```text
SYS_LOGIN_SUCCESS
La connexion a réussi.
```

```text
SYS_LOGIN_FAILED
La connexion a échoué. Réessayez ou demandez de l’aide.
```

## Questions

```text
SYS_ASK_INTENT
Que souhaitez-vous faire ?
```

```text
SYS_ASK_AMOUNT
Quel montant voulez-vous utiliser ?
```

```text
SYS_ASK_BENEFICIARY
À qui voulez-vous envoyer l’argent ?
```

```text
SYS_ASK_PHONE_ALIAS
Quel numéro enregistré voulez-vous recharger ?
```

```text
SYS_ASK_METER_ALIAS
Quel compteur enregistré voulez-vous utiliser ?
```

## Confirmation

```text
SYS_HEARD_AMOUNT
J’ai compris [montant] francs CFA. Est-ce correct ?
```

```text
SYS_HEARD_BENEFICIARY
J’ai trouvé [bénéficiaire], numéro se terminant par [chiffres]. Est-ce la bonne personne ?
```

```text
SYS_TRANSFER_SUMMARY
Vous allez envoyer [montant] francs CFA à [bénéficiaire]. Les frais sont de [frais]. Le total débité sera de [total]. Confirmez-vous la préparation ?
```

## Résultats

```text
SYS_BALANCE
Votre solde disponible est de [solde] francs CFA.
```

```text
SYS_TRANSFER_SUCCESS
Le transfert a réussi. Votre nouveau solde est de [solde] francs CFA.
```

```text
SYS_TRANSFER_FAILED
Le transfert a échoué. Aucun argent n’a été envoyé.
```

```text
SYS_AIRTIME_SUCCESS
L’achat de crédit a réussi.
```

```text
SYS_METER_SUCCESS
La recharge du compteur a réussi.
```

```text
SYS_METER_TOKEN
Voici le code de recharge : [code]. Dites répète pour l’entendre encore.
```

```text
SYS_BILL_SUCCESS
Le paiement de la facture a réussi.
```

## Absence de données enregistrées

```text
SYS_NO_BENEFICIARY
Aucun bénéficiaire n’est enregistré. Demandez à un proche ou à un agent de vous aider. Aucun transfert ne sera effectué.
```

```text
SYS_BENEFICIARY_NOT_FOUND
Je ne trouve pas ce nom dans vos bénéficiaires enregistrés.
```

```text
SYS_NO_METER
Aucun compteur n’est enregistré. Demandez à un proche ou à un agent de vous aider.
```

```text
SYS_NO_BILL_ACCOUNT
Aucun compte de service n’est enregistré.
```

## Erreurs

```text
SYS_NOT_UNDERSTOOD
Je n’ai pas bien compris. Répétez lentement.
```

```text
SYS_LOW_CONFIDENCE_AMOUNT
Je ne suis pas certain du montant. Répétez le montant.
```

```text
SYS_LOW_CONFIDENCE_NAME
Je ne suis pas certain du nom. Répétez le nom.
```

```text
SYS_NETWORK_UNAVAILABLE
Le réseau est indisponible. Votre opération n’a pas été envoyée et aucun argent n’a été retiré.
```

```text
SYS_INSUFFICIENT_BALANCE
Votre solde est insuffisant.
```

```text
SYS_OPERATION_CANCELLED
L’opération a été annulée. Aucun argent n’a été envoyé.
```

```text
SYS_TOO_MANY_FAILURES
Je ne peux pas terminer cette opération par la voix. Aucun argent n’a été envoyé. Demandez de l’aide.
```

## Formation

```text
SYS_TRAINING_START
Le mode entraînement commence. Aucune vraie transaction ne sera effectuée.
```

```text
SYS_TRAINING_SUCCESS
Très bien. La commande a été reconnue.
```

```text
SYS_TRAINING_RETRY
La commande n’a pas été reconnue. Écoutez puis répétez.
```

```text
SYS_TRAINING_END
La formation est terminée.
```

---

# 14. Fonctionnement de chaque menu

## Accueil

```text
connexion
→ message d’accueil
→ activation du microphone
→ détection de l’intention
```

## Solde

```text
CHECK_BALANCE
→ récupération du solde par API
→ lecture du solde
→ répéter ou retour
```

## Transfert

```text
SEND_MONEY
→ vérifier les bénéficiaires
→ demander le bénéficiaire
→ confirmer le nom et les derniers chiffres
→ demander le montant
→ convertir le nombre
→ confirmer le montant
→ récupérer les frais
→ lire le récapitulatif
→ confirmation vocale
→ biométrie ou PIN
→ exécution par API
→ annonce du résultat
```

Aucun transfert vers un numéro non enregistré.

## Crédit

```text
BUY_AIRTIME
→ choisir un numéro enregistré
→ demander le montant
→ confirmer
→ authentifier
→ exécuter
→ annoncer le résultat
```

## Forfait

```text
BUY_DATA_BUNDLE
→ choisir un numéro enregistré
→ proposer jour, semaine ou mois
→ annoncer le prix
→ confirmer
→ authentifier
→ exécuter
```

## Compteur

```text
RECHARGE_ELECTRICITY
→ choisir un compteur enregistré
→ demander le montant
→ annoncer frais et total
→ confirmer
→ authentifier
→ exécuter
→ lire le code de recharge
```

## Facture

```text
choisir eau ou électricité
→ choisir le compte enregistré
→ récupérer la facture
→ lire le montant
→ demander si l’utilisateur veut payer
→ confirmer
→ authentifier
→ exécuter
```

## Historique

```text
récupérer trois opérations maximum
→ lire une opération à la fois
→ répéter, suivante ou arrêter
```

## Entraînement

```text
utiliser un faux compte
→ écouter une commande
→ répéter la commande
→ vérifier la reconnaissance
→ aucune transaction réelle
```

---

# 15. Interface

## Écran principal

- grand microphone central ;
- bouton Répéter ;
- bouton Annuler ;
- bouton Aide ;
- icône casque ou confidentialité ;
- contraste élevé ;
- compatibilité TalkBack et VoiceOver.

## Signaux

```text
vibration courte : écoute démarrée
deux vibrations : commande comprise
vibration longue : erreur
trois vibrations : opération réussie
```

## Principes

- une question à la fois ;
- une action principale par écran ;
- très peu de texte ;
- grandes zones tactiles ;
- répétition illimitée ;
- possibilité d’annuler partout.

---

# 16. Machine à états

Exemple pour le transfert :

```text
IDLE
ASK_INTENT
CHECK_BENEFICIARIES
ASK_BENEFICIARY
CONFIRM_BENEFICIARY
ASK_AMOUNT
CONFIRM_AMOUNT
GET_FEES
READ_SUMMARY
ASK_CONFIRMATION
REQUEST_AUTHENTICATION
EXECUTE_TRANSACTION
ANNOUNCE_RESULT
END
```

Prévoir trois tentatives maximum pour une information critique. Après trois échecs, arrêter l’opération.

---

# 17. Format d’annotation

```json
{
  "audio_file": "speaker_012_send_money_003.wav",
  "speaker_id": "speaker_012",
  "language": "zarma",
  "transcription_originale": "",
  "transcription_normalisee": "",
  "traduction_francaise": "Je veux envoyer de l’argent",
  "intent": "SEND_MONEY",
  "slots": {},
  "environment": "quiet_room",
  "device": "android_mid_range",
  "age_group": "50_plus",
  "consent_id": "consent_012"
}
```

Organisation :

```text
dataset/
├── audio/train/
├── audio/validation/
├── audio/test/
├── annotations/train.jsonl
├── annotations/validation.jsonl
├── annotations/test.jsonl
├── vocabulary/intents.md
├── vocabulary/numbers.md
├── vocabulary/aliases.md
└── vocabulary/system_prompts.md
```

Ne jamais placer un même locuteur dans l’entraînement et dans le test final.

---

# 18. Consignes d’enregistrement

Pour chaque locuteur :

- enregistrer les chiffres ;
- enregistrer une sélection équilibrée de nombres ;
- enregistrer toutes les commandes globales ;
- enregistrer plusieurs intentions principales ;
- enregistrer les corrections ;
- enregistrer des phrases négatives ;
- enregistrer une version normale et une version lente ;
- ajouter quelques enregistrements en environnement bruyant.

Inclure :

- femmes et hommes ;
- jeunes adultes ;
- personnes âgées ;
- accents et prononciations différents ;
- voix faibles ;
- téléphones de qualités différentes ;
- locuteurs totalement inconnus dans le jeu de test.

---

# 19. Règles non négociables

1. Ne jamais deviner un montant.
2. Ne jamais choisir approximativement un bénéficiaire.
3. Aucun transfert vers un numéro non enregistré dans le MVP.
4. Le PIN ne doit jamais être prononcé.
5. Le « oui » vocal ne remplace pas l’authentification.
6. Toujours annoncer le bénéficiaire, le montant, les frais et le total.
7. Permettre l’annulation à chaque étape.
8. Considérer une opération sans confirmation du serveur comme non effectuée.
9. Ne pas réutiliser les voix sans consentement.
10. Le mode entraînement ne doit jamais utiliser de vrai argent.

---

# 20. Parcours à réussir dans la première démonstration

## Parcours 1

```text
connexion
→ solde
→ répétition
→ retour
```

## Parcours 2

```text
transfert
→ bénéficiaire enregistré
→ montant
→ confirmation
→ authentification
→ résultat
```

## Parcours 3

```text
achat de crédit
→ numéro enregistré
→ montant
→ confirmation
→ résultat
```

## Parcours 4

```text
recharge compteur
→ compteur enregistré
→ montant
→ confirmation
→ lecture du code
```

## Parcours 5

```text
commande mal comprise
→ répétition
→ correction
→ réussite ou annulation
```

La priorité du MVP est la fiabilité, la simplicité et la sécurité.
