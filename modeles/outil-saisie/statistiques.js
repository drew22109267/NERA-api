/*
  Bibliothèque statistique de l'outil de saisie — tout est écrit à la main (aucune bibliothèque).
  Chaque fonction rappelle sa formule. Utilisée par l'onglet « 3 · Indicateurs ».

  Contenu
    1. Lois de probabilité : normale, Student, khi-deux, Fisher (fonctions gamma et bêta incomplètes)
    2. Statistiques descriptives : moyenne, médiane, mode, quantiles, écart-type, asymétrie, aplatissement…
    3. Tests : Jarque-Bera, corrélations (Pearson, Spearman, Kendall) avec p-valeurs, khi-deux et V de Cramér,
       ANOVA, Kruskal-Wallis, Mann-Whitney, régression linéaire multiple
    4. Séries temporelles : ACF, PACF, Ljung-Box, ADF, KPSS, périodogramme, corrélation croisée
    5. Modèles de prévision : naïf, saisonnier naïf, moyenne mobile, lissage exponentiel simple, Holt,
       Holt-Winters additif, AR(p), ARIMA / SARIMA (somme conditionnelle des carrés + Nelder-Mead)
    6. Métriques de prévision : MAE, RMSE, MAPE, sMAPE, MASE, biais, couverture
*/
(function () {
  'use strict'
  const S = {}

  // ════════════════════════════════════════════════════════════════════════════════════
  // 1. LOIS DE PROBABILITÉ
  // ════════════════════════════════════════════════════════════════════════════════════
  // ln Γ(x) par l'approximation de Lanczos (g = 7, 9 coefficients), précise à ~1e-15.
  const LANCZOS = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
    12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7]
  S.lnGamma = function lnGamma(x) {
    if (x < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - lnGamma(1 - x)
    x -= 1; let a = LANCZOS[0]; const t = x + 7.5
    for (let i = 1; i < 9; i++) a += LANCZOS[i] / (x + i)
    return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a)
  }
  // Gamma incomplète régularisée P(a, x) : série si x < a + 1, sinon fraction continue (Lentz).
  S.gammaP = function (a, x) {
    if (x <= 0) return 0
    const pref = Math.exp(-x + a * Math.log(x) - S.lnGamma(a))
    if (x < a + 1) { let t = 1 / a, s = t, ap = a; for (let i = 0; i < 1000; i++) { ap++; t *= x / ap; s += t; if (Math.abs(t) < Math.abs(s) * 1e-15) break } return Math.min(1, s * pref) }
    let b = x + 1 - a, c = 1e300, d = 1 / b, h = d
    for (let i = 1; i < 1000; i++) { const an = -i * (i - a); b += 2; d = an * d + b; if (Math.abs(d) < 1e-300) d = 1e-300; c = b + an / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; const del = d * c; h *= del; if (Math.abs(del - 1) < 1e-15) break }
    return Math.max(0, 1 - pref * h)
  }
  // Bêta incomplète régularisée I_x(a, b) par fraction continue (Numerical Recipes, betacf).
  function betacf(a, b, x) {
    const qab = a + b, qap = a + 1, qam = a - 1; let c = 1, d = 1 - qab * x / qap
    if (Math.abs(d) < 1e-300) d = 1e-300; d = 1 / d; let h = d
    for (let m = 1; m <= 300; m++) {
      const m2 = 2 * m; let aa = m * (b - m) * x / ((qam + m2) * (a + m2))
      d = 1 + aa * d; if (Math.abs(d) < 1e-300) d = 1e-300; c = 1 + aa / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; h *= d * c
      aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
      d = 1 + aa * d; if (Math.abs(d) < 1e-300) d = 1e-300; c = 1 + aa / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d
      const del = d * c; h *= del; if (Math.abs(del - 1) < 1e-14) break
    }
    return h
  }
  S.betaI = function (a, b, x) {
    if (x <= 0) return 0; if (x >= 1) return 1
    const bt = Math.exp(S.lnGamma(a + b) - S.lnGamma(a) - S.lnGamma(b) + a * Math.log(x) + b * Math.log(1 - x))
    return x < (a + 1) / (a + b + 2) ? bt * betacf(a, b, x) / a : 1 - bt * betacf(b, a, 1 - x) / b
  }
  // Loi normale : Φ(z) via erf (Abramowitz-Stegun 7.1.26 amélioré par la relation Φ = ½ erfc(−z/√2) en série).
  S.phi = function (z) {
    // P(Z ≤ z) = ½ [1 + P(½, z²/2)·signe(z)]   (lien exact entre loi normale et gamma incomplète)
    const p = S.gammaP(0.5, z * z / 2) / 2
    return z >= 0 ? 0.5 + p : 0.5 - p
  }
  S.pNormaleBilat = (z) => 2 * (1 - S.phi(Math.abs(z)))
  // Student : P(|T| > t) = I_{ν/(ν+t²)}(ν/2, ½).
  S.pStudentBilat = (t, nu) => (nu > 0 ? S.betaI(nu / 2, 0.5, nu / (nu + t * t)) : NaN)
  // Quantile de Student à 97,5 % (pour les intervalles de confiance), par dichotomie sur la fonction ci-dessus.
  S.tCritique = function (nu, alpha = 0.05) {
    if (!(nu > 0)) return NaN; let lo = 0, hi = 50
    for (let i = 0; i < 80; i++) { const m = (lo + hi) / 2; if (S.pStudentBilat(m, nu) > alpha) lo = m; else hi = m }
    return (lo + hi) / 2
  }
  // Khi-deux : P(X > x) = 1 − P(k/2, x/2).
  S.pKhi2 = (x, k) => (x <= 0 ? 1 : 1 - S.gammaP(k / 2, x / 2))
  // Fisher : P(F > f) = I_{d2/(d2 + d1 f)}(d2/2, d1/2).
  S.pFisher = (f, d1, d2) => (f <= 0 ? 1 : S.betaI(d2 / 2, d1 / 2, d2 / (d2 + d1 * f)))

  // Quantile de la loi normale Φ⁻¹(p) (algorithme d'Acklam, erreur relative < 1,2e-9).
  S.qnorm = function (p) {
    if (p <= 0) return -Infinity; if (p >= 1) return Infinity
    const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239]
    const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572]
    const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783]
    const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416], pl = 0.02425
    if (p < pl) { const q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1) }
    if (p > 1 - pl) return -S.qnorm(1 - p)
    const q = p - 0.5, r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
  }
  // Intervalle de Wilson d'une proportion k/n : (p̂ + z²/2n ± z√(p̂(1−p̂)/n + z²/4n²)) / (1 + z²/n).
  S.wilson = function (k, n, z = 1.96) {
    if (!n) return [NaN, NaN]; const p = k / n, den = 1 + z * z / n, c = p + z * z / (2 * n), e = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [(c - e) / den, (c + e) / den]
  }

  // ════════════════════════════════════════════════════════════════════════════════════
  // 2. STATISTIQUES DESCRIPTIVES
  // ════════════════════════════════════════════════════════════════════════════════════
  const propres = (x) => x.filter((v) => v !== null && v !== undefined && Number.isFinite(v))
  S.moyenne = (x) => { const v = propres(x); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : NaN }
  // Quantile de type 7 (interpolation linéaire entre les deux valeurs voisines, comme R et pandas).
  S.quantile = function (trie, p) {
    if (!trie.length) return NaN; const h = (trie.length - 1) * p, b = Math.floor(h)
    return b + 1 < trie.length ? trie[b] + (h - b) * (trie[b + 1] - trie[b]) : trie[b]
  }
  S.descriptif = function (x) {
    const v = propres(x), n = v.length, manquants = x.length - n
    if (!n) return { n: 0, manquants }
    const t = v.slice().sort((a, b) => a - b), m = v.reduce((a, b) => a + b, 0) / n
    let m2 = 0, m3 = 0, m4 = 0; for (const e of v) { const d = e - m; m2 += d * d; m3 += d ** 3; m4 += d ** 4 }
    m2 /= n; m3 /= n; m4 /= n
    const variance = n > 1 ? m2 * n / (n - 1) : 0, ecart = Math.sqrt(variance), q = (p) => S.quantile(t, p)
    // Asymétrie G1 (corrigée) = √(n(n−1))/(n−2) · m3/m2^1,5 ; aplatissement G2 (excès, corrigé).
    const g1 = m2 > 0 ? m3 / m2 ** 1.5 : 0, g2 = m2 > 0 ? m4 / (m2 * m2) - 3 : 0
    const G1 = n > 2 ? Math.sqrt(n * (n - 1)) / (n - 2) * g1 : NaN
    const G2 = n > 3 ? ((n - 1) / ((n - 2) * (n - 3))) * ((n + 1) * g2 + 6) : NaN
    // Mode : valeur la plus fréquente (arrondie au dixième pour les valeurs continues).
    const freq = new Map(); for (const e of v) { const k = Math.round(e * 10) / 10; freq.set(k, (freq.get(k) ?? 0) + 1) }
    let mode = null, fm = 0; for (const [k, f] of freq) if (f > fm) { mode = k; fm = f }
    const med = q(0.5), mad = S.quantile(v.map((e) => Math.abs(e - med)).sort((a, b) => a - b), 0.5)
    const se = ecart / Math.sqrt(n), tc = n > 1 ? S.tCritique(n - 1) : NaN
    // Jarque-Bera : JB = n/6 · (g1² + g2²/4) ~ χ²(2) sous normalité.
    const jb = n / 6 * (g1 * g1 + g2 * g2 / 4)
    return { n, manquants, moyenne: m, mediane: med, mode, modeFreq: fm, variance, ecart, se, icBas: m - tc * se, icHaut: m + tc * se,
      min: t[0], max: t[n - 1], etendue: t[n - 1] - t[0], q1: q(0.25), q3: q(0.75), iqr: q(0.75) - q(0.25), p5: q(0.05), p10: q(0.1), p90: q(0.9), p95: q(0.95),
      mad, cv: m ? 100 * ecart / Math.abs(m) : NaN, asymetrie: G1, aplatissement: G2, somme: m * n,
      jb, pJb: S.pKhi2(jb, 2), aberrants: v.filter((e) => e < q(0.25) - 1.5 * (q(0.75) - q(0.25)) || e > q(0.75) + 1.5 * (q(0.75) - q(0.25))).length }
  }

  // ════════════════════════════════════════════════════════════════════════════════════
  // 3. CORRÉLATIONS ET TESTS
  // ════════════════════════════════════════════════════════════════════════════════════
  // Paires complètes seulement (les valeurs manquantes d'une variable ou de l'autre sont ignorées).
  function paires(x, y) { const a = [], b = []; for (let i = 0; i < x.length; i++) if (Number.isFinite(x[i]) && Number.isFinite(y[i])) { a.push(x[i]); b.push(y[i]) } return [a, b] }
  // Pearson : r = Σ(x−x̄)(y−ȳ)/√(Σ(x−x̄)²Σ(y−ȳ)²) ; test t = r√(n−2)/√(1−r²) ~ Student(n−2).
  S.pearson = function (x0, y0) {
    const [x, y] = paires(x0, y0), n = x.length; if (n < 3) return { r: NaN, p: NaN, n }
    const mx = x.reduce((a, b) => a + b, 0) / n, my = y.reduce((a, b) => a + b, 0) / n
    let sxy = 0, sxx = 0, syy = 0; for (let i = 0; i < n; i++) { const dx = x[i] - mx, dy = y[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy }
    if (!sxx || !syy) return { r: NaN, p: NaN, n }
    const r = Math.max(-1, Math.min(1, sxy / Math.sqrt(sxx * syy))), t = r * Math.sqrt((n - 2) / Math.max(1e-15, 1 - r * r))
    return { r, p: S.pStudentBilat(t, n - 2), n, pente: sxy / sxx, ordonnee: my - (sxy / sxx) * mx }
  }
  // Rangs avec ex æquo au rang moyen.
  S.rangs = function (x) {
    const idx = x.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]), r = new Array(x.length)
    for (let i = 0; i < idx.length;) { let j = i; while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++; const m = (i + j) / 2 + 1; for (let k = i; k <= j; k++) r[idx[k][1]] = m; i = j + 1 }
    return r
  }
  // Spearman = Pearson sur les rangs ; p-valeur par l'approximation de Student.
  S.spearman = function (x0, y0) { const [x, y] = paires(x0, y0); const res = S.pearson(S.rangs(x), S.rangs(y)); return { r: res.r, p: res.p, n: x.length } }
  // Kendall τ-b = (C − D)/√((n0 − n1)(n0 − n2)) ; z = 3(C − D)/√(n(n−1)(2n+5)/2) approx. normale.
  S.kendall = function (x0, y0) {
    const [x, y] = paires(x0, y0), n = x.length; if (n < 3 || n > 2500) return { tau: NaN, p: NaN, n }
    let c = 0, d = 0, tx = 0, ty = 0
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) { const a = Math.sign(x[i] - x[j]), b = Math.sign(y[i] - y[j]); if (a === 0 && b === 0) continue; if (a === 0) tx++; else if (b === 0) ty++; else if (a === b) c++; else d++ }
    const tau = (c - d) / Math.sqrt((c + d + tx) * (c + d + ty)), z = 3 * (c - d) / Math.sqrt(n * (n - 1) * (2 * n + 5) / 2)
    return { tau, p: S.pNormaleBilat(z), n }
  }
  // Tableau de contingence → χ² = Σ (O − E)²/E, ddl = (l−1)(c−1) ; V de Cramér = √(χ²/(n·(min(l,c)−1))).
  S.khi2 = function (a, b) {
    const L = [...new Set(a)], C = [...new Set(b)], O = L.map(() => C.map(() => 0))
    a.forEach((v, i) => { O[L.indexOf(v)][C.indexOf(b[i])]++ })
    const n = a.length, rl = O.map((r) => r.reduce((p, q) => p + q, 0)), cc = C.map((_, j) => O.reduce((p, r) => p + r[j], 0))
    let chi = 0; O.forEach((r, i) => r.forEach((o, j) => { const e = rl[i] * cc[j] / n; if (e > 0) chi += (o - e) ** 2 / e }))
    const ddl = (L.length - 1) * (C.length - 1), k = Math.min(L.length, C.length) - 1
    // Résidus standardisés (O − E)/√E : au-delà de ±2, la case s'écarte nettement de l'indépendance.
    const E = O.map((r, i) => r.map((_, j) => rl[i] * cc[j] / n)), residus = O.map((r, i) => r.map((o, j) => (E[i][j] ? (o - E[i][j]) / Math.sqrt(E[i][j]) : 0)))
    const faibles = E.flat().filter((e) => e < 5).length / Math.max(1, E.flat().length)
    return { E, residus, faibles, totLignes: rl, totColonnes: cc, chi2: chi, ddl, p: ddl > 0 ? S.pKhi2(chi, ddl) : NaN, v: k > 0 && n ? Math.sqrt(chi / (n * k)) : NaN, lignes: L, colonnes: C, O, n }
  }
  // Test t de Welch (variances inégales) : t = (x̄₁ − x̄₂)/√(s₁²/n₁ + s₂²/n₂), ddl de Welch-Satterthwaite.
  S.welch = function (a0, b0) {
    const a = propres(a0), b = propres(b0), n1 = a.length, n2 = b.length; if (n1 < 2 || n2 < 2) return { t: NaN, p: NaN }
    const m1 = a.reduce((p, q) => p + q, 0) / n1, m2 = b.reduce((p, q) => p + q, 0) / n2
    const v1 = a.reduce((p, q) => p + (q - m1) ** 2, 0) / (n1 - 1), v2 = b.reduce((p, q) => p + (q - m2) ** 2, 0) / (n2 - 1)
    const se2 = v1 / n1 + v2 / n2, t = (m1 - m2) / Math.sqrt(se2), ddl = se2 * se2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    // d de Cohen avec l'écart-type combiné.
    const sp = Math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    return { t, ddl, p: S.pStudentBilat(t, ddl), d: sp ? (m1 - m2) / sp : NaN }
  }
  // ANOVA à un facteur : F = (SCE_inter/(k−1)) / (SCE_intra/(n−k)).
  S.anova = function (groupes) {
    const g = groupes.filter((x) => x.length), n = g.reduce((a, b) => a + b.length, 0), k = g.length, m = g.flat().reduce((a, b) => a + b, 0) / n
    let inter = 0, intra = 0; for (const x of g) { const mx = x.reduce((a, b) => a + b, 0) / x.length; inter += x.length * (mx - m) ** 2; intra += x.reduce((a, b) => a + (b - mx) ** 2, 0) }
    const f = (inter / (k - 1)) / (intra / (n - k))
    return { f, d1: k - 1, d2: n - k, p: S.pFisher(f, k - 1, n - k), eta2: inter / (inter + intra) }
  }
  // Kruskal-Wallis : H = 12/(n(n+1)) Σ R_j²/n_j − 3(n+1) ~ χ²(k−1) (sans correction des ex æquo).
  S.kruskal = function (groupes) {
    const g = groupes.filter((x) => x.length), tout = g.flat(), r = S.rangs(tout), n = tout.length; let pos = 0, h = 0
    for (const x of g) { const s = r.slice(pos, pos + x.length).reduce((a, b) => a + b, 0); h += s * s / x.length; pos += x.length }
    h = 12 / (n * (n + 1)) * h - 3 * (n + 1)
    return { h, ddl: g.length - 1, p: S.pKhi2(h, g.length - 1), epsilon2: h / (n - 1) }
  }
  // Mann-Whitney : U = R₁ − n₁(n₁+1)/2 ; z = (U − n₁n₂/2)/√(n₁n₂(n₁+n₂+1)/12).
  S.mannWhitney = function (a, b) {
    const r = S.rangs([...a, ...b]), R1 = r.slice(0, a.length).reduce((p, q) => p + q, 0), n1 = a.length, n2 = b.length
    const u = R1 - n1 * (n1 + 1) / 2, z = (u - n1 * n2 / 2) / Math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    return { u, z, p: S.pNormaleBilat(z), r: Math.abs(z) / Math.sqrt(n1 + n2) }
  }
  // Résout A x = b (Gauss-Jordan avec pivot partiel) ; renvoie aussi l'inverse de A.
  function inverser(A) {
    const n = A.length, M = A.map((r, i) => [...r, ...r.map((_, j) => (i === j ? 1 : 0))])
    for (let c = 0; c < n; c++) {
      let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r
      if (Math.abs(M[p][c]) < 1e-12) return null; [M[c], M[p]] = [M[p], M[c]]
      const d = M[c][c]; for (let j = 0; j < 2 * n; j++) M[c][j] /= d
      for (let r = 0; r < n; r++) if (r !== c) { const f = M[r][c]; for (let j = 0; j < 2 * n; j++) M[r][j] -= f * M[c][j] }
    }
    return M.map((r) => r.slice(n))
  }
  S.inverser = inverser
  // Régression linéaire multiple par moindres carrés : β = (XᵀX)⁻¹Xᵀy ; se(β) = √(σ² diag((XᵀX)⁻¹)).
  S.regression = function (X0, y0, noms) {
    const lignes = []; X0.forEach((x, i) => { if (Number.isFinite(y0[i]) && x.every(Number.isFinite)) lignes.push([1, ...x, y0[i]]) })
    const n = lignes.length, p = (X0[0]?.length ?? 0) + 1; if (n <= p + 1) return null
    const X = lignes.map((l) => l.slice(0, p)), y = lignes.map((l) => l[p])
    const XtX = Array.from({ length: p }, (_, i) => Array.from({ length: p }, (_, j) => X.reduce((a, r) => a + r[i] * r[j], 0)))
    const inv = inverser(XtX); if (!inv) return null
    const Xty = Array.from({ length: p }, (_, i) => X.reduce((a, r, k) => a + r[i] * y[k], 0)), beta = inv.map((r) => r.reduce((a, v, j) => a + v * Xty[j], 0))
    const yhat = X.map((r) => r.reduce((a, v, j) => a + v * beta[j], 0)), ym = y.reduce((a, b) => a + b, 0) / n
    const sce = y.reduce((a, v, i) => a + (v - yhat[i]) ** 2, 0), sct = y.reduce((a, v) => a + (v - ym) ** 2, 0), s2 = sce / (n - p)
    const r2 = 1 - sce / sct, r2a = 1 - (1 - r2) * (n - 1) / (n - p), f = ((sct - sce) / (p - 1)) / s2
    return { n, r2, r2a, f, pF: S.pFisher(f, p - 1, n - p), rmse: Math.sqrt(sce / n), y, yhat, X: X.map((r) => r.slice(1)),
      coef: beta.map((b, j) => { const se = Math.sqrt(s2 * inv[j][j]), t = b / se; return { nom: j ? noms[j - 1] : 'Constante', b, se, t, p: S.pStudentBilat(t, n - p) } }) }
  }

  // Valeurs et vecteurs propres d'une matrice symétrique (méthode de Jacobi : rotations successives qui
  // annulent le plus grand terme hors diagonale ; converge pour toute matrice symétrique).
  S.jacobi = function (A0) {
    const p = A0.length, A = A0.map((r) => [...r]), V = A.map((_, i) => A.map((_, j) => (i === j ? 1 : 0)))
    for (let it = 0; it < 100 * p * p; it++) {
      let k = 0, l = 1, max = 0
      for (let i = 0; i < p; i++) for (let j = i + 1; j < p; j++) if (Math.abs(A[i][j]) > max) { max = Math.abs(A[i][j]); k = i; l = j }
      if (max < 1e-12) break
      const th = 0.5 * Math.atan2(2 * A[k][l], A[l][l] - A[k][k]), c = Math.cos(th), s = Math.sin(th)
      for (let i = 0; i < p; i++) { const aik = A[i][k], ail = A[i][l]; A[i][k] = c * aik - s * ail; A[i][l] = s * aik + c * ail }
      for (let j = 0; j < p; j++) { const akj = A[k][j], alj = A[l][j]; A[k][j] = c * akj - s * alj; A[l][j] = s * akj + c * alj }
      for (let i = 0; i < p; i++) { const vik = V[i][k], vil = V[i][l]; V[i][k] = c * vik - s * vil; V[i][l] = s * vik + c * vil }
    }
    const ordre = A.map((_, i) => i).sort((a, b) => A[b][b] - A[a][a])
    return { valeurs: ordre.map((i) => A[i][i]), vecteurs: ordre.map((i) => V.map((r) => r[i])) }
  }
  const matriceCorrelation = (Z, n) => Z[0].map((_, i) => Z[0].map((_, j) => Z.reduce((a, r) => a + r[i] * r[j], 0) / (n - 1)))
  // Générateur pseudo-aléatoire à graine (mulberry32) : l'analyse parallèle donne le même résultat à chaque calcul.
  const alea = (graine) => () => { graine |= 0; graine = (graine + 0x6d2b79f5) | 0; let t = Math.imul(graine ^ (graine >>> 15), 1 | graine); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }

  // Analyse en composantes principales normée (variables centrées-réduites, diagonalisation de la matrice
  // des corrélations R = ZᵀZ/(n−1)). X : lignes complètes (n × p).
  //  · valeurs propres λ_k = variance portée par l'axe k (somme = p) ; inertie = λ_k / p ;
  //  · coordonnées des individus F = Z·u_k ; corrélation variable–axe r_jk = u_jk·√λ_k ;
  //  · cos² = r_jk² (qualité de représentation) ; contribution = u_jk² (somme 100 % par axe) ;
  //  · Bartlett : χ² = −(n − 1 − (2p + 5)/6)·ln|R|, ddl p(p−1)/2 (H0 : R = identité, rien à résumer) ;
  //  · KMO = Σr² / (Σr² + Σa²), a = corrélations partielles tirées de R⁻¹ (> 0,5 : ACP justifiée) ;
  //  · analyse parallèle de Horn : 95e centile des valeurs propres de données permutées (axes au-delà du hasard) ;
  //  · bâton brisé : b_k = Σ_{i=k..p} 1/i.
  S.acp = function (X, noms, { permutations = 100 } = {}) {
    const n = X.length, p = X[0]?.length ?? 0; if (n < p + 3 || p < 2) return null
    const moy = Array.from({ length: p }, (_, j) => X.reduce((a, r) => a + r[j], 0) / n)
    const et = moy.map((m, j) => Math.sqrt(X.reduce((a, r) => a + (r[j] - m) ** 2, 0) / (n - 1)))
    if (et.some((s) => !(s > 0))) return null
    const Z = X.map((r) => r.map((v, j) => (v - moy[j]) / et[j])), R = matriceCorrelation(Z, n)
    const { valeurs: lam0, vecteurs: U0 } = S.jacobi(R), valeurs = lam0.map((v) => Math.max(0, v))
    // Signe : la variable la plus liée à l'axe y est positive (choix arbitraire mais stable d'un calcul à l'autre).
    const U = U0.map((u) => { const m = u.reduce((a, v, j) => (Math.abs(v) > Math.abs(u[a]) ? j : a), 0); return u[m] < 0 ? u.map((v) => -v) : u })
    const scores = Z.map((z) => U.map((u) => z.reduce((a, v, j) => a + v * u[j], 0)))
    const charges = noms.map((_, j) => U.map((u, k) => u[j] * Math.sqrt(valeurs[k])))
    const cos2 = charges.map((r) => r.map((v) => v * v)), contrib = noms.map((_, j) => U.map((u) => 100 * u[j] * u[j]))
    const det = valeurs.reduce((a, v) => a * Math.max(v, 1e-300), 1), ddl = p * (p - 1) / 2
    const chi2 = -(n - 1 - (2 * p + 5) / 6) * Math.log(det)
    const inv = S.inverser(R); let kmo = NaN, msa = noms.map(() => NaN)
    if (inv) {
      const a = R.map((r, i) => r.map((_, j) => (i === j ? 0 : -inv[i][j] / Math.sqrt(inv[i][i] * inv[j][j]))))
      let sr = 0, sa = 0; msa = noms.map((_, i) => { let r2 = 0, a2 = 0; for (let j = 0; j < p; j++) if (j !== i) { r2 += R[i][j] ** 2; a2 += a[i][j] ** 2 } sr += r2; sa += a2; return r2 / (r2 + a2) })
      kmo = sr / (sr + sa)
    }
    const rnd = alea(20250101), tirages = Array.from({ length: p }, () => [])
    for (let b = 0; b < permutations; b++) {
      const cols = Array.from({ length: p }, (_, j) => { const c = Z.map((r) => r[j]); for (let i = n - 1; i > 0; i--) { const k = Math.floor(rnd() * (i + 1)); [c[i], c[k]] = [c[k], c[i]] } return c })
      const Rb = matriceCorrelation(Z.map((_, i) => cols.map((c) => c[i])), n)
      S.jacobi(Rb).valeurs.forEach((v, k) => tirages[k].push(v))
    }
    const parallele = tirages.map((t) => S.quantile(t.sort((a, b) => a - b), 0.95))
    const baton = valeurs.map((_, k) => { let s = 0; for (let i = k + 1; i <= p; i++) s += 1 / i; return s })
    const retenus = Math.max(1, valeurs.filter((v, k) => v > parallele[k]).length)
    return { n, p, noms, moy, et, R, valeurs, vecteurs: U, scores, charges, cos2, contrib, parallele, baton, retenus, kmo, msa,
      bartlett: { chi2, ddl, p: S.pKhi2(chi2, ddl) }, inertie: valeurs.map((v) => 100 * v / p) }
  }

  // ════════════════════════════════════════════════════════════════════════════════════
  // 4. SÉRIES TEMPORELLES
  // ════════════════════════════════════════════════════════════════════════════════════
  S.acf = function (x, kmax) {
    const n = x.length, m = x.reduce((a, b) => a + b, 0) / n, c = x.map((v) => v - m), den = c.reduce((a, b) => a + b * b, 0) || 1
    return Array.from({ length: kmax + 1 }, (_, k) => { let s = 0; for (let t = 0; t + k < n; t++) s += c[t] * c[t + k]; return s / den })
  }
  // PACF par Durbin-Levinson.
  S.pacf = function (x, kmax) {
    const r = S.acf(x, kmax), res = [1]; let prec = []
    for (let k = 1; k <= kmax; k++) {
      const num = r[k] - prec.reduce((a, p, j) => a + p * r[k - 1 - j], 0), den = 1 - prec.reduce((a, p, j) => a + p * r[j + 1], 0)
      const pkk = den ? num / den : 0, cour = prec.map((p, j) => p - pkk * prec[k - 2 - j]); cour.push(pkk); prec = cour; res.push(pkk)
    }
    return res
  }
  // Ljung-Box : Q = n(n+2) Σ_{k=1..m} ρ̂_k²/(n−k) ~ χ²(m − ajustés).
  S.ljungBox = function (x, m, ajustes = 0) {
    const n = x.length, r = S.acf(x, m); let q = 0; for (let k = 1; k <= m; k++) q += r[k] * r[k] / (n - k)
    q *= n * (n + 2); return { q, ddl: m - ajustes, p: S.pKhi2(q, Math.max(1, m - ajustes)) }
  }
  // ADF (avec constante) : Δy_t = α + γ y_{t−1} + Σ δ_i Δy_{t−i} + ε ; statistique t de γ,
  // comparée aux valeurs critiques de MacKinnon (−3,43 à 1 %, −2,86 à 5 %, −2,57 à 10 %).
  S.adf = function (y, p) {
    p ??= Math.min(14, Math.floor(12 * (y.length / 100) ** 0.25))
    const dy = y.slice(1).map((v, i) => v - y[i]), X = [], Y = []
    for (let t = p; t < dy.length; t++) { X.push([y[t], ...Array.from({ length: p }, (_, i) => dy[t - 1 - i])]); Y.push(dy[t]) }
    const r = S.regression(X, Y, ['y(t−1)', ...Array.from({ length: p }, (_, i) => `Δy(t−${i + 1})`)]); if (!r) return null
    const t = r.coef[1].t
    return { stat: t, retards: p, critiques: { '1 %': -3.43, '5 %': -2.86, '10 %': -2.57 }, stationnaire5: t < -2.86 }
  }
  // KPSS (niveau) : η = Σ S_t² / (n² σ̂²_lr), S_t = somme cumulée des écarts à la moyenne,
  // σ̂²_lr de Newey-West (noyau de Bartlett). Valeurs critiques : 0,347 (10 %), 0,463 (5 %), 0,739 (1 %).
  S.kpss = function (y) {
    const n = y.length, m = y.reduce((a, b) => a + b, 0) / n, e = y.map((v) => v - m), l = Math.floor(4 * (n / 100) ** 0.25)
    let s = 0, num = 0; for (const v of e) { s += v; num += s * s }
    let lr = e.reduce((a, v) => a + v * v, 0) / n
    for (let k = 1; k <= l; k++) { let g = 0; for (let t = k; t < n; t++) g += e[t] * e[t - k]; lr += 2 * (1 - k / (l + 1)) * g / n }
    const eta = num / (n * n * lr)
    return { stat: eta, retards: l, critiques: { '10 %': 0.347, '5 %': 0.463, '1 %': 0.739 }, stationnaire5: eta < 0.463 }
  }
  // Périodogramme : I(f) = |Σ (x_t − x̄) e^{−2iπft}|² / n pour f = 1/n … ½ ; période = 1/f (en jours).
  S.periodogramme = function (x) {
    const n = x.length, m = x.reduce((a, b) => a + b, 0) / n, res = []
    for (let k = 1; k <= Math.floor(n / 2); k++) { let re = 0, im = 0; for (let t = 0; t < n; t++) { const a = 2 * Math.PI * k * t / n; re += (x[t] - m) * Math.cos(a); im -= (x[t] - m) * Math.sin(a) } res.push({ periode: n / k, puissance: (re * re + im * im) / n }) }
    return res
  }
  // Corrélation croisée : ρ_xy(k) = corr(x_{t−k}, y_t) pour k = 0 … kmax.
  S.ccf = (x, y, kmax) => Array.from({ length: kmax + 1 }, (_, k) => S.pearson(x.slice(0, x.length - k), y.slice(k)).r)
  // Force de la tendance et de la saisonnalité (Wang, Smith & Hyndman) : F = max(0, 1 − Var(R)/Var(composante + R)).
  S.forces = function (tend, saison, residu) {
    const v = (a) => { const p = a.filter(Number.isFinite), m = p.reduce((q, r) => q + r, 0) / p.length; return p.reduce((q, r) => q + (r - m) ** 2, 0) / p.length }
    const idx = residu.map((r, i) => i).filter((i) => Number.isFinite(residu[i]) && Number.isFinite(tend[i]))
    const R = idx.map((i) => residu[i]), TR = idx.map((i) => tend[i] + residu[i]), SR = idx.map((i) => saison[i] + residu[i])
    return { tendance: Math.max(0, 1 - v(R) / v(TR)), saisonnalite: Math.max(0, 1 - v(R) / v(SR)) }
  }

  // ════════════════════════════════════════════════════════════════════════════════════
  // 5. MODÈLES DE PRÉVISION
  //    Chaque modèle renvoie des prévisions « un pas en avant » (faites le soir du jour t pour t + 1)
  //    sur toute la série, et une fonction de prévision à h jours depuis la fin.
  // ════════════════════════════════════════════════════════════════════════════════════
  // Nelder-Mead (simplexe) : minimise f sur ℝᵈ ; réflexion 1, expansion 2, contraction ½, réduction ½.
  S.nelderMead = function (f, x0, { pas = 0.1, iterations = 400, tol = 1e-9 } = {}) {
    const d = x0.length; let simplexe = [x0.slice(), ...x0.map((_, i) => { const p = x0.slice(); p[i] += pas; return p })].map((x) => ({ x, v: f(x) }))
    for (let it = 0; it < iterations; it++) {
      simplexe.sort((a, b) => a.v - b.v)
      if (Math.abs(simplexe[d].v - simplexe[0].v) < tol * (1 + Math.abs(simplexe[0].v))) break
      const c = Array.from({ length: d }, (_, j) => simplexe.slice(0, d).reduce((a, s) => a + s.x[j], 0) / d), pire = simplexe[d]
      const pt = (k) => c.map((cj, j) => cj + k * (pire.x[j] - cj)), r = pt(-1), vr = f(r)
      if (vr < simplexe[0].v) { const e = pt(-2), ve = f(e); simplexe[d] = ve < vr ? { x: e, v: ve } : { x: r, v: vr } }
      else if (vr < simplexe[d - 1].v) simplexe[d] = { x: r, v: vr }
      else { const k = pt(0.5), vk = f(k); if (vk < pire.v) simplexe[d] = { x: k, v: vk }; else simplexe = simplexe.map((s, i) => (i ? { x: s.x.map((v, j) => simplexe[0].x[j] + 0.5 * (v - simplexe[0].x[j])), v: 0 } : s)).map((s, i) => (i ? { x: s.x, v: f(s.x) } : s)) }
    }
    simplexe.sort((a, b) => a.v - b.v); return simplexe[0]
  }
  const sig = (u) => 1 / (1 + Math.exp(-u))                     // paramètre dans ]0, 1[
  // Somme des carrés des erreurs un pas en avant, sur les seuls jours d'apprentissage t < fin.
  const sse = (y, p, debut = 1, fin = y.length) => { let s = 0; for (let t = debut; t < fin; t++) if (Number.isFinite(p[t])) s += (y[t] - p[t]) ** 2; return s }

  S.modeles = {
    naif: (y) => ({ nom: 'Naïf (demain = aujourd’hui)', k: 0, unPas: y.map((_, t) => (t ? y[t - 1] : NaN)), prevoir: (h) => Array(h).fill(y.at(-1)) }),
    saisonnierNaif: (y, fin, s = 7) => ({ nom: `Saisonnier naïf (même jour il y a ${s} j)`, k: 0, unPas: y.map((_, t) => (t >= s ? y[t - s] : NaN)), prevoir: (h) => Array.from({ length: h }, (_, i) => y[y.length - s + (i % s)]) }),
    moyenne: (y) => { const p = y.map((_, t) => (t ? y.slice(0, t).reduce((a, b) => a + b, 0) / t : NaN)); return { nom: 'Moyenne historique', k: 1, unPas: p, prevoir: (h) => Array(h).fill(y.reduce((a, b) => a + b, 0) / y.length) } },
    moyenneMobile: (y, fin, k = 7) => ({ nom: `Moyenne mobile ${k} j`, k: 0, unPas: y.map((_, t) => (t >= k ? y.slice(t - k, t).reduce((a, b) => a + b, 0) / k : NaN)), prevoir: (h) => Array(h).fill(y.slice(-k).reduce((a, b) => a + b, 0) / k) }),
    // Lissage exponentiel simple : l_t = α y_t + (1 − α) l_{t−1} ; ŷ_{t+1} = l_t.
    ses: (y, fin = y.length) => {
      const run = (a) => { const p = [NaN]; let l = y[0]; for (let t = 1; t < y.length; t++) { p.push(l); l = a * y[t] + (1 - a) * l } return { p, l } }
      const best = S.nelderMead((u) => sse(y, run(sig(u[0])).p, 1, fin), [0]), a = sig(best.x[0]), r = run(a)
      return { nom: `Lissage exponentiel simple (α = ${a.toFixed(2).replace('.', ',')})`, k: 1, unPas: r.p, prevoir: (h) => Array(h).fill(r.l), params: { alpha: a } }
    },
    // Holt (tendance amortie φ) : l_t = α y_t + (1 − α)(l + φb) ; b_t = β(l_t − l_{t−1}) + (1 − β)φb.
    holt: (y, fin = y.length) => {
      const run = (a, b, ph) => { const p = [NaN, NaN]; let l = y[1], tr = y[1] - y[0]; for (let t = 2; t < y.length; t++) { p.push(l + ph * tr); const l0 = l; l = a * y[t] + (1 - a) * (l + ph * tr); tr = b * (l - l0) + (1 - b) * ph * tr } return { p, l, tr } }
      const best = S.nelderMead((u) => sse(y, run(sig(u[0]), sig(u[1]), 0.8 + 0.18 * sig(u[2])).p, 2, fin), [0, -2, 1]), [a, b, ph] = [sig(best.x[0]), sig(best.x[1]), 0.8 + 0.18 * sig(best.x[2])], r = run(a, b, ph)
      return { nom: `Holt amorti (α = ${a.toFixed(2).replace('.', ',')}, β = ${b.toFixed(2).replace('.', ',')}, φ = ${ph.toFixed(2).replace('.', ',')})`, k: 3, unPas: r.p, prevoir: (h) => Array.from({ length: h }, (_, i) => { let s = 0; for (let j = 1; j <= i + 1; j++) s += ph ** j; return r.l + s * r.tr }) }
    },
    // Holt linéaire (tendance non amortie, φ = 1) : la tendance est prolongée telle quelle (ŷ_{t+h} = l_t + h·b_t).
    holtLineaire: (y, fin = y.length) => {
      const run = (a, b) => { const p = [NaN, NaN]; let l = y[1], tr = y[1] - y[0]; for (let t = 2; t < y.length; t++) { p.push(l + tr); const l0 = l; l = a * y[t] + (1 - a) * (l + tr); tr = b * (l - l0) + (1 - b) * tr } return { p, l, tr } }
      const best = S.nelderMead((u) => sse(y, run(sig(u[0]), sig(u[1])).p, 2, fin), [0, -2]), [a, b] = [sig(best.x[0]), sig(best.x[1])], r = run(a, b)
      return { nom: `Holt linéaire (α = ${a.toFixed(2).replace('.', ',')}, β = ${b.toFixed(2).replace('.', ',')})`, k: 2, unPas: r.p, prevoir: (h) => Array.from({ length: h }, (_, i) => r.l + (i + 1) * r.tr) }
    },
    // Lissage exponentiel saisonnier sans tendance (s = 7) : l_t = α(y_t − s_{t−7}) + (1 − α)l_{t−1} ;
    // s_t = γ(y_t − l_t) + (1 − γ)s_{t−7} ; ŷ_{t+h} = l_t + s_{t+h−7}. Utile quand il n'y a pas de tendance.
    sesSaisonnier: (y, fin = y.length, s = 7) => {
      if (y.length < 3 * s) return null
      const run = (a, g) => {
        let l = y.slice(0, s).reduce((p, q) => p + q, 0) / s; const se = y.slice(0, s).map((v) => v - l), p = Array(s).fill(NaN)
        for (let t = s; t < y.length; t++) { p.push(l + se[t - s]); l = a * (y[t] - se[t - s]) + (1 - a) * l; se.push(g * (y[t] - l) + (1 - g) * se[t - s]) }
        return { p, l, se }
      }
      const best = S.nelderMead((u) => sse(y, run(sig(u[0]), sig(u[1])).p, s, fin), [0, -1]), [a, g] = [sig(best.x[0]), sig(best.x[1])], r = run(a, g), n = y.length
      return { nom: `Lissage saisonnier sans tendance (α = ${a.toFixed(2).replace('.', ',')}, γ = ${g.toFixed(2).replace('.', ',')})`, k: 2 + s, unPas: r.p,
        prevoir: (h) => Array.from({ length: h }, (_, i) => r.l + r.se[n - s + (i % s)]) }
    },
    // Holt-Winters multiplicatif (s = 7) : la saison est un coefficient (× 1,2 le mercredi…), pour des séries
    // dont l'amplitude hebdomadaire grandit avec le niveau. Seulement si toutes les valeurs sont > 0.
    holtWintersMult: (y, fin = y.length, s = 7) => {
      if (y.length < 3 * s || y.some((v) => !(v > 0))) return null
      const run = (a, b, g, ph) => {
        let l = y.slice(0, s).reduce((p, q) => p + q, 0) / s, tr = (y.slice(s, 2 * s).reduce((p, q) => p + q, 0) / s - l) / s
        const se = y.slice(0, s).map((v) => v / l), p = Array(s).fill(NaN)
        for (let t = s; t < y.length; t++) { p.push((l + ph * tr) * se[t - s]); const l0 = l; l = a * (y[t] / se[t - s]) + (1 - a) * (l + ph * tr); tr = b * (l - l0) + (1 - b) * ph * tr; se.push(g * (y[t] / l) + (1 - g) * se[t - s]) }
        return { p, l, tr, se }
      }
      const best = S.nelderMead((u) => sse(y, run(sig(u[0]), sig(u[1]), sig(u[2]), 0.8 + 0.18 * sig(u[3])).p, s, fin), [0, -2, -1, 1])
      const [a, b, g, ph] = [sig(best.x[0]), sig(best.x[1]), sig(best.x[2]), 0.8 + 0.18 * sig(best.x[3])], r = run(a, b, g, ph), n = y.length
      return { nom: `Holt-Winters multiplicatif (α = ${a.toFixed(2).replace('.', ',')}, β = ${b.toFixed(2).replace('.', ',')}, γ = ${g.toFixed(2).replace('.', ',')})`, k: 4 + s, unPas: r.p,
        prevoir: (h) => Array.from({ length: h }, (_, i) => { let sm = 0; for (let j = 1; j <= i + 1; j++) sm += ph ** j; return (r.l + sm * r.tr) * r.se[n - s + (i % s)] }) }
    },
    // Méthode Thêta (Assimakopoulos et Nikolopoulos, 2000 ; forme de Hyndman et Billah, 2003) : lissage
    // exponentiel simple + la moitié de la pente de la droite de tendance b̂ (moindres carrés sur le temps) :
    // ŷ_{t+h} = l_t + ½ b̂ (h − 1 + 1/α). Souvent excellente sur les séries courtes.
    theta: (y, fin = y.length) => {
      const n0 = fin, tm = (n0 - 1) / 2, ym = y.slice(0, n0).reduce((p, q) => p + q, 0) / n0
      let num = 0, den = 0; for (let t = 0; t < n0; t++) { num += (t - tm) * (y[t] - ym); den += (t - tm) ** 2 } const b = den ? num / den : 0
      const run = (a) => { const p = [NaN]; let l = y[0]; for (let t = 1; t < y.length; t++) { p.push(l + 0.5 * b / a); l = a * y[t] + (1 - a) * l } return { p, l } }
      const best = S.nelderMead((u) => sse(y, run(sig(u[0])).p, 1, fin), [0]), a = sig(best.x[0]), r = run(a)
      return { nom: `Méthode Thêta (α = ${a.toFixed(2).replace('.', ',')})`, k: 2, unPas: r.p, prevoir: (h) => Array.from({ length: h }, (_, i) => r.l + 0.5 * b * (i + 1 / a)) }
    },
    // Holt-Winters additif (saison s) : niveau, tendance amortie et 7 indices saisonniers.
    holtWinters: (y, fin = y.length, s = 7) => {
      if (y.length < 3 * s) return null
      const run = (a, b, g, ph) => {
        let l = y.slice(0, s).reduce((p, q) => p + q, 0) / s, tr = (y.slice(s, 2 * s).reduce((p, q) => p + q, 0) / s - l) / s
        const se = y.slice(0, s).map((v) => v - l), p = Array(s).fill(NaN)
        for (let t = s; t < y.length; t++) { p.push(l + ph * tr + se[t - s]); const l0 = l; l = a * (y[t] - se[t - s]) + (1 - a) * (l + ph * tr); tr = b * (l - l0) + (1 - b) * ph * tr; se.push(g * (y[t] - l) + (1 - g) * se[t - s]) }
        return { p, l, tr, se }
      }
      const best = S.nelderMead((u) => sse(y, run(sig(u[0]), sig(u[1]), sig(u[2]), 0.8 + 0.18 * sig(u[3])).p, s, fin), [0, -2, -1, 1])
      const [a, b, g, ph] = [sig(best.x[0]), sig(best.x[1]), sig(best.x[2]), 0.8 + 0.18 * sig(best.x[3])], r = run(a, b, g, ph), n = y.length
      return { nom: `Holt-Winters additif (α = ${a.toFixed(2).replace('.', ',')}, β = ${b.toFixed(2).replace('.', ',')}, γ = ${g.toFixed(2).replace('.', ',')})`, k: 4 + s, unPas: r.p,
        prevoir: (h) => Array.from({ length: h }, (_, i) => { let sm = 0; for (let j = 1; j <= i + 1; j++) sm += ph ** j; return r.l + sm * r.tr + r.se[n - s + (i % s)] }) }
    },
    // AR(p) par moindres carrés, p choisi par AIC entre 1 et pmax.
    ar: (y, fin = y.length, pmax = 14) => {
      let meilleur = null
      for (let p = 1; p <= Math.min(pmax, Math.floor(fin / 4)); p++) {
        const X = [], Y = []; for (let t = p; t < fin; t++) { X.push(Array.from({ length: p }, (_, i) => y[t - 1 - i])); Y.push(y[t]) }
        const r = S.regression(X, Y, Array.from({ length: p }, (_, i) => `y(t−${i + 1})`)); if (!r) continue
        const sce = r.rmse ** 2 * r.n, aic = r.n * Math.log(sce / r.n) + 2 * (p + 1)
        if (!meilleur || aic < meilleur.aic) meilleur = { p, r, aic }
      }
      if (!meilleur) return null
      const c = meilleur.r.coef.map((e) => e.b), p = meilleur.p, pred = (hist) => c[0] + c.slice(1).reduce((a, b, i) => a + b * hist[hist.length - 1 - i], 0)
      return { nom: `AR(${p}) (ordre choisi par AIC)`, k: p + 1, aic: meilleur.aic, coef: meilleur.r.coef, unPas: y.map((_, t) => (t >= p ? pred(y.slice(0, t)) : NaN)),
        prevoir: (h) => { const hist = y.slice(); const out = []; for (let i = 0; i < h; i++) { const v = pred(hist); out.push(v); hist.push(v) } return out } }
    },
  }

  // ── ARIMA / SARIMA ─────────────────────────────────────────────────────────────────
  // (1 − φ₁B − …)(1 − Φ₁Bˢ − …)(1 − B)ᵈ(1 − Bˢ)ᴰ y_t = c + (1 + θ₁B + …)(1 + Θ₁Bˢ + …) ε_t
  // Estimation par somme conditionnelle des carrés des innovations (CSS), minimisée par Nelder-Mead ;
  // les paramètres passent par tanh pour rester dans ]−1, 1[ (stationnarité / inversibilité approchées).
  const mulPoly = (a, b) => { const r = Array(a.length + b.length - 1).fill(0); a.forEach((x, i) => b.forEach((y, j) => { r[i + j] += x * y })); return r }
  const polySaison = (coefs, s, signe) => { const p = Array(coefs.length * s + 1).fill(0); p[0] = 1; coefs.forEach((c, i) => { p[(i + 1) * s] = signe * c }); return p }
  const polyCourt = (coefs, signe) => [1, ...coefs.map((c) => signe * c)]
  const differencier = (y, d, D, s) => { let z = y.slice(); for (let i = 0; i < d; i++) z = z.slice(1).map((v, t) => v - z[t]); for (let i = 0; i < D; i++) z = z.slice(s).map((v, t) => v - z[t]); return z }
  S.sarima = function (y, ordre, fin = y.length) {
    const { p = 1, d = 0, q = 0, P = 0, D = 0, Q = 0, s = 7 } = ordre, z = differencier(y, d, D, s), n = z.length, nFit = n - (y.length - fin)
    if (nFit < 3 * (p + q + (P + Q) * s + 2)) return null
    const k = p + q + P + Q + 1
    const decoder = (u) => ({ phi: u.slice(0, p).map(Math.tanh), theta: u.slice(p, p + q).map(Math.tanh), Phi: u.slice(p + q, p + q + P).map(Math.tanh), Theta: u.slice(p + q + P, p + q + P + Q).map(Math.tanh), c: u[k - 1] })
    // Polynômes développés : AR(B) = φ(B)Φ(Bˢ) (coefficients à soustraire), MA(B) = θ(B)Θ(Bˢ).
    const polys = (m) => ({ ar: mulPoly(polyCourt(m.phi, -1), polySaison(m.Phi, s, -1)), ma: mulPoly(polyCourt(m.theta, 1), polySaison(m.Theta, s, 1)) })
    const filtrer = (m) => {
      const { ar, ma } = polys(m), e = Array(n).fill(0), pred = Array(n).fill(NaN), debut = Math.max(ar.length, ma.length) - 1
      for (let t = 0; t < n; t++) {
        let v = m.c; for (let i = 1; i < ar.length; i++) v -= ar[i] * (t - i >= 0 ? z[t - i] : 0); for (let j = 1; j < ma.length; j++) v += ma[j] * (t - j >= 0 ? e[t - j] : 0)
        pred[t] = v; e[t] = t < debut ? 0 : z[t] - v
      }
      return { e, pred, debut }
    }
    const zm = z.slice(0, nFit).reduce((a, b) => a + b, 0) / nFit
    const best = S.nelderMead((u) => { const f = filtrer(decoder(u)); let s2 = 0; for (let t = f.debut; t < nFit; t++) s2 += f.e[t] ** 2; return Number.isFinite(s2) ? s2 : 1e300 }, [...Array(k - 1).fill(0.1), zm * 0.5], { pas: 0.3, iterations: 120 * k })
    const m = decoder(best.x), f = filtrer(m), m2 = nFit - f.debut, sigma2 = best.v / m2
    const aic = m2 * Math.log(sigma2) + 2 * (k + 1), bic = m2 * Math.log(sigma2) + Math.log(m2) * (k + 1)
    // Retour à l'échelle d'origine : AR complet = AR(B)·(1 − B)ᵈ·(1 − Bˢ)ᴰ.
    let arComplet = polys(m).ar; for (let i = 0; i < d; i++) arComplet = mulPoly(arComplet, [1, -1]); for (let i = 0; i < D; i++) arComplet = mulPoly(arComplet, polySaison([1], s, -1))
    const maC = polys(m).ma
    // Prévision un pas en avant sur la série d'origine (avec les innovations estimées).
    const decal = y.length - n, eY = Array(y.length).fill(0); for (let t = 0; t < n; t++) eY[t + decal] = f.e[t]
    const unPas = y.map((_, t) => { if (t < decal + f.debut) return NaN; let v = m.c; for (let i = 1; i < arComplet.length; i++) v -= arComplet[i] * (t - i >= 0 ? y[t - i] : 0); for (let j = 1; j < maC.length; j++) v += maC[j] * (t - j >= 0 ? eY[t - j] : 0); return v })
    // Poids ψ (représentation MA(∞)) pour les intervalles : Var(e_h) = σ² Σ_{j<h} ψ_j².
    const psi = (h) => { const w = [1]; for (let j = 1; j < h; j++) { let v = j < maC.length ? maC[j] : 0; for (let i = 1; i < arComplet.length && i <= j; i++) v -= arComplet[i] * w[j - i]; w.push(v) } return w }
    return {
      nom: `SARIMA(${p},${d},${q})(${P},${D},${Q})${s}`, ordre: { p, d, q, P, D, Q, s }, k: k + 1, aic, bic, sigma2, params: m, residus: f.e.slice(f.debut, nFit), unPas,
      prevoir: (h) => {
        const yy = y.slice(), ee = eY.slice(), out = []
        for (let i = 0; i < h; i++) { const t = yy.length; let v = m.c; for (let a = 1; a < arComplet.length; a++) v -= arComplet[a] * (t - a >= 0 ? yy[t - a] : 0); for (let j = 1; j < maC.length; j++) v += maC[j] * (t - j >= 0 ? ee[t - j] : 0); yy.push(v); ee.push(0); out.push(v) }
        return out
      },
      intervalle: (h, z95 = 1.96) => { const w = psi(h); let c = 0; return w.map((v) => { c += v * v; return z95 * Math.sqrt(sigma2 * c) }) },
    }
  }
  // Recherche automatique : petits ordres, critère AIC (comparables seulement à d et D égaux) puis BIC global.
  S.sarimaAuto = function (y, fin = y.length, s = 7) {
    // Grille réduite (60 modèles) : d, D ∈ {0, 1} ; (p, q) ∈ {(1,0), (0,1), (1,1), (2,0), (2,1)} ; (P, Q) ∈ {(0,0), (1,0), (0,1)}.
    // Le BIC n'est comparable qu'à d et D égaux (la série modélisée change) : on retient pour chaque (d, D)
    // le meilleur BIC, puis on départage ces quatre candidats par l'erreur un pas en avant sur la validation (t ≥ fin).
    const essais = [], parDiff = {}
    for (const d of [0, 1]) for (const D of [0, 1]) for (const [p, q] of [[1, 0], [0, 1], [1, 1], [2, 0], [2, 1]]) for (const [P, Q] of [[0, 0], [1, 0], [0, 1]]) {
      const m = S.sarima(y, { p, d, q, P, D, Q, s }, fin); if (!m || !Number.isFinite(m.bic)) continue
      const e = S.metriques(y.slice(fin), m.unPas.slice(fin))
      essais.push({ nom: m.nom, aic: m.aic, bic: m.bic, maeVal: e?.mae ?? NaN, d, D })
      const k = `${d}${D}`; if (!parDiff[k] || m.bic < parDiff[k].bic) parDiff[k] = m
    }
    const cands = Object.values(parDiff), score = (m) => S.metriques(y.slice(fin), m.unPas.slice(fin))?.mae ?? Infinity
    const meilleur = cands.length ? cands.reduce((a, b) => (fin < y.length ? (score(b) < score(a) ? b : a) : (b.bic < a.bic ? b : a))) : null
    return { meilleur, essais: essais.sort((a, b) => a.bic - b.bic) }
  }

  // ════════════════════════════════════════════════════════════════════════════════════
  // 6. MÉTRIQUES DE PRÉVISION (sur les jours où la prévision existe)
  // ════════════════════════════════════════════════════════════════════════════════════
  S.metriques = function (y, p, echelle) {
    const i = y.map((_, k) => k).filter((k) => Number.isFinite(p[k]) && Number.isFinite(y[k])); if (!i.length) return null
    const e = i.map((k) => y[k] - p[k]), n = e.length
    const mae = e.reduce((a, b) => a + Math.abs(b), 0) / n, rmse = Math.sqrt(e.reduce((a, b) => a + b * b, 0) / n)
    const nz = i.filter((k) => y[k] !== 0), mape = nz.length ? 100 * nz.reduce((a, k) => a + Math.abs((y[k] - p[k]) / y[k]), 0) / nz.length : NaN
    const smape = 100 * i.reduce((a, k) => a + (Math.abs(y[k]) + Math.abs(p[k]) ? 2 * Math.abs(y[k] - p[k]) / (Math.abs(y[k]) + Math.abs(p[k])) : 0), 0) / n
    return { n, mae, rmse, mape, smape, mase: echelle ? mae / echelle : NaN, biais: e.reduce((a, b) => a + b, 0) / n }
  }

  // Diebold-Mariano (perte quadratique, h = 1, correction de Harvey-Leybourne-Newbold) :
  // d_t = e1_t² − e2_t² ; DM = d̄ / √(Var(d)/n) × √((n − 1)/n) ~ Student(n − 1). DM < 0 : le modèle 1 est meilleur.
  S.dieboldMariano = function (e1, e2) {
    const d = e1.map((e, i) => e * e - e2[i] * e2[i]).filter(Number.isFinite), n = d.length; if (n < 5) return { stat: NaN, p: NaN }
    const m = d.reduce((a, b) => a + b, 0) / n, v = d.reduce((a, b) => a + (b - m) ** 2, 0) / n
    if (!v) return { stat: 0, p: 1 }
    const st = m / Math.sqrt(v / n) * Math.sqrt((n - 1) / n)
    return { stat: st, p: S.pStudentBilat(st, n - 1) }
  }

  window.Stat = S
})()
