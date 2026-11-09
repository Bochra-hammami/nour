# decouper_risala.py — LIT donnees/risala_1_nettoye.jsonl (sans le modifier)
# Crée : donnees/risala_2_masail.jsonl  (une ligne par مسألة, ou par partie d'une longue مسألة)
import json
import re
from pathlib import Path

ENTREE = "donnees/risala_1_nettoye.jsonl"
SORTIE = "donnees/risala_2_masail.jsonl"
MATN = "الرسالة"
TAILLE_MAX = 800          # au-delà, une مسألة est recoupée en parties

# Premiers mots qui CONTINUENT la مسألة précédente (comparés sans harakat)
SUITE = {"ثم", "وقيل", "وكذلك", "وكذا", "وذلك", "إلا", "الا", "اللهم", "أو", "او"}
# Premiers mots sans « و » qui OUVRENT quand même une nouvelle مسألة
OUVRE_SANS_WAW = {"من", "إذا", "اذا", "إن", "ان"}
# Après « ؛ » (lien fort avec la phrase d'avant), seuls ces mots ouvrent une nouvelle مسألة
OUVRE_APRES_POINT_VIRGULE = {"ومن", "وإن", "وان", "وإذا", "واذا", "وأما", "واما", "ويجب", "ويستحب",
                             "ويكره", "ولا", "وليس", "وكل"}

HARAKAT = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670]")   # harakat, shadda, sukun, alif suscrit
REPERE_PAGE = re.compile(r"⟦ص (\d+)⟧")
SOUS_TITRE = re.compile(r"⟦عنوان: ([^⟧]*)⟧")
FIN_PHRASE = re.compile(r"(?<=[.؛])\s+")                     # coupe après « . » ou « ؛ »
REF_AYA = re.compile(r"\s*\[آية [٠-٩]+\]")                   # [آية ١٥] : gardé à l'affichage, pas pour chercher


def normaliser(texte):
    """Version pour la recherche : sans harakat ni tatweel, alifs unifiés.
    (Plus tard, cette fonction ira dans outils/ pour être partagée avec le backend.)"""
    texte = HARAKAT.sub("", texte).replace("ـ", "")
    texte = re.sub("[إأآٱ]", "ا", texte)
    return re.sub(r"\s+", " ", texte).strip()


def sans_reperes(texte):
    """Enlève les repères ⟦ص N⟧ et ⟦عنوان: …⟧ pour l'affichage."""
    return re.sub(r"\s+", " ", re.sub(r"⟦[^⟧]*⟧", " ", texte)).strip()


def premier_mot(phrase):
    """Premier mot de la phrase, sans harakat ni ponctuation (pour décider, jamais pour afficher)."""
    mots = HARAKAT.sub("", sans_reperes(phrase)).split()
    return mots[0].strip("-–«\"(:،") if mots else ""


def ouvre_une_masala(phrase, apres_point_virgule=False):
    mot = premier_mot(phrase)
    if apres_point_virgule:
        return mot in OUVRE_APRES_POINT_VIRGULE
    if mot in SUITE or mot.rstrip(":") in SUITE:
        return False
    if mot.startswith("ف") and mot != "في":     # فإن، فإذا، فلا، فيكون… = conséquence
        return False
    return mot.startswith("و") or mot in OUVRE_SANS_WAW


# ---------- niveau 1 : sections ----------
def sections(texte_bab):
    """-> liste de (titre_section ou None, texte). Le texte avant le 1er sous-titre a pour titre None."""
    morceaux = SOUS_TITRE.split(texte_bab)            # ["avant", "titre1", "texte1", "titre2", …]
    resultat = [(None, morceaux[0])] if morceaux[0].strip() else []
    for i in range(1, len(morceaux), 2):
        resultat.append((morceaux[i].strip(), morceaux[i + 1]))
    return resultat


