"""Ajoute le zarma comme langue M2M100 (code 'dje'), de façon non destructive.

M2M100 ne supporte nativement qu'environ 100 langues et le zarma n'en fait
pas partie. Ce module centralise la logique validée par
`_sanity_check_tokenizer.py` : le checkpoint pré-entraîné a en réalité plus
de lignes d'embeddings (128112) que ce que le tokenizer expose via __len__
(128104) — 8 emplacements de réserve existent déjà. On réutilise l'un de ces
emplacements pour 'dje' plutôt que de resize (ce qui tronquerait le modèle),
et on réinitialise cette ligne à partir de l'embedding du hausa ('ha' —
langue la plus proche géographiquement/en contact, seule langue songhay-
adjacente supportée nativement) comme point de départ pour le fine-tuning.
"""

from __future__ import annotations

import torch
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

ZARMA_CODE = "dje"
ZARMA_TOKEN = "__dje__"
PROXY_LANG_CODE = "ha"  # hausa — point de départ pour l'embedding réinitialisé


def add_zarma_language(
    tokenizer: M2M100Tokenizer, model: M2M100ForConditionalGeneration
) -> int:
    """Enregistre 'dje' comme langue du tokenizer et prépare l'embedding
    correspondant sur le modèle. Retourne l'ID du token __dje__."""

    if ZARMA_CODE not in tokenizer.lang_code_to_id:
        tokenizer.add_special_tokens({"additional_special_tokens": [ZARMA_TOKEN]})
        new_id = tokenizer.convert_tokens_to_ids(ZARMA_TOKEN)
        # Les 4 dictionnaires internes de M2M100Tokenizer doivent être tenus
        # cohérents ensemble (cf. tokenization_m2m_100.py) — sinon
        # get_lang_token()/set_src_lang_special_tokens() lèvent un KeyError.
        tokenizer.lang_code_to_token[ZARMA_CODE] = ZARMA_TOKEN
        tokenizer.lang_token_to_id[ZARMA_TOKEN] = new_id
        tokenizer.id_to_lang_token[new_id] = ZARMA_TOKEN
        tokenizer.lang_code_to_id[ZARMA_CODE] = new_id
    else:
        new_id = tokenizer.lang_code_to_id[ZARMA_CODE]

    native_size = model.get_input_embeddings().weight.shape[0]
    target_size = max(len(tokenizer), native_size)
    if target_size > native_size:
        # Cas de sécurité seulement : ne devrait pas arriver avec le
        # checkpoint m2m100_418M actuel (voir docstring du module), mais si
        # jamais le nombre de réserves venait à changer, on agrandit sans
        # jamais réduire.
        model.resize_token_embeddings(target_size)

    embed_weight = model.get_input_embeddings().weight
    ha_id = tokenizer.lang_code_to_id[PROXY_LANG_CODE]
    with torch.no_grad():
        embed_weight[new_id] = embed_weight[ha_id].clone()
        out_embed = model.get_output_embeddings()
        if out_embed is not None and out_embed.weight.data_ptr() != embed_weight.data_ptr():
            out_embed.weight[new_id] = out_embed.weight[ha_id].clone()

    return new_id


def freeze_embeddings_except(model: M2M100ForConditionalGeneration, keep_id: int) -> None:
    """Rend l'embedding d'entrée entraînable, mais masque le gradient de
    toutes les lignes sauf `keep_id` — seul le nouveau token 'dje' apprend,
    le reste du vocabulaire pré-entraîné (français compris) n'est pas
    perturbé. Évite d'avoir à dupliquer toute la matrice d'embeddings comme
    le ferait peft `modules_to_save` (~130M paramètres, hors de portée en
    mémoire sur cette machine)."""

    embed_weight = model.get_input_embeddings().weight
    embed_weight.requires_grad_(True)

    def _mask_grad(grad: torch.Tensor) -> torch.Tensor:
        # Le masque est recréé à chaque appel sur le device du gradient
        # (le modèle est déplacé vers MPS par le Trainer APRÈS l'appel à
        # cette fonction, donc un masque pré-calculé resterait sur CPU et
        # ferait échouer la multiplication avec un gradient sur MPS).
        mask = torch.zeros_like(grad)
        mask[keep_id] = 1.0
        return grad * mask

    embed_weight.register_hook(_mask_grad)
