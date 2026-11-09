"""Appels aux deux services externes (simples requêtes HTTP, sans GPU ni gros modèle) :
- Cloudflare Workers AI : texte → vecteur BGE-M3 (1024 nombres) ;
- Groq : messages → réponse du LLM.
"""
import math
import time

import httpx

from . import config


def _normaliser_vecteur(v):
    norme = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norme for x in v]


def _post(http, url, donnees, essais=3):
    """POST avec quelques nouvelles tentatives si le service est saturé (429) ou en panne (5xx)."""
    for essai in range(essais):
        r = http.post(url, json=donnees)
        if (r.status_code == 429 or r.status_code >= 500) and essai < essais - 1:
            attente = float(r.headers.get("retry-after", 0) or 0) or 1.5 * (essai + 1)
            time.sleep(min(attente, 8))
            continue
        if r.status_code == 429:
            raise RuntimeError("الخدمة مشغولة حاليًا (تجاوز حد الطلبات)، أعد المحاولة بعد دقيقة.")
        if r.status_code >= 400:
            raise RuntimeError(f"Erreur HTTP {r.status_code} de {httpx.URL(url).host} : {r.text[:300]}")
        return r


class Cloudflare:
    """BGE-M3 hébergé par Cloudflare (gratuit : 10 000 neurons par jour)."""

    def __init__(self):
        self.url = (f"https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}"
                    f"/ai/run/{config.MODELE_EMBEDDING}")
        self.http = httpx.Client(timeout=60, headers={"Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}"})

    def vecteur(self, texte):
        """Un texte (déjà normalisé) → son vecteur de 1024 nombres, de longueur 1."""
        corps = _post(self.http, self.url, {"text": [texte]}).json()
        if not corps.get("success", True) or "result" not in corps:
            raise RuntimeError(f"Erreur Cloudflare : {corps.get('errors')}")
        v = corps["result"]["data"][0]
        if len(v) != config.DIMENSION:
            raise RuntimeError(f"Vecteur de taille inattendue : {len(v)}")
        return _normaliser_vecteur(v)


class Groq:
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        self.http = httpx.Client(timeout=90, headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"})

    def repondre(self, messages):
        """Messages (système + utilisateur) → (texte de la réponse, nombre de tokens utilisés)."""
        donnees = {"model": config.MODELE_LLM, "messages": messages, "temperature": 0,
                   "max_completion_tokens": config.MAX_TOKENS}
        if config.MODELE_LLM.startswith("openai/gpt-oss"):
            # Modèle qui « réfléchit » avant de répondre : réflexion courte et cachée de la réponse.
            donnees["reasoning_effort"] = config.EFFORT_RAISONNEMENT
            donnees["include_reasoning"] = False
        corps = _post(self.http, self.URL, donnees).json()
        choix = corps["choices"][0]
        texte = (choix["message"].get("content") or "").strip()
        if not texte:
            if choix.get("finish_reason") == "length":
                raise RuntimeError("النموذج استهلك حدّ الرموز قبل أن يجيب (زد MAX_TOKENS).")
            raise RuntimeError("لم يُرجع النموذج أي جواب.")
        return texte, corps.get("usage", {}).get("total_tokens", 0)
