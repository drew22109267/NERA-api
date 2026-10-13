// Jours fériés et vacances scolaires du Cameroun : mêmes règles et mêmes dates que la chaîne Python
// (svr/calendrier.py, donnees/feries_supplementaires.csv, donnees/vacances_scolaires.csv).
// Un test Python (tests/test_calendrier.py) vérifie que les listes ci-dessous sont identiques aux fichiers.
//
// Trois sortes de fêtes :
//   1. à date fixe : 1er janvier, 11 février (Jeunesse), 1er mai, 20 mai (fête nationale), 15 août, 25 décembre ;
//   2. liées à Pâques : Vendredi saint (Pâques − 2 j), Ascension (Pâques + 39 j) ;
//   3. musulmanes (Aïd el-Fitr, Tabaski) : fixées chaque année par la Commission nationale du croissant
//      lunaire ; on ne les calcule pas, on les recopie des communiqués (liste FERIES_ANNONCES).
(function () {
  const FIXES = [[1, 1, 'Nouvel An'], [2, 11, 'Fête de la Jeunesse'], [5, 1, 'Fête du Travail'], [5, 20, 'Fête nationale'], [8, 15, 'Assomption'], [12, 25, 'Noël']]
  // Fêtes annoncées (source détaillée dans donnees/feries_supplementaires.csv).
  const FERIES_ANNONCES = [
    ['2024-04-10', 'Aïd el-Fitr'], ['2024-06-16', 'Tabaski'], ['2024-06-17', 'Lendemain de la Tabaski (décrété férié)'],
    ['2025-03-31', 'Aïd el-Fitr'], ['2025-06-06', 'Tabaski'],
    ['2026-03-20', 'Aïd el-Fitr'], ['2026-05-27', 'Tabaski (à confirmer)'],
  ]
  // Vacances scolaires, bornes comprises (arrêtés MINEDUB/MINESEC ; voir donnees/vacances_scolaires.csv).
  const VACANCES = [
    ['2024-06-08', '2024-09-08', 'Grandes vacances 2024'], ['2024-12-21', '2025-01-05', 'Congés de Noël 2024'],
    ['2025-04-05', '2025-04-21', 'Congés de Pâques 2025'], ['2025-06-16', '2025-09-07', 'Grandes vacances 2025'],
    ['2025-12-20', '2026-01-04', 'Congés de Noël 2025'], ['2026-04-03', '2026-04-19', 'Congés de Pâques 2026'],
    ['2026-06-15', '2026-09-06', 'Grandes vacances 2026'],
  ]
  // Pâques : algorithme « anonyme grégorien » (Meeus/Jones/Butcher), comme dans svr/calendrier.py.
  function paques(an) {
    const a = an % 19, b = Math.floor(an / 100), c = an % 100, d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25)
    const g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30, i = Math.floor(c / 4), k = c % 4
    const l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451), t = h + l - 7 * m + 114
    return Date.UTC(an, Math.floor(t / 31) - 1, (t % 31) + 1) / 86400000           // numéro du jour (jours depuis 1970)
  }
  const num = (iso) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86400000
  const cache = new Map()
  // Fériés de l'année : Map numéro du jour → nom de la fête.
  function feriesAnnee(an) {
    if (cache.has(an)) return cache.get(an)
    const r = new Map(FIXES.map(([m, j, nom]) => [Date.UTC(an, m - 1, j) / 86400000, nom]))
    const p = paques(an); r.set(p - 2, 'Vendredi saint'); r.set(p + 39, 'Ascension')
    for (const [d, nom] of FERIES_ANNONCES) if (+d.slice(0, 4) === an) r.set(num(d), nom)
    cache.set(an, r); return r
  }
  const anDe = (n) => new Date(n * 86400000).getUTCFullYear()
  const PERIODES = VACANCES.map(([d, f, nom]) => ({ debut: num(d), fin: num(f), nom }))
  window.CALENDRIER_CM = {
    FERIES_ANNONCES, VACANCES, paques,
    ferie: (n) => feriesAnnee(anDe(n)).get(n) ?? null,                                 // nom de la fête, ou null
    vacances: (n) => PERIODES.find((p) => n >= p.debut && n <= p.fin)?.nom ?? null,   // nom de la période, ou null
    // Vacances connues seulement pour ces années : hors de cet intervalle, on ne sait pas (null partout).
    // (les congés de 2023-2024 avant juin 2024 ne sont pas recopiés : la saisie commence en juillet 2024).
    vacancesConnues: (n) => n >= PERIODES[0].debut && n <= PERIODES.at(-1).fin,
    periodes: PERIODES,
  }
})()
