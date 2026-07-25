# services/asr

Service du modèle ASR **serverless GPU** (Modal) — charge les modèles Omnilingual
et expose `POST /transcribe`. Moteur vocal **remplaçable**, isolé du reste : l'API
ne l'appelle jamais en dur, uniquement via l'interface `SpeechRecognizer`
(`RemoteCtcRecognizer` / `RemoteLlmRecognizer` côté `services/api`).

## Isolation

- Image **lourde et séparée** de l'API (torch + `omnilingual-asr`), déployée et
  redémarrée indépendamment.
- **Hors workspace uv racine** → la CI reste **sans GPU**. Ce service ne fait pas
  partie des tests CI standard ; seul le smoke test réel (AC4) l'exerce, à la main.

## Modèles (poids Apache 2.0, chargés dans le service)

| Mode | Modèle | `lang` |
|------|--------|--------|
| `ctc` | `omniASR_CTC_300M_v2` | — (aucune) |
| `llm` | `omniASR_LLM_300M_v2` | `["dje_Latn"]` |

## Contrat `/transcribe`

```
POST /transcribe            (HTTPS Modal, secret Bearer)
multipart : audio (WAV PCM16 mono 16 kHz), model, lang? (JSON)
200 : { text, acoustic_score, candidates[], latency_ms, model_version }
```

## Déploiement

```bash
# Secrets Modal (hors Git) :
modal secret create zarma-asr-token ASR_ENDPOINT_TOKEN=…

# Déploiement indépendant de l'API :
modal deploy services/asr/app/main.py
```

Basculer l'API de Mock au modèle réel = **configuration seule** (aucun changement
d'API ni de mobile) :

```bash
# services/api/.env (hors Git)
ASR_MODE=ctc                 # ou llm
ASR_ENDPOINT_URL=https://…modal.run
ASR_ENDPOINT_TOKEN=…         # secret, jamais committé, jamais côté mobile
```

## Smoke test réel (AC4, hors CI)

```bash
ASR_ENDPOINT_URL=… ASR_ENDPOINT_TOKEN=… \
ASR_SMOKE_AUDIO=dataset/benchmark/<echantillon>.wav ASR_SMOKE_EXPECTED=372 \
uv run pytest services/asr/tests/smoke_real_recognizer.py -q
```

En cas d'échec/cold start côté endpoint, le recognizer replie sur `decision=repeat`
(jamais de nombre inventé) — voir `services/api/app/asr/remote.py`.
