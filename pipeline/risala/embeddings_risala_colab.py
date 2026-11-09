# embeddings_risala_colab.py — à lancer dans Google Colab (GPU T4)
# LIT  : risala_2_masail.jsonl (que tu téléverses)
# ÉCRIT: les 169 lignes + leurs vecteurs dans la table fiqh_chunks de Supabase
#        (upsert : si tu relances, les lignes sont mises à jour, jamais dupliquées)

# ---------- Cellule 1 : installer ----------
# !pip install -q -U sentence-transformers supabase

# ---------- Cellule 2 : tout le reste ----------
import json
import os
from getpass import getpass

import torch
from sentence_transformers import SentenceTransformer
from supabase import create_client

FICHIER = "risala_2_masail.jsonl"
SUPABASE_URL = "https://hxyfdvfnjynpysgelsyf.supabase.co"
TITRE_MATN = "الرسالة"

# 1. Le fichier : téléversé dans Colab (icône dossier à gauche) ou demandé ici
if not os.path.exists(FICHIER):
    from google.colab import files
    files.upload()

# 2. La clé secrète : jamais écrite dans le code
try:
    from google.colab import userdata
    CLE = userdata.get("SUPABASE_SERVICE_KEY")       # Colab > icône clé > Secrets
except Exception:
    CLE = getpass("Colle ta clé service_role Supabase : ")
supabase = create_client(SUPABASE_URL, CLE)

# 3. Lire les مسائل
lignes = [json.loads(l) for l in open(FICHIER, encoding="utf-8") if l.strip()]
print(len(lignes), "lignes lues")

# 4. Calculer les vecteurs avec BGE-M3 (GPU + fp16 = rapide)
appareil = "cuda" if torch.cuda.is_available() else "cpu"
print("Appareil :", appareil)
modele = SentenceTransformer("BAAI/bge-m3", device=appareil)
if appareil == "cuda":
    modele.half()
modele.max_seq_length = 512
vecteurs = modele.encode([l["texte_embedding"] for l in lignes], batch_size=32,
                         normalize_embeddings=True, show_progress_bar=True)
print("Vecteurs :", vecteurs.shape)               # attendu : (169, 1024)

# 5. Retrouver le numéro du livre dans la table matns
matn_id = supabase.table("matns").select("id").eq("titre", TITRE_MATN).single().execute().data["id"]
print("matn_id =", matn_id)

# 6. Envoyer par paquets de 50 (upsert sur la clé unique matn_id + ordre + partie)
CHAMPS = ["kitab", "bab", "ordre_bab", "section", "ordre", "partie", "page",
          "texte_affichage", "texte_recherche", "texte_embedding"]
lots = []
for l, v in zip(lignes, vecteurs):
    ligne = {c: l[c] for c in CHAMPS}
    ligne["matn_id"] = matn_id
    ligne["embedding"] = "[" + ",".join(f"{x:.6f}" for x in v.tolist()) + "]"   # format pgvector
    lots.append(ligne)
for i in range(0, len(lots), 50):
    supabase.table("fiqh_chunks").upsert(lots[i:i + 50], on_conflict="matn_id,ordre,partie").execute()
    print("envoyé", min(i + 50, len(lots)), "/", len(lots))

# 7. Vérifier
total = supabase.table("fiqh_chunks").select("id", count="exact").eq("matn_id", matn_id).execute().count
print("Dans Supabase :", total, "lignes (attendu", len(lignes), ")")
