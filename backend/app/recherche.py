"""Tout ce qui parle à Supabase (par son API REST, avec la clé secrète, côté serveur uniquement) :
- charger les 269 مسائل en mémoire au démarrage (textes, pas les vecteurs) → Corpus ;
- chercher les مسائل les plus proches d'un vecteur (fonction SQL chercher_fiqh) ;
- trouver les voisines d'une مسألة (small-to-big), directement dans le Corpus en mémoire.
"""
from dataclasses import dataclass, field

import httpx

from . import config


@dataclass
class Masala:
    """Une ligne de fiqh_chunks : une مسألة (ou une partie d'une longue مسألة)."""
    cle: str            # ex. "risala-38-2" (livre-ordre-partie)
    id: int
    livre: str          # "risala" | "akhdari"
    bab_index: int      # ordre_bab
    bab: str
    section: str | None
    ordre: int
    partie: int
    page: int | None
    texte: str          # texte_affichage (avec harakat)
    numero: str = ""    # numéro affiché dans le lecteur : "38" ou "38/2"


@dataclass
class Livre:
    cle: str
    titre: str
    auteur: str
    madhhab: str
    babs: dict = field(default_factory=dict)   # bab_index -> {"index", "title", "cles": [...]}


class Corpus:
    """Les livres et leurs مسائل, en mémoire (≈150 Ko) : lecture rapide et voisines sans requête SQL."""

    def __init__(self, lignes):
        self.livres: dict[str, Livre] = {}
        self.masail: dict[str, Masala] = {}
        self.par_id: dict[int, Masala] = {}
        self._position: dict[str, tuple] = {}   # cle -> (liste des clés de sa section, position)

        lignes = sorted(lignes, key=lambda l: (l["matn_id"], l["ordre"], l["partie"]))
        nb_parties = {}
        for l in lignes:
            nb_parties[(l["matn_id"], l["ordre"])] = nb_parties.get((l["matn_id"], l["ordre"]), 0) + 1

        sections = {}
        for l in lignes:
            m = l["matns"]
            cle_livre = config.CLES_LIVRES.get(m["titre"], f"matn{l['matn_id']}")
            livre = self.livres.setdefault(cle_livre, Livre(cle_livre, m["titre"], m["auteur"], m["madhhab"]))
            multi = nb_parties[(l["matn_id"], l["ordre"])] > 1
            masala = Masala(
                cle=f"{cle_livre}-{l['ordre']}-{l['partie']}", id=l["id"], livre=cle_livre,
                bab_index=l["ordre_bab"], bab=l["bab"], section=l["section"], ordre=l["ordre"],
                partie=l["partie"], page=l["page"], texte=l["texte_affichage"],
                numero=f"{l['ordre']}/{l['partie']}" if multi else str(l["ordre"]))
            self.masail[masala.cle] = masala
            self.par_id[masala.id] = masala
            bab = livre.babs.setdefault(masala.bab_index, {"index": masala.bab_index, "title": masala.bab, "cles": []})
            bab["cles"].append(masala.cle)
            sections.setdefault((cle_livre, masala.bab_index, masala.section), []).append(masala.cle)

        for cles in sections.values():
            for i, cle in enumerate(cles):
                self._position[cle] = (cles, i)

    def section_de(self, cle):
        """Les clés de toutes les مسائل de la même section, dans l'ordre du livre (tuple)."""
        return tuple(self._position[cle][0])

    def voisines(self, cle, n=1):
        """La مسألة + ses n voisines de chaque côté, dans la même section du même bab, dans l'ordre du livre."""
        cles, i = self._position[cle]
        return cles[max(0, i - n): i + n + 1]


class Supabase:
    def __init__(self):
        cle = config.SUPABASE_SERVICE_KEY
        entetes = {"apikey": cle, "Content-Type": "application/json"}
        if cle.startswith("eyJ"):  # ancienne clé service_role (JWT) : il faut aussi cet en-tête
            entetes["Authorization"] = f"Bearer {cle}"
        self.http = httpx.Client(base_url=config.SUPABASE_URL.rstrip("/") + "/rest/v1",
                                 headers=entetes, timeout=30)

    @staticmethod
    def _verifier(r):
        if r.status_code >= 400:
            raise RuntimeError(f"Erreur Supabase {r.status_code} : {r.text[:300]}")
        return r

    def charger_corpus(self):
        """Lit toutes les مسائل (sans les vecteurs), 1000 par 1000."""
        colonnes = "id,matn_id,kitab,bab,ordre_bab,section,ordre,partie,page,texte_affichage,matns(titre,auteur,madhhab)"
        lignes, debut = [], 0
        while True:
            r = self._verifier(self.http.get("/fiqh_chunks", params={"select": colonnes, "order": "id"},
                                             headers={"Range": f"{debut}-{debut + 999}"}))
            paquet = r.json()
            lignes += paquet
            if len(paquet) < 1000:
                return Corpus(lignes)
            debut += 1000

    def chercher(self, vecteur, madhhab, nb):
        """Appelle la fonction SQL chercher_fiqh → les nb مسائل les plus proches, avec leur similarité."""
        texte_vecteur = "[" + ",".join(f"{x:.7f}" for x in vecteur) + "]"
        r = self._verifier(self.http.post("/rpc/chercher_fiqh", json={
            "question_embedding": texte_vecteur, "p_madhhab": madhhab, "nb": nb}))
        return r.json()

    def ping(self):
        """Petite requête pour /api/health?deep=1 (et le ping quotidien qui empêche Supabase de s'endormir)."""
        self._verifier(self.http.get("/matns", params={"select": "id", "limit": "1"}))
        return True
