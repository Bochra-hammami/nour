"""Le chef d'orchestre : question → réponse vérifiée.

1. normaliser la question                        (texte.py)
2. question → vecteur                            (clients.py : Cloudflare)
3. vecteur → ~10 مسائل candidates + scores        (recherche.py : chercher_fiqh)
4. FILTRE 1 : meilleur score < SEUIL → abstention, sans appeler le LLM
5. garder les مسائل proches du meilleur score (NB_MAX au plus)
6. ajouter les voisines (small-to-big), fusionner, limiter la taille
7. prompt → réponse                               (clients.py : Groq)
8. FILTRE 2 : le LLM a répondu « لم يرد في النص… » → abstention
9. FILTRE 3 : chaque citation «…» doit exister mot pour mot dans les passages
"""
import re
import time

from . import config
from .texte import normaliser, trouver_citation

ABSTENTION = "لم يرد في النص ما يجيب عن هذا السؤال."

PROMPT_SYSTEME = f"""أنت مساعد يستخرج الأحكام من نصوص فقهية من المذهب المالكي، ولست مفتيًا.

طريقة العمل:
1. حدّد ما يُسأل عنه بالضبط: حكم، أو وقت، أو عدد، أو سبب، أو شرط، أو كيفية.
2. المقطع الواحد قد يجمع مسائل كثيرة متقاربة الألفاظ. اختر الجملة التي تجيب عن السؤال فعلًا، لا الجملة التي تشترك معه في الكلمات فقط.
3. قدّم القاعدة العامة التي ينصّ عليها الكتاب على المسائل المتفرعة عنها (مثل: «ومن نسي…»، «وإن طال…»، «إلا أن…»)، ولا تذكر المتفرعات إلا إذا سأل عنها السؤال.
4. لا تكتب في الجواب إلا ما تدل عليه الجمل التي نقلتها، ولا تستعمل أي معلومة من خارج المقاطع.
5. لا تُضف حكمًا أو وصفًا (واجب، سنة، فضيلة، مكروه...) إلا إذا ورد حرفيًا في النص.
6. انقل كل جملة يقوم عليها الجواب حرفيًا بين «» دون تغيير أي كلمة، مع رقم المقطع بين معقوفين. إن احتجت جملتين فانقل الاثنتين.
7. إن ذكر الكتابان المسألة فاذكر عبارة كل كتاب مع رقمه.
8. إن لم تُجب المقاطع عن السؤال صراحة، اكتب هذه الجملة فقط: {ABSTENTION}

صيغة الإجابة:
الجواب: جملة أو جملتان.
الدليل: «نص منقول حرفيًا» [رقم المقطع]
الدليل: «نص منقول حرفيًا» [رقم المقطع] (عند الحاجة)"""

CITATION = re.compile(r"«([^»]+)»\s*(?:\[(\d+)\])?")
JAWAB = re.compile(r"الجواب\s*:\s*(.*?)(?=\n\s*الدليل\s*:|$)", re.S)


