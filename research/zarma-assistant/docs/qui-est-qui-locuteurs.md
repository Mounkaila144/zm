# Qui est qui — correspondance des locuteurs

Le corpus compte aujourd'hui **18 voix**, mais certaines sont probablement
**la même personne** enregistrée lors des deux campagnes.

À quoi ça sert : uniquement à mesurer honnêtement. Si on compte 18 personnes
là où il y en a 12, l'évaluation testera parfois une voix déjà entendue à
l'entraînement, et le score sera trop beau — celui-là même que tu
présenteras aux investisseurs. Ça ne change ni les données ni la qualité du
modèle, seulement la sincérité du chiffre.

---

## Pour écouter

Ouvre le Terminal, colle cette ligne une fois :

```bash
cd /Users/pc/project/zarma/research/zarma-assistant/data/asr_corpus/clips
```

Puis les commandes `afplay` ci-dessous, telles quelles.

---

## PARTIE 1 — Les 8 voix anonymes (première campagne)

Ce sont elles le vrai travail : leurs dossiers s'appellent `v1`, `v2`… et
on ne sait pas qui parle. **Écoute et écris le prénom.**

Indice : `/Users/pc/Music/2voix/` contient huit enregistrements *nommés*
(abdoulaye, amina, haoua, layhana, mounkaila, sharifa, zizigna, zouera)
faits par les mêmes personnes — utile pour reconnaître les voix.

### v1

98 clips · 2.1 min · séances `op4 + v1 + v4`

```bash
afplay v4_999999.wav
afplay v4_12345.wav
afplay v4_5432.wav
```

**Qui est-ce ?** → `mounkaila`

### v2

81 clips · 1.7 min · séances `op3 + v2 + v8`

```bash
afplay v8_12345.wav
afplay v8_5432.wav
afplay v8_12000500.wav
```

**Qui est-ce ?** → `haoua`

### v3

93 clips · 1.7 min · séances `op1 + v3 + v5`

```bash
afplay v5_100099.wav
afplay v5_999.wav
afplay v5_223.wav
```

**Qui est-ce ?** → `sharifa`

### v6

59 clips · 1.5 min · séances `op2 + v6`

```bash
afplay v6_12542.wav
afplay v6_5432.wav
afplay v6_900099.wav
```

**Qui est-ce ?** → `zouera`

### v7

55 clips · 1.1 min · séances `v7`

```bash
afplay v7_5439.wav
afplay v7_3435.wav
afplay v7_900099.wav
```

**Qui est-ce ?** → `abdoulaye`

### v9

53 clips · 1.4 min · séances `v9`

```bash
afplay v9_999999.wav
afplay v9_4534.wav
afplay v9_223.wav
```

**Qui est-ce ?** → `leyhana`

### v10

53 clips · 1.2 min · séances `v10`

```bash
afplay v10_5032.wav
afplay v10_100099.wav
afplay v10_223.wav
```

**Qui est-ce ?** → `limou`

### v11

53 clips · 1.2 min · séances `v11`

```bash
afplay v11_12030.wav
afplay v11_5035.wav
afplay v11_12000500.wav
```

**Qui est-ce ?** → `amina`

---

## PARTIE 2 — Les 10 voix de l'application (seconde campagne)

Leur prénom est déjà connu. **Ne remplis que si la personne avait**
**aussi participé à la première campagne** — indique alors quelle voix
`v…` c'était. Laisse vide si elle est nouvelle.

| prénom | code | clips | avait aussi enregistré en tant que |
|---|---|---|------------------------------------|
| **abdoulaye** | `app_5x5b` | 32 | `v7`                               |
| **daban** | `app_2g4s` | 32 | `________`                         |
| **fatiya** | `app_vztk` | 31 | `________`                         |
| **haoua** | `app_9vpj` | 32 | `v2`                               |
| **leyhana** | `app_3jun` | 32 | `v9`                               |
| **mounkaila** | `app_tksw` | 32 | `v1`                               |
| **ous-mane** | `app_238h` | 32 | `________`                         |
| **rachida** | `app_k6jw` | 32 | `________`                         |
| **sharifa** | `app_dfun` | 32 | `v3`                               |
| **zouera** | `app_632q` | 32 | `v6`                               |

---

## Quand c'est rempli

Renvoie-moi simplement ce fichier, ou recopie les réponses dans le chat.
En cas de doute, **déclare la correspondance** : compter deux personnes
comme une seule ne fait que rendre la mesure plus sévère, l'inverse la fausse.
