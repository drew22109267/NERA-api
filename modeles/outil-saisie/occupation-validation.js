// ═══════════════════════════════════════════════════════════════════════════════════════════
// Quatre façons indépendantes de retracer ou de contrôler l'occupation (rubrique « Occupation ») :
//
//  1. Bilan des flux         P(t) = P(t−1) + entrées(t) − sorties(t), recalable sur un comptage réel
//                            (cahier de garde, rapport de relève, comptage de terrain).
//  2. Simulation de Monte-Carlo : chaque durée incertaine est tirée au hasard (convention nuits / jours,
//                            durée inconnue tirée parmi les séjours connus de même prix ou même issue),
//                            puis le recensement de minuit est refait ; N tirages → intervalle de confiance.
//  3. Analyse de survie      Kaplan-Meier de la durée de séjour : les enfants encore hospitalisés à la fin
//                            de la saisie sont « censurés » (on sait seulement que leur séjour dure au moins
//                            jusque-là) ; test du log-rank entre groupes.
//  4. Modèle de file M/G/∞   arrivées au hasard, durées quelconques, lits illimités : le nombre de présents
//                            suit une loi de Poisson de moyenne λ·W ; comparée à la loi observée, à une
//                            binomiale négative et à un mélange de Poisson mois par mois (saisonnalité).
//
// Tout est écrit à la main ; utilise les outils graphiques et statistiques d'indicateurs.js et de statistiques.js.
// ═══════════════════════════════════════════════════════════════════════════════════════════
(function () {
  // Générateur pseudo-aléatoire à graine (mulberry32) : le même calcul donne toujours le même résultat.
  const alea = (graine) => () => { graine |= 0; graine = (graine + 0x6d2b79f5) | 0; let t = Math.imul(graine ^ (graine >>> 15), 1 | graine); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
  const quantileTrie = (t, q) => { if (!t.length) return NaN; const h = (t.length - 1) * q, b = Math.floor(h); return b + 1 < t.length ? t[b] + (h - b) * (t[b + 1] - t[b]) : t[b] }
  const prixDe = (l) => { const m = String(l.prix ?? '').replace(/[\s. ]/g, '').match(/\d{3,6}/); return m ? +m[0] : null }
  const issueDeL = (l) => { const i = issueDe(l); return i === 'Non renseignée' ? null : i }

  // Graphique x–y générique : courbes (en escalier ou non), bandes, barres, repères horizontaux.
  function courbesXY({ W, H, series = [], bandes = [], barres = [], refs = [], xmin, xmax, ymin = 0, ymax, titreX = '', titreY = '' }) {
    const leg = [...barres.map((b) => ({ nom: b.nom, couleur: b.couleur, barre: true })), ...series.map((s) => ({ nom: s.nom, couleur: s.couleur, epaisseur: s.epaisseur, pointille: s.pointille })),
      ...bandes.map((b) => ({ nom: b.nom, couleur: b.couleur, bande: true, opacite: b.opacite })), ...refs.map((r) => ({ nom: r.nom, couleur: r.couleur, pointille: '6 4' }))]
    const { x, y, fond } = cadre({ W, H, xmin, xmax, ymin, ymax, titreX, titreY, mb: 40 + 17 * lignesLegende(leg, 56, W - 14) })
    const chemin = (pts, esc) => pts.map(([a, b], i) => (i ? `${esc ? `L${x(a).toFixed(1)},${y(pts[i - 1][1]).toFixed(1)}` : ''}L${x(a).toFixed(1)},${y(b).toFixed(1)}` : `M${x(a).toFixed(1)},${y(b).toFixed(1)}`)).join('')
    const zone = (pts, esc) => { const h = pts.map(([a, , hi]) => [a, hi]), b = pts.map(([a, lo]) => [a, lo]).reverse(); return `${chemin(h, esc)}${chemin(b, esc).replace(/^M/, 'L')}Z` }
    const lb = barres.length ? Math.max(2, (x(xmin + 1) - x(xmin)) * 0.7 / barres.length) : 0
    return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${fond}
      ${bandes.map((b) => `<path d="${zone(b.pts, b.escalier)}" fill="${b.couleur}" fill-opacity="${b.opacite ?? 0.18}" stroke="none"/>`).join('')}
      ${barres.map((b, k) => b.pts.map(([a, v]) => `<rect x="${x(a) - (lb * barres.length) / 2 + k * lb}" y="${y(v)}" width="${lb}" height="${Math.max(0, y(ymin) - y(v))}" fill="${b.couleur}" fill-opacity="${b.opacite ?? 0.6}"><title>${echapper(b.nom)} · ${nf(a, 0)} : ${nf(v, 4)}</title></rect>`).join('')).join('')}
      ${refs.map((r) => `<line x1="${x(xmin)}" x2="${x(xmax)}" y1="${y(r.valeur)}" y2="${y(r.valeur)}" stroke="${r.couleur}" stroke-width="1.4" stroke-dasharray="6 4"/>`).join('')}
      ${series.map((s) => `<path d="${chemin(s.pts, s.escalier)}" fill="none" stroke="${s.couleur}" stroke-width="${s.epaisseur ?? 2}" ${s.pointille ? `stroke-dasharray="${s.pointille}"` : ''} stroke-linejoin="round"/>${s.points ? s.pts.map(([a, b]) => `<circle cx="${x(a)}" cy="${y(b)}" r="3" fill="${s.couleur}"><title>${echapper(s.nom)} · ${nf(a, 0)} : ${nf(b, 4)}</title></circle>`).join('') : ''}`).join('')}
      ${legendeSvg(leg, 56, H - 6, W - 14)}</svg>`
  }

  // Fins possibles d'un séjour, comme dans le calcul principal (scénario « attendu »).
  const sejoursExploitables = (d) => (d.sejours ?? []).filter((s) => s.statut !== 'inconnue')

  // ── 1. Bilan des flux ──────────────────────────────────────────────────────────────────
  function lireComptages(texte) {
    return String(texte ?? '').split(/[;\n]+/).map((x) => x.trim()).filter(Boolean).map((x) => {
      const m = x.match(/^(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{4}|\d{2})\s*[=:]\s*(\d+(?:[.,]\d+)?)$/); if (!m) return null
      const an = m[3].length === 2 ? 2000 + +m[3] : +m[3]; return { jour: Date.UTC(an, +m[2] - 1, +m[1]) / 86400000, n: +m[4].replace(',', '.') }
    }).filter(Boolean)
  }
  function rendreBilanFlux(c, W, H) {
    const d = c.d, n = d.presents.length, deb = d.debutNum, A = new Array(n).fill(0), S = new Array(n).fill(0)
    for (const s of sejoursExploitables(d)) {
      const i = s.entree - deb; if (i >= 0 && i < n) A[i]++
      const dc = d.reglages?.decal ?? 0     // comptage journalier : l'enfant compte encore le jour de sa sortie
      const fins = s.sortie === null ? [] : s.statut === 'calculee' && s.basse < s.sortie ? [[s.basse + dc, s.p], [s.sortie + dc, 1 - s.p]] : [[s.sortie + dc, 1]]
      for (const [j, w] of fins) { const k = j - deb; if (k >= 0 && k < n && w > 0) S[k] += w }
    }
    // P(t) = P(t − 1) + entrées(t) − sorties(t), en partant de l'effectif du premier jour.
    const P = [d.presents[0]]; for (let i = 1; i < n; i++) P.push(P[i - 1] + A[i] - S[i])
    // Présence pondérée : le stock est celui du comptage journalier, dont on retire chaque jour la part du jour
    // d'entrée avant l'arrivée et celle du jour de sortie après le départ (mêmes heures typiques que le calcul).
    if (d.reglages?.comptage === 'pondere') {
      const { a, b, m } = d.reglages.heures, corr = new Array(n).fill(0)
      for (const s of sejoursExploitables(d)) {
        const i = s.entree - deb; if (i >= 0 && i < n) corr[i] += a
        const fins = s.sortie === null ? [] : s.statut === 'calculee' && s.basse < s.sortie ? [[s.basse, s.p], [s.sortie, 1 - s.p]] : [[s.sortie, 1]]
        for (const [j, w] of fins) { const k = j - deb; if (k >= 0 && k < n && j < d.extraction && w > 0) corr[k] += w * (j === s.entree ? 1 - m - a : 1 - b) }
      }
      // le premier jour sert de point de départ : on garde la même base que le calcul principal
      const base = P[0] - corr[0] - d.presents[0]
      for (let i = 0; i < n; i++) P[i] = P[i] - corr[i] - base
    }
    const ecartMax = Math.max(...P.map((v, i) => Math.abs(v - d.presents[i])))
    // Recalage : chaque comptage réel corrige le stock à partir de sa date (les flux, eux, ne changent pas).
    const comptes = lireComptages(c.opts.comptages).filter((k) => k.jour >= deb && k.jour < deb + n).sort((a, b) => a.jour - b.jour)
    const recale = P.slice(); let decal = 0, kc = 0
    for (let i = 0; i < n; i++) { while (kc < comptes.length && comptes[kc].jour - deb <= i) { decal = comptes[kc].n - P[comptes[kc].jour - deb]; kc++ } recale[i] = P[i] + decal }
    const lignesComptes = comptes.map((k) => { const i = k.jour - deb, rec = d.presents[i]; return [fmtDate(versDate(k.jour)), nf(k.n, 0), nf(rec, 1), `${k.n - rec >= 0 ? '+' : ''}${nf(k.n - rec, 1)}`, rec ? `${nf(100 * (k.n - rec) / rec, 0)} %` : '—'] })
    const ecarts = comptes.map((k) => k.n - d.presents[k.jour - deb])
    const options = `<label class="ind-case" style="flex:1 1 100%">Comptages réels (cahier de garde, relève…) : <input class="input" style="flex:1;min-width:280px" data-o="comptages" value="${echapper(c.opts.comptages ?? '')}" placeholder="12/12/24=14; 05/01/25=11; 20/07/25=6"></label>`
    const series = [{ nom: enJournee() ? 'Comptage journalier (registre)' : 'Recensement de minuit (registre)', valeurs: d.presents, couleur: COUL.bleu, epaisseur: 1.6 }, { nom: 'Bilan des flux', valeurs: P, couleur: COUL.orange, epaisseur: 1.4, pointille: '5 3' }]
    if (comptes.length) series.push({ nom: 'Série recalée sur les comptages', valeurs: recale, couleur: COUL.vert, epaisseur: 2 })
    return { options,
      avant: bandeauStats([['Entrées sur la période', nf(A.reduce((a, b) => a + b, 0), 0)], ['Sorties sur la période', nf(S.reduce((a, b) => a + b, 0), 0)], ['Écart maximal flux / recensement', `${nf(ecartMax, 3)} enfant`], ...(comptes.length ? [['Comptages réels', comptes.length], ['Écart moyen (réel − registre)', `${ecarts.reduce((a, b) => a + b, 0) / ecarts.length >= 0 ? '+' : ''}${nf(ecarts.reduce((a, b) => a + b, 0) / ecarts.length, 1)} enfant(s)`], ['Écart absolu moyen', nf(ecarts.reduce((a, b) => a + Math.abs(b), 0) / ecarts.length, 1)]] : [])]),
      html: `${lignesSvg({ W, H, debutNum: deb, series, refs: c.lits ? [{ nom: `${c.lits} lits`, valeur: c.lits, couleur: COUL.rouge }] : [], titreY: 'Enfants présents', verticales: comptes.map((k) => ({ i: k.jour - deb, nom: '' })) })}
        ${comptes.length ? `<div style="margin-top:10px">${tableau(['Date', 'Comptage réel', 'Reconstitué (registre)', 'Écart', 'Écart relatif'], lignesComptes)}</div>` : ''}`,
      lecture: `le <b>bilan des flux</b> retrace l’occupation comme un stock : présents(t) = présents(t − 1) + entrées(t) − sorties(t). À partir des mêmes séjours, il doit redonner exactement le comptage des présents (${enJournee() ? 'présence dans la journée' : 'recensement de minuit'}) : l’écart maximal affiché (${nf(ecartMax, 3)}) le vérifie. Son vrai intérêt est le <b>recalage</b> : tapez dans la case des comptages réels, sous la forme <b>jj/mm/aa=nombre</b> séparés par des points-virgules (effectif noté au cahier de garde ou au rapport de relève, ou compté vous-même). L’outil compare chaque comptage au registre (tableau) et trace la série <b>recalée</b> : à chaque comptage, le stock est remis à la valeur réelle, puis évolue avec les entrées et sorties du registre. Un écart <b>systématiquement positif</b> signale des enfants présents mais absents du registre (néonatologie, chirurgie, enfants gardés après leur sortie administrative) ; un écart qui varie au hasard autour de 0 <b>valide</b> la reconstitution.` }
  }

  // ── 2. Simulation de Monte-Carlo ───────────────────────────────────────────────────────
  let cacheMC = null
  function simulerMC(c, N) {
    const d = c.d, deb = d.debutNum, n = d.presents.length, fin = deb + n - 1, lits = c.lits
    const cle = `${deb}|${n}|${d.sejours?.length}|${lits}|${N}|${d.presents.reduce((a, b) => a + b, 0)}|${d.reglages?.comptage}|${JSON.stringify(d.reglages?.heures ?? '')}|${(d.litsJour ?? []).join(',')}`; if (cacheMC?.cle === cle) return cacheMC
    const tous = d.sejours ?? [], connus = tous.filter((s) => s.statut === 'observee' || s.statut === 'calculee')
    // Banques de durées connues (en nuits), par prix puis par issue (au moins 5 séjours), sinon tout le service.
    const banque = (cle2) => { const g = {}; for (const s of connus) { const k = cle2(s.l); if (k !== null) (g[k] ??= []).push(s.sortie - s.entree) } return Object.fromEntries(Object.entries(g).filter(([, v]) => v.length >= 5)) }
    const parPrix = banque(prixDe), parIssue = banque(issueDeL), toutes = connus.map((s) => s.sortie - s.entree)
    const incertains = tous.filter((s) => s.statut === 'imputee' || s.statut === 'inconnue').map((s) => ({ s, b: parPrix[prixDe(s.l)] ?? parIssue[issueDeL(s.l)] ?? toutes }))
    const rnd = alea(20250611), series = [], moyennes = [], sur = [], maxi = []
    for (let r = 0; r < N; r++) {
      const diff = new Float64Array(n + 1)
      const dc = d.reglages?.decal ?? 0
      const pond = d.reglages?.comptage === 'pondere' ? d.reglages.heures : null, corr = pond ? new Float64Array(n) : null
      const ajouter = (e, sortie) => {
        const a = Math.max(e, deb), b = Math.min((sortie === null ? fin + 1 : sortie + dc) - 1, fin); if (b >= a) { diff[a - deb] += 1; diff[b - deb + 1] -= 1 }
        if (pond) {                                         // présence pondérée : parts de journée (heures typiques)
          if (e >= deb && e <= fin) corr[e - deb] += pond.a
          if (sortie !== null && sortie >= deb && sortie <= fin) corr[sortie - deb] += sortie === e ? 1 - pond.m - pond.a : 1 - pond.b
        }
      }
      for (const s of tous) {
        if (s.statut === 'observee') ajouter(s.entree, s.sortie)
        else if (s.statut === 'calculee') ajouter(s.entree, s.basse < s.sortie && rnd() < s.p ? s.basse : s.sortie)
        else if (s.statut === 'censuree') ajouter(s.entree, null)
      }
      for (const { s, b } of incertains) ajouter(s.entree, s.entree + b[Math.floor(rnd() * b.length)])
      const p = new Float64Array(n); let cum = 0; for (let i = 0; i < n; i++) { cum += diff[i]; p[i] = cum - (corr ? corr[i] : 0) }
      series.push(p); moyennes.push(p.reduce((a, v) => a + v, 0) / n); maxi.push(Math.max(...p)); sur.push(lits ? p.filter((v, i) => v > (d.litsJour?.[i] ?? lits)).length : 0)
    }
    const qJour = (q) => Array.from({ length: n }, (_, i) => quantileTrie(series.map((p) => p[i]).sort((a, b) => a - b), q))
    const trier = (v) => v.slice().sort((a, b) => a - b)
    cacheMC = { cle, N, n, incertains: incertains.length, q05: qJour(0.05), q50: qJour(0.5), q95: qJour(0.95), moyennes: trier(moyennes), sur: trier(sur), maxi: trier(maxi), pDepasse: lits ? sur.filter((v) => v > 0).length / N : NaN }
    return cacheMC
  }
  function rendreMonteCarlo(c, W, H) {
    const N = +c.opts.mcN || 300, R = simulerMC(c, N), lits = c.lits, ic = (v, k = 1) => `${nf(quantileTrie(v, 0.5), k)} [${nf(quantileTrie(v, 0.025), k)} ; ${nf(quantileTrie(v, 0.975), k)}]`
    const litsMoy = c.d.litsJour?.length ? c.d.litsJour.reduce((a, b) => a + b, 0) / c.d.litsJour.length : lits
    const tom = (v) => (lits ? v.map((m) => 100 * m / litsMoy) : [])            // capacité moyenne si elle a changé
    return { options: libelle('Nombre de tirages', choix('mcN', N, [[100, '100 (rapide)'], [300, '300'], [1000, '1 000 (précis, plus lent)']])),
      avant: bandeauStats([['Séjours de durée incertaine tirés au hasard', R.incertains], ['Présents moyens [IC 95 %]', ic(R.moyennes, 2)], ...(lits ? [['Taux d’occupation [IC 95 %]', `${ic(tom(R.moyennes))} %`], ['Jours en sureffectif [IC 95 %]', ic(R.sur, 0)], ['Probabilité d’au moins un jour > lits', `${nf(100 * R.pDepasse, 0)} %`]] : []), ['Maximum [IC 95 %]', ic(R.maxi, 0)]]),
      html: lignesSvg({ W, H, debutNum: c.d.debutNum, series: [{ nom: 'Médiane des simulations', valeurs: R.q50, couleur: COUL.violet, epaisseur: 2.2 }, { nom: 'Calcul principal', valeurs: c.d.presents, couleur: COUL.orange, epaisseur: 1.3 }],
        bandes: [{ nom: '90 % des simulations (5e – 95e centile)', bas: R.q05, haut: R.q95, couleur: COUL.cyan, opacite: 0.3 }], refs: lits ? [{ nom: `${lits} lits`, valeur: lits, couleur: COUL.rouge }] : [], titreY: 'Enfants présents' }),
      lecture: `au lieu d’une seule hypothèse, l’outil refait ${N} fois le comptage des présents (${enJournee() ? 'présence dans la journée' : 'recensement de minuit'}) en tirant au hasard tout ce qui est incertain : pour une sortie <b>calculée</b> (entrée + nombre de jours), la convention « nuits » ou « jours entrée et sortie comprises » est tirée avec la proportion p mesurée sur les lignes complètes ; pour un séjour <b>sans sortie ni nombre de jours</b> (${R.incertains} séjours), la durée est tirée parmi les séjours connus de <b>même prix</b> (sinon de même issue, sinon de tout le service). Les sorties écrites ne bougent pas. La <b>bande bleu clair</b> contient 90 % des simulations jour par jour ; la <b>courbe violette</b> est leur médiane, la <b>courbe orange</b> le calcul principal, le <b>trait rouge</b> le nombre de lits ; les crochets donnent l’<b>intervalle de confiance à 95 %</b> de chaque indicateur. Une bande étroite veut dire que les données manquantes changent peu le résultat : c’est l’argument pour écrire que l’occupation reconstituée est <b>robuste</b>. À la différence du calcul principal, la simulation inclut toujours les séjours de durée inconnue, même si le réglage les exclut.` }
  }

  // ── 3. Analyse de survie (Kaplan-Meier) ─────────────────────────────────────────────────
  function kaplanMeier(obs) {
    // obs : [{ t, e }] (t en nuits, e = 1 sortie observée, 0 censuré). S(t) = Π_{t_i ≤ t} (1 − d_i / n_i) ;
    // variance de Greenwood : S² Σ d_i / (n_i (n_i − d_i)).
    const tri = obs.slice().sort((a, b) => a.t - b.t), temps = [...new Set(tri.filter((o) => o.e).map((o) => o.t))]
    let S = 1, g = 0, k = 0, aRisque = tri.length; const pts = [{ t: 0, S: 1, bas: 1, haut: 1, n: aRisque }]
    for (const t of temps) {
      while (k < tri.length && tri[k].t < t) { aRisque--; k++ }
      const dI = tri.filter((o) => o.t === t && o.e).length, nI = aRisque
      if (nI > 0) { S *= 1 - dI / nI; if (nI > dI) g += dI / (nI * (nI - dI)) }
      const se = S * Math.sqrt(g); pts.push({ t, S, bas: Math.max(0, S - 1.96 * se), haut: Math.min(1, S + 1.96 * se), n: nI })
    }
    const quant = (q) => pts.find((p) => p.S <= 1 - q)?.t ?? NaN, en = (t) => pts.filter((p) => p.t <= t).at(-1)?.S ?? 1
    let aire = 0; for (let i = 0; i < pts.length; i++) { const t0 = pts[i].t, t1 = Math.min(i + 1 < pts.length ? pts[i + 1].t : 30, 30); if (t1 > t0) aire += pts[i].S * (t1 - t0) }
    return { pts, mediane: quant(0.5), q1: quant(0.25), q3: quant(0.75), en, moyenne30: aire, n: obs.length, ev: obs.filter((o) => o.e).length }
  }
  function logRank(groupes) {
    // χ² ≈ Σ_g (O_g − E_g)² / E_g, ddl = k − 1 (forme simplifiée du log-rank)
    const tous = groupes.flatMap((g, i) => g.map((o) => ({ ...o, g: i }))), temps = [...new Set(tous.filter((o) => o.e).map((o) => o.t))].sort((a, b) => a - b)
    const O = groupes.map(() => 0), E = groupes.map(() => 0)
    for (const t of temps) {
      const risque = groupes.map((g) => g.filter((o) => o.t >= t).length), dG = groupes.map((g) => g.filter((o) => o.t === t && o.e).length)
      const nT = risque.reduce((a, b) => a + b, 0), dT = dG.reduce((a, b) => a + b, 0); if (!nT) continue
      groupes.forEach((_, i) => { O[i] += dG[i]; E[i] += dT * risque[i] / nT })
    }
    const chi2 = O.reduce((a, o, i) => a + (E[i] ? (o - E[i]) ** 2 / E[i] : 0), 0), ddl = groupes.length - 1
    return { chi2, ddl, p: ddl > 0 ? Sx.pKhi2(chi2, ddl) : NaN, O, E }
  }
  function rendreSurvie(c, W, H) {
    const d = c.d, ext = d.extraction, tous = d.sejours ?? []
    const obs = tous.filter((s) => s.statut === 'observee' || s.statut === 'calculee' || s.statut === 'censuree')
      .map((s) => ({ t: s.statut === 'censuree' ? ext - s.entree : s.sortie - s.entree, e: s.statut === 'censuree' ? 0 : 1, l: s.l })).filter((o) => o.t >= 0 && o.t <= 90)
    const manquants = tous.length - obs.length
    const STRATES = { aucune: ['Tous les séjours', () => 'Tous'], issue: ['Issue (sortie / SCAM / autres)', (l) => { const i = issueDe(l); return i.startsWith('Sortie (') ? 'Sortie à domicile' : i.startsWith('Sortie contre') ? 'SCAM' : 'Autres issues ou non renseignée' }],
      age: ['Tranche d’âge', (l) => trancheAge(l)], cause: ['Grande cause (4 plus fréquentes)', (l) => causeDe(l)] }
    if (!STRATES[c.opts.kmStrate]) c.opts.kmStrate = 'issue'
    const [, cleG] = STRATES[c.opts.kmStrate], grp = {}
    for (const o of obs) { const k = cleG(o.l); if (k && k !== 'Non renseigné') (grp[k] ??= []).push(o) }
    let noms = Object.keys(grp).sort((a, b) => grp[b].length - grp[a].length); if (c.opts.kmStrate === 'cause') noms = noms.slice(0, 4)
    noms = noms.filter((k) => grp[k].length >= 10)
    const km = noms.map((k) => ({ nom: k, ...kaplanMeier(grp[k]) })), lr = noms.length > 1 ? logRank(noms.map((k) => grp[k])) : null
    const xmax = Math.min(30, Math.max(7, ...km.map((k) => k.q3 * 2 || 10))), cou = [COUL.bleu, COUL.rouge, COUL.vert, COUL.orange, COUL.violet]
    const series = km.map((k, i) => ({ nom: `${k.nom} (${k.n})`, pts: k.pts.filter((p) => p.t <= xmax).map((p) => [p.t, p.S]).concat([[xmax, k.pts.filter((p) => p.t <= xmax).at(-1).S]]), couleur: cou[i % cou.length], escalier: true }))
    const bandes = km.length === 1 ? [{ nom: 'IC 95 % (Greenwood)', pts: km[0].pts.filter((p) => p.t <= xmax).map((p) => [p.t, p.bas, p.haut]), couleur: COUL.bleu, escalier: true, opacite: 0.15 }] : []
    return { options: libelle('Comparer selon', choix('kmStrate', c.opts.kmStrate, Object.entries(STRATES).map(([k, [n]]) => [k, n]))),
      avant: bandeauStats([['Séjours analysés', obs.length], ['dont censurés (encore hospitalisés)', obs.filter((o) => !o.e).length], ['Exclus (parti sans date ni durée)', manquants], ...(lr ? [['Log-rank', `χ² = ${nf(lr.chi2, 1)} · ddl ${lr.ddl} · p ${fp(lr.p)}`]] : [])]),
      html: `${courbesXY({ W, H, series, bandes, xmin: 0, xmax, ymin: 0, ymax: 1, titreX: 'Nuits depuis l’entrée', titreY: 'Proportion encore hospitalisée' })}
        <div style="margin-top:10px">${tableau(['Groupe', 'Séjours', 'Sorties observées', 'Censurés', 'Médiane (nuits)', 'Q1 – Q3', 'Encore là à 3 nuits', 'Encore là à 7 nuits', 'Durée moyenne (≤ 30 nuits)'],
          km.map((k) => [echapper(k.nom), k.n, k.ev, k.n - k.ev, nf(k.mediane, 0), `${nf(k.q1, 0)} – ${nf(k.q3, 0)}`, `${nf(100 * k.en(3), 0)} %`, `${nf(100 * k.en(7), 0)} %`, nf(k.moyenne30, 2)]))}</div>`,
      lecture: `la courbe de <b>Kaplan-Meier</b> donne, pour chaque nombre de nuits t, la part des enfants <b>encore hospitalisés</b> après t nuits : S(t) = Π (1 − dᵢ/nᵢ), où dᵢ est le nombre de sorties à la nuit tᵢ et nᵢ le nombre d’enfants encore présents juste avant. Son avantage sur une simple moyenne : les enfants <b>encore hospitalisés</b> à la fin de la saisie ne sont ni jetés ni comptés comme sortis ; ils sont « <b>censurés</b> » (on sait seulement que leur séjour dure au moins jusque-là). La <b>médiane</b> est la durée à laquelle la moitié des enfants sont sortis. Les séjours d’enfants partis sans date ni nombre de jours ne sont pas des censures mais des données manquantes : ils sont exclus ici (voir la simulation de Monte-Carlo pour leur effet). Le <b>test du log-rank</b> compare les groupes : p < 0,05 signifie que leurs durées de séjour diffèrent. Exemple de lecture : une courbe « SCAM » qui descend plus vite que « Sortie à domicile » montre que les SCAM raccourcissent les séjours. <b>Pour le SVR</b> : la durée de séjour fixe pendant combien de jours une admission pèse sur l’occupation, donc le nombre de jours d’admissions passées à donner au modèle.` }
  }

  // ── 4. Modèle de file M/G/∞ ────────────────────────────────────────────────────────────
  function rendreFileMGinf(c, W, H) {
    const d = c.d, p = d.presents, n = p.length, lits = c.lits
    const T = d.lignes.at(-1), lam = T.adm / T.J, Wm = T.wComptage ?? T.dms, m = p.reduce((a, b) => a + b, 0) / n, v = p.reduce((a, b) => a + (b - m) ** 2, 0) / (n - 1)
    const kmax = Math.max(lits ?? 0, Math.ceil(Math.max(...p))) + 4, ks = Array.from({ length: kmax + 1 }, (_, k) => k)
    const lnF = (k) => Sx.lnGamma(k + 1)
    const poisson = (mu) => ks.map((k) => Math.exp(k * Math.log(mu) - mu - lnF(k)))
    const obs = ks.map((k) => p.filter((x) => Math.round(x) === k).length / n)
    const pois = poisson(lam * Wm)
    const r = v > m ? m * m / (v - m) : Infinity, q = m / v
    const bn = isFinite(r) ? ks.map((k) => Math.exp(Sx.lnGamma(k + r) - Sx.lnGamma(r) - lnF(k) + r * Math.log(q) + k * Math.log(1 - q))) : pois
    // Mélange de Poisson mois par mois : chaque jour suit Poisson(moyenne de son mois) → effet de la saisonnalité.
    const parMois = {}; p.forEach((x, i) => (parMois[versDate(d.debutNum + i).slice(0, 7)] ??= []).push(x))
    const melange = ks.map(() => 0); for (const xs of Object.values(parMois)) { const mu = xs.reduce((a, b) => a + b, 0) / xs.length, pm = poisson(mu); ks.forEach((k) => { melange[k] += pm[k] * xs.length / n }) }
    const queue = (dist, s) => dist.slice(s).reduce((a, b) => a + b, 0)
    const seuils = lits ? [Math.round(0.85 * lits), lits + 1] : [10, 15]
    const lignes = [['Observé (recensement)', obs], ['Poisson (M/G/∞, λ·W)', pois], ['Mélange de Poisson par mois', melange], ['Binomiale négative', bn]].map(([nom, dist]) => {
      const moy = ks.reduce((a, k) => a + k * dist[k], 0), va = ks.reduce((a, k) => a + (k - moy) ** 2 * dist[k], 0)
      return [nom, nf(moy, 2), nf(va, 2), ...seuils.map((s) => `${nf(100 * queue(dist, s), 1)} %`)]
    })
    return { avant: bandeauStats([['λ admissions / jour', nf(lam, 2)], [d.reglages?.decal ? 'W durée moyenne (jours de présence)' : 'W durée moyenne (nuits)', nf(Wm, 2)], ['λ·W (moyenne théorique)', nf(lam * Wm, 2)], ['Moyenne observée', nf(m, 2)], ['Variance observée', nf(v, 2)], ['Indice de dispersion (variance ÷ moyenne)', nf(v / m, 2)]]),
      html: `${courbesXY({ W, H, xmin: -0.5, xmax: kmax + 0.5, ymin: 0, ymax: Math.max(...obs, ...pois, ...melange) * 1.15, titreX: `Nombre d’enfants ${enJournee() ? 'présents dans la journée' : 'présents à minuit'}`, titreY: 'Part des jours',
          barres: [{ nom: 'Observé', pts: ks.map((k) => [k, obs[k]]), couleur: COUL.bleu, opacite: 0.55 }],
          series: [{ nom: 'Poisson (λ·W)', pts: ks.map((k) => [k, pois[k]]), couleur: COUL.rouge, points: true }, { nom: 'Mélange par mois', pts: ks.map((k) => [k, melange[k]]), couleur: COUL.vert, points: true }, { nom: 'Binomiale négative', pts: ks.map((k) => [k, bn[k]]), couleur: COUL.violet, pointille: '5 3' }] })}
        <div style="margin-top:10px">${tableau(['Loi', 'Moyenne', 'Variance', ...seuils.map((s) => lits && s > lits ? `Plus de ${lits} enfants (sureffectif)` : `${s} enfants ou plus`)], lignes)}</div>`,
      lecture: `si les enfants arrivaient <b>au hasard</b> (taux λ constant) et restaient chacun une durée quelconque de moyenne W, sans limite de lits, le nombre de présents suivrait une <b>loi de Poisson</b> de moyenne <b>λ·W</b> (modèle de file M/G/∞) : c’est la loi de Little appliquée non plus à la moyenne mais à <b>toute la distribution</b>. Pour une loi de Poisson, variance = moyenne (indice de dispersion = 1). Un indice nettement supérieur à 1 (ici ${nf(v / m, 2)}) veut dire que l’occupation varie <b>plus que le hasard</b> : les arrivées viennent par vagues. Le <b>mélange de Poisson mois par mois</b> (chaque mois avec sa propre moyenne) teste si la <b>saisonnalité</b> suffit à expliquer cet excès ; s’il colle aux barres observées, oui. La <b>binomiale négative</b> est la loi classique des comptages sur-dispersés. Le tableau donne la probabilité, selon chaque loi, d’atteindre un service tendu ou en sureffectif : la loi de Poisson simple <b>sous-estime</b> ces risques quand l’indice dépasse 1. <b>Pour le SVR</b> : c’est l’argument pour un modèle qui suit la saison et vise un quantile élevé (τ = 0,8) plutôt que la moyenne.` }
  }

  // ── 5. Pic de la journée : encadrement exact ────────────────────────────────────────────
  function rendrePic(c, W, H) {
    const d = c.d, bas = d.picBas, haut = d.picHaut
    if (!bas?.length) return { html: vide('Pic non calculé.') }
    const n = bas.length, moy = (t) => t.reduce((a, b) => a + b, 0) / n, L = (i) => d.litsJour?.[i] ?? c.lits
    const depasse = (t) => (c.lits ? t.filter((v, i) => v > L(i)).length : null)
    const minuit = bas.map((_, i) => i)                        // indices (pour les repères)
    return {
      avant: bandeauStats([['Pic moyen de la journée', `entre ${nf(moy(bas), 1)} et ${nf(moy(haut), 1)} enfants`],
        ['Plus haut pic', `entre ${nf(Math.max(...bas), 0)} et ${nf(Math.max(...haut), 0)}`],
        ...(c.lits ? [['Jours où le pic dépasse les lits', `au moins ${depasse(bas)}, au plus ${depasse(haut)}`],
          ['Pic moyen rapporté aux lits', `${nf(100 * moy(bas.map((v, i) => v / L(i))), 0)} % à ${nf(100 * moy(haut.map((v, i) => v / L(i))), 0)} %`]] : [])]),
      html: lignesSvg({ W, H, debutNum: d.debutNum, titreY: 'Enfants présents en même temps',
        bandes: [{ nom: 'Pic de la journée (entre les deux bornes)', bas, haut, couleur: COUL.cyan, opacite: 0.28 }],
        series: [{ nom: 'Borne basse : max des deux minuits', valeurs: bas, couleur: COUL.bleu, epaisseur: 1.4 },
          { nom: 'Borne haute : présents dans la journée', valeurs: haut, couleur: COUL.orange, epaisseur: 1.2 }],
        refs: c.lits ? [{ nom: `${c.lits} lits`, valeur: c.lits, couleur: COUL.rouge }] : [] }),
      lecture: `le registre ne donne pas les heures : on ne connaît pas le nombre exact d’enfants présents <b>au moment le plus chargé</b> de la journée, mais on l’<b>encadre exactement</b>, sans aucune hypothèse. Borne basse : le minuit qui ouvre la journée et celui qui la ferme sont deux moments de cette journée, donc le pic est au moins égal au plus grand des deux. Borne haute : tous les enfants présents à un moment de la journée (comptage journalier) ; le pic ne peut pas dépasser ce nombre. Le vrai pic est dans la <b>bande bleu clair</b>. C’est la grandeur qui dit <b>combien de lits il faut</b> : un service peut avoir une occupation moyenne modeste et des pics qui dépassent sa capacité. Les jours où même la borne basse dépasse les lits sont des sureffectifs <b>certains</b> ; ceux où seule la borne haute dépasse sont des sureffectifs <b>possibles</b>.` }
  }

  const occ = ONGLETS.find((o) => o.nom === 'Occupation')
  occ.sections.push(
    { t: 'Pic de la journée : plus grand nombre d’enfants présents en même temps', h: 320, occ: true, sansComptage: true, rendre: (c, W, H) => rendrePic(c, W, H) },
    { t: 'Bilan des flux (entrées − sorties) et recalage sur des comptages réels', h: 320, occ: true, rendre: (c, W, H) => rendreBilanFlux(c, W, H) },
    { t: 'Simulation de Monte-Carlo : incertitude de l’occupation', h: 320, occ: true, rendre: (c, W, H) => rendreMonteCarlo(c, W, H) },
    { t: 'Analyse de survie : durée de séjour (Kaplan-Meier, log-rank)', h: 320, occ: true, rendre: (c, W, H) => rendreSurvie(c, W, H) },
    { t: 'Modèle de file M/G/∞ : loi du nombre d’enfants présents', h: 300, occ: true, rendre: (c, W, H) => rendreFileMGinf(c, W, H) },
  )
  occ.desc = 'Taux, pic de la journée, flux, Monte-Carlo, survie, file d’attente'
})()
