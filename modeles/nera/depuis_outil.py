r"""
Conversion du CSV exporté par l'outil de saisie (« Aperçu » ou « CSV du service ») au format « dataset
harmonisé » de l'application NERA, que lit nera.chargement.lire_export.

Pourquoi : pendant que la saisie est encore corrigée, on relance toute la chaîne à chaque nouvelle version
du fichier sans repasser par l'import NERA. Les règles sont EXACTEMENT celles de l'import NERA
(HopitalApi/Services/Recherche/ImportRegistreService.cs) ; le chemin par NERA reste celui de la production.

Règles reprises de l'import NERA, ligne par ligne
-------------------------------------------------
  Dates          jj/mm/aa, jj/mm/aaaa (séparateurs / . -) ; une date suivie de « ? » est lue sans le « ? »
                 (doute à la transcription) ; « 0?/03/25 » (chiffre illisible) est illisible.
  Nombre de jours  premier nombre de la case (« 3 jrs » → 3) ; ignoré si la case contient une date (« / »),
                 s'il est négatif ou s'il dépasse 90 nuits (prix recopié).
  Date d'entrée illisible  sortie − nombre de jours si les deux sont lus et cohérents avec l'enregistrement,
                 sinon date d'enregistrement ; sans aucune des deux, la ligne est rejetée.
  Sortie         rejet si elle précède l'entrée ; laissée vide si le séjour dépasse 90 nuits ; si elle n'est
                 pas écrite et que le nombre de jours l'est : sortie = entrée + nombre de jours, marquée
                 « sortie_calculee » (la convention des jours est traitée ensuite par nera.chargement).
  Issue          harmonisée avec le vocabulaire NERA (même logique que issueDe de l'outil) :
                 décès (observation ou remarque) → « Décès » ; SCAM → « Sortie contre avis médical » ;
                 évadé → « Évasion » ; référé, déféré, transféré → « Transfert externe » ;
                 mise en observation (MEO) ou sortie → « Sortie » ; sinon vide.
  Prix           premier nombre de la case (« 7500F » → 7500).

Règle supplémentaire (contrôle de cohérence, absente de l'import NERA) : une date d'entrée à plus de 30 jours avant (ou 10 jours après) la
la date d'enregistrement est une faute de frappe sur l'année ou le mois (« 12/02/2023 » enregistrée le
13/02/2026). On essaie les corrections d'un an ou d'un mois qui ramènent l'entrée entre 2 jours après et
30 jours avant l'enregistrement ; la sortie est décalée d'autant. Sans correction possible, l'entrée prend la
date d'enregistrement. Chaque correction est listée (corrections_dates_<SERVICE>.csv) pour être reportée dans
l'outil de saisie : la source doit être corrigée, ce n'est qu'un garde-fou.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DUREE_MAX_NUITS = 90
RE_DATE = re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\s*$")


def _cle(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().lower())


COLONNES = {  # nom normalisé de la colonne de l'outil → code du dataset harmonisé
    "ndordre": "numero", "dateenregistrement": "date_enregistrement", "anciennouveau": "ancien_nouveau",
    "sexe": "sexe", "age": "age", "domicile": "quartier", "datedentree": "date_entree", "datedesortie": "date_sortie",
    "diagnostic": "diagnostic_entree", "bilandemande": "bilan", "t3recu": "traitement_initial", "getdrpalu": "ge_tdr",
    "diagnosticdesortie": "diagnostic_sortie", "t3desortie": "traitement_sortie", "nbredejours": "duree_jours",
    "prix": "prix", "observation": "observation", "remarquedesaisie": "remarque",
}


def lire_date(brut: str | None) -> date | None:
    """Date du registre ; un « ? » final (doute) est ignoré, un chiffre illisible rend la date illisible."""
    if not brut or not brut.strip():
        return None
    s = re.sub(r"\s*\?+\s*$", "", brut.strip())
    m = RE_DATE.match(s)
    if not m:
        return None
    j, mo, a = int(m[1]), int(m[2]), int(m[3])
    a = a + 2000 if a < 100 else a
    try:
        return date(a, mo, j)
    except ValueError:
        return None


def lire_nombre(brut: str | None) -> float | None:
    if not brut or not brut.strip():
        return None
    s = re.sub(r"[\s ]", "", brut.strip()).replace(",", ".")
    m = re.match(r"^-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


def _decaler(d: date, ans: int = 0, mois: int = 0) -> date | None:
    m = d.month - 1 + mois
    a, m = d.year + ans + m // 12, m % 12 + 1
    try:
        return d.replace(year=a, month=m)
    except ValueError:
        return None


def corriger_entree(entree: date, sortie: date | None, enreg: date | None) -> tuple[date, date | None, str] | None:
    """Correction d'une faute d'année ou de mois sur l'entrée (voir l'en-tête), ou None si l'entrée est cohérente."""
    if enreg is None or -10 <= (enreg - entree).days <= 30:          # petits écarts : laissés, signalés dans l'outil
        return None
    for ans, mois in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        e2 = _decaler(entree, ans, mois)
        if e2 is not None and -2 <= (enreg - e2).days <= 30:
            s2 = _decaler(sortie, ans, mois) if sortie is not None else None
            return e2, s2, f"{'année' if ans else 'mois'} {'+' if ans + mois > 0 else '−'}1"
    return enreg, (sortie if sortie is not None and sortie >= enreg else None), "date d'enregistrement"


