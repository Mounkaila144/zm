"""Vérifie que l'ajout du zarma comme code langue M2M100 fonctionne avant
de lancer un entraînement complet : le zarma n'est pas dans les ~100 langues
nativement supportées par M2M100, donc on ajoute un token spécial __dje__ et
on redimensionne les embeddings. Ce script vérifie juste que l'API attendue
(tokenizer.lang_code_to_id, encodage/décodage) se comporte comme prévu sur la
version installée de transformers, avant d'y investir un entraînement long.
"""

from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

MODEL_NAME = "facebook/m2m100_418M"

print("Chargement du tokenizer...")
tokenizer = M2M100Tokenizer.from_pretrained(MODEL_NAME)

print(f"'fr' déjà supporté : {'fr' in tokenizer.lang_code_to_id}")
print(f"'dje' déjà supporté : {'dje' in tokenizer.lang_code_to_id}")
print(f"'ha' (hausa, proxy géographique) déjà supporté : {'ha' in tokenizer.lang_code_to_id}")
print(f"Taille du vocabulaire avant ajout : {len(tokenizer)}")

new_token = "__dje__"
num_added = tokenizer.add_special_tokens({"additional_special_tokens": [new_token]})
print(f"Tokens ajoutés : {num_added}")

new_id = tokenizer.convert_tokens_to_ids(new_token)
print(f"ID du nouveau token : {new_id}")

# M2M100Tokenizer maintient 4 dictionnaires parallèles pour gérer les codes
# langue (cf. tokenization_m2m_100.py) — il faut les mettre à jour ensemble,
# sinon get_lang_token()/set_src_lang_special_tokens() lèvent un KeyError.
tokenizer.lang_code_to_token["dje"] = new_token
tokenizer.lang_token_to_id[new_token] = new_id
tokenizer.id_to_lang_token[new_id] = new_token
tokenizer.lang_code_to_id["dje"] = new_id

print(f"Taille du vocabulaire après ajout : {len(tokenizer)}")

# Test d'encodage fr -> dje
tokenizer.src_lang = "fr"
encoded = tokenizer("Bonjour, comment allez-vous ?", return_tensors="pt")
print(f"Encodage fr (input_ids[0]): {encoded['input_ids'][0][:5].tolist()}")

tokenizer.src_lang = "dje"
tokenizer.tgt_lang = "dje"
encoded_dje = tokenizer("Fofo, mate ni go ?", return_tensors="pt")
print(f"Encodage dje (input_ids[0]): {encoded_dje['input_ids'][0][:5].tolist()}")
assert encoded_dje["input_ids"][0][0].item() == new_id, "Le préfixe __dje__ n'a pas été inséré correctement"
print("OK : le préfixe __dje__ est bien inséré en tête de séquence.")

forced_bos = tokenizer.get_lang_id("dje")
print(f"forced_bos_token_id pour dje : {forced_bos} (doit être égal à {new_id})")
assert forced_bos == new_id

print("\nChargement du modèle (pour vérifier le resize)...")
model = M2M100ForConditionalGeneration.from_pretrained(MODEL_NAME)
native_size = model.get_input_embeddings().weight.shape[0]
print(f"Taille embeddings native du modèle : {native_size}")
print(f"Taille vocab tokenizer (avant ajout dje comptée par __len__) : {len(tokenizer) - 1}")

# IMPORTANT : le modèle a plus de lignes d'embeddings (128112) que ce que
# tokenizer.__len__() rapporte (128104 avant ajout de dje) — 8 emplacements
# de réserve existent déjà dans le checkpoint pré-entraîné (vraisemblablement
# des "madeupword" fairseq prévus pour l'extension future du vocabulaire).
# Le nouvel ID assigné à __dje__ (128104) tombe PILE dans cette réserve.
# resize_token_embeddings(len(tokenizer)) SUPPRIMERAIT ces 8 lignes (128112 ->
# 128105) puisque len(tokenizer) est inférieur à la taille native — on ne
# resize donc que si c'est strictement nécessaire, jamais vers le bas.
target_size = max(len(tokenizer), native_size)
if target_size != native_size:
    model.resize_token_embeddings(target_size)
    print(f"Resize appliqué -> {target_size} (agrandissement réel nécessaire)")
else:
    print(f"Pas de resize nécessaire : {new_id} tombe déjà dans une ligne réservée existante ({native_size} lignes).")

assert model.get_input_embeddings().weight.shape[0] >= native_size, "Des lignes d'embeddings ont été perdues !"
print(f"Taille embeddings finale : {model.get_input_embeddings().weight.shape}")

# La ligne réservée contient une valeur pré-entraînée arbitraire (jamais
# utilisée jusqu'ici) — on la réinitialise à partir de l'embedding du hausa
# (__ha__), langue la plus proche géographiquement/en contact avec le zarma
# parmi celles supportées nativement, comme point de départ pour le
# fine-tuning plutôt qu'un vecteur potentiellement non entraîné.
ha_id = tokenizer.lang_code_to_id["ha"]
with __import__("torch").no_grad():
    embed_weight = model.get_input_embeddings().weight
    embed_weight[new_id] = embed_weight[ha_id].clone()
    if model.get_output_embeddings() is not None and model.get_output_embeddings().weight.data_ptr() != embed_weight.data_ptr():
        out_weight = model.get_output_embeddings().weight
        out_weight[new_id] = out_weight[ha_id].clone()
        print("Embeddings d'entrée ET de sortie initialisés depuis __ha__ (non liés).")
    else:
        print("Embeddings d'entrée et de sortie liés (tied) — un seul réinit nécessaire.")

print("\nTout est cohérent — prêt pour l'entraînement.")
