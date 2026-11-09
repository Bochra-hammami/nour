# nettoyer_risala.py — LIT al_risala_brut.txt (sans le modifier)
# Crée : donnees/risala_1_nettoye.jsonl  (une ligne par bab)
#        donnees/risala_1_notes.jsonl    (les notes du محقق, une ligne par page)
import json
import re
import unicodedata
from pathlib import Path

ENTREE = "al_risala_brut.txt"
SORTIE = "donnees/risala_1_nettoye.jsonl"
SORTIE_NOTES = "donnees/risala_1_notes.jsonl"

ABWAB = [  # (kitab, titre, page imprimée de début) — d'après le فهرس, édition التتائي/السناري
    ("الطهارة", "باب ما يجب منه الوضوء والغسل", 90),
    ("الطهارة", "باب طهارة الماء والثوب والبقعة وما يجزئ من اللباس في الصلاة", 93),
    ("الطهارة", "باب صفة الوضوء ومسنونه ومفروضه وذكر الاستنجاء والاستجمار", 96),
    ("الطهارة", "باب في الغسل", 104),
    ("الطهارة", "باب في من لم يجد الماء وصفة التيمم", 106),
    ("الطهارة", "باب في المسح على الخفين", 109),
    ("الصلاة", "باب في أوقات الصلاة وأسمائها", 110),
    ("الصلاة", "باب في الأذان والإقامة", 113),
    ("الصلاة", "باب صفة العمل في الصلوات المفروضة وما يتصل بها من النوافل والسنن", 115),
    ("الصلاة", "باب في الإمامة وحكم الإمام والمأموم", 129),
    ("الصلاة", "باب جامع في الصلاة", 131),
    ("الصلاة", "باب في سجود القرآن", 140),
    ("الصلاة", "باب صلاة السفر", 142),
    ("الصلاة", "باب صلاة الجمعة", 144),
    ("الصلاة", "باب في صلاة الخوف", 146),
    ("الصلاة", "باب في صلاة العيدين والتكبير أيام منى", 147),
    ("الصلاة", "باب في صلاة الخسوف", 149),
    ("الصلاة", "باب صلاة الاستسقاء", 151),
    ("الصلاة", "باب ما يفعل بالمحتضر وفي غسل الميت وكفنه وتحنيطه وحمله ودفنه", 152),
    ("الصلاة", "باب في الصلاة على الجنائز والدعاء للميت", 156),
    ("الصلاة", "باب في الدعاء للطفل والصلاة عليه وغسله", 161),
]

HARAKAT = "\u064b-\u0652\u0670"          # fatha … sukun + alif suscrit (plage Unicode)
APPEL = re.compile(r"\s*\([٠-٩]+\)")      # appel de note : (١) (١٢)
MANUSCRIT = re.compile(r"/\s*[أخج]\s*[٠-٩]+\s*[أب]?\s*/")   # / خ ٦٥ ب/  ou  / أ ٨٠/
SOUS_TITRE = re.compile(r"\[\[\s*(.+?)\s*:?\s*\]\]")         # [[أسباب الحدث:]]
SOUS_TITRE_SIMPLE = re.compile(r"(?<!\[)\[([^\[\]]{2,60}?):\](?!\])")   # [مَنْ نسي سجود السهو:] (4 cas)
EGAL = re.compile(r"\s*=\s*")                                    # « = » : signe du محقق entre condition et réponse
MOT_AJOUTE = re.compile(r"\[(?!آية )([^\[\]]+)\]")             # [في] -> في  (mais [آية ١٥] reste entre crochets)
ESPACE_MANQUANT = re.compile(r"([.؟!:؛])(?=[^\s\d.،:؛)\]»\"⟧])")   # «البولِ.وأمَّا» -> «البولِ. وأمَّا»
CORRECTIONS = {  # fautes de frappe trouvées dans la source elle-même : {texte fautif: texte corrigé}
    "رُكْبَتَيْهِوأسافلَ": "رُكْبَتَيْهِ وأسافلَ",   # باب في الغسل : deux mots collés
    "إِنَّانَسْتَجِيرُ": "إِنَّا نَسْتَجِيرُ",       # باب الجنائز (دعاء) : deux mots collés
}

# ---------- 1. découper par page ----------
def lire_pages(chemin):
    """-> liste de (page_imprimee, contenu_brut)"""
    texte = Path(chemin).read_text(encoding="utf-8")
    morceaux = re.split(r"^\[page_site \d+ \| ص (\d+)\]\n", texte, flags=re.M)
    # morceaux = ["", "90", "contenu…", "91", "contenu…", …]
    return [(int(morceaux[i]), morceaux[i + 1].strip()) for i in range(1, len(morceaux), 2)]


# ---------- 2. séparer texte et notes ----------
def separer_notes(contenu):
    """Les notes commencent au 2e «(١)» de la page (vérifié sur les 71 pages)."""
    positions = [m.start() for m in re.finditer(r"\(١\)", contenu)]
    if len(positions) < 2:
        return contenu, ""
    return contenu[:positions[1]], contenu[positions[1]:]