class Rag:
    def __init__(self, corpus, supabase, cloudflare, groq):
        self.corpus, self.supabase, self.cloudflare, self.groq = corpus, supabase, cloudflare, groq

    # ---------- étapes 1 à 3 : recherche ----------
    def candidats(self, question, madhhab):
        vecteur = self.cloudflare.vecteur(normaliser(question))
        lignes = self.supabase.chercher(vecteur, madhhab, config.NB_CANDIDATS)
        resultat = []
        for l in lignes:
            masala = self.corpus.par_id.get(l["id"])
            if masala:  # ligne ajoutée après le démarrage du serveur : ignorée jusqu'au prochain redémarrage
                resultat.append((masala, float(l["similarite"])))
        return sorted(resultat, key=lambda c: -c[1])

    # ---------- étapes 4 à 6 : sélection ----------
    def passages(self, candidats):
        if not candidats or candidats[0][1] < config.SEUIL:      # FILTRE 1
            return []
        meilleur = candidats[0][1]
        gardes = [c for c in candidats if c[1] >= meilleur - config.ECART_MAX][:config.NB_MAX]

        scores = {m.cle: s for m, s in gardes}       # les مسائل trouvées par la recherche, avec leur score
        a_envoyer = set()                            # + leurs voisines (small-to-big)
        for masala, _ in gardes:
            a_envoyer.update(self.corpus.voisines(masala.cle, config.VOISINES))

        # On parcourt chaque section dans l'ordre du livre et on fait des blocs de مسائل qui se suivent :
        # deux مسائل voisines forment un seul bloc, et aucune مسألة n'est envoyée deux fois.
        blocs = []
        for section in {self.corpus.section_de(c) for c in a_envoyer}:
            bloc = []
            for cle in section:
                if cle in a_envoyer:
                    bloc.append(cle)
                elif bloc:
                    blocs.append(bloc)
                    bloc = []
            if bloc:
                blocs.append(bloc)

        resultat = []
        for cles in blocs:
            principale = max((c for c in cles if c in scores), key=scores.get)   # la مسألة trouvée du bloc
            resultat.append({"cles": cles, "principale": principale, "score": scores[principale],
                             "texte": " ".join(self.corpus.masail[c].texte for c in cles)})
        resultat.sort(key=lambda p: -p["score"])

        # Limite de taille : le meilleur passage d'abord, puis les autres tant que ça rentre
        gardes_finaux, total = [], 0
        for p in resultat:
            if gardes_finaux and total + len(p["texte"]) > config.MAX_CARACTERES:
                break
            gardes_finaux.append(p)
            total += len(p["texte"])
        return gardes_finaux

    # ---------- étape 7 : prompt ----------
    def messages(self, question, passages):
        blocs = []
        for i, p in enumerate(passages, 1):
            m = self.corpus.masail[p["principale"]]
            livre = self.corpus.livres[m.livre]
            blocs.append(f"[{i}] ({livre.titre} — {m.bab})\n{p['texte']}")
        return [{"role": "system", "content": PROMPT_SYSTEME},
                {"role": "user", "content": "المقاطع:\n" + "\n\n".join(blocs) + f"\n\nالسؤال: {question}"}]

    # ---------- étape 9 : FILTRE 3 ----------
    def verifier(self, brut, passages):
        """→ (réponse courte, liste des preuves, statut : grounded | not_found | no_quote)."""
        m = JAWAB.search(brut)
        reponse = (m.group(1) if m else CITATION.split(brut)[0]).strip() or brut.strip()
        preuves = []
        for citation, numero in CITATION.findall(brut):
            ordre = list(range(len(passages)))
            if numero and 1 <= int(numero) <= len(passages):   # le passage cité d'abord, puis les autres
                ordre.remove(int(numero) - 1)
                ordre.insert(0, int(numero) - 1)
            preuve = {"quote": citation.strip(), "passage": int(numero) if numero else None,
                      "found": False, "unit_key": None, "spans": []}
            for i in ordre:
                if not trouver_citation(passages[i]["texte"], citation):
                    continue
                preuve.update(found=True, passage=i + 1, unit_key=passages[i]["principale"])
                for cle in passages[i]["cles"]:   # la مسألة précise qui contient la citation (pour surligner)
                    zones = trouver_citation(self.corpus.masail[cle].texte, citation)
                    if zones:
                        preuve.update(unit_key=cle, spans=zones)
                        break
                break
            preuves.append(preuve)
        if not preuves:
            statut = "no_quote"
        else:
            statut = "grounded" if all(p["found"] for p in preuves) else "not_found"
        return reponse, preuves, statut

    # ---------- tout le trajet ----------
    def demander(self, question, madhhab="maliki"):
        debut = time.time()
        candidats = self.candidats(question, madhhab)
        passages = self.passages(candidats)
        resultat = {"question": question, "madhhab": madhhab, "answer": ABSTENTION, "raw": "",
                    "evidence": [], "grounding": "n/a", "abstained": None, "tokens": 0,
                    "passages": [self._public(p) for p in passages],
                    "top_score": round(candidats[0][1], 4) if candidats else None}
        if not passages:
            resultat["abstained"] = "retrieval"                      # filtre 1
        else:
            brut, tokens = self.groq.repondre(self.messages(question, passages))
            resultat.update(raw=brut, tokens=tokens)
            if normaliser(ABSTENTION[:20]) in normaliser(brut):
                resultat["abstained"] = "model"                      # filtre 2
            else:
                resultat["answer"], resultat["evidence"], resultat["grounding"] = self.verifier(brut, passages)
        resultat["elapsed"] = round(time.time() - debut, 3)
        return resultat

    def _public(self, p):
        """Ce que le frontend reçoit pour chaque passage (mêmes noms de champs que le frontend de l'ami)."""
        m = self.corpus.masail[p["principale"]]
        livre = self.corpus.livres[m.livre]
        pages = sorted({self.corpus.masail[c].page for c in p["cles"] if self.corpus.masail[c].page})
        return {"book_key": m.livre, "book": livre.titre, "author": livre.auteur,
                "bab_index": m.bab_index, "bab_title": m.bab, "section": m.section or m.bab,
                "unit_key": m.cle, "unit_number": m.numero, "units": p["cles"],
                "pages": pages, "text": p["texte"], "score": round(p["score"], 4)}
