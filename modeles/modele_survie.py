r"""
MODÈLE DE SURVIE J0 / J1 / J2 : probabilité que chaque enfant hospitalisé sorte aujourd'hui,
demain ou après-demain (données verrouillées ; le coffre n'est lu qu'au test final).

Méthode (détails et formules : svr/survie.py et svr/classification.py)
  - tableau patient-jour (une ligne par jour de présence, censure et sorties non écrites traitées) ;
  - hasard journalier h(k, x) appris par un SVM linéaire à COÛTS ASYMÉTRIQUES (C+ / C− : les
    sorties sont rares parmi les jours de présence), transformé en probabilité par la méthode de
    Platt sur une période de calibration distincte ;
  - P(J0) = h₀, P(J1) = (1 − h₀) h₁, P(J2) = (1 − h₀)(1 − h₁) h₂ ; sorties attendues d'un jour =
    somme des probabilités des enfants présents ;
  - risques concurrents (option --causes) : un hasard par cause de sortie (domicile, transfert,
    décès, autre) quand il y a au moins 30 sorties de cette cause à l'entraînement.

Comparé à (même découpage, mêmes jours) :
  - table de survie (ancienneté seule) ;
  - loi gamma de la durée (protocole) ;
  - SVM à coûts SYMÉTRIQUES (pour mesurer l'apport de l'asymétrie).

Découpage dans le temps (aucune information du futur) :
  entraînement  jours < début de calibration
  calibration   les `jours_calibration` jours suivants (Platt uniquement)
  validation    du début de validation (6 mois avant le verrou) au verrou
Au test final (--confirmation) : entraînement + calibration avant le verrou, test sur le coffre.

Mesures sur les jours-patients de validation : score de Brier, log-loss, AUC du hasard journalier ;
et, jour par jour, l'écart entre sorties attendues (Σ P) et sorties réelles des enfants présents le
matin, pour J0, J1 et J2 (MAE en nombre de sorties par jour).

Exemple :
    ~/memoire-env/bin/python modele_survie.py donnees/<export>.csv --service PED --lits 20 --causes
Sorties dans resultats/ : survie_<S>.csv / .md (tableau comparatif), survie_<S>_causes.csv,
survie_<S>_calibration.png, survie_<S>_hasard.png, survie_<S>_sorties.png,
survie_<S>_modele.json (le modèle retenu, pour l'API), survie_<S>_environnement.json.
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import torch

from benchmark_choix import en_markdown
from nera.chargement import lire_export, periode_exploitable, preparer_sejours
from nera.occupation import reconstituer_occupation
from nera.verrou import DATE_VERROU
from svr import survie as S
from svr.calendrier import feries
from svr.caracteristiques import Standardiseur
from svr.classification import CalibrationPlatt, SVMLineaireClassifieur, auc, brier, log_loss
from svr.modeles import Entrainement
from svr.reproductibilite import ecrire_environnement

TYPE = torch.float64
K_MAX = 30


class HasardSVM:
    """Un SVM + sa calibration de Platt, utilisables comme fonction hasard(lignes) → probabilités."""

    def __init__(self, encodeur, std, C_pos, C_neg, entrainement):
        self.encodeur, self.std = encodeur, std
        self.svm = SVMLineaireClassifieur(C_pos, C_neg, entrainement)

    def entrainer(self, lignes, y, cal, y_cal):
        X = self.std.transformer(self.encodeur.transformer(lignes))
        self.svm.entrainer(X, y, lignes["poids"].to_numpy())
        scores_cal = self.svm.predire(self.std.transformer(self.encodeur.transformer(cal)))
        self.platt = CalibrationPlatt().ajuster(scores_cal, y_cal, cal["poids"].to_numpy())
        return self

    def __call__(self, lignes) -> torch.Tensor:
        return self.platt.probabilite(self.svm.predire(self.std.transformer(self.encodeur.transformer(lignes))))


def main() -> None:
    p = argparse.ArgumentParser(description="Probabilité de sortie J0/J1/J2 par enfant hospitalisé.")
    p.add_argument("export")
    p.add_argument("--service", required=True)
    p.add_argument("--lits", type=int, help="lits du service (variable « pression sur les lits » ; sinon occupation relative)")
    p.add_argument("--C", type=float, default=0.01, help="coût de base des erreurs du SVM (0,01)")
    p.add_argument("--jours-calibration", type=int, default=60)
    p.add_argument("--debut-validation", help="défaut : 6 mois avant le verrou")
    p.add_argument("--iterations", type=int, default=3000)
    p.add_argument("--causes", action="store_true", help="risques concurrents : un hasard par cause de sortie")
    p.add_argument("--extraction", help="test final : date du relevé (aaaa-mm-jj)")
    p.add_argument("--confirmation", help="test final : phrase d'ouverture du coffre")
    a = p.parse_args()

    final = a.confirmation is not None
    if final and not a.extraction:
        raise SystemExit("Le test final demande --extraction.")
    sortie = Path("resultats"); sortie.mkdir(exist_ok=True)
    ecrire_environnement(sortie / f"survie_{a.service}_environnement.json", **{k: v for k, v in vars(a).items() if k != "confirmation"})
    df = lire_export(a.export, confirmation_coffre=a.confirmation) if final else lire_export(a.export)
    extraction = pd.Timestamp(a.extraction) if final else DATE_VERROU
    sejours, _ = preparer_sejours(df, a.service, extraction)

    # Pression sur les lits : taux d'occupation de la veille (ou occupation relative à la moyenne).
    periode = periode_exploitable(sejours)
    occ = reconstituer_occupation(sejours, extraction, debut=periode["debut"])
    pression = occ["presents"] / a.lits if a.lits else occ["presents"] / occ["presents"].mean()

    lignes = S.lignes_patient_jour(sejours, extraction)
    if final:
        debut_val, fin_val = DATE_VERROU, extraction
    else:
        debut_val = pd.Timestamp(a.debut_validation) if a.debut_validation else DATE_VERROU - pd.DateOffset(months=6)
        fin_val = DATE_VERROU
    debut_cal = debut_val - pd.Timedelta(days=a.jours_calibration)
    entr = lignes[lignes["jour"] < debut_cal]
    cal = lignes[(lignes["jour"] >= debut_cal) & (lignes["jour"] < debut_val)]
    val = lignes[(lignes["jour"] >= debut_val) & (lignes["jour"] < fin_val)]
    print(f"Jours-patients : entraînement {len(entr)} · calibration {len(cal)} · validation {len(val)} "
          f"(sorties pondérées : {entr['poids'][entr['evenement'] == 1].sum():.0f} / "
          f"{cal['poids'][cal['evenement'] == 1].sum():.0f} / {val['poids'][val['evenement'] == 1].sum():.0f})")

    jours_feries = feries(range(lignes["jour"].min().year, lignes["jour"].max().year + 2), Path("donnees") / "feries_supplementaires.csv")
    enc = S.EncodeurVariables(jours_feries, pression).ajuster(entr)
    noms = enc.noms()
    continues = [j for j, n in enumerate(noms) if n in ("mois_sin", "mois_cos", "log_age", "occupation_veille")]
    std = Standardiseur(continues).ajuster(enc.transformer(entr))
    e = Entrainement(iterations=a.iterations, taux=0.05)

    # ── Modèles comparés ─────────────────────────────────────────────────────
    y_entr, y_cal = torch.tensor(entr["evenement"].to_numpy(), dtype=TYPE), torch.tensor(cal["evenement"].to_numpy(), dtype=TYPE)
    w_entr = torch.tensor(entr["poids"].to_numpy(), dtype=TYPE)
    n_pos, n_neg = float((w_entr * y_entr).sum()), float((w_entr * (1 - y_entr)).sum())
    avant_val = pd.concat([entr, cal])                       # les références peuvent utiliser aussi la calibration
    h_table = S.table_de_survie(avant_val, K_MAX)
    sorties_avant = avant_val[avant_val["evenement"] == 1]
    forme, echelle = S.ajuster_gamma(torch.tensor(sorties_avant["k"].to_numpy(), dtype=TYPE),
                                     torch.tensor(sorties_avant["poids"].to_numpy(), dtype=TYPE))
    h_gamma = S.hasard_gamma(K_MAX, forme, echelle)
    par_anciennete = lambda h: (lambda L: h[torch.tensor(L["k"].clip(upper=K_MAX).to_numpy())])
    ratio = n_neg / n_pos
    modeles = {
        "Table de survie (ancienneté seule)": par_anciennete(h_table),
        f"Loi gamma de la durée (a = {forme:.2f}, θ = {echelle:.2f})": par_anciennete(h_gamma),
        "SVM linéaire, coûts symétriques + Platt": HasardSVM(enc, std, a.C, a.C, e).entrainer(entr, y_entr, cal, y_cal),
        f"SVM linéaire, coûts asymétriques C+/C− = {ratio:.1f} + Platt (retenu)": HasardSVM(enc, std, a.C * ratio, a.C, e).entrainer(entr, y_entr, cal, y_cal),
    }
    retenu = list(modeles)[-1]

    # Risques concurrents : un hasard par cause, total = somme des hasards (borné à 0,999).
    lignes_causes = []
    if a.causes:
        par_cause = {}
        for c in sorted(set(S.CAUSES.values())):
            yc = torch.tensor(((entr["evenement"] == 1) & (entr["cause"] == c)).to_numpy(), dtype=TYPE)
            n_c = float((w_entr * yc).sum())
            if n_c < 30:
                print(f"  cause « {c} » : {n_c:.0f} sortie(s) à l'entraînement, trop peu pour un modèle propre (regroupée)")
                continue
            ycal = torch.tensor(((cal["evenement"] == 1) & (cal["cause"] == c)).to_numpy(), dtype=TYPE)
            r_c = float((w_entr * (1 - yc)).sum()) / n_c
            par_cause[c] = HasardSVM(enc, std, a.C * r_c, a.C, e).entrainer(entr, yc, cal, ycal)
        if par_cause:
            modeles["SVM par cause (risques concurrents), somme des hasards"] = (
                lambda L: torch.stack([m(L) for m in par_cause.values()]).sum(dim=0).clamp(max=0.999))

    # ── Évaluation sur les jours-patients de validation ──────────────────────
    y_val, w_val = val["evenement"].to_numpy(), val["poids"].to_numpy()
    # Chaque matin évalué : les enfants présents, et leurs sorties réelles à J0, J1, J2 (J2 doit rester avant la fin).
    jours_val = list(pd.date_range(debut_val, fin_val - pd.Timedelta(days=3), freq="D"))
    presents_par_jour = {d: S.presents_le_matin(val, d) for d in jours_val}
    observes = {j: [S.sorties_observees(val, pr, d, j) if not pr.empty else 0.0 for d, pr in presents_par_jour.items()]
                for j in range(3)}
    lignes_tab, series = [], {}
    for nom, hasard in modeles.items():
        h = hasard(val)
        attendus = {j: [] for j in range(3)}
        for d, presents in presents_par_jour.items():
            P = S.probabilites_j012(hasard, presents) if not presents.empty else torch.zeros(0, 3, dtype=TYPE)
            for j in range(3):
                attendus[j].append(float(P[:, j].sum()))
        series[nom] = attendus
        lignes_tab.append({"modèle": nom, "Brier": round(brier(h, y_val, w_val), 4), "log-loss": round(log_loss(h, y_val, w_val), 4),
                           "AUC": round(auc(h, y_val, w_val), 3)})
    for ligne in lignes_tab:
        att = series[ligne["modèle"]]
        for j in range(3):
            o, a_ = torch.tensor(observes[j], dtype=TYPE), torch.tensor(att[j], dtype=TYPE)
            ligne[f"MAE J{j} (sorties/jour)"] = round(float((o - a_).abs().mean()), 3)
        ligne["biais J0"] = round(float((torch.tensor(observes[0]) - torch.tensor(att[0])).mean()), 3)
    tableau = pd.DataFrame(lignes_tab).set_index("modèle")
    print(f"\n── Modèle de survie — {a.service} · {len(val)} jours-patients, {len(jours_val)} matins évalués\n{tableau.to_string()}")
    tableau.to_csv(sortie / f"survie_{a.service}.csv", sep=";", encoding="utf-8-sig")
    meilleur = tableau["Brier"].idxmin()
    texte = [f"# Modèle de survie J0/J1/J2 — {a.service}\n",
             f"{'Test final sur le coffre' if final else 'Validation'} : {len(val)} jours-patients, {len(jours_val)} matins. "
             "« (retenu) » = modèle retenu. Brier et log-loss : plus petit = meilleur ; AUC : plus grand = meilleur ; "
             "MAE J0/J1/J2 : écart moyen entre sorties attendues et réelles par jour.\n", en_markdown(tableau), "\n",
             f"Meilleur score de Brier : **{meilleur}**." + ("" if meilleur == retenu else " ⚠ Le modèle retenu n'est pas le meilleur : à revoir.") + "\n"]

    # Prévisions par cause sur la validation (sorties attendues contre réelles)
    if a.causes and par_cause:
        for c, m in par_cause.items():
            h_c = m(val)
            obs_c = float(val["poids"][(val["evenement"] == 1) & (val["cause"] == c)].sum())
            lignes_causes.append({"cause": c, "sorties réelles": round(obs_c, 1), "sorties attendues": round(float((h_c * torch.tensor(w_val)).sum()), 1)})
        tc = pd.DataFrame(lignes_causes).set_index("cause")
        print(f"\n── Par cause de sortie (validation)\n{tc.to_string()}")
        tc.to_csv(sortie / f"survie_{a.service}_causes.csv", sep=";", encoding="utf-8-sig")
        texte += ["\n## Par cause de sortie\n", en_markdown(tc), "\n"]
    (sortie / f"survie_{a.service}.md").write_text("\n".join(texte), encoding="utf-8")

    # ── Figures ──────────────────────────────────────────────────────────────
    # Calibration : hasard prévu (par déciles) contre fréquence réelle des sorties.
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.plot([0, 1], [0, 1], ls="--", color="#999", label="Calibration parfaite")
    for nom in (list(modeles)[0], retenu):
        h = modeles[nom](val)
        bornes = torch.quantile(h, torch.linspace(0, 1, 11, dtype=TYPE))
        xs, ys = [], []
        for i in range(10):
            dans = (h >= bornes[i]) & (h <= bornes[i + 1]) if i == 9 else (h >= bornes[i]) & (h < bornes[i + 1])
            if dans.any():
                w = torch.tensor(w_val, dtype=TYPE)[dans]
                xs.append(float((h[dans] * w).sum() / w.sum())); ys.append(float((torch.tensor(y_val, dtype=TYPE)[dans] * w).sum() / w.sum()))
        ax.plot(xs, ys, "o-", label=nom.replace(" (retenu)", ""))
    ax.set_xlabel("Probabilité de sortie prévue (moyenne du décile)"); ax.set_ylabel("Fréquence réelle des sorties")
    ax.set_title("Calibration du hasard journalier"); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(sortie / f"survie_{a.service}_calibration.png", dpi=150); plt.close(fig)

    # Hasard selon l'ancienneté : réel (validation) contre modèles.
    fig, ax = plt.subplots(figsize=(9, 4))
    reel = S.table_de_survie(val, K_MAX)
    ax.plot(range(K_MAX + 1), reel.numpy(), "o", color="#2b2f36", label="Réel (validation)")
    ax.plot(range(K_MAX + 1), h_table.numpy(), label="Table de survie (avant validation)")
    ax.plot(range(K_MAX + 1), h_gamma.numpy(), label=f"Loi gamma (a = {forme:.2f})")
    k_val = torch.tensor(val["k"].clip(upper=K_MAX).to_numpy())
    h_ret = modeles[retenu](val)
    moyenne_svm = [float(h_ret[k_val == k].mean()) if (k_val == k).any() else float("nan") for k in range(K_MAX + 1)]
    ax.plot(range(K_MAX + 1), moyenne_svm, label="SVM retenu (moyenne par ancienneté)")
    ax.set_xlabel("Ancienneté du séjour k (jours)"); ax.set_ylabel("P(sortie ce jour | présent)")
    ax.set_title("Hasard de sortie selon l'ancienneté"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(sortie / f"survie_{a.service}_hasard.png", dpi=150); plt.close(fig)

    # Sorties attendues contre réelles, jour par jour.
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    for j, ax in enumerate(axes):
        ax.plot(jours_val, observes[j], "o-", ms=3, lw=1, color="#2b2f36", label="Réel")
        ax.plot(jours_val, series[retenu][j], lw=1.3, color="#1f5fbf", label="Attendu (SVM retenu)")
        ax.plot(jours_val, series[list(modeles)[0]][j], lw=1, color="#e07b00", alpha=0.8, label="Attendu (table de survie)")
        ax.set_ylabel(f"Sorties J{j}"); ax.legend(fontsize=7, loc="upper right")
    axes[0].set_title("Sorties des enfants présents le matin : attendues contre réelles")
    fig.tight_layout(); fig.savefig(sortie / f"survie_{a.service}_sorties.png", dpi=150); plt.close(fig)

    # ── Le modèle retenu, pour l'API (paramètres en clair, aucune donnée de patient) ─
    m = modeles[retenu]
    (sortie / f"survie_{a.service}_modele.json").write_text(json.dumps({
        "service": a.service, "variables": noms, "w": m.svm.parametres["w"].tolist(), "b": float(m.svm.parametres["b"][0]),
        "standardisation": {"colonnes": continues, "moyenne": m.std.moyenne.tolist(), "ecart": m.std.ecart.tolist()},
        "platt": {"A": m.platt.A, "B": m.platt.B}, "diagnostics": enc.diagnostics, "age_median_mois": enc.age_median,
        "tranches_anciennete": S.TRANCHES_ANCIENNETE, "lits": a.lits,
        "formule": "P = 1/(1 + exp(A·(w·z + b) + B)), z = variables standardisées ; J0 = h0, J1 = (1−h0)h1, J2 = (1−h0)(1−h1)h2",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRésultats, figures et modèle écrits dans {sortie.resolve()}")


if __name__ == "__main__":
    main()
