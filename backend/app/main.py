"""Les adresses (routes) de l'API. Chaque fonction répond à une adresse :
  GET  /api/health                     l'API marche-t-elle ? (?deep=1 interroge aussi Supabase)
  GET  /api/madhahib                   les 4 madhahib et ceux qui sont disponibles
  GET  /api/books?madhhab=maliki       les livres et leurs abwab (page « مكتبتي »)
  GET  /api/books/{livre}/babs/{n}     toutes les مسائل d'un bab (le lecteur)
  POST /api/ask                        {question, madhhab} → réponse vérifiée (rag.py)

Lancer en local, depuis le dossier backend/ :  uvicorn app.main:app --reload --port 8000
"""
import logging
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("nour")

app = FastAPI(title="Nour API")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

_verrou = threading.Lock()


def creer_rag():
    """Créé à la première requête, puis gardé en mémoire tant que le serveur reste allumé."""
    manquantes = config.variables_manquantes()
    if manquantes:
        raise HTTPException(503, f"Variables d'environnement manquantes : {', '.join(manquantes)}")
    from .clients import Cloudflare, Groq
    from .rag import Rag
    from .recherche import Supabase
    supabase = Supabase()
    corpus = supabase.charger_corpus()
    if not corpus.masail:
        raise HTTPException(503, "La base est vide.")
    log.info("%d مسائل chargées depuis Supabase", len(corpus.masail))
    return Rag(corpus, supabase, Cloudflare(), Groq())


def rag(request: Request):
    r = getattr(request.app.state, "rag", None)
    if r is None:
        with _verrou:   # deux premières requêtes en même temps : un seul chargement
            r = getattr(request.app.state, "rag", None)
            if r is None:
                r = request.app.state.rag = creer_rag()
    return r


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    madhhab: str = "maliki"


@app.get("/api/health")
def health(request: Request, deep: bool = False):
    info = {"status": "ok", "llm": config.MODELE_LLM}
    if deep:
        r = rag(request)
        r.supabase.ping()
        info.update(units=len(r.corpus.masail), db="ok")
    elif config.variables_manquantes():
        info.update(status="misconfigured", missing=config.variables_manquantes())
    return info


@app.get("/api/madhahib")
def madhahib():
    return config.MADHAHIB


@app.get("/api/books")
def livres(request: Request, madhhab: str = "maliki"):
    corpus = rag(request).corpus
    return [{"key": l.cle, "title": l.titre, "author": l.auteur, "madhhab": l.madhhab,
             "babs": [{"index": b["index"], "title": b["title"], "units": len(b["cles"])}
                      for b in sorted(l.babs.values(), key=lambda b: b["index"])]}
            for l in corpus.livres.values() if l.madhhab == madhhab]


@app.get("/api/books/{cle_livre}/babs/{index}")
def bab(request: Request, cle_livre: str, index: int):
    corpus = rag(request).corpus
    livre = corpus.livres.get(cle_livre)
    if livre is None or index not in livre.babs:
        raise HTTPException(404, "bab introuvable")
    indices = sorted(livre.babs)
    pos = indices.index(index)
    b = livre.babs[index]
    return {
        "book_key": livre.cle, "book": livre.titre, "author": livre.auteur,
        "bab_index": index, "bab_title": b["title"],
        "prev": indices[pos - 1] if pos > 0 else None,
        "next": indices[pos + 1] if pos + 1 < len(indices) else None,
        "units": [{"key": m.cle, "number": m.numero, "section": m.section or b["title"],
                   "page": m.page, "text": m.texte}
                  for m in (corpus.masail[c] for c in b["cles"])],
    }


@app.post("/api/ask")
def demander(request: Request, corps: Question):
    if not any(m["key"] == corps.madhhab and m["available"] for m in config.MADHAHIB):
        raise HTTPException(400, "هذا المذهب غير متاح بعد")
    try:
        return rag(request).demander(corps.question.strip(), corps.madhhab)
    except RuntimeError as erreur:   # service externe en erreur (quota, clé invalide…)
        log.exception("échec de /api/ask")
        raise HTTPException(503, str(erreur)) from erreur
