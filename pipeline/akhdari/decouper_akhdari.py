# decouper_akhdari.py — LIT al_akhdari_source.txt et akhdari_shamela_openiti.txt (sans les modifier)
# Crée : donnees/akhdari_2_masail.jsonl  (une ligne par مسألة, même format que la Risala)
import json
import re
from pathlib import Path

SOURCE = "al_akhdari_source.txt"             # version de l'ami + 2 فصول (eau, impuretés)
SHAMELA = "akhdari_shamela_openiti.txt"       # texte Shamela n° 31995 (OpenITI) : sert seulement pour les pages
SORTIE = "donnees/akhdari_2_masail.jsonl"
MATN = "مختصر الأخضري"
TAILLE_MAX = 800
ABWAB_TAHARA = {"باب في الطهارة", "باب في التيمم", "باب في الحيض", "باب في النفاس"}   # les autres = الصلاة

# Mêmes règles que decouper_risala.py
SUITE = {"ثم", "وقيل", "وكذلك", "وكذا", "وذلك", "إلا", "الا", "اللهم", "أو", "او",
         "والثاني", "والثالث", "والأسباب", "والاسباب"}       # suites d'une énumération (أحدهما… والثاني…)
OUVRE_SANS_WAW = {"من", "إذا", "اذا", "إن", "ان"}
OUVRE_APRES_POINT_VIRGULE = {"ومن", "وإن", "وان", "وإذا", "واذا", "وأما", "واما", "ويجب", "ويستحب",
                             "ويكره", "ولا", "وليس", "وكل"}
HARAKAT = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670]")
LETTRES_SEULES = re.compile(r"[^\u0621-\u064a\u064b-\u0652\s]")   # garde seulement les lettres arabes et les harakat
FIN_PHRASE = re.compile(r"(?<=[.؛])\s+")


def normaliser(texte):
    texte = HARAKAT.sub("", texte).replace("ـ", "")
    texte = re.sub("[إأآٱ]", "ا", texte)
    return re.sub(r"\s+", " ", texte).strip()


def premier_mot(phrase):
    mots = HARAKAT.sub("", phrase).split()
    return mots[0].strip("-–«\"(:،") if mots else ""


def ouvre_une_masala(phrase, apres_point_virgule=False):
    mot = premier_mot(phrase)
    if apres_point_virgule:
        return mot in OUVRE_APRES_POINT_VIRGULE
    if mot in SUITE or mot.rstrip(":") in SUITE:
        return False
    if mot.startswith("ف") and mot != "في":
        return False
    return mot.startswith("و") or mot in OUVRE_SANS_WAW


# ---------- 1. lire le livre : abwab et paragraphes ----------
def lire_abwab(chemin):
    """-> liste de (titre_bab, [paragraphes]). Une ligne « باب … » ouvre un bab ; une ligne vide sépare les paragraphes."""
    texte = Path(chemin).read_text(encoding="utf-8").replace("\r\n", "\n")
    abwab = []
    for bloc in re.split(r"\n\s*\n", texte):
        lignes = [l.strip() for l in bloc.split("\n") if l.strip()]
        if not lignes:
            continue
        if lignes[0].startswith("باب "):                       # titre de bab (seul sur sa ligne)
            abwab.append((lignes[0], []))
            lignes = lignes[1:]
        if lignes:
            abwab[-1][1].append(" ".join(lignes))              # une coupure de ligne simple = même paragraphe
    return abwab


# ---------- 2. le titre de section de chaque paragraphe ----------
def section_de(paragraphe, section_parente):
    """« فصل: فرائض الوضوء سبع: … » -> « فرائض الوضوء سبع » ; « (وسننه): … » -> « فرائض الوضوء سبع — وسننه » ;
    « سنن الصلاة: … » -> « سنن الصلاة ». Renvoie (section de ce paragraphe, section parente pour les suivants)."""
    m = re.match(r"^\(([^)]{2,30})\)", paragraphe)              # (وسننه) (وفضائله) (ونواقضه)…
    if m:
        nom = m.group(1).strip()
        return (f"{section_parente} — {nom}" if section_parente else nom), section_parente
    f = re.match(r"^فصل\s*:\s*", paragraphe)
    reste = paragraphe[f.end():] if f else paragraphe
    t = re.match(r"^([^:،.()]{2,40}?)\s*:", reste)              # « فرائض الوضوء سبع: »
    if f or (t and len(t.group(1).split()) <= 4):
        titre = (t.group(1) if t else " ".join(reste.split()[:5])).strip(" ،.")
        return titre, titre
    return section_parente, section_parente


# ---------- 3. les مسائل d'un paragraphe ----------
def masail(paragraphe):
    groupes = []
    for phrase in FIN_PHRASE.split(paragraphe.strip()):
        if not phrase.strip():
            continue
        apres_pv = bool(groupes) and groupes[-1].endswith("؛")
        if not groupes or ouvre_une_masala(phrase, apres_pv):
            groupes.append(phrase)
        else:
            groupes[-1] += " " + phrase
    return groupes