# ---------- 3 à 7. nettoyer le texte d'une page ----------
def nettoyer_texte(texte):
    texte = unicodedata.normalize("NFC", texte)                    # 0. même ordre des harakat partout
    for fautif, correct in CORRECTIONS.items():                    #    puis corrections à la main
        texte = texte.replace(unicodedata.normalize("NFC", fautif), unicodedata.normalize("NFC", correct))
    texte = APPEL.sub(" ", texte)                                  # 3. appels de note (-> espace :
    texte = re.sub(r"\s+([.،:؛؟!])", r"\1", texte)                #    «وكفنه(٣)وتحنيطه» reste séparé)
    texte = MANUSCRIT.sub(" ", texte)                              # 4. repères des manuscrits
    texte = SOUS_TITRE.sub(r" ⟦عنوان: \1⟧ ", texte)                # 5. sous-titres -> repère
    texte = SOUS_TITRE_SIMPLE.sub(r" ⟦عنوان: \1⟧ ", texte)         #    (aussi ceux à crochets simples)
    texte = EGAL.sub(" ", texte)                                   # 5b. signes « = »
    texte = MOT_AJOUTE.sub(r"\1", texte)                           # 6. [في] -> في
    texte = ESPACE_MANQUANT.sub(r"\1 ", texte)                     # 7. espace après . : ؟
    return re.sub(r"\s+", " ", texte).strip()


# ---------- 8. repérer les abwab ----------
def motif_souple(titre):
    """Regex qui trouve le titre même avec harakat et variantes d'alif / ya / ta marbuta."""
    variantes = {"ا": "[اأإآ]", "أ": "[اأإآ]", "إ": "[اأإآ]", "آ": "[اأإآ]",
                 "ي": "[يى]", "ى": "[يى]", "ة": "[ةه]", "ه": "[ةه]"}
    morceaux = []
    for lettre in titre:
        if lettre == " ":
            morceaux.append(r"\s+")
        else:
            morceaux.append(variantes.get(lettre, re.escape(lettre)) + f"[{HARAKAT}]*")
    return re.compile("".join(morceaux))


def trouver_abwab(texte):
    """-> liste de (debut_titre, fin_titre) pour chaque bab, dans l'ordre."""
    positions, depart = [], 0
    for kitab, titre, page in ABWAB:
        repere = texte.find(f"⟦ص {page}⟧", depart)                # on cherche à partir de sa page
        if repere < 0:
            raise SystemExit(f"Page {page} introuvable pour «{titre}»")
        # on cherche le début du titre (4 premiers mots), puis on avale le reste du titre s'il est là
        debut = motif_souple(" ".join(titre.split()[:4])).search(texte, repere)
        if debut is None:
            raise SystemExit(f"Titre introuvable : «{titre}» (page {page})")
        complet = motif_souple(titre).match(texte, debut.start())
        fin = complet.end() if complet else debut.end()
        positions.append((debut.start(), fin))
        depart = fin
    return positions


def page_a(texte, position):
    """Dernier repère ⟦ص N⟧ avant cette position."""
    pages = re.findall(r"⟦ص (\d+)⟧", texte[:position + 1])
    return int(pages[-1])


# ---------- programme principal ----------
pages = lire_pages(ENTREE)
if len(pages) != 71:
    raise SystemExit(f"STOP : {len(pages)} pages au lieu de 71")

morceaux, notes = [], []
for page, contenu in pages:
    texte, note = separer_notes(contenu)
    morceaux.append(f"⟦ص {page}⟧ {nettoyer_texte(texte)}")
    notes.append({"page": page, "notes": note.strip()})
tout = " ".join(morceaux)                                          # pages recollées

abwab = trouver_abwab(tout)
lignes = []
for i, ((kitab, titre, _), (debut, fin)) in enumerate(zip(ABWAB, abwab), start=1):
    fin_bab = abwab[i][0] if i < len(abwab) else len(tout)
    # un repère ⟦ص N⟧ juste avant le bab suivant appartient au bab suivant : on l'enlève
    corps = re.sub(r"(\s*⟦ص \d+⟧)+\s*$", "", tout[fin:fin_bab]).rstrip(" .،")
    lignes.append({
        "kitab": kitab, "bab": titre, "ordre_bab": i,
        "page_debut": page_a(tout, debut), "page_fin": page_a(tout, fin + len(corps) - 1),
        "texte": corps.lstrip(" .،:"),
    })

Path(SORTIE).parent.mkdir(parents=True, exist_ok=True)
for chemin, donnees in [(SORTIE, lignes), (SORTIE_NOTES, notes)]:
    with open(chemin, "w", encoding="utf-8") as f:
        for d in donnees:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"{len(donnees)} lignes écrites dans {chemin}")