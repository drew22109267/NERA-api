r"""
Les niveaux de l'analyse d'ablation (protocole, étape 4.4) : chaque niveau ajoute UNE brique
au précédent, pour mesurer ce qu'elle apporte réellement.

    0  références           persistance, saisonnière hebdomadaire, moyenne mobile
    1  SVR linéaire         perte ε-insensible
    2  SVR à noyau RBF      + non-linéarité
    3  SVR quantile RBF     + coût asymétrique (pinball ε-insensible, τ)       ← brique 1
    4  SVR quantile composite + noyau composite à poids appris                 ← brique 2
    5  empilement           + combinaison des niveaux précédents               ← brique 3

Les niveaux 3 à 5 produisent un intervalle (quantiles 5 % et 95 %) et la prévision au
quantile décisionnel τ = c(pénurie)/(c(pénurie) + c(surcapacité)).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .modeles import Entrainement, IntervalleQuantile, Perte, SVRLineaire, SVRNoyau, SVRNoyauComposite
from .noyaux import NoyauComposite, NoyauRBF


@dataclass
class Hyperparametres:
    """Valeurs de départ raisonnables ; la recherche (grille / PSO) les remplace."""
    C: float = 1.0
    epsilon: float = 1.0          # niveaux 1-2, en lits : une erreur d'un lit ne coûte rien
    epsilon_quantile: float = 0.0 # niveaux 3-4 : un tube ε > 0 déforme le quantile (voir pertes.py)
    gamma: float = 0.05           # portée du noyau RBF (variables standardisées)
    gamma1: float = 0.05          # noyau composite : bloc occupation
    gamma2: float = 0.1           # noyau composite : bloc flux et saison
    tau: float = 0.8              # quantile décisionnel (pénurie 4 fois plus coûteuse)
    taus_intervalle: tuple = (0.05, 0.5, 0.95)
    entrainement: Entrainement = field(default_factory=Entrainement)

    def vers_dict(self) -> dict:
        d = asdict(self)
        d["taus_intervalle"] = list(self.taus_intervalle)
        return d


def fabrique(niveau: int, hp: Hyperparametres, blocs: dict[str, list[int]]):
    """Renvoie une fonction sans argument qui crée un modèle neuf du niveau demandé."""
    e = hp.entrainement
    if niveau == 1:
        return lambda: SVRLineaire(C=hp.C, perte=Perte("epsilon", hp.epsilon), entrainement=e)
    if niveau == 2:
        return lambda: SVRNoyau(NoyauRBF(hp.gamma), C=hp.C, perte=Perte("epsilon", hp.epsilon), entrainement=e)
    if niveau == 3:
        modele = lambda tau: SVRNoyau(NoyauRBF(hp.gamma), C=hp.C,
                                      perte=Perte("pinball_epsilon", epsilon=hp.epsilon_quantile, tau=tau), entrainement=e)
        return lambda: IntervalleQuantile(modele, tuple(sorted({*hp.taus_intervalle, hp.tau})))
    if niveau == 4:
        noyau = NoyauComposite(blocs["occupation"], blocs["flux_saison"], hp.gamma1, hp.gamma2)
        modele = lambda tau: SVRNoyauComposite(noyau, C=hp.C,
                                               perte=Perte("pinball_epsilon", epsilon=hp.epsilon_quantile, tau=tau), entrainement=e)
        return lambda: IntervalleQuantile(modele, tuple(sorted({*hp.taus_intervalle, hp.tau})))
    raise ValueError(f"Niveau sans modèle entraînable : {niveau}")