def recouper(texte):
    if len(texte) <= TAILLE_MAX:
        return [texte]
    unites = re.split(r"(?<=،)\s+(?=\S*و)", texte) if len(FIN_PHRASE.split(texte)) == 1 else FIN_PHRASE.split(texte)
    parties, courant = [], ""
    for u in unites:
        if courant and len(courant) + 1 + len(u) > TAILLE_MAX:
            parties.append(courant)
            courant = u
        else:
            courant = (courant + " " + u).strip()
    parties.append(courant)
    return parties


# ---------- 4. les pages, retrouvées dans le texte Shamela ----------
def mots_avec_pages(chemin):
    """Texte Shamela -> liste de (mot normalisé, page). « PageV01P004 » marque la FIN de la page 4."""
    texte = Path(chemin).read_text(encoding="utf-8")
    texte = texte[texte.find("#META#Header#End#") + len("#META#Header#End#"):]
    mots, page = [], 1
    for jeton in re.split(r"(PageV\d+P\d+)", texte):
        m = re.match(r"PageV\d+P(\d+)", jeton)
        if m:
            page = int(m.group(1)) + 1
            continue
        propre = re.sub(r"ms\d+|###|\| AUTO|~~|#", " ", jeton)
        for mot in normaliser(LETTRES_SEULES.sub(" ", propre)).split():
            mots.append((mot, page))
    return mots


def trouver_page(debut_masala, mots_shamela, depart):
    """Cherche les 5 premiers mots de la مسألة dans le texte Shamela, à partir de `depart`. -> (page, nouvelle position).
    Les étiquettes ajoutées par l'ami (« فصل: », « سنن الصلاة: »…) ne sont pas dans la Shamela : on réessaie sans elles."""
    seulement_mots = [m for m, _ in mots_shamela]
    sans_etiquette = re.sub(r"^\s*(فصل\s*:\s*)?(\([^)]*\)\s*:?\s*)?", "", debut_masala)
    apres_deux_points = debut_masala.split(":", 1)[1] if ":" in debut_masala[:40] else debut_masala
    for essai in (debut_masala, sans_etiquette, apres_deux_points):
        cible = normaliser(LETTRES_SEULES.sub(" ", essai)).split()[:5]
        for i in range(depart, len(seulement_mots) - len(cible) + 1):
            if seulement_mots[i:i + len(cible)] == cible:
                return mots_shamela[i][1], i
    return None, depart


# ---------- programme principal ----------
abwab = lire_abwab(SOURCE)
mots_shamela = mots_avec_pages(SHAMELA)
lignes, ordre, position, sans_page = [], 0, 0, 0

for ordre_bab, (bab, paragraphes) in enumerate(abwab, start=1):
    kitab = "الطهارة" if bab in ABWAB_TAHARA else "الصلاة"
    parente = None
    for paragraphe in paragraphes:
        section, parente = section_de(paragraphe, parente)
        for masala in masail(paragraphe):
            ordre += 1
            for n, partie in enumerate(recouper(masala), start=1):
                page, position = trouver_page(partie, mots_shamela, position)
                sans_page += page is None
                contexte = " › ".join(x for x in [MATN, bab, section] if x)
                lignes.append({
                    "matn": MATN, "kitab": kitab, "bab": bab, "ordre_bab": ordre_bab,
                    "section": section, "ordre": ordre, "partie": n, "page": page,
                    "texte_affichage": partie,
                    "texte_recherche": normaliser(partie),
                    "texte_embedding": normaliser(f"{contexte} › {partie}"),
                })

# ---------- vérifications ----------
avant = normaliser(" ".join(" ".join(p) for _, p in abwab)).replace(" ", "")
apres = normaliser(" ".join(l["texte_affichage"] for l in lignes)).replace(" ", "")
if avant != apres:
    raise SystemExit("STOP : du texte a été perdu ou dupliqué pendant le découpage")

tailles = sorted(len(l["texte_affichage"]) for l in lignes)
print(f"{len(abwab)} abwab, {ordre} مسائل -> {len(lignes)} lignes (avec les parties)")
print(f"tailles : min {tailles[0]}, médiane {tailles[len(tailles) // 2]}, max {tailles[-1]} caractères")
print(f"pages retrouvées : {len(lignes) - sans_page}/{len(lignes)}")
print("aucun texte perdu ni dupliqué ✔")

Path(SORTIE).parent.mkdir(parents=True, exist_ok=True)
with open(SORTIE, "w", encoding="utf-8") as f:
    for l in lignes:
        f.write(json.dumps(l, ensure_ascii=False) + "\n")
print(f"{len(lignes)} lignes écrites dans {SORTIE}")
