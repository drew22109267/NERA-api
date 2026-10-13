r"""
Construction du tableau d'apprentissage à partir de la série d'occupation.

Le soir du jour t (l'« origine »), on prévoit l'occupation du jour t + h. Chaque ligne du
tableau correspond à une origine t ; ses variables n'utilisent QUE ce qui est connu au jour t
(aucune fuite d'information venant du futur).

Variables, regroupées en deux blocs pour le noyau composite (brique 2) :
  Bloc « occupation » : occupation des 7 derniers jours  y_t, y_{t−1}, …, y_{t−6}
  Bloc « flux et saison » :
      admissions des 3 et des 7 derniers jours, sorties des 7 derniers jours
      jour de la semaine du jour cible (7 indicatrices 0/1 : le planning est connu à l'avance)
      mois du jour cible en coordonnées circulaires  sin(2π m/12), cos(2π m/12)
      (décembre et janvier sont voisins sur le cercle, pas aux deux bouts d'une échelle)
En pédiatrie il n'y a pas d'admissions programmées : le second bloc remplace
« admissions programmées » du protocole par « flux récents + saison » (adaptation au terrain).

Standardisation : chaque variable continue est centrée-réduite, z = (x − moyenne)/écart-type,
avec la moyenne et l'écart-type calculés sur les SEULES lignes d'entraînement de chaque
découpage (sinon le test « voit » des informations du futur). Le noyau RBF dépend des
distances : sans standardisation, une variable en dizaines (l'occupation) écraserait une
variable entre −1 et 1 (le sinus du mois). Les indicatrices 0/1 ne sont pas standardisées.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
import torch

TYPE = torch.float64
JOURS_RETARD = 7


@dataclass
class Tableau:
    X: torch.Tensor                  # n × d
    y: torch.Tensor                  # n, occupation du jour cible
    origines: torch.Tensor           # n, indice du jour t dans la série
    dates_origine: pd.DatetimeIndex
    dates_cible: pd.DatetimeIndex
    noms: list[str]
    blocs: dict[str, list[int]]      # colonnes de chaque bloc (noyau composite)
    continues: list[int]             # colonnes à standardiser
    serie: torch.Tensor              # occupation complète (pour les références)
    h: int


def construire(occupation: pd.DataFrame, h: int, retards: int = JOURS_RETARD, flux: bool = True,
               calendrier: bool = True, feries: set | None = None, vacances: set | None = None,
               debut_min: int = 0) -> Tableau:
    """
    `occupation` : sortie de nera.occupation.reconstituer_occupation (index = jours consécutifs).

    Options (pour mesurer l'apport de chaque groupe de variables, voir benchmark_choix.py) :
      retards     nombre de jours d'occupation passée (7 par défaut : y_t … y_{t−6})
      flux        admissions 3 j et 7 j, sorties 7 j
      calendrier  jour de la semaine de la cible (7 indicatrices) et mois (sinus, cosinus)
      feries      ensemble de dates fériées (svr/calendrier.py) : ajoute « la cible est fériée »
                  et « la veille de la cible est fériée » (indicatrices 0/1, connues à l'avance)
      vacances    ensemble de jours de vacances scolaires (svr/calendrier.vacances) : ajoute
                  « la cible tombe pendant les vacances » (indicatrice 0/1, connue à l'avance)
      debut_min   première origine possible ; on la fixe quand on compare des variantes, pour
                  que toutes soient évaluées sur exactement les mêmes jours.
    Le défaut reproduit le tableau du modèle principal.
    """
    if h < 1:
        raise ValueError("L'horizon h doit valoir au moins 1 jour.")
    if retards < 1:
        raise ValueError("Il faut au moins un jour d'occupation passée.")
    y_serie = torch.tensor(occupation["presents"].to_numpy(), dtype=TYPE)
    adm = torch.tensor(occupation["admissions"].to_numpy(), dtype=TYPE)
    colonnes_sorties = [c for c in occupation.columns if c.startswith("sorties_")]
    sor = torch.tensor(occupation[colonnes_sorties].sum(axis=1).to_numpy(), dtype=TYPE)
    jours = occupation.index
    # Première origine : il faut `retards` jours d'historique, et 7 jours pour les flux.
    origines = torch.arange(max(retards - 1, 6 if flux else 0, debut_min), len(jours) - h)
    if len(origines) == 0:
        raise ValueError("Série trop courte pour cet horizon.")

    noms = [f"occ_j-{k}" for k in range(retards)]
    if flux:
        noms += ["adm_3j", "adm_7j", "sorties_7j"]
    if calendrier:
        noms += [f"cible_jour_{j}" for j in range(7)] + ["mois_sin", "mois_cos"]
    if feries is not None:
        noms += ["cible_feriee", "veille_feriee"]
    if vacances is not None:
        noms += ["cible_vacances"]
    lignes = []
    for t in origines.tolist():
        cible = jours[t + h]
        valeurs = [float(y_serie[t - k]) for k in range(retards)]                       # occupation passée
        if flux:
            valeurs += [float(adm[t - 2: t + 1].sum()), float(adm[t - 6: t + 1].sum()), float(sor[t - 6: t + 1].sum())]
        if calendrier:
            valeurs += [1.0 if cible.dayofweek == j else 0.0 for j in range(7)]          # jour de la semaine
            angle = 2 * math.pi * (cible.month - 1) / 12                                  # mois sur un cercle
            valeurs += [math.sin(angle), math.cos(angle)]
        if feries is not None:
            valeurs += [1.0 if cible.date() in feries else 0.0,
                        1.0 if (cible - pd.Timedelta(days=1)).date() in feries else 0.0]
        if vacances is not None:
            valeurs += [1.0 if cible.date() in vacances else 0.0]
        lignes.append(torch.tensor(valeurs, dtype=TYPE))

    X = torch.stack(lignes)
    idx_occ = list(range(retards))
    idx_flux = list(range(retards, X.shape[1]))
    # Variables continues (à standardiser) : retards, flux, sinus et cosinus du mois ; pas les indicatrices 0/1.
    continues = [j for j, nom in enumerate(noms)
                 if nom.startswith("occ_") or nom in ("adm_3j", "adm_7j", "sorties_7j", "mois_sin", "mois_cos")]
    return Tableau(X=X, y=y_serie[origines + h], origines=origines,
                   dates_origine=jours[origines.numpy()], dates_cible=jours[(origines + h).numpy()],
                   noms=noms, blocs={"occupation": idx_occ, "flux_saison": idx_flux},
                   continues=continues, serie=y_serie, h=h)


@dataclass
class Standardiseur:
    """z = (x − μ)/σ sur les colonnes continues ; μ et σ appris sur l'entraînement seulement."""
    colonnes: list[int]

    def ajuster(self, X: torch.Tensor) -> "Standardiseur":
        sous = X[:, self.colonnes]
        if not self.colonnes:                           # aucune colonne à standardiser (variante « sans »)
            self.moyenne = self.ecart = torch.empty(0, dtype=X.dtype)
            return self
        self.moyenne = sous.mean(dim=0)
        self.ecart = sous.std(dim=0, unbiased=False)
        self.ecart[self.ecart < 1e-12] = 1.0            # variable constante : on ne divise pas par 0
        return self

    def transformer(self, X: torch.Tensor) -> torch.Tensor:
        Z = X.clone()
        Z[:, self.colonnes] = (X[:, self.colonnes] - self.moyenne) / self.ecart
        return Z
