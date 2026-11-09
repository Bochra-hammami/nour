"""Traitements de texte arabe partagés par tout le backend.

normaliser() doit rester IDENTIQUE à celle du pipeline (pipeline/risala/decouper_risala.py) :
les questions et les مسائل doivent être transformées de la même façon.
"""
import re

HARAKAT = re.compile(r"[ؐ-ًؚ-ٰٟ]")   # harakat, shadda, sukun, alif suscrit
ALIFS = re.compile("[إأآٱ]")


def normaliser(texte):
    """Version pour la recherche : sans harakat ni tatweel, alifs unifiés."""
    texte = HARAKAT.sub("", texte).replace("ـ", "")
    texte = ALIFS.sub("ا", texte)
    return re.sub(r"\s+", " ", texte).strip()


# ---------- Filtre 3 : retrouver une citation dans un texte ----------

def _mots_seulement(texte):
    """Texte réduit à ses lettres et chiffres (sans harakat ni ponctuation),
    + pour chaque caractère gardé, sa position dans le texte d'origine."""
    sortie, positions = [], []
    espace_en_attente = False
    for i, c in enumerate(texte):
        if HARAKAT.match(c) or c == "ـ":
            continue
        if ALIFS.match(c):
            c = "ا"
        if c.isalnum():
            if espace_en_attente and sortie:
                sortie.append(" ")
                positions.append(i)
            espace_en_attente = False
            sortie.append(c)
            positions.append(i)
        else:
            espace_en_attente = True
    return "".join(sortie), positions


def trouver_citation(texte, citation):
    """Positions [(début, fin), …] de la citation dans le texte, ou None si elle n'y est pas.
    Insensible aux harakat et à la ponctuation. Une citation coupée par « … » est cherchée morceau par morceau."""
    mots, positions = _mots_seulement(texte)
    mots = f" {mots} "
    zones = []
    for morceau in re.split(r"\.\.\.|…", citation):
        cherche, _ = _mots_seulement(morceau)
        if not cherche:
            continue
        i = mots.find(f" {cherche} ")
        if i < 0:
            return None
        debut, fin = i, i + len(cherche) - 1          # +1 espace au début de `mots`, -1 pour le dernier caractère
        zones.append((positions[debut], positions[fin] + 1))
    return zones or None