# ---------- niveaux 2 et 3 : phrases, puis مسائل ----------
def masail(texte_section):
    """Coupe en phrases, puis colle chaque phrase « suite » à la مسألة en cours."""
    groupes = []
    for phrase in FIN_PHRASE.split(texte_section.strip()):
        if groupes and not sans_reperes(phrase):       # un repère ⟦ص N⟧ seul : on le colle
            groupes[-1] += " " + phrase
            continue
        apres_pv = bool(groupes) and sans_reperes(groupes[-1]).endswith("؛")
        if not groupes or ouvre_une_masala(phrase, apres_pv):
            groupes.append(phrase)
        else:
            groupes[-1] += " " + phrase
    return [g for g in groupes if g and sans_reperes(g)]


# ---------- niveau 4 : recouper les مسائل trop longues ----------
def recouper(texte):
    """Coupe une longue مسألة en parties ≤ TAILLE_MAX : d'abord aux fins de phrase,
    sinon à « ، » suivie d'un mot en « و », sinon au dernier espace."""
    if len(sans_reperes(texte)) <= TAILLE_MAX:
        return [texte]
    unites = FIN_PHRASE.split(texte)
    if len(unites) == 1:
        unites = re.split(r"(?<=،)\s+(?=\S*و)", texte)
    parties, courant = [], ""
    for u in unites:
        if courant and len(sans_reperes(courant + " " + u)) > TAILLE_MAX:
            parties.append(courant)
            courant = u
        else:
            courant = (courant + " " + u).strip()
    parties.append(courant)
    final = []                                         # filet de sécurité : morceau encore trop long
    for p in parties:
        while len(p) > TAILLE_MAX * 1.5:
            coupe = p.rfind(" ", 0, TAILLE_MAX)
            final.append(p[:coupe])
            p = p[coupe:].strip()
        final.append(p)
    return final


# ---------- programme principal ----------
abwab = [json.loads(l) for l in Path(ENTREE).read_text(encoding="utf-8").splitlines() if l.strip()]
lignes, ordre = [], 0

for bab in abwab:
    page = bab["page_debut"]                           # page courante, mise à jour aux repères ⟦ص N⟧
    for titre_section, texte_section in sections(bab["texte"]):
        for masala in masail(texte_section):
            ordre += 1
            for n, partie in enumerate(recouper(masala), start=1):
                debut = partie.lstrip()
                if debut.startswith("⟦ص"):              # la partie commence sur une nouvelle page
                    page = int(REPERE_PAGE.match(debut).group(1))
                affichage = sans_reperes(partie)
                contexte = " › ".join(x for x in [MATN, bab["bab"], titre_section] if x)
                lignes.append({
                    "matn": MATN, "kitab": bab["kitab"], "bab": bab["bab"], "ordre_bab": bab["ordre_bab"],
                    "section": titre_section, "ordre": ordre, "partie": n, "page": page,
                    "texte_affichage": affichage,
                    "texte_recherche": normaliser(REF_AYA.sub("", affichage)),
                    "texte_embedding": normaliser(f"{contexte} › {REF_AYA.sub('', affichage)}"),
                })
                pages_vues = REPERE_PAGE.findall(partie)
                if pages_vues:                         # la partie finit sur une autre page
                    page = int(pages_vues[-1])

# ---------- vérifications ----------
avant = normaliser(" ".join(sans_reperes(b["texte"]) for b in abwab)).replace(" ", "")
apres = normaliser(" ".join(l["texte_affichage"] for l in lignes)).replace(" ", "")
if avant != apres:
    raise SystemExit("STOP : du texte a été perdu ou dupliqué pendant le découpage")

tailles = sorted(len(l["texte_affichage"]) for l in lignes)
print(f"{ordre} مسائل -> {len(lignes)} lignes (avec les parties)")
print(f"tailles : min {tailles[0]}, médiane {tailles[len(tailles) // 2]}, max {tailles[-1]} caractères")
print("aucun texte perdu ni dupliqué ✔")

Path(SORTIE).parent.mkdir(parents=True, exist_ok=True)
with open(SORTIE, "w", encoding="utf-8") as f:
    for l in lignes:
        f.write(json.dumps(l, ensure_ascii=False) + "\n")
print(f"{len(lignes)} lignes écrites dans {SORTIE}")
