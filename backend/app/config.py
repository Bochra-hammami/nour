"""Tous les réglages du backend, au même endroit.

Chaque valeur peut être changée par une variable d'environnement :
- en local : fichier .env à la racine du dépôt (copie de .env.example) ;
- en ligne : Vercel → Project → Settings → Environment Variables.
"""
import os
from pathlib import Path

try:  # python-dotenv sert seulement en local
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass


def _env(nom, defaut, type_=str):
    valeur = os.getenv(nom)
    return defaut if valeur in (None, "") else type_(valeur)


# --- Clés (secrètes : jamais dans le code ni sur GitHub) ---
SUPABASE_URL = _env("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = _env("SUPABASE_SERVICE_KEY", "")        # sb_secret_… : côté serveur uniquement
CLOUDFLARE_ACCOUNT_ID = _env("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = _env("CLOUDFLARE_API_TOKEN", "")
GROQ_API_KEY = _env("GROQ_API_KEY", "")

# --- Modèles ---
MODELE_EMBEDDING = _env("MODELE_EMBEDDING", "@cf/baai/bge-m3")    # le même que pour les مسائل
DIMENSION = 1024
MODELE_LLM = _env("MODELE_LLM", "openai/gpt-oss-120b")
EFFORT_RAISONNEMENT = _env("EFFORT_RAISONNEMENT", "low")           # gpt-oss : low | medium | high
MAX_TOKENS = _env("MAX_TOKENS", 1024, int)                         # réflexion + réponse

# --- Recherche et sélection des passages ---
NB_CANDIDATS = _env("NB_CANDIDATS", 10, int)       # combien de مسائل demander à chercher_fiqh
SEUIL = _env("SEUIL", 0.45, float)                 # filtre 1 : meilleur score en dessous → abstention
ECART_MAX = _env("ECART_MAX", 0.06, float)         # garder les مسائل à moins de 0,06 du meilleur score
NB_MAX = _env("NB_MAX", 3, int)                    # au plus 3 مسائل retenues
VOISINES = _env("VOISINES", 1, int)                # nombre de voisines de chaque côté (small-to-big)
MAX_CARACTERES = _env("MAX_CARACTERES", 3000, int) # taille maximale du texte envoyé au LLM

# Origines autorisées (seulement si le site et l'API ne sont pas sur le même domaine)
CORS_ORIGINS = _env("CORS_ORIGINS", "http://localhost:5173").split(",")

# Clé courte de chaque livre (utilisée par le frontend dans les adresses et les couleurs)
CLES_LIVRES = {"الرسالة": "risala", "مختصر الأخضري": "akhdari"}

MADHAHIB = [
    {"key": "maliki", "label": "مالكي", "available": True},
    {"key": "hanafi", "label": "حنفي", "available": False},
    {"key": "shafii", "label": "شافعي", "available": False},
    {"key": "hanbali", "label": "حنبلي", "available": False},
]


def variables_manquantes():
    """Noms des clés obligatoires qui ne sont pas remplies."""
    cles = {"SUPABASE_URL": SUPABASE_URL, "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
            "CLOUDFLARE_ACCOUNT_ID": CLOUDFLARE_ACCOUNT_ID, "CLOUDFLARE_API_TOKEN": CLOUDFLARE_API_TOKEN,
            "GROQ_API_KEY": GROQ_API_KEY}
    return [nom for nom, valeur in cles.items() if not valeur]
