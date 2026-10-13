r"""
Indicateurs hospitaliers classiques, par mois et sur toute la période.

Définitions (pour une période de J jours et un service de N lits) :

  Journées d'hospitalisation  JH = Σ_jours (patients présents à minuit)
                              = nombre total de nuits passées à l'hôpital.

  Taux d'occupation moyen     TOM = JH / (N × J) × 100
      Part des lits disponibles réellement occupés. C'est aussi la moyenne des taux
      journaliers « présents / lits ». Un TOM > 100 % signale un sureffectif (lits ajoutés,
      enfants partageant un lit).

  Durée moyenne de séjour     DMS = Σ durées des séjours terminés dans le mois / nombre de sorties
      (en nuits ; les séjours encore en cours ne sont pas comptés : leur durée n'est pas connue).

  Rotation des lits           = sorties du mois / N
      Combien de patients se sont succédé en moyenne sur chaque lit.

  Intervalle de rotation      = (N × J − JH) / sorties
      Nombre moyen de jours où un lit reste vide entre deux patients. Négatif : sureffectif.

  Mortalité hospitalière      = décès / sorties × 100   (toutes issues confondues au dénominateur)

Sorties calculées (voir nera.occupation) : chaque sortie possible porte un poids w (p ou 1 − p
dans le scénario « attendue », 0 ou 1 dans les bornes). Sorties = Σ w, décès = Σ w·[décès],
DMS = Σ w·nuits / Σ w : ce sont les espérances des sommes, et la DMS est le rapport des deux.

Fourchette du TOM : TOM_bas (tout inclusif) ≤ TOM ≤ TOM_haut (tout en nuits), mois par mois,
puisque JH est croissant en chaque date de sortie.

  Capacité variable (lits ajoutés ou fermés) : N × J est remplacé par la somme des lits de
  chaque jour, Σ_d N_d ; la rotation utilise le nombre moyen de lits de la période.

  Contrôle de cohérence (loi de Little, mois par mois) : TOM × N ≈ admissions/jour × DMS.
"""
from __future__ import annotations

import pandas as pd

from .occupation import sorties_possibles


def indicateurs(occ: pd.DataFrame, sejours: pd.DataFrame, lits: int | None = None, par: str = "M",
                scenario: str = "attendue") -> pd.DataFrame:
    """
    `occ` : série de nera.occupation pour ce `scenario` ; `sejours` : nera.chargement.
    `par` : 'M' (mois) ou 'Y' (année). Une dernière ligne « Total » couvre toute la période.
    """
    if "lits" not in occ:                                          # capacité fixe donnée en argument
        if not lits or lits <= 0:
            raise ValueError("Le nombre de lits est nécessaire pour calculer le taux d'occupation.")
        occ = occ.assign(lits=float(lits))
    debut, fin = occ.index.min(), occ.index.max()
    ev = sorties_possibles(sejours, fin + pd.Timedelta(days=1), scenario)
    termines = ev[ev["reelle"] & (ev["fin"] > debut) & (ev["fin"] <= fin + pd.Timedelta(days=1))]

    def bloc(jours: pd.DataFrame, sorties: pd.DataFrame) -> dict:
        J, JH, n_sorties = len(jours), float(jours["presents"].sum()), float(sorties["poids"].sum())
        capacite = float(jours["lits"].sum())                     # Σ_d N_d = lits × J si la capacité est fixe
        lits_moyens = capacite / J if J else None
        deces = float(sorties.loc[sorties["issue"] == "Décès", "poids"].sum())
        return {
            "jours": J,
            "admissions": int(jours["admissions"].sum()),
            "sorties": round(n_sorties, 2),
            "journees_hospitalisation": round(JH, 2),
            "TOM_%": round(100 * JH / capacite, 1) if J else None,
            "occupation_max": round(float(jours["presents"].max()), 2) if J else None,
            "jours_en_sureffectif": int((jours["presents"] > jours["lits"]).sum()),
            "DMS_nuits": round(float((sorties["poids"] * sorties["duree_nuits"]).sum()) / n_sorties, 2) if n_sorties else None,
            "rotation_lits": round(n_sorties / lits_moyens, 2) if J else None,
            "intervalle_rotation_jours": round((capacite - JH) / n_sorties, 2) if n_sorties else None,
            "deces": round(deces, 2),
            "mortalite_%": round(100 * deces / n_sorties, 2) if n_sorties else None,
        }

    lignes = []
    periodes_jours = occ.index.to_period(par)
    periodes_sorties = termines["fin"].dt.to_period(par)
    for periode in periodes_jours.unique():
        lignes.append({"periode": str(periode), **bloc(occ[periodes_jours == periode], termines[periodes_sorties == periode])})
    lignes.append({"periode": "Total", **bloc(occ, termines)})
    return pd.DataFrame(lignes).set_index("periode")


def indicateurs_avec_fourchette(occs: dict[str, pd.DataFrame], sejours: pd.DataFrame, lits: int | None = None,
                                par: str = "M") -> pd.DataFrame:
    """Indicateurs du scénario « attendue », plus TOM_bas_% et TOM_haut_% (même découpage)."""
    t = indicateurs(occs["attendue"], sejours, lits, par, "attendue")
    for sc, nom in (("basse", "TOM_bas_%"), ("haute", "TOM_haut_%")):
        t.insert(t.columns.get_loc("TOM_%") + (1 if sc == "basse" else 2), nom,
                 indicateurs(occs[sc], sejours, lits, par, sc)["TOM_%"])
    return t
