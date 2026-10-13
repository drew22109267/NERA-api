r"""
Reproductibilité : chaque script écrit, à côté de ses résultats, de quoi refaire exactement le
même calcul plus tard (annexe du mémoire).

Ce qui est noté : date et heure, commande lancée, versions de Python, PyTorch, pandas,
matplotlib, système, et l'identifiant du code (commit git) s'il existe — avec un avertissement
si des fichiers ont été modifiés depuis ce commit. Tous nos tirages aléatoires (essaim
particulaire, importance par permutation) utilisent une graine fixe : avec le même code, les
mêmes données et ces versions, on retrouve les mêmes chiffres.
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
import pandas as pd
import torch


def _git(*args: str) -> str | None:
    try:
        sortie = subprocess.run(["git", *args], cwd=Path(__file__).resolve().parent.parent,
                                capture_output=True, text=True, timeout=10)
        return sortie.stdout.strip() if sortie.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def ecrire_environnement(chemin: str | Path, **contexte) -> dict:
    """Écrit (et renvoie) la fiche d'environnement au format JSON ; `contexte` = paramètres du script."""
    modifies = _git("status", "--porcelain", "--", ".")
    fiche = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "commande": " ".join(sys.argv),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "pandas": pd.__version__,
        "matplotlib": matplotlib.__version__,
        "systeme": platform.platform(),
        "commit_git": _git("rev-parse", "HEAD"),
        "fichiers_modifies_depuis_le_commit": bool(modifies) if modifies is not None else None,
        "parametres": contexte,
    }
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    Path(chemin).write_text(json.dumps(fiche, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return fiche
