# نور — Nour

Application web avec un chat RAG qui répond uniquement à partir de sources islamiques vérifiées, en citant ses passages.

**Stack :** React (Vite) · FastAPI · Supabase (PostgreSQL + pgvector) · BGE-M3 (1024 dimensions) · Gemini

## Avancement

| Étape | Risala (maliki) |
|---|---|
| Source vérifiée | ✅ édition التتائي / السناري (voir `SOURCES.md`) |
| Nettoyage | ✅ 21 abwab |
| Découpage en مسائل | ✅ 164 مسائل, 169 lignes |
| Base Supabase | ✅ tables + recherche (`sql/001_init_fiqh.sql`) |
| Embeddings + import | ⏳ `embeddings_risala_colab.py` (Colab, GPU) |

## Pipeline de la Risala

Depuis `pipeline/risala/` :

```bash
python nettoyer_risala.py    # al_risala_brut.txt -> donnees/risala_1_nettoye.jsonl (+ notes)
python decouper_risala.py    # -> donnees/risala_2_masail.jsonl
```

Résultat attendu : `164 مسائل -> 169 lignes`, `aucun texte perdu ni dupliqué ✔`.

Puis, dans Google Colab (GPU T4), `embeddings_risala_colab.py` calcule les vecteurs BGE-M3
et envoie les 169 lignes dans la table `fiqh_chunks` (secret Colab : `SUPABASE_SERVICE_KEY`).

## Méthode de découpage (small-to-big)

- Chaque bab est coupé en sections (sous-titres du محقق), puis en مسائل (une règle = un morceau).
- Chaque مسألة a son vecteur, calculé sur « الرسالة › bab › section › texte ».
- Au moment de répondre, on ajoute la مسألة d'avant et celle d'après, dans la même section.

## Clés

Copier `.env.example` en `.env` et le remplir. Le fichier `.env` n'est jamais envoyé sur GitHub.
