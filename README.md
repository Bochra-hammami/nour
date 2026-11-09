# نور — Nour

Application web avec un chat RAG qui répond uniquement à partir de sources islamiques vérifiées, en citant ses passages mot pour mot.

**Sources (maliki) :** الرسالة (ابن أبي زيد القيرواني) et مختصر الأخضري — كتاب الطهارة + كتاب الصلاة. Voir `SOURCES.md`.

## Architecture (gratuite)

```
Navigateur ─► Vercel : site React (frontend/) + API FastAPI (backend/), même domaine
                ├─► Cloudflare Workers AI : BGE-M3 → vecteur de la question
                ├─► Supabase (pgvector)   : chercher_fiqh() → مسائل les plus proches
                └─► Groq                  : openai/gpt-oss-120b → réponse avec citations
GitHub Actions : ping quotidien pour que Supabase gratuit ne s'endorme pas
```

## Structure

```
nour/
├── sql/                 base Supabase (tables, chercher_fiqh, livres)
├── pipeline/            préparer les données : nettoyer, découper en مسائل, vecteurs
├── backend/app/
│   ├── config.py        réglages (clés, seuil 0,45, nombre de passages…)
│   ├── texte.py         normaliser() + retrouver une citation dans un texte
│   ├── clients.py       Cloudflare (vecteur) et Groq (réponse)
│   ├── recherche.py     Supabase : مسائل en mémoire, chercher_fiqh, voisines
│   ├── rag.py           le chef d'orchestre : les 3 filtres + le prompt
│   └── main.py          les routes de l'API (/api/ask…)
├── frontend/            React + Vite, de droite à gauche (repris du prototype de l'ami)
├── vercel.json          mise en ligne : /api/* → backend, le reste → frontend
└── .github/workflows/keepalive.yml
```

## Trajet d'une question

`POST /api/ask` → `main.py` → `rag.py` :

1. normaliser la question, puis Cloudflare → vecteur
2. `chercher_fiqh` → 10 مسائل candidates
3. **Filtre 1** : meilleur score < 0,45 → « لم يرد في النص… » sans appeler le LLM
4. garder les مسائل à moins de 0,06 du meilleur (3 au plus) + leurs voisines dans la même section
5. Groq répond en citant les phrases entre «» avec le numéro du passage
6. **Filtre 2** : le LLM peut répondre « لم يرد في النص… » si les passages ne répondent pas
7. **Filtre 3** : chaque citation est cherchée dans les passages (sans harakat) → ✅ ou ⚠️

## Pipeline des données (déjà fait)

```bash
cd pipeline/risala && python nettoyer_risala.py && python decouper_risala.py   # 164 مسائل -> 169 lignes
cd pipeline/akhdari && python decouper_akhdari.py                               # 98 مسائل -> 100 lignes
```

Les vecteurs BGE-M3 sont dans Supabase (269 lignes). Cloudflare et Colab donnent les mêmes vecteurs (similarité 1,0000).

## Lancer en local

1. Copier `.env.example` en `.env` (à la racine) et remplir les 5 clés.
2. Backend (terminal 1) :
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```
   Vérifier : http://localhost:8000/api/health?deep=1 → `"db": "ok"`, `"units": 269`.
3. Frontend (terminal 2) :
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Ouvrir http://localhost:5173.

## Clés

Les clés ne vont jamais dans le code ni sur GitHub : `.env` en local, variables d'environnement sur Vercel.