def harmoniser_issue(observation: str | None, remarque: str | None) -> str | None:
    t = (observation or "").lower()
    if re.search(r"d[ée]c[éèe]d|d[ée]c[eè]s|\bdcd\b", f"{t} {(remarque or '').lower()}"):
        return "Décès"
    if "scam" in t:
        return "Sortie contre avis médical"
    if re.search(r"[ée]vad", t):
        return "Évasion"
    if re.search(r"r[ée]f[ée]r|d[ée]f[ée]r|transf[ée]r", t):
        return "Transfert externe"
    if re.search(r"\bmeo\b|observation|sorti|ambulatoire|gratuit", t):
        return "Sortie"
    return None


def convertir(chemin: str | Path, service: str = "PED", aujourdhui: date | None = None) -> tuple[pd.DataFrame, dict]:
    """Lit le CSV de l'outil et renvoie (dataset harmonisé, rapport de conversion)."""
    aujourdhui = aujourdhui or date.today()
    texte = Path(chemin).read_text(encoding="utf-8-sig")
    premiere = texte.split("\n", 1)[0]
    sep = max([";", ",", "\t"], key=premiere.count)
    lignes = list(csv.reader(io.StringIO(texte), delimiter=sep))
    entete = [COLONNES.get(_cle(h)) for h in lignes[0]]
    sortie, rejets, corrections, avert = [], [], [], {"entree_deduite": 0, "duree_ignoree": 0, "sortie_trop_longue": 0, "sortie_calculee": 0}
    for numero, v in enumerate(lignes[1:], start=2):
        if not any(c.strip() for c in v):
            continue
        val = {k: (v[i].strip() or None) for i, k in enumerate(entete) if k and i < len(v)}
        dj = val.get("duree_jours")
        duree = None if dj is None or "/" in dj else lire_nombre(dj)
        duree = int(round(duree)) if duree is not None else None
        if duree is not None and not (0 <= duree <= DUREE_MAX_NUITS):
            duree = None
        if dj is not None and duree is None:
            avert["duree_ignoree"] += 1
        enreg = lire_date(val.get("date_enregistrement"))
        sort = lire_date(val.get("date_sortie"))
        entree = lire_date(val.get("date_entree"))
        if entree is None and enreg is not None:
            deduite = sort - timedelta(days=duree) if sort is not None and duree is not None else None
            entree = deduite if deduite is not None and enreg - timedelta(days=DUREE_MAX_NUITS) <= deduite <= enreg else enreg
            avert["entree_deduite"] += 1
        if entree is None:
            rejets.append((numero, "date d'entrée absente ou illisible, sans date d'enregistrement")); continue
        c = corriger_entree(entree, sort, enreg)
        if c is not None:
            corrections.append({"ligne": numero, "numero_ordre": val.get("numero"), "date_enregistrement": enreg,
                                "entree_ecrite": entree, "sortie_ecrite": sort, "entree_retenue": c[0],
                                "sortie_retenue": c[1], "correction": c[2]})
            entree, sort = c[0], c[1]
        if sort is not None and sort < entree:
            rejets.append((numero, "date de sortie antérieure à la date d'entrée")); continue
        if sort is not None and (sort - entree).days > DUREE_MAX_NUITS:
            sort = None; avert["sortie_trop_longue"] += 1
        calculee = False
        if sort is None and duree is not None:
            sort = entree + timedelta(days=duree); calculee = True; avert["sortie_calculee"] += 1
        if entree > aujourdhui or (sort is not None and sort > aujourdhui):
            rejets.append((numero, "date postérieure à aujourd'hui")); continue
        prix = lire_nombre(val.get("prix"))
        sortie.append({
            "hopital": "", "role": "", "service_code": service, "id_anonyme": None,
            "date_enregistrement": enreg, "date_entree": entree, "date_sortie": sort,
            "ancien_nouveau": val.get("ancien_nouveau"), "sexe": val.get("sexe"), "age_texte": val.get("age"),
            "quartier": val.get("quartier"), "diagnostic_entree": val.get("diagnostic_entree"),
            "bilan": val.get("bilan"), "traitement_initial": val.get("traitement_initial"), "ge_tdr": val.get("ge_tdr"),
            "diagnostic_sortie": val.get("diagnostic_sortie"), "traitement_sortie": val.get("traitement_sortie"),
            "duree_jours": duree, "prix": prix, "issue": harmoniser_issue(val.get("observation"), val.get("remarque")),
            "sortie_calculee": calculee, "numero_ordre": val.get("numero"),
            "duree_sejour_jours": (sort - entree).days if sort is not None else None,
        })
    df = pd.DataFrame(sortie)
    for c in ("date_enregistrement", "date_entree", "date_sortie"):
        df[c] = pd.to_datetime(df[c])
    rapport = {"lignes_lues": len(lignes) - 1, "lignes_converties": len(df), "rejets": len(rejets),
               "detail_rejets": rejets[:20], **avert, "dates_corrigees": len(corrections), "corrections": corrections}
    return df, rapport


def ecrire_export(df: pd.DataFrame, chemin: str | Path) -> None:
    """Écrit au format exact de l'export NERA (séparateur « ; », dates aaaa-mm-jj, sortie_calculee 0/1)."""
    d = df.copy()
    for c in ("date_enregistrement", "date_entree", "date_sortie"):
        d[c] = d[c].dt.strftime("%Y-%m-%d")
    d["sortie_calculee"] = d["sortie_calculee"].map({True: "1", False: "0"})
    d.to_csv(chemin, sep=";", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="CSV de l'outil de saisie → dataset harmonisé NERA (modeles/donnees/).")
    p.add_argument("source"); p.add_argument("--service", default="PED")
    p.add_argument("--sortie", default="donnees/export_outil_PED.csv")
    a = p.parse_args()
    df, rapport = convertir(a.source, a.service)
    ecrire_export(df, a.sortie)
    corr = rapport.pop("corrections")
    if corr:
        chemin_c = Path(a.sortie).with_name(f"corrections_dates_{a.service}.csv")
        pd.DataFrame(corr).to_csv(chemin_c, sep=";", index=False, encoding="utf-8-sig")
        print(f"  {len(corr)} date(s) d'entrée corrigée(s), à reporter dans l'outil : {chemin_c}")
        for c in corr:
            print(f"    N° {c['numero_ordre']} enregistré le {c['date_enregistrement']:%d/%m/%Y} : entrée {c['entree_ecrite']:%d/%m/%Y}"
                  f" → {c['entree_retenue']:%d/%m/%Y} ({c['correction']})")
    for k, v in rapport.items():
        print(f"  {k} : {v}")
    print(f"Écrit : {a.sortie}")
