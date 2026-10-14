// ════════════════════════════════════════════════════════════════════════════════════════
// 3 · INDICATEURS — barre latérale (rubriques et sections) et contenu qui défile.
// Tous les graphiques sont dessinés à la main en SVG ; toutes les statistiques viennent de statistiques.js.
// Chargé après le script principal de saisie.html (utilise etat, registre(), lireDate(), jourNum()…).
// ════════════════════════════════════════════════════════════════════════════════════════
const COUL = { bleu: '#0055f7', orange: '#e07b00', rouge: '#d7263d', vert: '#2e9e5b', violet: '#7b3fe4', gris: '#9ca2ab', noir: '#17181a', cyan: '#0aa2c0' }
const fmtDate = (s) => s.split('-').reverse().join('/')
const MOIS_COURTS = ['jan', 'fév', 'mar', 'avr', 'mai', 'juin', 'juil', 'aoû', 'sep', 'oct', 'nov', 'déc']
const arrondi = (v, k = 1) => (v === null || v === undefined || !Number.isFinite(v) ? null : Math.round(v * 10 ** k) / 10 ** k)
const aff = (v, s = '') => (v === null || v === undefined || (typeof v === 'number' && !Number.isFinite(v)) ? '—' : `${typeof v === 'number' ? v.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) : v}${s}`)

// ── Outils de séries temporelles (calculés à la main) ────────────────────────────────────
// Moyenne mobile « passée » sur k jours : m_t = (x_t + x_{t−1} + … + x_{t−k+1}) / k.
// Elle n'utilise que le passé (comme une prévision) ; elle lisse les variations d'un jour à l'autre.
const moyenneMobile = (x, k) => x.map((_, i) => (i + 1 < k ? null : x.slice(i - k + 1, i + 1).reduce((a, b) => a + b, 0) / k))
const medianeMobile = (x, k) => x.map((_, i) => { if (i + 1 < k) return null; const f = x.slice(i - k + 1, i + 1).sort((a, b) => a - b); return k % 2 ? f[(k - 1) / 2] : (f[k / 2 - 1] + f[k / 2]) / 2 })
const ecartMobile = (x, k) => { const m = moyenneMobile(x, k); return x.map((_, i) => (m[i] === null ? null : Math.sqrt(x.slice(i - k + 1, i + 1).reduce((a, b) => a + (b - m[i]) ** 2, 0) / k))) }
const minMobile = (x, k) => x.map((_, i) => (i + 1 < k ? null : Math.min(...x.slice(i - k + 1, i + 1))))
const maxMobile = (x, k) => x.map((_, i) => (i + 1 < k ? null : Math.max(...x.slice(i - k + 1, i + 1))))
// Tendance linéaire par moindres carrés : x_t ≈ a + b·t, b = Σ(t − t̄)(x − x̄) / Σ(t − t̄)².
function tendance(x) {
  const n = x.length; if (n < 2) return { a: x[0] ?? 0, b: 0, valeurs: x.slice() }
  const tm = (n - 1) / 2, xm = x.reduce((a, b) => a + b, 0) / n
  let num = 0, den = 0; x.forEach((v, t) => { num += (t - tm) * (v - xm); den += (t - tm) ** 2 })
  const b = num / den, a = xm - b * tm
  return { a, b, valeurs: x.map((_, t) => a + b * t) }
}
// Autocorrélation ρ(k) = Σ (x_t − x̄)(x_{t+k} − x̄) / Σ (x_t − x̄)².
function autocorrelation(x, kmax) {
  const n = x.length, m = x.reduce((a, b) => a + b, 0) / n, c = x.map((v) => v - m), den = c.reduce((a, b) => a + b * b, 0) || 1
  return Array.from({ length: kmax + 1 }, (_, k) => { let s = 0; for (let t = 0; t + k < n; t++) s += c[t] * c[t + k]; return s / den })
}
// Décomposition additive classique : tendance = moyenne mobile CENTRÉE sur 7 jours,
// saisonnalité = moyenne, par jour de la semaine, de (x − tendance) recentrée à somme nulle,
// résidu = x − tendance − saisonnalité.
function decomposition(x, debutNum) {
  const n = x.length, tend = x.map((_, i) => (i < 3 || i > n - 4 ? null : x.slice(i - 3, i + 4).reduce((a, b) => a + b, 0) / 7))
  const somme = [0, 0, 0, 0, 0, 0, 0], nb = [0, 0, 0, 0, 0, 0, 0], jds = (i) => (new Date((debutNum + i) * 86400000).getUTCDay() + 6) % 7
  x.forEach((v, i) => { if (tend[i] !== null) { somme[jds(i)] += v - tend[i]; nb[jds(i)]++ } })
  const prof = somme.map((s, j) => (nb[j] ? s / nb[j] : 0)), moyP = prof.reduce((a, b) => a + b, 0) / 7, profil = prof.map((p) => p - moyP)
  const saison = x.map((_, i) => profil[jds(i)])
  return { tend, saison, residu: x.map((v, i) => (tend[i] === null ? null : v - tend[i] - saison[i])), profil }
}
const statsSerie = (x) => {
  const v = x.filter((e) => e !== null && Number.isFinite(e)); if (!v.length) return {}
  const n = v.length, m = v.reduce((a, b) => a + b, 0) / n, s = Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / n)
  const acf = autocorrelation(v, Math.min(7, n - 1))
  return { m, s, cv: m ? 100 * s / m : null, min: Math.min(...v), max: Math.max(...v), pente: tendance(v).b * 30.4, a1: acf[1], a7: acf[7] }
}

// ── Graphiques SVG à la taille de la zone (W × H en pixels réels) ─────────────────────────
// Marge gauche : assez large pour les chiffres de l'axe (et leur suffixe) + le titre vertical.
const margeY = (min, max, suffixe = '') => Math.max(54, Math.round(30 + 6.6 * Math.max(...[0, 1, 2, 3, 4].map((k) => `${etiq(min + k * (max - min) / 4)}${suffixe}`.length))))
function axesY(min, max, y, ml, W, suffixe) {
  const pas = (max - min) / 4
  return [0, 1, 2, 3, 4].map((k) => { const g = min + k * pas; return `<line x1="${ml}" x2="${W}" y1="${y(g)}" y2="${y(g)}" stroke="#eceef1"/><text x="${ml - 6}" y="${y(g) + 4}" text-anchor="end" font-size="11" fill="#8a9099">${etiq(g)}${suffixe}</text>` }).join('')
}
const largeurItem = (it) => 34 + it.nom.length * 6.3
// Nombre de lignes de légende nécessaires pour une largeur donnée (la légende passe à la ligne).
function lignesLegende(items, x0, W) { let x = x0, l = 1; for (const it of items) { if (x + largeurItem(it) > W && x > x0) { l++; x = x0 } x += largeurItem(it) } return l }
function legendeSvg(items, x0, yb, W = Infinity) {
  let x = x0, ligne = 0, nb = lignesLegende(items, x0, W)
  return items.map((it) => {
    if (x + largeurItem(it) > W && x > x0) { ligne++; x = x0 }
    const y0 = yb - (nb - 1 - ligne) * 17
    const motif = it.bande ? `<rect x="${x}" y="${yb - 9}" width="20" height="10" fill="${it.couleur}" fill-opacity="${it.opacite ?? 0.18}"/>`
      : it.barre ? `<rect x="${x + 4}" y="${yb - 10}" width="12" height="11" rx="2" fill="${it.couleur}"/>`
      : `<line x1="${x}" x2="${x + 20}" y1="${yb - 4}" y2="${yb - 4}" stroke="${it.couleur}" stroke-width="${it.epaisseur ?? 2}" ${it.pointille ? `stroke-dasharray="${it.pointille}"` : ''}/>`
    // Élément cliquable (legende.js) : cache ou réaffiche ce qui est dessiné avec cette couleur et ce motif.
    const type = it.bande ? 'bande' : it.barre ? 'barre' : 'ligne'
    const s = `<g class="leg-item" data-leg-nom="${echapper(String(it.nom))}" data-leg-couleur="${it.couleur}" data-leg-type="${type}" transform="translate(0 ${y0 - yb})" style="cursor:pointer"><title>Cliquer pour afficher ou masquer</title><rect x="${x - 2}" y="${yb - 12}" width="${largeurItem(it) - 6}" height="16" fill="transparent"/>${motif}<text x="${x + 26}" y="${yb}" font-size="11.5" fill="#3d434c">${it.nom}</text></g>`
    x += largeurItem(it)
    return s
  }).join('')
}
// Courbes jour par jour : series = [{nom, valeurs, couleur, epaisseur, pointille}], bandes = [{nom, bas, haut, couleur, opacite}].
function lignesSvg({ W, H, debutNum, series, bandes = [], refs = [], titreY, suffixe = '', barres = null, verticales = [], calendrier = false, jours = null, pas = 'jour' }) {
  // jours : premier jour de chaque point quand la vue est zoomée ou regroupée (semaine, mois, année) — voir temps.js.
  const jourDe = (i) => (jours ? jours[i] : debutNum + i)
  if (jours && pas !== 'jour') calendrier = false
  const nCal = Math.max(...series.map((s) => s.valeurs.length), barres ? barres.valeurs.length : 0)
  const calLeg = calendrier ? [{ nom: 'vacances scolaires', couleur: COUL.vert, bande: true, opacite: 0.12 }, { nom: 'jour férié', couleur: COUL.rouge, epaisseur: 1.4, pointille: '3 2' }] : []
  const leg = [...calLeg, ...(barres ? [{ nom: barres.nom, couleur: barres.couleur, barre: true }] : []),...series.map((s) => ({ nom: s.nom, couleur: s.couleur, epaisseur: s.epaisseur, pointille: s.pointille })), ...bandes.map((b) => ({ nom: b.nom, couleur: b.couleur, opacite: b.opacite, bande: true })), ...refs.map((r) => ({ nom: r.nom, couleur: r.couleur, pointille: '6 4' }))]
  let ml = 54; const mr = 14, mt = 12, mb = 48 + 17 * (lignesLegende(leg, 54, W - 14) - 1), n = Math.max(...series.map((s) => s.valeurs.length), barres ? barres.valeurs.length : 0)
  const toutes = [...series.flatMap((s) => s.valeurs), ...bandes.flatMap((b) => [...b.bas, ...b.haut]), ...refs.map((r) => r.valeur), ...(barres ? barres.valeurs : [])].filter((v) => v !== null && Number.isFinite(v))
  let max = Math.max(1, ...toutes), min = Math.min(0, ...toutes); max += (max - min) * 0.08
  ml = margeY(min, max, suffixe)
  const x = (i) => ml + (i / Math.max(1, n - 1)) * (W - ml - mr), y = (v) => mt + (1 - (v - min) / (max - min)) * (H - mt - mb)
  const chemin = (vals) => { let s = '', ouvert = false; vals.forEach((v, i) => { if (v === null || !Number.isFinite(v)) { ouvert = false; return } s += `${ouvert ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; ouvert = true }); return s }
  const zone = (bas, haut) => { const idx = bas.map((_, i) => i).filter((i) => bas[i] !== null && haut[i] !== null); if (!idx.length) return ''
    return idx.map((i, k) => `${k ? 'L' : 'M'}${x(i).toFixed(1)},${y(haut[i]).toFixed(1)}`).join('') + idx.slice().reverse().map((i) => `L${x(i).toFixed(1)},${y(bas[i]).toFixed(1)}`).join('') + 'Z' }
  const debutsMois = Array.from({ length: n }, (_, i) => i).filter((i) => (pas === 'annee' ? true
    : jours ? i === 0 || versDate(jourDe(i)).slice(0, 7) !== versDate(jourDe(i - 1)).slice(0, 7) : versDate(debutNum + i).endsWith('-01')))
  const pasEtiq = Math.max(1, Math.ceil(debutsMois.length / Math.max(4, Math.floor((W - ml) / 70))))
  const lb = barres ? Math.max(1, (W - ml - mr) / n - 1) : 0
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <text x="14" y="${(H - mb + mt) / 2}" transform="rotate(-90 14 ${(H - mb + mt) / 2})" text-anchor="middle" font-size="11.5" fill="#5a606a">${titreY}</text>
    ${axesY(min, max, y, ml, W - mr, suffixe)}
    ${debutsMois.map((i) => `<line x1="${x(i)}" x2="${x(i)}" y1="${mt}" y2="${H - mb}" stroke="#f3f4f6"/>`).join('')}
    ${calendrier ? calendrierSvg(debutNum, nCal, x, mt, H - mb) : ''}
    ${barres ? (lb >= 2.5 ? barres.valeurs.map((v, i) => (v ? `<rect x="${x(i) - lb / 2}" y="${y(v)}" width="${lb}" height="${y(0) - y(v)}" fill="${barres.couleur}" fill-opacity="0.45"/>` : '')).join('')
      // trop de jours pour des barres lisibles : courbe pleine (aire) et trait de la même couleur
      : `<path d="${chemin(barres.valeurs)}L${x(n - 1).toFixed(1)},${y(0).toFixed(1)}L${x(0).toFixed(1)},${y(0).toFixed(1)}Z" fill="${barres.couleur}" fill-opacity="0.18" stroke="none"/><path d="${chemin(barres.valeurs)}" fill="none" stroke="${barres.couleur}" stroke-width="1.2" stroke-opacity="0.85"/>`) : ''}
    ${bandes.map((b) => `<path d="${zone(b.bas, b.haut)}" fill="${b.couleur}" fill-opacity="${b.opacite ?? 0.18}" stroke="none"/>`).join('')}
    ${refs.map((r) => `<line x1="${ml}" x2="${W - mr}" y1="${y(r.valeur)}" y2="${y(r.valeur)}" stroke="${r.couleur}" stroke-width="1.5" stroke-dasharray="6 4"/><text x="${W - mr - 4}" y="${y(r.valeur) - 5}" text-anchor="end" font-size="11" font-weight="600" fill="${r.couleur}">${r.nom}</text>`).join('')}
    ${series.map((s) => `<path d="${chemin(s.valeurs)}" fill="none" stroke="${s.couleur}" stroke-width="${s.epaisseur ?? 1.6}" ${s.pointille ? `stroke-dasharray="${s.pointille}"` : ''} stroke-linejoin="round"/>`).join('')}
    ${debutsMois.filter((_, k) => k % pasEtiq === 0).map((i) => { const d = versDate(jourDe(i)); return `<text x="${x(i)}" y="${H - mb + 16}" text-anchor="middle" font-size="11" fill="#5a606a">${pas === 'annee' ? d.slice(0, 4) : `${MOIS_COURTS[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`}</text>` }).join('')}
    ${verticales.map((v) => `<line x1="${x(v.i)}" x2="${x(v.i)}" y1="${mt}" y2="${H - mb}" stroke="#5a606a" stroke-dasharray="2 3"/><text x="${x(v.i) - 4}" y="${mt + 11}" text-anchor="end" font-size="11" fill="#5a606a">${v.nom}</text>`).join('')}
    <rect class="survol-zone" x="${ml}" y="${mt}" width="${Math.max(0, W - ml - mr)}" height="${Math.max(0, H - mt - mb)}" fill="transparent" data-g="${enregistrerGraphe({ debutNum, jours, pas, n, suffixe, ymin: min, ymax: max, mt, mb, H, series: [...(barres ? [{ nom: barres.nom, valeurs: barres.valeurs, couleur: barres.couleur }] : []), ...series.map((e) => ({ nom: e.nom, valeurs: e.valeurs, couleur: e.couleur })), ...bandes.map((b) => ({ nom: b.nom, bas: b.bas, haut: b.haut, couleur: b.couleur }))] })}" data-n="${n}" data-ml="${ml}" data-mr="${mr}" data-debut="${debutNum}"/>
    ${legendeSvg(leg, ml, H - 10, W - mr)}
  </svg>`
}
// Fond des courbes : périodes de vacances scolaires (bandes vertes) et jours fériés (traits rouges pointillés).
function calendrierSvg(debutNum, n, x, haut, bas) {
  if (!CAL || n < 2) return ''
  const demi = (x(1) - x(0)) / 2, fin = debutNum + n - 1
  const bandes = CAL.periodes.filter((p) => p.fin >= debutNum && p.debut <= fin).map((p) => {
    const a = Math.max(p.debut, debutNum) - debutNum, b = Math.min(p.fin, fin) - debutNum
    return `<rect x="${x(a) - demi}" y="${haut}" width="${x(b) - x(a) + 2 * demi}" height="${bas - haut}" fill="${COUL.vert}" fill-opacity=".12"><title>${p.nom} (${fmtDate(versDate(p.debut))} → ${fmtDate(versDate(p.fin))})</title></rect>`
  })
  const traits = []
  for (let i = 0; i < n; i++) { const f = ferieDe(debutNum + i); if (f) traits.push(`<line x1="${x(i)}" x2="${x(i)}" y1="${haut}" y2="${bas}" stroke="${COUL.rouge}" stroke-width="1.4" stroke-dasharray="3 2" opacity=".75"><title>${fmtDate(versDate(debutNum + i))} : ${f}</title></line>`) }
  return bandes.join('') + traits.join('')
}
// Barres verticales groupées ; erreurs = [{bas, haut}] (trait noir) sur la 1re série.
function barresSvg({ W, H, categories, series, titreY, refs = [], erreurs = null, suffixe = '' }) {
  let ml = 54; const mr = 14, mt = 14, mb = series.length > 1 || refs.length ? 52 : 34
  const toutes = [...series.flatMap((s) => s.valeurs), ...(erreurs ? erreurs.map((e) => e.haut) : []), ...refs.map((r) => r.valeur)].filter((v) => v !== null && Number.isFinite(v))
  const max = Math.max(1, ...toutes) * 1.1, y = (v) => mt + (1 - v / max) * (H - mt - mb)
  ml = margeY(0, max, suffixe)
  const lg = (W - ml - mr) / Math.max(1, categories.length), lb = Math.min(46, (lg * 0.78) / series.length)
  const x0 = (i) => ml + i * lg + (lg - lb * series.length) / 2, pasE = Math.max(1, Math.ceil(categories.length / Math.max(4, Math.floor((W - ml) / 52))))
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <text x="14" y="${(H - mb + mt) / 2}" transform="rotate(-90 14 ${(H - mb + mt) / 2})" text-anchor="middle" font-size="11.5" fill="#5a606a">${titreY}</text>
    ${axesY(0, max, y, ml, W - mr, suffixe)}
    ${refs.map((r) => `<line x1="${ml}" x2="${W - mr}" y1="${y(r.valeur)}" y2="${y(r.valeur)}" stroke="${r.couleur}" stroke-width="1.5" stroke-dasharray="6 4"/><text x="${W - mr - 4}" y="${y(r.valeur) - 5}" text-anchor="end" font-size="11" font-weight="600" fill="${r.couleur}">${r.nom}</text>`).join('')}
    ${categories.map((c, i) => series.map((s, k) => { const v = s.valeurs[i]; if (v === null || !Number.isFinite(v)) return ''
      return `<rect x="${x0(i) + k * lb}" y="${y(v)}" width="${Math.max(1, lb - (lb > 8 ? 3 : 0.4))}" height="${Math.max(0, y(0) - y(v))}" fill="${s.couleur}" rx="3"><title>${c} · ${s.nom} : ${arrondi(v)}${suffixe}</title></rect>
        ${lb > 26 ? `<text x="${x0(i) + k * lb + (lb - 3) / 2}" y="${y(v) - 4}" text-anchor="middle" font-size="10.5" fill="#3d434c">${arrondi(v, v < 10 ? 1 : 0)}</text>` : ''}` }).join('')
      + (erreurs?.[i] && erreurs[i].bas !== null ? `<g stroke="#17181a" stroke-width="1.4"><line x1="${x0(i) + lb / 2 - 1.5}" x2="${x0(i) + lb / 2 - 1.5}" y1="${y(erreurs[i].bas)}" y2="${y(erreurs[i].haut)}"/><line x1="${x0(i) + lb / 2 - 6}" x2="${x0(i) + lb / 2 + 3}" y1="${y(erreurs[i].bas)}" y2="${y(erreurs[i].bas)}"/><line x1="${x0(i) + lb / 2 - 6}" x2="${x0(i) + lb / 2 + 3}" y1="${y(erreurs[i].haut)}" y2="${y(erreurs[i].haut)}"/></g>` : '')
      + (i % pasE === 0 ? `<text x="${x0(i) + (lb * series.length) / 2}" y="${H - mb + 16}" text-anchor="middle" font-size="11" fill="#5a606a">${c}</text>` : '')).join('')}
    ${series.length > 1 || refs.length ? legendeSvg([...series.map((s) => ({ nom: s.nom, couleur: s.couleur, barre: true })), ...(erreurs ? [{ nom: 'fourchette', couleur: COUL.noir, epaisseur: 1.4 }] : []), ...refs.map((r) => ({ nom: r.nom, couleur: r.couleur, pointille: '6 4' }))], ml, H - 10) : ''}
  </svg>`
}
function barresHorizSvg({ W, items, couleur }) {
  // Hauteur automatique : 30 px par barre. Chaque item peut donner son propre texte (sinon : valeur et %).
  const total = items.reduce((a, b) => a + (b.valeur ?? 0), 0) || 1, max = Math.max(1, ...items.map((i) => i.valeur ?? 0))
  const texteMax = Math.max(60, ...items.map((i) => String(i.texte ?? `${i.valeur} (100 %)`).replace(/<[^>]+>/g, '').length * 6.9 + 20))
  const ml = Math.min(340, W * 0.4), lh = 30, hb = 18, H = Math.max(40, items.length * lh + 6), lg = Math.max(40, W - ml - texteMax)
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${items.map((it, i) => `
    <text x="${ml - 10}" y="${i * lh + lh / 2 + 4}" text-anchor="end" font-size="12.5" fill="#3d434c"><title>${echapper(it.label)}</title>${echapper(it.label.length > Math.floor((ml - 16) / 6.9) ? it.label.slice(0, Math.floor((ml - 16) / 6.9) - 1) + '…' : it.label)}</text>
    <rect x="${ml}" y="${i * lh + (lh - hb) / 2}" width="${Math.max(2, lg * (it.valeur ?? 0) / max)}" height="${hb}" fill="${couleur}" fill-opacity="${it.pale ? 0.3 : 1}" rx="3"><title>${echapper(it.label)} : ${String(it.texte ?? it.valeur).replace(/<[^>]+>/g, '')}</title></rect>
    <text x="${ml + lg * (it.valeur ?? 0) / max + 8}" y="${i * lh + lh / 2 + 4}" font-size="12.5" font-weight="600" fill="#17181a">${it.texte ?? `${it.valeur} <tspan fill="#757b85" font-weight="400">(${Math.round(100 * it.valeur / total)} %)</tspan>`}</text>`).join('')}</svg>`
}
// Plusieurs petits graphiques empilés (décomposition).
const empiler = (H, n, f) => Array.from({ length: n }, (_, k) => f(Math.floor(H / n), k)).join('')

// ── Les onglets : chaque onglet affiche TOUTES ses statistiques, les unes sous les autres ─────
// Les graphiques ont une hauteur fixe raisonnable ; seul le cadre des indicateurs défile.
const OPTIONS_SERIES = [
  ['mm7', 'Moyenne mobile 7 j'], ['mm30', 'Moyenne mobile 30 j'], ['med7', 'Médiane mobile 7 j'], ['tend', 'Tendance linéaire'],
  ['bol', 'Bande ± 2 écarts-types (30 j)'], ['minmax', 'Min – max sur 7 j'], ['fourchette', 'Fourchette (sorties non écrites)'], ['cap', 'Capacité (lits)'],
  ['cal', 'Jours fériés et vacances scolaires'],
]
// Calendrier camerounais (calendrier.js) : nom du férié / de la période de vacances d'un jour, ou null.
const CAL = window.CALENDRIER_CM
const ferieDe = (j) => CAL?.ferie(j) ?? null
const vacancesDe = (j) => (CAL?.vacancesConnues(j) ? (CAL.vacances(j) ? 1 : 0) : null)
// Méthode de comptage en vigueur (bouton « Calcul ») : tous les libellés de graphes la reprennent.
const modeComptage = () => cacheIndicateurs?.d?.reglages?.comptage ?? 'minuit'
const enJournee = () => modeComptage() === 'journee'
const NOMS_COMPTAGE = { minuit: 'Recensement de minuit (nuits passées)', journee: 'Présence dans la journée (jour de sortie compris)',
  pondere: 'Présence pondérée par le temps (heures typiques)' }
const nomPresents = (court = false) => `${court ? 'Présents' : 'Enfants présents'} ${{ minuit: 'à minuit', journee: 'dans la journée', pondere: '(présence pondérée)' }[modeComptage()]}`
const SERIES_CHOIX = [['presents', 'Enfants présents'], ['taux', 'Taux d’occupation (%)'], ['adm', 'Admissions / jour'], ['sor', 'Sorties / jour']]
const JOURS_SEMAINE = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
const jourSemaine = (j) => (new Date(j * 86400000).getUTCDay() + 6) % 7
const ordre = (obj) => Object.entries(obj).map(([label, valeur]) => ({ label, valeur })).sort((a, b) => b.valeur - a.valeur)
const kpi = (label, valeur, note) => `<div class="kpi"><span class="label">${label}</span><span class="value">${valeur}</span><span class="note">${note}</span></div>`
const etiquettePeriode = (p) => (p.length === 7 ? `${MOIS_COURTS[+p.slice(5) - 1]} ${p.slice(2, 4)}`
  : p.length === 10 ? `${p.slice(8)}/${p.slice(5, 7)}/${p.slice(2, 4)}` : p.startsWith('S') ? `sem. ${p.slice(9)}/${p.slice(6, 8)}/${p.slice(3, 5)}` : p)
// Nom de la période de regroupement choisie en haut (« par jour / semaine / mois / année »).
const uniteParNom = (par) => ({ jour: 'jour', semaine: 'semaine', annee: 'année' })[par] ?? 'mois'
const trancheAge = (l) => { const m = ageEnMois(l.age); return m === null ? null : m < 12 ? '0 – 11 mois' : m < 60 ? '12 – 59 mois' : m < 180 ? '5 – 14 ans' : '15 ans et plus' }
const moyennePonderee = (liste) => { const w = liste.reduce((a, b) => a + b.poids, 0); return w ? liste.reduce((a, b) => a + b.poids * b.nuits, 0) / w : null }

function serieChoisie(c, cle) {
  const { d, lits } = c
  const L = (i) => d.litsJour?.[i] ?? lits                        // capacité du jour i
  if (cle === 'taux' && lits) return { x: d.presents.map((v, i) => 100 * v / L(i)), bas: d.bas.map((v, i) => 100 * v / L(i)), haut: d.haut.map((v, i) => 100 * v / L(i)), nom: 'Taux d’occupation', unite: ' %', cap: 100 }
  if (cle === 'adm') return { x: d.adm.slice(), nom: 'Admissions du jour', unite: '' }
  if (cle === 'sor') return { x: sortiesParJour(d), nom: 'Sorties du jour', unite: '' }
  return { x: d.presents.slice(), bas: d.bas, haut: d.haut, nom: nomPresents(), unite: '', cap: lits }
}
function sortiesParJour(d) { const s = new Array(d.presents.length).fill(0); for (const f of d.sorties) { const i = f.jour - d.debutNum; if (i >= 0 && i < s.length) s[i] += f.poids } return s }
const bandeauStats = (paires) => `<div class="ind-stats">${paires.map(([l, v]) => `<div><span>${l}</span><b>${v}</b></div>`).join('')}</div>`
// Autocorrélation partielle (récursion de Durbin-Levinson) : l'effet propre du retard k.
function autocorrelationPartielle(x, kmax) {
  const r = autocorrelation(x, kmax), phi = [1]; let prec = []
  for (let k = 1; k <= kmax; k++) {
    const num = r[k] - prec.reduce((a, p, j) => a + p * r[k - 1 - j], 0), den = 1 - prec.reduce((a, p, j) => a + p * r[j + 1], 0)
    const pkk = den ? num / den : 0, cour = prec.map((p, j) => p - pkk * prec[k - 2 - j]); cour.push(pkk); prec = cour; phi.push(pkk)
  }
  return phi
}

// Chaque rubrique (barre latérale) : { nom, ico, desc, occ (besoin de l'occupation), sections }.
// Chaque section : { t (titre), h (hauteur du graphique), occ, rendre(c, W, H) → { html, avant, lecture, survol, options } }
// Rappel de la méthode de comptage choisie (bouton « Calcul »), en tête des explications de l'occupation.
const texteComptage = (c) => (c.d.reglages?.comptage === 'pondere'
  ? `<b>Présence pondérée par le temps</b> : chaque enfant compte la fraction de chaque jour où il est là, avec des heures typiques (entrée ${nf(c.d.reglages.heures.a * 24, 1)} h, sortie ${nf(c.d.reglages.heures.b * 24, 1)} h, séjour du même jour ${nf(c.d.reglages.heures.m * 24, 1)} h) : jour d’entrée 1 − h_e/24, jours pleins 1, jour de sortie h_s/24. C’est l’occupation moyenne réelle si ces heures sont justes ; elle dépend d’elles (à demander au service).`
  : c.d.reglages?.comptage === 'journee'
  ? '<b>Comptage journalier</b> : un enfant compte chaque jour où il est présent, jour de sortie compris (entrée ≤ jour ≤ sortie) ; une mise en observation compte 1 jour. Limite : un lit libéré le matin et réoccupé l’après-midi compte deux fois, ce qui peut surestimer le nombre de lits occupés en même temps.'
  : '<b>Recensement de minuit</b> (norme des statistiques hospitalières) : un enfant compte les nuits passées (entrée ≤ jour < sortie) ; une mise en observation (entrée et sortie le même jour) compte 0. Limite : il ne voit ni les mises en observation ni le jour de sortie, et sous-estime donc l’occupation de jour. Autre méthode : bouton « Calcul » → Comptage.')

const ONGLETS = [
  { nom: 'Synthèse', ico: 'synthese', desc: 'Votre saisie, chiffres clés, qualité des soins', sections: [
    { t: 'Votre saisie', rendre: (c) => ({ html: htmlSaisie(c), lecture: `vous saisissez le registre <b>progressivement</b> : tous les calculs portent uniquement sur la période entre votre premier et votre dernier jour saisi, jamais jusqu’à aujourd’hui. Quand vous ajoutez des pages, tout se met à jour. Les séjours sont classés selon ce qu’on sait de leur fin : sortie <b>écrite</b>, sortie <b>calculée</b> (entrée + nombre de jours), <b>encore hospitalisé</b> à la fin de la saisie, ou durée <b>inconnue</b> (ni sortie ni nombre de jours : exclu de l’occupation).` }) },
    { t: 'Chiffres clés de l’occupation', occ: true, rendre: (c) => ({ html: htmlCles(c), lecture: `${texteComptage(c)} Chiffres calculés du ${fmtDate(c.d.debut)} au ${fmtDate(c.d.fin)}. Le calcul commence après un <b>rodage de ${c.d.rodage} jours</b> (depuis le ${fmtDate(c.d.base)}) : les enfants entrés avant le début de votre saisie occupent des lits mais sont absents de vos lignes. <b>TOM</b> = lits-jours occupés ÷ lits-jours disponibles (85 % : service tendu ; 100 % : plein). <b>Rotation</b> = patients par lit. <b>Intervalle de rotation</b> = jours où un lit reste vide entre deux patients (négatif : sureffectif). <b>Convention des jours :</b> ${c.d.convention}` }) },
    { t: 'Patients et qualité des soins', rendre: (c) => ({ html: htmlQualite(c), lecture: `proportions calculées sur toutes les lignes saisies. <b>SCAM</b> : sortie contre avis médical. <b>Référés</b> : envoyés vers un autre hôpital. Une part élevée de SCAM ou de référés peut signaler un manque de moyens ou de lits. L’<b>âge médian</b> est l’âge qui partage les enfants en deux moitiés.` }) },
  ] },
  { nom: 'Statistiques descriptives', ico: 'sigma', desc: 'Moyenne, médiane, quantiles, forme, normalité', sections: [
    { t: 'Variables numériques des patients', rendre: (c) => rendreTableDescriptive(c, 'p') },
    { comptage: true, t: 'Variables numériques journalières', rendre: (c) => rendreTableDescriptive(c, 'j') },
    { t: 'Distribution d’une variable', h: 260, rendre: (c, W, H) => rendreDistribution(c, W, H) },
    { t: 'Variables qualitatives : effectifs et proportions', rendre: (c) => rendreQualitatives(c) },
    { t: 'Comparaison d’une variable entre groupes', rendre: (c, W) => rendreParGroupe(c, W) },
  ] },
  { nom: 'Corrélations et tests', ico: 'nuage', desc: 'Pearson, Spearman, Kendall, χ², régression', sections: [
    { t: 'Matrice de corrélation — patients', rendre: (c, W) => rendreMatrice(c, W, 'p') },
    { comptage: true, t: 'Matrice de corrélation — variables journalières', rendre: (c, W) => rendreMatrice(c, W, 'j') },
    { t: 'Toutes les paires de variables, classées par force du lien', rendre: (c) => rendrePaires(c) },
    { t: 'Nuage de points et droite de régression', h: 340, rendre: (c, W, H) => rendreNuage(c, W, H) },
    { t: 'Nuage de points en 3D (trois variables)', h: 480, d3: true, rendre: (c, W, H) => rendreNuage3D(c, W, H) },
    { t: 'Liens entre variables qualitatives (khi-deux, V de Cramér)', rendre: (c, W) => rendreCramer(c, W) },
    { t: 'Tableau croisé', rendre: (c) => rendreContingence(c) },
    { t: 'Tests de comparaison de groupes (tous les croisements)', rendre: (c) => rendreTestsGroupes(c) },
    { t: 'Régression linéaire multiple', rendre: (c) => rendreRegression(c) },
    { t: 'Régression à deux variables : plan ajusté en 3D', h: 480, d3: true, rendre: (c, W, H) => rendreRegression3D(c, W, H) },
    { t: 'Jours fériés et vacances scolaires : effet sur les admissions', rendre: (c) => rendreCalendrier(c) },
    { t: 'Corrélation croisée : admissions → présents', h: 240, occ: true, rendre: (c, W, H) => rendreCcf(c, W, H) },
  ] },
  { nom: 'Analyse multivariée (ACP)', ico: 'acp', desc: 'Composantes principales : axes, cercle, profils', sections: [
    { t: 'Variables, adéquation (KMO, Bartlett) et valeurs propres', rendre: (c) => rendreAcpDonnees(c) },
    { t: 'Éboulis des valeurs propres : combien d’axes garder', h: 300, rendre: (c, W, H) => rendreAcpEboulis(c, W, H) },
    { t: 'Vue 3D interactive des trois premiers axes (F1, F2, F3)', h: 560, d3: true, rendre: (c, W, H) => rendreAcp3D(c, W, H) },
    { t: 'Cercle des corrélations', rendre: (c, W) => rendreAcpCercle(c, W) },
    { t: 'Projection des patients sur le plan factoriel', h: 440, rendre: (c, W, H) => rendreAcpIndividus(c, W, H) },
    { t: 'Corrélations, qualité (cos²) et contributions des variables', rendre: (c) => rendreAcpVariables(c) },
    { t: 'Modalités caractéristiques des axes (valeurs-test)', rendre: (c) => rendreAcpModalites(c) },
    { t: 'Interprétation des axes', rendre: (c) => rendreAcpInterpretation(c) },
  ] },
  { nom: 'Occupation', ico: 'lit', occ: true, desc: 'Taux d’occupation, pics, jours de la semaine', sections: [
    { t: 'Taux d’occupation par période', h: 300, occ: true, rendre: (c) => rendreTom(c) },
    { t: 'Occupation moyenne et maximale par mois', h: 280, occ: true, rendre: (c) => rendreOccMax(c) },
    { t: 'Répartition des jours selon le taux d’occupation', h: 260, occ: true, rendre: (c) => rendreNiveaux(c) },
    { t: 'Occupation selon le jour de la semaine', h: 260, occ: true, rendre: (c) => rendreHebdo(c) },
    { t: 'Loi de Little et file d’attente (Erlang B) : contrôle et nombre de lits', occ: true, rendre: (c) => rendreFileAttente(c) },
  ] },
  { nom: 'Séries temporelles', ico: 'courbe', occ: true, desc: 'Courbes, lissages, décomposition, ACF, PACF', sections: [
    { t: 'Courbe jour par jour (options à cocher)', h: 360, occ: true, rendre: (c, W, H) => rendreCourbe(c, W, H) },
    { sansComptage: true, t: 'Admissions jour par jour', h: 300, occ: true, rendre: (c, W, H) => rendreAdmissions(c, W, H) },
    { t: 'Décomposition : tendance, semaine, imprévus', h: 390, occ: true, rendre: (c, W, H) => rendreDecomposition(c, W, H) },
    { t: 'Autocorrélation (ACF)', h: 250, occ: true, rendre: (c, W, H) => rendreAcf(c, W, H) },
    { t: 'Autocorrélation partielle (PACF)', h: 250, occ: true, rendre: (c, W, H) => rendrePacf(c, W, H) },
    { t: 'Volatilité : écart-type mobile', h: 260, occ: true, rendre: (c, W, H) => rendreVolatilite(c, W, H) },
  ] },
  { nom: 'Modèles de prévision', ico: 'prevision', desc: 'Stationnarité, SARIMA, Holt-Winters, comparaison', sections: [
    { comptage: true, t: 'Série étudiée et tests de stationnarité', rendre: (c) => rendreStationnarite(c) },
    { comptage: true, t: 'Tendance, saisonnalité et dispersion (tests)', rendre: (c) => rendreTestsSerie(c) },
    { comptage: true, t: 'Périodogramme : les cycles de la série', h: 310, rendre: (c, W, H) => rendrePeriodogramme(c, W, H) },
    { comptage: true, t: 'Comparaison des modèles sur la période de validation', h: 320, rendre: (c, W, H) => rendreComparaison(c, W, H) },
    { comptage: true, t: 'SARIMA : estimation et prévision', h: 320, rendre: (c, W, H) => rendreSarima(c, W, H) },
    { comptage: true, t: 'Diagnostic des résidus du SARIMA', h: 220, rendre: (c, W, H) => rendreResidus(c, W, H) },
    { comptage: true, t: 'Prévisions de tous les modèles', h: 320, rendre: (c, W, H) => rendrePrevisions(c, W, H) },
  ] },
  { nom: 'Flux et séjours', ico: 'flux', occ: true, desc: 'Admissions, sorties, durées de séjour', sections: [
    { sansComptage: true, t: 'Admissions et sorties par période', h: 280, occ: true, rendre: (c) => rendreFlux(c) },
    { sansComptage: true, t: 'Durée des séjours (en nuits)', h: 280, occ: true, rendre: (c, W, H) => rendreDurees(c, W, H) },
    { sansComptage: true, t: 'Durée moyenne de séjour par mois', h: 260, occ: true, rendre: (c) => rendreDmsMois(c) },
    { sansComptage: true, t: 'Durée moyenne de séjour par cause', h: 0, occ: true, rendre: (c, W) => rendreDmsGroupe(c, W, 'cause') },
    { sansComptage: true, t: 'Durée moyenne de séjour par tranche d’âge', h: 0, occ: true, rendre: (c, W) => rendreDmsGroupe(c, W, 'age') },
  ] },
  { nom: 'Patients', ico: 'patient', desc: 'Âge, sexe, causes, issues, quartiers', sections: [
    { t: 'Âge et sexe des enfants', h: 260, rendre: (c) => rendreAges(c) },
    { t: 'Principales causes d’hospitalisation', h: 0, rendre: (c, W) => ({ html: barresHorizSvg({ W, items: ordre(c.st.causes).slice(0, 13), couleur: COUL.bleu }), lecture: `regroupement automatique du diagnostic de sortie (ou d’entrée s’il manque) en grandes causes, à partir des mots écrits (APG → paludisme, GEF → gastro-entérite…). Un enfant est compté une fois, dans sa première cause reconnue. À comparer avec les « dix principales causes » du récapitulatif mensuel du registre.` }) },
    { t: 'Issue du séjour', h: 0, rendre: (c, W) => ({ html: barresHorizSvg({ W, items: ordre(c.st.issues), couleur: COUL.vert }), lecture: `comment les séjours se sont terminés, d’après la colonne Observation : sortie à domicile, mise en observation (MEO), sortie contre avis médical (SCAM), référé ou transféré, décès, évadé. « Non renseignée » : rien d’écrit.` }) },
    { t: 'Admissions selon le jour de la semaine', h: 240, rendre: (c) => ({ html: barresSvg({ W: c.W, H: c.H, categories: JOURS_SEMAINE, series: [{ nom: 'Admissions', valeurs: c.st.semaine, couleur: COUL.bleu }], titreY: 'Nombre d’admissions' }), lecture: `le nombre d’enregistrements selon le jour de la semaine. Un creux le week-end peut venir du service (moins d’admissions) ou du registre (enregistrements regroupés le lundi).` }) },
    { t: 'Quartiers de résidence les plus fréquents', h: 0, rendre: (c, W) => ({ html: barresHorizSvg({ W, items: ordre(c.st.quartiers).slice(0, 12), couleur: COUL.violet }), lecture: `d’où viennent les enfants hospitalisés (colonne Domicile ; les écritures d’un même quartier sont regroupées : « CV », « Cité verte », « cite verte » comptent ensemble, de même que majuscules, accents et « ? » ; liste des abréviations dans registres.js, ALIAS_QUARTIERS). Utile pour décrire l’aire de recrutement du service.` }) },
    { t: 'Durée moyenne de séjour selon l’âge', h: 270, rendre: (c, W, H) => rendreDureeAge(c, W, H) },
    { t: 'Transfusions par mois', h: 240, rendre: (c) => { const m = Object.keys(c.st.parMois).sort(); return { html: barresSvg({ W: c.W, H: c.H, categories: m.map(etiquettePeriode), series: [{ nom: 'Transfusions', valeurs: m.map((k) => c.st.parMois[k].transf), couleur: COUL.rouge }], titreY: 'Enfants transfusés' }), lecture: `nombre d’enfants dont le traitement reçu mentionne une transfusion. Les pics suivent en général ceux du paludisme grave avec anémie.` } } },
  ] },
  { nom: 'Tableaux', ico: 'tableau', desc: 'Récapitulatif mensuel, indicateurs, causes', sections: [
    { t: 'Récapitulatif mensuel (à comparer avec celui du registre)', rendre: (c) => ({ html: htmlRecap(c), lecture: `les mêmes chiffres que le <b>récapitulatif mensuel</b> écrit à la fin de chaque mois dans le registre, calculés à partir de <b>votre saisie</b>. S’ils diffèrent beaucoup, il manque des lignes ou certaines sont mal saisies : c’est le contrôle de qualité le plus simple à montrer dans le mémoire.` }) },
    { t: 'Indicateurs hospitaliers par période', occ: true, rendre: (c) => ({ html: htmlTable(c), lecture: `<b>Journées d’hospitalisation</b> = somme des ${nomPresents().toLowerCase()} · <b>TOM</b> = journées ÷ Σ des lits de chaque jour (lits × jours si la capacité est fixe) · <b>DMS</b> = nuits moyennes des séjours terminés · <b>rotation</b> = sorties ÷ lits · <b>intervalle de rotation</b> = (lits × jours − journées) ÷ sorties · décès repérés par « décès / DCD » dans l’observation. Mêmes définitions que l’application NERA.` }) },
    { t: 'Indicateurs par cause d’hospitalisation', rendre: (c) => ({ html: htmlCauses(c), lecture: `pour chaque grande cause : nombre d’enfants, durée moyenne de séjour (sur les séjours terminés), nombre de décès, de SCAM et de référés. Les causes à la fois fréquentes et longues pèsent le plus dans l’occupation des lits.` }) },
  ] },
]

function htmlSaisie({ d, st }) {
  const mois = Object.keys(st.parMois).sort(), trous = []
  for (let a = +(mois[0] ?? '0').slice(0, 4), m = +(mois[0] ?? '00-00').slice(5); mois.length && `${a}-${String(m).padStart(2, '0')}` <= mois.at(-1); m === 12 ? (a++, m = 1) : m++) {
    const k = `${a}-${String(m).padStart(2, '0')}`; if (!st.parMois[k]) trous.push(k)
  }
  const s = d.statuts ?? {}
  return `<div class="grid g4">
    ${kpi('Lignes saisies', st.n, 'dans le service affiché')}
    ${kpi('Premier jour saisi', d.premierSaisi ? fmtDate(d.premierSaisi) : '—', 'date d’enregistrement la plus ancienne')}
    ${kpi('Dernier jour saisi', d.dernierSaisi ? fmtDate(d.dernierSaisi) : '—', 'les calculs s’arrêtent ici')}
    ${kpi('Lignes dont la durée est connue', `${st.n ? Math.round(100 * ((s.observee ?? 0) + (s.calculee ?? 0)) / st.n) : 0}<small> %</small>`, `${st.sortiesEcrites} avec date de sortie · ${st.nbJoursEcrits} avec nombre de jours`)}
    ${kpi('Sortie écrite', s.observee ?? 0, 'séjours')}${kpi('Sortie calculée', s.calculee ?? 0, 'entrée + nombre de jours')}
    ${kpi('Encore hospitalisés', s.censuree ?? 0, `à la fin de la saisie (entrés depuis moins de ${d.reglages?.fenetreCensure ?? 30} j)`)}
    ${s.imputee ? kpi('Durée estimée', s.imputee, d.reglages.inconnues === 'estimee'
      ? `d’après le prix (${d.reglages.sources.prix}), l’issue (${d.reglages.sources.issue}) ou la médiane (${d.reglages.sources.mediane})`
      : `comptés avec la durée médiane (${d.reglages.mediane} nuits)`) : kpi('Durée inconnue', s.inconnue ?? 0, `exclus de l’occupation${d.reglages?.partisSansDuree ? ` · dont ${d.reglages.partisSansDuree} partis (SCAM, sortie, MEO…) sans date ni nombre de jours` : ''}`)}
  </div>
  ${d.message ? `<div class="alert warn" style="margin-top:12px;display:block">${d.message}</div>` : ''}
  ${alertePeriode(d)}${alerteTrous(d)}${alerteDoublons(d)}
  ${trous.length ? `<div class="alert warn" style="margin-top:12px;display:block">Mois sans aucune ligne entre le premier et le dernier jour saisi : <b>${trous.map((t) => t.split('-').reverse().join('/')).join(', ')}</b>. L’occupation de ces mois (et des semaines suivantes) sera fausse tant qu’ils ne sont pas saisis.</div>` : ''}`
}
// Prévient quand l'occupation ne porte que sur une partie de la saisie, et dit quels mois bloquent.
function alertePeriode(d) {
  const rg = d.reglages; if (!rg?.bloquants?.length || !d.premierSaisi) return ''
  const saisis = Math.round((new Date(d.dernierSaisi) - new Date(d.premierSaisi)) / 86400000) + 1
  const calcules = d.debut ? Math.round((new Date(d.fin) - new Date(d.debut)) / 86400000) + 1 : 0
  if (d.debut && calcules >= 0.8 * saisis) return ''
  const mois = rg.bloquants.map((q) => `<b>${etiquettePeriode(q.mois)}</b> (${Math.floor(100 * q.part)} %, ${q.lignes - q.connues} ligne(s) sans sortie ni nombre de jours)`).join(', ')
  return `<div class="alert crit" style="margin-top:12px;display:block;line-height:1.55"><b>${d.debut ? `L’occupation ne porte que sur ${calcules} jour(s) (du ${fmtDate(d.debut)} au ${fmtDate(d.fin)}) sur ${saisis} jours saisis.` : 'L’occupation ne peut pas être calculée.'}</b>
    Le calcul commence après le dernier mois où moins de ${Math.round(100 * rg.seuil)} % des séjours ont une durée connue : ${mois}.
    Taux d’occupation et jours en sureffectif ne valent que pour cette courte période.
    Pour élargir : complétez la date de sortie ou le nombre de jours de ces lignes, ou, en haut, baissez le seuil « Durées connues » ou choisissez « Durée inconnue : estimée (prix, issue) » (à signaler dans le mémoire).</div>`
}
// Pages pas encore saisies : trous dans les N° d'ordre. Celui de la fin arrête le calcul (saisie continue).
function alerteTrous(d) {
  const rg = d.reglages; if (!rg) return ''
  const j = (n) => fmtDate(versDate(n)), plage = (t) => `n° ${t.de}${t.a > t.de ? ` à ${t.a}` : ''}`
  const tous = (rg.manquants ?? rg.trous ?? []).filter((t) => t !== rg.trouFinal && !(rg.trouFinal && t.mois === rg.trouFinal.mois && t.de === rg.trouFinal.de))
  // Avertissement : TOUS les numéros manquants, mois par mois (page oubliée, numéro sauté ou ligne effacée).
  const parMois = {}; for (const t of tous) (parMois[t.mois] ??= []).push(t)
  const total = tous.reduce((s, t) => s + t.a - t.de + 1, 0)
  const liste = Object.entries(parMois).sort().map(([m, ts]) => `<li><b>${etiquettePeriode(m)}</b> : ${ts.map((t) => `${plage(t)} <span class="text-muted">(entre le ${j(t.apres)} et le ${j(t.avant)})</span>`).join(' · ')} — ${ts.reduce((s, t) => s + t.a - t.de + 1, 0)} ligne(s)</li>`).join('')
  return (tous.length ? `<div class="alert warn" style="margin-top:12px;display:block;line-height:1.55"><b>${total} N° d’ordre manquant(s) dans ${Object.keys(parMois).length} mois</b> : page non photographiée, numéro sauté dans le registre ou ligne effacée (blanc correcteur, « doublon »). Vérifiez sur le registre et saisissez-les si possible ; sinon, signalez-les dans les limites du mémoire.
      <ul style="margin:6px 0 0;padding-left:18px">${liste}</ul></div>` : '')
    + (rg.trouFinal ? `<div class="alert warn" style="margin-top:12px;display:block;line-height:1.55"><b>Occupation calculée jusqu’au ${j(rg.trouFinal.apres)}, dernier jour de saisie continue</b> : les ${plage(rg.trouFinal)} de ${etiquettePeriode(rg.trouFinal.mois)} ne sont pas encore saisis. Les lignes suivantes (jusqu’au ${fmtDate(rg.dernierSaisi)}) sont gardées pour les patients, mais compter l’occupation après ce trou la ferait baisser à tort.</div>` : '')
    + (rg.entreesApprochees ? `<div class="alert info" style="margin-top:12px;display:block">${rg.entreesApprochees} date(s) d’entrée illisible(s) (« 0?/03/25 »…) reconstituée(s) : sortie − nombre de jours, sinon date d’enregistrement.</div>` : '')
}
// Même enfant probablement écrit deux fois : même date d'entrée, sexe, âge et quartier. Plus les lignes écartées.
function alerteDoublons(d) {
  const r = registre(), n = (s) => String(s ?? '').toLowerCase().replace(/\s+/g, ''), groupes = {}
  for (const l of lignesService()) {
    if (!n(l.age)) continue
    const k = [l.date_entree || l[r.dateReference], n(l.age), l.sexe, n(l.domicile)].join('|');
    (groupes[k] ??= []).push(l)
  }
  const dbl = Object.values(groupes).filter((g) => g.length > 1)
  const desc = (l) => `n° ${echapper(l[r.ordre] || '?')} du ${echapper(l[r.dateReference] || '?')}`
  return (dbl.length ? `<div class="alert warn" style="margin-top:12px;display:block;line-height:1.55"><b>${dbl.length} doublon(s) probable(s)</b> (même date d’entrée, sexe, âge et quartier) : un même séjour compté deux fois gonfle l’occupation. Vérifiez sur les photos et supprimez la ligne en trop :
      ${dbl.slice(0, 25).map((g) => `${g.map(desc).join(' et ')} (${echapper(g[0].sexe || '?')}, ${echapper(g[0].age)}, ${echapper(g[0].domicile || '?')}, entrée ${echapper(g[0].date_entree || '?')})`).join(' · ')}${dbl.length > 25 ? ' · …' : ''}</div>` : '')
    + (d.reglages?.aberrantes ? `<div class="alert warn" style="margin-top:12px;display:block"><b>${d.reglages.aberrantes} durée(s) aberrante(s)</b> (plus de 90 nuits, ou une date ou un prix recopié dans « Nbre de jours ») : traitée(s) comme absente(s). Corrigez la case.</div>` : '')
    + (d.reglages?.rejetees ? `<div class="alert warn" style="margin-top:12px;display:block"><b>${d.reglages.rejetees} ligne(s) écartée(s)</b> : la date de sortie est avant la date d’entrée (souvent une faute sur le mois ou l’année). Corrigez-les pour qu’elles comptent.</div>` : '')
}
// Explique pourquoi le nombre de séjours des statistiques de durée est plus petit que le nombre de lignes.
function htmlRepartition(d) {
  const r = d.repartition; if (!r) return ''
  return `<div class="alert info" style="display:block;margin-top:10px;font-size:12.8px;line-height:1.55"><b>Un séjour = une hospitalisation = une ligne du registre.</b> Vos <b>${r.lignes}</b> lignes datées se répartissent ainsi :
    <b>${r.dansPeriode}</b> séjours terminés <b>pendant la période de calcul</b> (du ${fmtDate(d.debut)} au ${fmtDate(d.fin)}) — ce sont eux qui servent aux durées et à la DMS ·
    <b>${r.pendantRodage}</b> terminés <b>avant le début du calcul</b> (le calcul commence le ${fmtDate(d.debut)}, après ${d.rodage} jours de rodage depuis le ${fmtDate(d.base)} : avant, des enfants entrés avant votre saisie manqueraient) ·
    <b>${r.encoreHospitalises}</b> <b>encore hospitalisés</b> à la fin de votre saisie (durée pas encore connue) ·
    ${r.imputees ? `<b>${r.imputees}</b> sans sortie ni nombre de jours, comptés dans l’occupation avec une durée estimée (${d.reglages.inconnues === 'estimee' ? 'médiane des séjours de même prix, sinon de même issue' : `médiane du service, ${d.reglages.mediane} nuits`} ; fourchette du 1er au 3e quartile) mais pas dans la DMS ·` : ''}
    <b>${r.inconnues}</b> sans sortie ni nombre de jours (durée inconnue). Les ${r.lignes - r.inconnues} séjours de durée connue ou en cours comptent dans l’occupation des lits jour par jour, et toutes les lignes comptent dans les statistiques des patients (âge, sexe, causes…). Plus vous saisissez de pages, plus la part « dans la période » grandit.</div>`
}
function htmlCles({ d, lits }) {
  const t = d.lignes.at(-1), sx = statsSerie(d.presents)
  return `${alertePeriode(d)}${d.reglages?.trouFinal ? alerteTrous({ reglages: { ...d.reglages, trous: [d.reglages.trouFinal] } }) : ''}<div class="grid g4" style="margin-top:12px">
    ${kpi('Taux d’occupation moyen', lits ? `${aff(t.tom)}<small> %</small>` : '—', lits ? `entre ${aff(t.tomBas)} et ${aff(t.tomHaut)} %` : 'indiquez le nombre de lits')}
    ${kpi('Enfants présents (moyenne)', aff(arrondi(t.JH / Math.max(1, t.J))), `écart-type ${aff(arrondi(sx.s))} · maximum ${Math.round(t.max)}`)}
    ${kpi('Admissions par jour', aff(arrondi(t.adm / Math.max(1, t.J))), `${t.adm} admissions en ${t.J} jours`)}
    ${kpi('Durée moyenne de séjour', `${aff(t.dms)}<small> nuits</small>`, `sur ${Math.round(t.ns)} séjours terminés dans la période`)}
    ${kpi('Journées d’hospitalisation', Math.round(t.JH), `en ${t.J} jours`)}
    ${kpi('Jours en sureffectif', lits ? t.sur : '—', 'plus d’enfants que de lits')}
    ${kpi('Rotation des lits', aff(t.rot), 'patients par lit')}
    ${kpi('Intervalle de rotation', `${aff(t.inter)}<small> j</small>`, 'lit vide entre deux patients')}
  </div>${htmlRepartition(d)}`
}
function htmlQualite({ st }) {
  const pct = (k) => (st.n ? arrondi(100 * (st.issues[k] ?? 0) / st.n) : null)
  const transf = Object.values(st.parMois).reduce((a, s) => a + s.transf, 0), moins5 = (st.ages['0 – 11 mois'].M + st.ages['0 – 11 mois'].F + st.ages['12 – 59 mois'].M + st.ages['12 – 59 mois'].F)
  const totAge = Object.values(st.ages).reduce((a, s) => a + s.M + s.F, 0), G = Object.values(st.ages).reduce((a, s) => a + s.M, 0), F = Object.values(st.ages).reduce((a, s) => a + s.F, 0)
  return `<div class="grid g4">
    ${kpi('Décès', `${st.issues['Décès'] ?? 0}`, `${aff(pct('Décès'))} % des séjours`)}
    ${kpi('Sorties contre avis (SCAM)', `${st.issues['Sortie contre avis (SCAM)'] ?? 0}`, `${aff(pct('Sortie contre avis (SCAM)'))} % des séjours`)}
    ${kpi('Référés / transférés', `${st.issues['Référé / transféré'] ?? 0}`, `${aff(pct('Référé / transféré'))} % des séjours`)}
    ${kpi('Mises en observation (MEO)', `${st.issues['Mise en observation (MEO)'] ?? 0}`, `${aff(pct('Mise en observation (MEO)'))} % des séjours`)}
    ${kpi('Transfusions', transf, `${st.n ? aff(arrondi(100 * transf / st.n)) : '—'} % des enfants`)}
    ${kpi('Âge médian', st.ageMedian === null ? '—' : st.ageMedian < 24 ? `${Math.round(st.ageMedian)}<small> mois</small>` : `${arrondi(st.ageMedian / 12)}<small> ans</small>`, 'la moitié des enfants est plus jeune')}
    ${kpi('Moins de 5 ans', `${totAge ? Math.round(100 * moins5 / totAge) : 0}<small> %</small>`, `${moins5} enfants`)}
    ${kpi('Garçons / filles', `${G} / ${F}`, `${F ? arrondi(G / F, 2) : '—'} garçon(s) par fille`)}
  </div>`
}
function rendreCourbe(c, W, H) {
  const o = c.opts, sc = serieChoisie(c, o.serie), x = sc.x, series = [], bandes = [], refs = []
  if (o.bol) { const m = moyenneMobile(x, 30), s = ecartMobile(x, 30); bandes.push({ nom: '± 2 écarts-types (30 j)', bas: m.map((v, i) => (v === null ? null : v - 2 * s[i])), haut: m.map((v, i) => (v === null ? null : v + 2 * s[i])), couleur: COUL.violet, opacite: 0.10 }) }
  if (o.minmax) bandes.push({ nom: 'min – max 7 j', bas: minMobile(x, 7), haut: maxMobile(x, 7), couleur: COUL.cyan, opacite: 0.14 })
  if (o.fourchette && sc.bas) bandes.push({ nom: 'Fourchette', bas: sc.bas, haut: sc.haut, couleur: COUL.bleu, opacite: 0.18 })
  series.push({ nom: sc.nom, valeurs: x, couleur: COUL.bleu, epaisseur: 1.3 })
  if (o.mm7) series.push({ nom: 'Moyenne mobile 7 j', valeurs: moyenneMobile(x, 7), couleur: COUL.orange, epaisseur: 2.2 })
  if (o.mm30) series.push({ nom: 'Moyenne mobile 30 j', valeurs: moyenneMobile(x, 30), couleur: COUL.rouge, epaisseur: 2.4 })
  if (o.med7) series.push({ nom: 'Médiane mobile 7 j', valeurs: medianeMobile(x, 7), couleur: COUL.vert, epaisseur: 2, pointille: '4 3' })
  if (o.tend) series.push({ nom: 'Tendance', valeurs: tendance(x).valeurs, couleur: COUL.noir, epaisseur: 1.6, pointille: '8 5' })
  if (o.cap && sc.cap) refs.push({ nom: sc.unite ? 'plein 100 %' : `${c.lits} lits`, valeur: sc.cap, couleur: COUL.rouge })
  const st = statsSerie(x), u = sc.unite
  return {
    options: `<select class="input ind-serie">${SERIES_CHOIX.filter(([k]) => k !== 'taux' || c.lits).map(([k, l]) => `<option value="${k}" ${o.serie === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
      ${OPTIONS_SERIES.map(([k, l]) => `<label class="ind-case"><input type="checkbox" data-opt="${k}" ${o[k] ? 'checked' : ''}>${l}</label>`).join('')}`,
    avant: bandeauStats([['Moyenne', aff(arrondi(st.m)) + u], ['Écart-type', aff(arrondi(st.s)) + u], ['Coef. de variation', aff(arrondi(st.cv)) + ' %'], ['Min', aff(arrondi(st.min)) + u], ['Max', aff(arrondi(st.max)) + u],
      ['Tendance', `${st.pente >= 0 ? '+' : ''}${aff(arrondi(st.pente, 2))}${u} / mois`], ['Autocorr. J−1', aff(arrondi(st.a1, 2))], ['Autocorr. J−7', aff(arrondi(st.a7, 2))]]),
    html: lignesSvg({ W, H, debutNum: c.d.debutNum, series, bandes, refs, titreY: sc.nom + (u ? ' (%)' : ''), suffixe: u, calendrier: !!o.cal }),
    survol: { serie: x, nom: sc.nom, unite: u },
    lecture: `la courbe bleue fine est la valeur de chaque jour (${sc.nom.toLowerCase()}) ; changez la série dans la liste. Cochez des repères :
      <b>moyennes mobiles</b> (moyenne des 7 ou 30 derniers jours : elles lissent les variations et montrent l’évolution réelle), <b>médiane mobile</b> (moins sensible à un jour exceptionnel),
      <b>tendance</b> (droite qui résume la hausse ou la baisse ; sa pente par mois est en haut), <b>bande ± 2 écarts-types</b> (95 % des jours tombent dedans : un jour hors de la bande est inhabituel),
      <b>min – max 7 j</b> (amplitude de la semaine), <b>fourchette</b> (incertitude des sorties non écrites), <b>jours fériés</b> (traits rouges) et <b>vacances scolaires</b> (fond vert) du Cameroun. <b>Autocorrélation J−1</b> proche de 1 : la valeur d’aujourd’hui ressemble à celle d’hier, ce qui rend la prévision possible.
      Passez la souris sur la courbe pour lire un jour précis.` }
}
function rendreAdmissions(c, W, H) {
  const x = c.d.adm, n = x.length, m = x.reduce((a, b) => a + b, 0) / Math.max(1, n), v = x.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(1, n)
  return { avant: bandeauStats([['Moyenne par jour', aff(arrondi(m))], ['Écart-type', aff(arrondi(Math.sqrt(v)))], ['Indice de dispersion (variance ÷ moyenne)', aff(arrondi(m ? v / m : null, 2))], ['Jours sans admission', x.filter((e) => e === 0).length], ['Maximum en un jour', Math.max(0, ...x)]]),
    html: lignesSvg({ W, H, debutNum: c.d.debutNum, calendrier: !!c.opts.cal, barres: { nom: 'Admissions du jour', valeurs: x, couleur: COUL.bleu }, series: [{ nom: 'Moyenne mobile 7 j', valeurs: moyenneMobile(x, 7), couleur: COUL.orange, epaisseur: 2.2 }, { nom: 'Moyenne mobile 30 j', valeurs: moyenneMobile(x, 30), couleur: COUL.rouge, epaisseur: 2.2 }], titreY: 'Admissions par jour' }),
    survol: { serie: x, nom: 'Admissions', unite: '' },
    lecture: `chaque barre est le nombre d’enfants admis ce jour-là ; les courbes sont les moyennes mobiles sur 7 et 30 jours. L’<b>indice de dispersion</b> compare la variance à la moyenne : proche de 1, les arrivées se font « au hasard » (loi de Poisson, hypothèse des modèles de files d’attente comme Erlang) ; nettement au-dessus de 1, il y a des jours de rush (épidémies, week-ends).` }
}
function rendreHebdo(c) {
  const x = c.d.presents, s = [[], [], [], [], [], [], []]
  x.forEach((v, i) => s[jourSemaine(c.d.debutNum + i)].push(c.lits ? 100 * v / (c.d.litsJour?.[i] ?? c.lits) : v))
  const m = s.map((a) => (a.length ? a.reduce((p, q) => p + q, 0) / a.length : null)), e = s.map((a, j) => (a.length ? Math.sqrt(a.reduce((p, q) => p + (q - m[j]) ** 2, 0) / a.length) : null))
  return { html: barresSvg({ W: c.W, H: c.H, categories: JOURS_SEMAINE, series: [{ nom: c.lits ? 'Taux d’occupation moyen' : 'Enfants présents (moyenne)', valeurs: m, couleur: COUL.bleu }], erreurs: m.map((v, j) => ({ bas: v === null ? null : v - e[j], haut: v === null ? null : v + e[j] })), titreY: c.lits ? 'Taux d’occupation (%)' : 'Enfants présents', suffixe: c.lits ? ' %' : '' }),
    lecture: `l’occupation moyenne selon le jour de la semaine ; le trait noir montre la dispersion (± 1 écart-type). Un jour nettement différent (souvent le week-end, moins de sorties signées) explique pourquoi le modèle de prévision tient compte du jour de la semaine.` }
}
function rendreDecomposition(c, W, H) {
  const dc = decomposition(c.d.presents, c.d.debutNum), h = Math.floor(H / 3)
  const bloc = (titre, valeurs, couleur) => lignesSvg({ W, H: h, debutNum: c.d.debutNum, series: [{ nom: titre, valeurs, couleur, epaisseur: 1.6 }], titreY: '' })
  return { html: `${bloc('Tendance (moyenne mobile centrée 7 j)', dc.tend, COUL.rouge)}${bloc('Saisonnalité hebdomadaire', dc.saison, COUL.vert)}${bloc('Résidu (les imprévus)', dc.residu, COUL.gris)}`,
    avant: bandeauStats(JOURS_SEMAINE.map((j, k) => [j, `${dc.profil[k] >= 0 ? '+' : ''}${aff(arrondi(dc.profil[k]))}`])),
    lecture: `l’occupation est découpée en trois morceaux qui, additionnés, la redonnent : <b>tendance</b> (l’évolution de fond), <b>saisonnalité hebdomadaire</b> (ce qui revient chaque semaine ; les valeurs en haut disent de combien d’enfants chaque jour est au-dessus ou en dessous de la tendance) et <b>résidu</b> (les imprévus). Un résidu petit et sans motif signifie que tendance + jour de la semaine expliquent l’essentiel.` }
}
function rendreAcf(c, W, H) {
  const x = c.d.presents, k = Math.max(1, Math.min(28, x.length - 2)), acf = autocorrelation(x, k).slice(1), seuil = 1.96 / Math.sqrt(x.length)
  return { html: barresZeroSvg({ W, H, valeurs: acf, etiquettes: acf.map((_, i) => `${i + 1}`), seuil, titreY: 'Autocorrélation' }),
    lecture: `chaque barre (retard k = 1, 2, … jours) dit à quel point l’occupation d’un jour <b>ressemble à celle d’il y a k jours</b> (1 = identique, 0 = aucun lien, négatif = opposé). Des barres qui baissent lentement : forte « mémoire », d’où les 7 derniers jours utilisés par le modèle. Un pic à 7, 14, 21 j : rythme hebdomadaire. Seules les barres colorées, hors de la bande orange (± 1,96/√n), sont significatives.` }
}
function rendrePacf(c, W, H) {
  const x = c.d.presents, k = Math.max(1, Math.min(21, x.length - 2)), p = autocorrelationPartielle(x, k).slice(1), seuil = 1.96 / Math.sqrt(x.length)
  return { html: barresZeroSvg({ W, H, valeurs: p, etiquettes: p.map((_, i) => `${i + 1}`), seuil, couleur: COUL.violet, titreY: 'Autocorr. partielle' }),
    lecture: `l’<b>effet propre</b> du jour J−k, une fois les jours plus proches pris en compte (récursion de Durbin-Levinson). Les retards hors de la bande orange apportent une information nouvelle : c’est un argument pour choisir combien de jours passés donner au modèle, et l’ordre p d’un modèle AR (la PACF « se coupe » après p).` }
}
function rendreTom(c) {
  if (!c.lits) return { html: '<div class="alert warn" style="display:block">Indiquez le nombre de lits du service (en haut) pour calculer le taux d’occupation.</div>', lecture: 'le taux d’occupation a besoin du nombre de lits.' }
  const L = c.d.lignes.filter((l) => l.periode !== 'Total')
  return { html: barresSvg({ W: c.W, H: c.H, categories: L.map((l) => etiquettePeriode(l.periode)), series: [{ nom: 'Taux d’occupation moyen', valeurs: L.map((l) => l.tom), couleur: COUL.bleu }], erreurs: L.map((l) => ({ bas: l.tomBas, haut: l.tomHaut })), titreY: 'Taux d’occupation (%)', suffixe: ' %', refs: [{ nom: 'tendu 85 %', valeur: 85, couleur: COUL.orange }, { nom: 'plein 100 %', valeur: 100, couleur: COUL.rouge }] }),
    lecture: `une barre par ${uniteParNom(c.par)} : le pourcentage des lits occupés en moyenne. Le trait noir est la <b>fourchette</b> due aux sorties non écrites. Au-dessus de 85 % le service est tendu ; au-dessus de 100 % il déborde.` }
}
function rendreOccMax(c) {
  const L = c.d.lignes.filter((l) => l.periode !== 'Total')
  return { html: barresSvg({ W: c.W, H: c.H, categories: L.map((l) => etiquettePeriode(l.periode)), series: [{ nom: 'Moyenne', valeurs: L.map((l) => arrondi(l.JH / Math.max(1, l.J))), couleur: COUL.bleu }, { nom: 'Maximum', valeurs: L.map((l) => Math.round(l.max)), couleur: COUL.rouge }], titreY: 'Enfants présents', refs: c.lits ? [{ nom: `${c.lits} lits`, valeur: c.lits, couleur: COUL.noir }] : [] }),
    lecture: `pour chaque période, le nombre moyen d’enfants présents (bleu) et le jour le plus chargé (rouge). Un maximum au-dessus de la capacité alors que la moyenne est basse signale des pics courts : c’est eux que la prévision doit anticiper.` }
}
function rendreNiveaux(c) {
  if (!c.lits) return { html: '<div class="alert warn" style="display:block">Indiquez le nombre de lits pour voir cette répartition.</div>', lecture: 'il faut le nombre de lits.' }
  const cl = ['moins de 50 %', '50 – 70 %', '70 – 85 %', '85 – 100 %', 'plus de 100 %'], n = [0, 0, 0, 0, 0]
  for (const [i, v] of c.d.presents.entries()) { const t = 100 * v / (c.d.litsJour?.[i] ?? c.lits); n[t < 50 ? 0 : t < 70 ? 1 : t < 85 ? 2 : t <= 100 ? 3 : 4]++ }
  return { html: barresSvg({ W: c.W, H: c.H, categories: cl, series: [{ nom: 'Jours', valeurs: n, couleur: COUL.vert }], titreY: 'Nombre de jours' }),
    lecture: `combien de jours le service a été peu rempli, normalement rempli, tendu (85 – 100 %) ou en sureffectif (plus de 100 %). C’est plus parlant qu’une moyenne : un service à 75 % en moyenne peut passer beaucoup de jours au-dessus de 100 %.` }
}
function rendreFlux(c) {
  const L = c.d.lignes.filter((l) => l.periode !== 'Total')
  return { html: barresSvg({ W: c.W, H: c.H, categories: L.map((l) => etiquettePeriode(l.periode)), series: [{ nom: 'Admissions', valeurs: L.map((l) => l.adm), couleur: COUL.bleu }, { nom: 'Sorties', valeurs: L.map((l) => Math.round(l.ns)), couleur: COUL.orange }], titreY: 'Nombre d’enfants' }),
    lecture: `entrées (bleu) et sorties (orange) par ${uniteParNom(c.par)}. Quand les admissions dépassent les sorties, l’occupation monte ; l’inverse la fait baisser. Un mois avec très peu d’admissions signale souvent des pages manquantes.` }
}
function rendreDurees(c, W, H) {
  const cl = ['0', '1', '2', '3', '4', '5', '6', '7', '8–10', '11–14', '15 et +'], dist = new Array(cl.length).fill(0)
  for (const s of c.d.sorties) { const n = s.nuits; dist[n <= 7 ? n : n <= 10 ? 8 : n <= 14 ? 9 : 10] += s.poids }
  const tri = c.d.sorties.map((s) => s.nuits).sort((a, b) => a - b), q = (p) => (tri.length ? tri[Math.floor(p * (tri.length - 1))] : null)
  return { avant: bandeauStats([['Médiane', `${aff(q(0.5))} nuits`], ['Moyenne (DMS)', `${aff(c.d.lignes.at(-1).dms)} nuits`], ['25 % durent moins de', `${aff(q(0.25))} nuits`], ['75 % durent moins de', `${aff(q(0.75))} nuits`], ['90 % durent moins de', `${aff(q(0.9))} nuits`], ['Plus long séjour', `${aff(tri.at(-1))} nuits`]]),
    html: barresSvg({ W, H, categories: cl.map((x) => `${x} n.`), series: [{ nom: 'Séjours', valeurs: dist.map((x) => Math.round(x)), couleur: COUL.vert }], titreY: 'Séjours terminés dans la période' }) + htmlRepartition(c.d),
    lecture: `combien de séjours ont duré 0 nuit (entrée et sortie le même jour), 1 nuit, 2 nuits… La plupart sont courts ; la queue à droite (longs séjours) pèse lourd dans l’occupation. La <b>moyenne</b> est plus haute que la <b>médiane</b> à cause de ces longs séjours. Les quartiles (25 %, 75 %) disent entre quelles durées se trouve la moitié des séjours.` }
}
function rendreDmsMois(c) {
  const L = c.d.lignes.filter((l) => l.periode !== 'Total')
  return { html: barresSvg({ W: c.W, H: c.H, categories: L.map((l) => etiquettePeriode(l.periode)), series: [{ nom: 'DMS', valeurs: L.map((l) => l.dms), couleur: COUL.violet }], titreY: 'Nuits en moyenne' }),
    lecture: `durée moyenne des séjours terminés chaque ${uniteParNom(c.par)}. Une DMS qui monte, à admissions égales, fait monter l’occupation : c’est l’autre moteur de la charge en lits avec le nombre d’admissions (loi de Little : présents ≈ admissions par jour × durée moyenne).` }
}
const ORDRE_AGES = ['0 – 11 mois', '12 – 59 mois', '5 – 14 ans', '15 ans et plus', 'Âge non lisible']
function rendreDmsGroupe(c, W, type) {
  const g = {}
  for (const s of c.d.sorties) { const k = type === 'cause' ? causeDe(s.l) : trancheAge(s.l) ?? 'Âge non lisible'; (g[k] ??= []).push(s) }
  const items = Object.entries(g).map(([label, l]) => {
    const n = Math.round(l.reduce((a, b) => a + b.poids, 0)), m = arrondi(moyennePonderee(l))
    return { label, valeur: m, pale: n < 5, texte: `${aff(m)} nuit${m >= 2 ? 's' : ''} en moyenne <tspan fill="#757b85" font-weight="400">· ${n} enfant${n > 1 ? 's' : ''}${n < 5 ? ' (trop peu)' : ''}</tspan>` }
  }).sort((a, b) => (type === 'age' ? ORDRE_AGES.indexOf(a.label) - ORDRE_AGES.indexOf(b.label) : b.valeur - a.valeur))
  const commun = `Chaque barre = la <b>durée moyenne de séjour</b> (en nuits passées à l’hôpital) des enfants de ce groupe ; le nombre après le point est le <b>nombre d’enfants</b> sur lequel la moyenne est calculée. Seuls comptent les séjours <b>terminés pendant la période de calcul de l’occupation</b> (du ${fmtDate(c.d.debut)} au ${fmtDate(c.d.fin)}). Une barre <b>pâle</b> repose sur moins de 5 enfants : sa moyenne n’est pas fiable (un seul long séjour suffit à la gonfler).`
  return { html: barresHorizSvg({ W, items, couleur: COUL.violet }),
    lecture: type === 'cause' ? `${commun} Les causes à la fois longues et fréquentes (voir Patients) occupent le plus de lits.` : `${commun} Exemple : « 2,6 nuits en moyenne · 49 enfants » veut dire que les 49 enfants de 1 à 4 ans sortis pendant la période sont restés en moyenne 2,6 nuits. Pour une vue sur toutes les lignes saisies (pas seulement la période), voir Patients → « Durée moyenne de séjour selon l’âge ».` }
}
function rendreAges(c) {
  const a = Object.keys(c.st.ages)
  return { html: barresSvg({ W: c.W, H: c.H, categories: a, series: [{ nom: 'Garçons', valeurs: a.map((k) => c.st.ages[k].M), couleur: COUL.bleu }, { nom: 'Filles', valeurs: a.map((k) => c.st.ages[k].F), couleur: COUL.orange }], titreY: 'Nombre d’enfants' }),
    lecture: `les enfants hospitalisés par tranche d’âge (les mêmes que le récapitulatif mensuel du registre), garçons en bleu, filles en orange. Les moins de 5 ans sont en général les plus nombreux et les plus fragiles.` }
}
function htmlRecap({ st }) {
  const mois = Object.keys(st.parMois).sort()
  return `<div class="table-wrap"><table class="table" style="font-size:13px"><thead><tr><th>Mois</th><th class="num">Malades</th><th class="num">Garçons</th><th class="num">Filles</th><th class="num">0–11 mois</th><th class="num">12–59 mois</th><th class="num">5–14 ans</th><th class="num">MEO</th><th class="num">SCAM</th><th class="num">Référés</th><th class="num">Décès</th><th class="num">Transfusions</th></tr></thead>
    <tbody>${mois.map((m) => { const s = st.parMois[m]; return `<tr style="cursor:default"><td>${m.split('-').reverse().join('/')}</td><td class="num">${s.malades}</td><td class="num">${s.M}</td><td class="num">${s.F}</td><td class="num">${s.t0}</td><td class="num">${s.t1}</td><td class="num">${s.t2}</td><td class="num">${s.meo}</td><td class="num">${s.scam}</td><td class="num">${s.ref}</td><td class="num">${s.dcd}</td><td class="num">${s.transf}</td></tr>` }).join('')}</tbody></table></div>`
}
function htmlTable({ d }) {
  return `<div class="table-wrap"><table class="table" style="font-size:13px"><thead><tr><th>Période</th><th class="num">Jours</th><th class="num">Admissions</th><th class="num">Sorties</th><th class="num">Journées d’hosp.</th><th class="num">TOM %</th><th class="num">TOM bas %</th><th class="num">TOM haut %</th><th class="num">Occup. max</th><th class="num">Sureffectif (j)</th><th class="num">DMS (nuits)</th><th class="num">Rotation</th><th class="num">Interv. rotation (j)</th><th class="num">Décès</th><th class="num">Mortalité %</th></tr></thead>
    <tbody>${d.lignes.map((l) => `<tr style="cursor:default;${l.periode === 'Total' ? 'font-weight:700;background:var(--surface-2)' : ''}"><td>${etiquettePeriode(l.periode)}</td><td class="num">${l.J}</td><td class="num">${l.adm}</td><td class="num">${Math.round(l.ns)}</td><td class="num">${Math.round(l.JH)}</td><td class="num" style="${l.tom > 100 ? 'color:var(--sev-1-ink);font-weight:700' : ''}">${aff(l.tom)}</td><td class="num">${aff(l.tomBas)}</td><td class="num">${aff(l.tomHaut)}</td><td class="num">${Math.round(l.max)}</td><td class="num">${l.sur}</td><td class="num">${aff(l.dms)}</td><td class="num">${aff(l.rot)}</td><td class="num">${aff(l.inter)}</td><td class="num">${Math.round(l.dc)}</td><td class="num">${aff(l.mort)}</td></tr>`).join('')}</tbody></table></div>`
}
// ── Loi de Little et file d'attente (mêmes formules que nera/garde_fous.py) ──────────────
// Erlang B (système M/M/c/c) : B(0) = 1, B(k) = a·B(k−1) / (k + a·B(k−1)), a = λ × W la charge en lits.
const erlangB = (c, a) => { let b = 1; for (let k = 1; k <= c; k++) b = a * b / (k + a * b); return b }
const litsPour = (a, cible) => { let c = 0; while (erlangB(c, a) > cible && c < 500) c++; return c }
function rendreFileAttente(c) {
  const { d, lits } = c, L = d.lignes
  const ligne = (x) => {
    const lam = x.J ? x.adm / x.J : null, Lm = x.J ? x.JH / x.J : null, W = x.wComptage ?? x.dms, lw = lam !== null && W ? lam * W : null
    const ecart = lw ? 100 * (Lm - lw) / lw : null, a = Lm   // charge offerte : la présence moyenne mesurée (= λW si Little tient)
    return `<tr style="cursor:default"><td>${x.periode === 'Total' ? '<b>Total</b>' : etiquettePeriode(x.periode)}</td>
      <td class="num">${aff(arrondi(lam, 2))}</td><td class="num">${aff(W)}</td><td class="num">${aff(arrondi(lw, 1))}</td><td class="num">${aff(arrondi(Lm, 1))}</td>
      <td class="num" style="color:${ecart === null ? 'inherit' : Math.abs(ecart) <= 10 ? COUL.vert : Math.abs(ecart) <= 25 ? COUL.orange : COUL.rouge}">${ecart === null ? '—' : `${ecart > 0 ? '+' : ''}${arrondi(ecart, 0)} %`}</td>
      <td class="num">${lits && a !== null ? `${aff(arrondi(100 * erlangB(lits, a), 1))} %` : '—'}</td><td class="num">${x.J ? `${arrondi(100 * x.sur / x.J, 0)} %` : '—'}</td>
      <td class="num">${a !== null ? litsPour(a, 0.05) : '—'}</td><td class="num">${a !== null ? litsPour(a, 0.01) : '—'}</td></tr>`
  }
  const tot = L.at(-1), aT = tot.J ? tot.JH / tot.J : 0, pire = L.slice(0, -1).reduce((m, x) => (x.J >= 10 && x.JH / x.J > (m?.JH / m?.J || 0) ? x : m), null)
  return { html: `<div class="table-wrap"><table class="table" style="font-size:13px"><thead><tr><th>Période</th><th class="num">λ admissions / jour</th><th class="num">W durée (nuits)</th><th class="num">λ × W</th><th class="num">L présents mesurés</th><th class="num">Écart de Little</th>
      <th class="num">Erlang B : saturation prévue${lits ? ` (${lits} lits)` : ''}</th><th class="num">Jours en sureffectif observés</th><th class="num">Lits pour ≤ 5 %</th><th class="num">Lits pour ≤ 1 %</th></tr></thead>
      <tbody>${L.map(ligne).join('')}</tbody></table></div>
    <div class="alert info" style="display:block;margin-top:10px;font-size:12.8px;line-height:1.55">Sur toute la période, la charge moyenne est de <b>${aff(arrondi(aT, 1))} lits</b> : ${litsPour(aT, 0.05)} lits suffisent pour être saturé moins de 5 % du temps, ${litsPour(aT, 0.01)} pour moins de 1 %.
      ${pire ? `Mais le mois le plus chargé (<b>${etiquettePeriode(pire.periode)}</b>, ${aff(arrondi(pire.JH / pire.J, 1))} lits en moyenne) en demande <b>${litsPour(pire.JH / pire.J, 0.05)}</b> pour ≤ 5 % et <b>${litsPour(pire.JH / pire.J, 0.01)}</b> pour ≤ 1 % : on dimensionne sur les pics, pas sur la moyenne.` : ''}</div>`,
    lecture: `<b>Loi de Little</b> : dans tout service stable, présents moyens L = admissions par jour λ × durée moyenne W. Elle ne dépend d’aucune hypothèse sur la forme des arrivées ou des durées. Un écart de plus de 10 % (orange, rouge au-delà de 25 %) signale un problème de données : pages manquantes (λ trop bas), doublons, sorties mal lues, durées estimées, ou un mois coupé (effet de bord : enfants entrés le mois d’avant). <b>Erlang B</b> (file d’attente M/M/c/c, c = lits) donne la probabilité qu’un enfant arrive quand tous les lits sont pris, pour une charge a = λW. Ici a est la présence moyenne mesurée. Comme le service ajoute des lits au lieu de refuser, comparez la saturation prévue aux jours en sureffectif réellement observés : s’ils sont plus nombreux, les arrivées sont plus groupées que le hasard (épidémies de paludisme, saisons). Les deux dernières colonnes donnent le nombre de lits qui ramènerait la saturation à 5 % ou 1 %.` }
}
function htmlCauses({ d, st }) {
  const g = {}
  for (const x of lignesService()) { const k = causeDe(x); const s = (g[k] ??= { n: 0, dcd: 0, scam: 0, ref: 0, sorties: [] }); s.n++; const i = issueDe(x); if (i === 'Décès') s.dcd++; if (i.startsWith('Sortie contre')) s.scam++; if (i.startsWith('Référé')) s.ref++ }
  for (const s of d.sorties ?? []) (g[causeDe(s.l)] ??= { n: 0, dcd: 0, scam: 0, ref: 0, sorties: [] }).sorties.push(s)
  return `<div class="table-wrap"><table class="table" style="font-size:13px"><thead><tr><th>Cause</th><th class="num">Enfants</th><th class="num">% du total</th><th class="num">DMS (nuits)</th><th class="num">Décès</th><th class="num">SCAM</th><th class="num">Référés</th></tr></thead>
    <tbody>${Object.entries(g).sort((a, b) => b[1].n - a[1].n).map(([k, s]) => `<tr style="cursor:default"><td>${echapper(k)}</td><td class="num">${s.n}</td><td class="num">${st.n ? arrondi(100 * s.n / st.n) : '—'}</td><td class="num">${aff(arrondi(moyennePonderee(s.sorties), 2))}</td><td class="num">${s.dcd}</td><td class="num">${s.scam}</td><td class="num">${s.ref}</td></tr>`).join('')}</tbody></table></div>`
}


// ════════════════════════════════════════════════════════════════════════════════════════
// STATISTIQUES DU DATA SCIENTIST — tout est calculé à la main par statistiques.js (window.Stat)
// ════════════════════════════════════════════════════════════════════════════════════════
const Sx = window.Stat
const nf = (v, k = 2) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : v.toLocaleString('fr-FR', { maximumFractionDigits: k }))
const fp = (p) => (!Number.isFinite(p) ? '—' : p < 0.001 ? '< 0,001' : nf(p, 3))
const etoiles = (p) => (!Number.isFinite(p) ? '' : p < 0.001 ? '***' : p < 0.01 ? '**' : p < 0.05 ? '*' : '')
const badge = (ok, oui, non) => `<span class="ind-badge ${ok === null ? 'neutre' : ok ? 'oui' : 'non'}">${ok === null ? '—' : ok ? oui : non}</span>`
const forceLien = (r) => { const a = Math.abs(r); return !Number.isFinite(a) ? '—' : a < 0.1 ? 'négligeable' : a < 0.3 ? 'faible' : a < 0.5 ? 'modéré' : a < 0.7 ? 'fort' : 'très fort' }
function tableau(entetes, lignes, { gras = () => false, hauteur } = {}) {
  return `<div class="table-wrap" ${hauteur ? `style="max-height:${hauteur}px"` : ''}><table class="table"><thead><tr>${entetes.map((e, i) => `<th class="${i ? 'num' : ''}">${e}</th>`).join('')}</tr></thead>
    <tbody>${lignes.map((l, k) => `<tr style="cursor:default;${gras(k) ? 'font-weight:700;background:var(--brand-soft)' : ''}">${l.map((v, i) => `<td class="${i ? 'num' : ''}">${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`
}
const choix = (cle, valeur, options, attrs = '') => `<select class="input" data-o="${cle}" ${attrs}>${options.map(([k, l]) => `<option value="${k}" ${String(valeur) === String(k) ? 'selected' : ''}>${l}</option>`).join('')}</select>`
const libelle = (t, html) => `<label class="ind-case" style="cursor:default">${t} ${html}</label>`
// IC 95 % de la moyenne ; borne basse ramenée à 0 pour une variable qui ne peut pas être négative (durée, âge, effectif).
const icTexte = (d) => `${nf(d.min >= 0 ? Math.max(0, d.icBas) : d.icBas)} – ${nf(d.icHaut)}`
const vide = (t) => `<div class="ind-vide">${t}</div>`

// ── Variables extraites des lignes saisies ───────────────────────────────────────────────
const nombre = (t) => { const m = String(t ?? '').replace(/\s/g, '').replace(',', '.').match(/-?\d+(?:\.\d+)?/); return m ? parseFloat(m[0]) : null }
const binaire = (v, oui, non) => (oui.test(v ?? '') ? 1 : non.test(v ?? '') ? 0 : null)
const aCol = (k) => colonnes().some((c) => c.k === k)
const RE_EXAMENS = /nfs|crp|\bbu\b|\bge\b|tdr|atb|lcr|gs|rx|eeg|[ée]cho|iono|ur[ée]e|cr[ée]at|glyc|\bhb\b|widal|ecbu|copro|vs\b|ts\b/gi
function lignesPeriode() {
  const r = registre(), cfgV = CONFIG.dateVerrou ? lireDate(CONFIG.dateVerrou.split('-').reverse().join('/')) : null, verrou = cfgV ? jourNum(cfgV.d) : Infinity
  return lignesService().map((l) => ({ l, d: lireDate(l[r.dateReference] || l.date_entree || '') }))
    .filter((x) => x.d && jourNum(x.d.d) < verrou).map((x) => ({ l: x.l, j: jourNum(x.d.d) }))
}
function dureeEcrite(l) {
  const e = lireDate(l.date_entree || l.date_enregistrement || ''), s = lireDate(l.date_sortie || '')
  if (e && s) { const v = jourNum(s.d) - jourNum(e.d); return v >= 0 && v < 365 ? v : null }
  const n = nombre(l.nb_jours); return n !== null && n >= 0 && n < 365 ? n : null
}
const issueUrg = (l) => { const t = String(l.decision ?? '').toLowerCase(); return !t.trim() ? null : /d[ée]c[ée]d/.test(t) ? 'Décédé' : /r[ée]f[ée]r/.test(t) ? 'Référé' : /scam/.test(t) ? 'SCAM' : /hospit/.test(t) ? 'Hospitalisé' : /meo|observ/.test(t) ? 'MEO' : /extern/.test(t) ? 'Externe' : 'Autre' }
const issueDeLigne = (l) => (aCol('decision') ? issueUrg(l) : issueDe(l) === 'Non renseignée' ? null : issueDe(l))
const TA = (l, i) => { const m = String(l.ta ?? '').match(/(\d{2,3})\s*[/\-]\s*(\d{2,3})/); return m ? +m[i] : null }
const VARS_PATIENT = [
  { k: 'age', nom: 'Âge (mois)', f: (x) => ageEnMois(x.l.age) },
  { k: 'duree', nom: 'Durée de séjour (jours écrits)', col: 'nb_jours', f: (x) => dureeEcrite(x.l) },
  { k: 'prix', nom: 'Montant payé (FCFA)', col: 'prix', f: (x) => nombre(x.l.prix) },
  { k: 'nbT3', nom: 'Médicaments reçus (nombre)', col: 't3_recu', f: (x) => (x.l.t3_recu?.trim() ? x.l.t3_recu.split(/\s*\+\s*|\s*,\s*/).filter((s) => s.trim()).length : null) },
  { k: 'nbBilan', nom: 'Examens demandés (nombre)', col: 'bilan', f: (x) => (x.l.bilan?.trim() ? (x.l.bilan.match(RE_EXAMENS) ?? []).length || 1 : null) },
  { k: 'densite', nom: 'Densité parasitaire (/µL)', col: 'ge_tdr', f: (x) => { const v = nombre(String(x.l.ge_tdr ?? '').replace(/\./g, '')); return v !== null && v >= 50 ? v : null } },
  { k: 'pouls', nom: 'Pouls (battements/min)', col: 'pouls', f: (x) => nombre(x.l.pouls) },
  { k: 'tas', nom: 'TA systolique (mmHg)', col: 'ta', f: (x) => TA(x.l, 1) },
  { k: 'tad', nom: 'TA diastolique (mmHg)', col: 'ta', f: (x) => TA(x.l, 2) },
  { k: 'glycemie', nom: 'Glycémie', col: 'glycemie', f: (x) => nombre(x.l.glycemie) },
  { k: 'poids', nom: 'Poids (kg)', col: 'poids', f: (x) => nombre(x.l.poids) },
  { k: 'temperature', nom: 'Température (°C)', col: 'temperature', f: (x) => nombre(x.l.temperature) },
  { k: 'sexe', nom: 'Garçon (1) / fille (0)', bin: true, f: (x) => binaire(x.l.sexe, /^\s*m/i, /^\s*f/i) },
  { k: 'nouveau', nom: 'Nouveau (1) / ancien (0)', bin: true, col: 'ancien_nouveau', f: (x) => binaire(x.l.ancien_nouveau, /^\s*n/i, /^\s*a/i) },
  { k: 'transf', nom: 'Transfusé (1 = oui)', bin: true, col: 't3_recu', f: (x) => (x.l.t3_recu?.trim() ? (/transfus/i.test(x.l.t3_recu) ? 1 : 0) : null) },
  { k: 'ge', nom: 'GE / TDR positif (1 = oui)', bin: true, col: 'ge_tdr', f: (x) => { const t = x.l.ge_tdr ?? ''; return /\+/.test(t) ? 1 : /−|-|n[ée]g/i.test(t) ? 0 : null } },
  { k: 'grave', nom: 'Issue défavorable (1 = oui)', bin: true, f: (x) => { const i = issueDeLigne(x.l); return i === null ? null : /D[ée]c|R[ée]f|SCAM|contre/.test(i) ? 1 : 0 } },
  { k: 'weekend', nom: 'Arrivé le week-end (1 = oui)', bin: true, f: (x) => (jourSemaine(x.j) >= 5 ? 1 : 0) },
  { k: 'ferie', nom: 'Arrivé un jour férié (1 = oui)', bin: true, f: (x) => (ferieDe(x.j) ? 1 : 0) },
  { k: 'vacances', nom: 'Arrivé pendant les vacances scolaires (1 = oui)', bin: true, f: (x) => vacancesDe(x.j) },
]
const VARS_QUALI = [
  { k: 'sexe', nom: 'Sexe', f: (x) => (/^\s*m/i.test(x.l.sexe ?? '') ? 'Garçon' : /^\s*f/i.test(x.l.sexe ?? '') ? 'Fille' : null) },
  { k: 'tranche', nom: 'Tranche d’âge', f: (x) => trancheAge(x.l) },
  { k: 'cause', nom: 'Grande cause', f: (x) => { const c = causeDe(x.l); return c === 'Non renseigné' ? null : c } },
  { k: 'issue', nom: 'Issue / décision', f: (x) => issueDeLigne(x.l) },
  { k: 'jour', nom: 'Jour d’arrivée', f: (x) => JOURS_SEMAINE[jourSemaine(x.j)] },
  { k: 'mois', nom: 'Mois d’arrivée', f: (x) => etiquettePeriode(versDate(x.j).slice(0, 7)) },
  { k: 'nouveau', nom: 'Ancien / nouveau', col: 'ancien_nouveau', f: (x) => (/^\s*n/i.test(x.l.ancien_nouveau ?? '') ? 'Nouveau' : /^\s*a/i.test(x.l.ancien_nouveau ?? '') ? 'Ancien' : null) },
  { k: 'ge', nom: 'Résultat GE / TDR', col: 'ge_tdr', f: (x) => { const t = x.l.ge_tdr ?? ''; return /\+/.test(t) ? 'Positif' : /−|-|n[ée]g/i.test(t) ? 'Négatif' : null } },
  { k: 'transf', nom: 'Transfusion', col: 't3_recu', f: (x) => (x.l.t3_recu?.trim() ? (/transfus/i.test(x.l.t3_recu) ? 'Oui' : 'Non') : null) },
  { k: 'scolaire', nom: 'Période scolaire', f: (x) => { const v = vacancesDe(x.j); return v === null ? null : v ? 'Vacances scolaires' : 'Période de classe' } },
  { k: 'quartier', nom: 'Quartier (8 plus fréquents)' },
]
function donneesPatients() {
  const L = lignesPeriode(), dispo = (v) => !v.col || aCol(v.col)
  const num = VARS_PATIENT.filter(dispo).map((v) => ({ ...v, x: L.map(v.f) }))
    .filter((v) => { const p = v.x.filter((e) => e !== null && Number.isFinite(e)); return p.length >= 8 && new Set(p).size > 1 })
  const q0 = {}; for (const x of L) { const t = quartierDe(x.l); if (t) q0[t] = (q0[t] ?? 0) + 1 }
  const top = new Set(Object.entries(q0).sort((a, b) => b[1] - a[1]).slice(0, 8).map((e) => e[0]))
  const quartier = (x) => { const t = quartierDe(x.l); return t ? (top.has(t) ? t : 'Autres quartiers') : null }
  const quali = VARS_QUALI.filter(dispo).map((v) => ({ ...v, x: L.map(v.k === 'quartier' ? quartier : v.f) })).filter((v) => new Set(v.x.filter((e) => e !== null)).size > 1)
  return { n: L.length, num, quali }
}
// Série des arrivées par jour sur toute la période saisie (existe même sans occupation : urgences).
function serieBrute() {
  const L = lignesPeriode(); if (!L.length) return null
  let j0 = Infinity, j1 = -Infinity; for (const e of L) { j0 = Math.min(j0, e.j); j1 = Math.max(j1, e.j) }
  const x = new Array(j1 - j0 + 1).fill(0); for (const e of L) x[e.j - j0]++
  return { debutNum: j0, x }
}
const decaler = (x, k) => x.map((_, i) => (i >= k && x[i - k] !== null ? x[i - k] : null))
// Variables journalières : celles de l'occupation si sa période de calcul compte au moins 21 jours ;
// sinon les arrivées par jour sur toute la période saisie (toujours disponibles dès les premières pages).
function donneesJour(c) {
  if (!c.d.message && c.d.presents.length >= 21) {
    const p = c.d.presents, a = c.d.adm, s = sortiesParJour(c.d), deb = c.d.debutNum
    return [{ k: 'presents', nom: nomPresents(true), x: p }, { k: 'adm', nom: 'Admissions du jour', x: a }, { k: 'sor', nom: 'Sorties du jour', x: s },
      ...(c.lits ? [{ k: 'taux', nom: 'Taux d’occupation (%)', x: p.map((v, i) => 100 * v / (c.d.litsJour?.[i] ?? c.lits)) }] : []),
      { k: 'p1', nom: 'Présents la veille (J−1)', x: decaler(p, 1) }, { k: 'p7', nom: 'Présents il y a 7 jours (J−7)', x: decaler(p, 7) },
      { k: 'a1', nom: 'Admissions de la veille', x: decaler(a, 1) }, { k: 'am7', nom: 'Admissions, moyenne des 7 jours précédents', x: decaler(moyenneMobile(a, 7), 1) },
      { k: 'we', nom: 'Week-end (1 = oui)', bin: true, x: p.map((_, i) => (jourSemaine(deb + i) >= 5 ? 1 : 0)) }, ...joursCalendrier(p.length, deb), { k: 't', nom: 'Temps (jours écoulés)', x: p.map((_, i) => i) }]
  }
  if (!c.brut) return []
  const a = c.brut.x, deb = c.brut.debutNum
  return [{ k: 'arr', nom: 'Arrivées du jour', x: a }, { k: 'a1', nom: 'Arrivées de la veille', x: decaler(a, 1) }, { k: 'a7', nom: 'Arrivées il y a 7 jours', x: decaler(a, 7) },
    { k: 'am7', nom: 'Arrivées, moyenne des 7 jours précédents', x: decaler(moyenneMobile(a, 7), 1) }, { k: 'we', nom: 'Week-end (1 = oui)', bin: true, x: a.map((_, i) => (jourSemaine(deb + i) >= 5 ? 1 : 0)) }, ...joursCalendrier(a.length, deb), { k: 't', nom: 'Temps (jours écoulés)', x: a.map((_, i) => i) }]
}
// Variables de calendrier par jour (connues à l'avance, comme dans le modèle Python : svr/caracteristiques.py).
const joursCalendrier = (n, deb) => [
  { k: 'fer', nom: 'Jour férié (1 = oui)', bin: true, x: Array.from({ length: n }, (_, i) => (ferieDe(deb + i) ? 1 : 0)) },
  { k: 'vac', nom: 'Vacances scolaires (1 = oui)', bin: true, x: Array.from({ length: n }, (_, i) => vacancesDe(deb + i)) },
].filter((v) => v.x.some((e) => e === 1) && v.x.some((e) => e === 0))
const variablesNiveau = (c, niv) => (niv === 'p' ? c.pat.num : c.jour)
const trouverVar = (c, code) => { const [niv, k] = String(code).split(':'); return variablesNiveau(c, niv).find((v) => v.k === k) }
const optionsNum = (c, sansBinaires) => [...c.pat.num.filter((v) => !(sansBinaires && v.bin)).map((v) => [`p:${v.k}`, `Patient · ${v.nom}`]), ...c.jour.filter((v) => !(sansBinaires && v.bin)).map((v) => [`j:${v.k}`, `Jour · ${v.nom}`])]

// ── Graphiques statistiques (SVG à la main) ───────────────────────────────────────────────
// Graduations « rondes » (pas de 1, 2, 2,5 ou 5 × 10ᵏ) comprises entre min et max.
function graduations(min, max, n = 5) {
  const brut = (max - min) / Math.max(1, n - 1) || 1, p = 10 ** Math.floor(Math.log10(brut)), pas = [1, 2, 2.5, 5, 10].map((m) => m * p).find((v) => v >= brut * 0.85) ?? 10 * p
  const res = []; for (let v = Math.ceil(min / pas - 1e-9) * pas; v <= max + 1e-9; v += pas) res.push(Math.round(v / pas) * pas)
  return res.length >= 2 ? res : [min, max]
}
const etiq = (v) => (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('fr-FR') : String(Math.round(v * 10) / 10).replace('.', ','))
function cadre({ W, H, ml = 56, mr = 14, mt = 12, mb = 40, xmin, xmax, ymin, ymax, titreX = '', titreY = '', sansX = false, sansY = false }) {
  const x = (v) => ml + (v - xmin) / ((xmax - xmin) || 1) * (W - ml - mr), y = (v) => mt + (1 - (v - ymin) / ((ymax - ymin) || 1)) * (H - mt - mb)
  const fond = `${sansY ? '' : graduations(ymin, ymax).map((g) => `<line x1="${ml}" x2="${W - mr}" y1="${y(g)}" y2="${y(g)}" stroke="#eceef1"/><text x="${ml - 6}" y="${y(g) + 4}" text-anchor="end" font-size="11" fill="#8a9099">${etiq(g)}</text>`).join('')}
    ${sansX ? '' : graduations(xmin, xmax, 6).map((g) => `<text x="${x(g)}" y="${H - mb + 16}" text-anchor="${x(g) - ml < 16 ? 'start' : W - mr - x(g) < 16 ? 'end' : 'middle'}" font-size="11" fill="#8a9099">${etiq(g)}</text>`).join('')}
    ${sansX ? '' : graduations(xmin, xmax, 6).map((g) => `<line x1="${x(g)}" x2="${x(g)}" y1="${H - mb}" y2="${H - mb + 4}" stroke="#c9cdd3"/>`).join('')}
    <line x1="${ml}" x2="${W - mr}" y1="${H - mb}" y2="${H - mb}" stroke="#c9cdd3"/>
    <text x="${(ml + W - mr) / 2}" y="${H - 6}" text-anchor="middle" font-size="11.5" fill="#5a606a">${titreX}</text>
    <text x="13" y="${(H - mb + mt) / 2}" transform="rotate(-90 13 ${(H - mb + mt) / 2})" text-anchor="middle" font-size="11.5" fill="#5a606a">${titreY}</text>`
  return { x, y, fond }
}
// Histogramme : classes de Freedman-Diaconis (h = 2·IQR·n^(−1/3)), ou une classe par entier ; courbe normale de même moyenne et écart-type.
function histogrammeSvg({ W, H, valeurs, nom, couleur = COUL.bleu }) {
  const v = valeurs.filter((e) => e !== null && Number.isFinite(e)), n = v.length; if (n < 3) return vide('Pas assez de valeurs.')
  const ds = Sx.descriptif(v), entier = v.every(Number.isInteger) && ds.etendue <= 40
  let largeur, debut, k
  if (entier) { largeur = 1; debut = ds.min - 0.5; k = ds.etendue + 1 }
  else { const h = 2 * ds.iqr * n ** (-1 / 3) || ds.etendue / 10; k = Math.min(40, Math.max(6, Math.ceil(ds.etendue / h))); largeur = ds.etendue / k || 1; debut = ds.min }
  const nb = new Array(k).fill(0); for (const e of v) nb[Math.min(k - 1, Math.floor((e - debut) / largeur))]++
  const dens = (t) => n * largeur * Math.exp(-0.5 * ((t - ds.moyenne) / ds.ecart) ** 2) / (ds.ecart * Math.sqrt(2 * Math.PI))
  const ymax = Math.max(...nb, ds.ecart ? dens(ds.moyenne) : 0) * 1.1, xmin = debut, xmax = debut + k * largeur
  const legH = lignesLegende([{ nom }, { nom: 'loi normale' }, { nom: 'moyenne 000,0' }, { nom: 'médiane 000,0' }], 56, W - 14), { x, y, fond } = cadre({ W, H, xmin, xmax, ymin: 0, ymax, mb: 38 + 17 * legH, titreY: 'Effectif' })
  const courbe = ds.ecart ? Array.from({ length: 81 }, (_, i) => { const t = xmin + i * (xmax - xmin) / 80; return `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(dens(t)).toFixed(1)}` }).join('') : ''
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${fond}
    ${nb.map((c, i) => `<rect x="${x(debut + i * largeur) + 0.5}" y="${y(c)}" width="${Math.max(1, x(debut + (i + 1) * largeur) - x(debut + i * largeur) - 1)}" height="${y(0) - y(c)}" fill="${couleur}" fill-opacity=".55"><title>${etiq(debut + i * largeur)} – ${etiq(debut + (i + 1) * largeur)} : ${c}</title></rect>`).join('')}
    <path d="${courbe}" fill="none" stroke="${COUL.rouge}" stroke-width="1.8"/>
    <line x1="${x(ds.moyenne)}" x2="${x(ds.moyenne)}" y1="12" y2="${y(0)}" stroke="${COUL.noir}" stroke-width="1.5" stroke-dasharray="5 3"/>
    <line x1="${x(ds.mediane)}" x2="${x(ds.mediane)}" y1="12" y2="${y(0)}" stroke="${COUL.vert}" stroke-width="2"/>
    ${legendeSvg([{ nom, couleur, barre: true }, { nom: 'loi normale', couleur: COUL.rouge, epaisseur: 1.8 }, { nom: `moyenne ${nf(ds.moyenne, 1)}`, couleur: COUL.noir, pointille: '5 3' }, { nom: `médiane ${nf(ds.mediane, 1)}`, couleur: COUL.vert }], 56, H - 6, W - 14)}</svg>`
}
// Boîte à moustaches : boîte Q1–Q3, trait médian, losange = moyenne, moustaches jusqu'à 1,5 IQR, points = valeurs atypiques.
function boitesSvg({ W, groupes, nom }) {
  // Une rangée de 76 px par groupe. Au-dessus de la boîte : la médiane. Sous les moustaches : min et max
  // (regroupés en « min – max » s'ils sont trop proches). Le nom et l'effectif sont à gauche, la légende en dessous.
  const g = groupes.filter((e) => e.valeurs.filter(Number.isFinite).length >= 2); if (!g.length) return ''
  const tout = g.flatMap((e) => e.valeurs.filter(Number.isFinite)), xmin0 = Math.min(...tout), xmax = Math.max(...tout), marge = (xmax - xmin0) * 0.04 || 1, xmin = xmin0 >= 0 && xmin0 - marge < 0 ? marge : xmin0
  const ml = Math.min(250, Math.max(150, W * 0.26)), mr = 22, lh = 76, H = 8 + g.length * lh + 46
  const { x, fond } = cadre({ W, H, ml, mr, xmin: xmin - marge, xmax: xmax + marge, ymin: 0, ymax: 1, mt: 8, mb: 46, titreX: nom, sansY: true })
  const borne = (v, largeur, ancre) => { const px = x(v), l = ancre === 'middle' ? largeur / 2 : largeur; return ancre === 'end' ? Math.max(ml + l, px) : ancre === 'start' ? Math.min(W - mr - l, px) : Math.min(W - mr - l, Math.max(ml + l, px)) }
  const lignes = g.map((e, i) => {
    const d = Sx.descriptif(e.valeurs), ym = 8 + i * lh + lh / 2 + 2, bas = d.q1 - 1.5 * d.iqr, haut = d.q3 + 1.5 * d.iqr, v = e.valeurs.filter(Number.isFinite)
    const mi = Math.min(...v.filter((t) => t >= bas)), ma = Math.max(...v.filter((t) => t <= haut)), atyp = v.filter((t) => t < bas || t > haut)
    const resume = `${e.nom} — n ${d.n} · min ${nf(d.min)} · Q1 ${nf(d.q1)} · médiane ${nf(d.mediane)} · moyenne ${nf(d.moyenne)} · Q3 ${nf(d.q3)} · max ${nf(d.max)} · écart-type ${nf(d.ecart)} · ${atyp.length} atypique(s)`
    const maxCar = Math.max(8, Math.floor((ml - 18) / 7.2)), court = e.nom.length > maxCar ? e.nom.slice(0, maxCar - 1) + '…' : e.nom
    const tMed = `médiane ${nf(d.mediane, 1)}`, tMi = nf(mi, 1), tMa = nf(ma, 1), proches = x(ma) - x(mi) < (tMi.length + tMa.length) * 6.4 + 14
    const bornes = proches ? `<text x="${borne((mi + ma) / 2, (tMi.length + tMa.length + 3) * 6.2, 'middle')}" y="${ym + 31}" text-anchor="middle" font-size="10.5" fill="#5a606a">${mi === ma ? tMi : `${tMi} – ${tMa}`}</text>`
      : `<text x="${borne(mi, tMi.length * 6.2, 'middle')}" y="${ym + 31}" text-anchor="middle" font-size="10.5" fill="#5a606a">${tMi}</text><text x="${borne(ma, tMa.length * 6.2, 'middle')}" y="${ym + 31}" text-anchor="middle" font-size="10.5" fill="#5a606a">${tMa}</text>`
    return `${i % 2 ? `<rect x="${ml}" y="${ym - lh / 2}" width="${W - ml - mr}" height="${lh}" fill="#f7f8fa"/>` : ''}
      <text x="${ml - 12}" y="${ym - 2}" text-anchor="end" font-size="13" font-weight="600" fill="#17181a"><title>${resume}</title>${echapper(court)}</text>
      <text x="${ml - 12}" y="${ym + 14}" text-anchor="end" font-size="11" fill="#5a606a">n = ${d.n} · Q1–Q3 : ${nf(d.q1, 1)} – ${nf(d.q3, 1)}</text>
      <line x1="${x(mi)}" x2="${x(ma)}" y1="${ym}" y2="${ym}" stroke="#3d434c" stroke-width="1.6"/>
      <line x1="${x(mi)}" x2="${x(mi)}" y1="${ym - 10}" y2="${ym + 10}" stroke="#3d434c" stroke-width="1.6"/><line x1="${x(ma)}" x2="${x(ma)}" y1="${ym - 10}" y2="${ym + 10}" stroke="#3d434c" stroke-width="1.6"/>
      <rect x="${x(d.q1)}" y="${ym - 15}" width="${Math.max(3, x(d.q3) - x(d.q1))}" height="30" rx="3" fill="${COUL.bleu}" fill-opacity=".22" stroke="${COUL.bleu}" stroke-width="1.6"><title>${resume}</title></rect>
      <line x1="${x(d.mediane)}" x2="${x(d.mediane)}" y1="${ym - 15}" y2="${ym + 15}" stroke="${COUL.bleu}" stroke-width="3.2"/>
      <path d="M${x(d.moyenne)},${ym - 7}l7,7l-7,7l-7,-7z" fill="${COUL.rouge}" stroke="#fff" stroke-width="1.2"><title>moyenne : ${nf(d.moyenne)}</title></path>
      <text x="${borne(d.mediane, tMed.length * 6.4, 'middle')}" y="${ym - 21}" text-anchor="middle" font-size="11" font-weight="700" fill="#0047d1">${tMed}</text>
      ${bornes}
      ${atyp.slice(0, 300).map((t) => `<circle cx="${x(t)}" cy="${ym}" r="4" fill="#fff" stroke="${COUL.orange}" stroke-width="1.8"><title>valeur atypique : ${nf(t)}</title></circle>`).join('')}`
  }).join('')
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${fond}${lignes}</svg>
    <div class="ind-legende"><span><i class="boite"></i>boîte : 50 % centraux (Q1 – Q3)</span><span><i class="med"></i>médiane</span><span><i class="moy"></i>moyenne</span>
      <span><i class="moust"></i>moustaches : min – max hors valeurs atypiques</span><span><i class="atyp"></i>valeur atypique (au-delà de 1,5 × IQR)</span></div>`
}
// Droite de Henry (QQ-plot) : quantiles observés centrés-réduits contre quantiles théoriques Φ⁻¹((i − ½)/n).
function qqSvg({ W, H, valeurs }) {
  const v = valeurs.filter((e) => e !== null && Number.isFinite(e)).sort((a, b) => a - b), n = v.length; if (n < 3) return ''
  const ds = Sx.descriptif(v), pts = v.map((e, i) => [Sx.qnorm((i + 0.5) / n), ds.ecart ? (e - ds.moyenne) / ds.ecart : 0])
  const lim = Math.max(3, ...pts.map((p) => Math.abs(p[1]))) * 1.05
  const { x, y, fond } = cadre({ W, H, xmin: -lim, xmax: lim, ymin: -lim, ymax: lim, titreX: 'Quantile théorique (loi normale)', titreY: 'Valeur centrée réduite' })
  const pas = Math.max(1, Math.floor(n / 600))
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${fond}<line x1="${x(-lim)}" y1="${y(-lim)}" x2="${x(lim)}" y2="${y(lim)}" stroke="${COUL.rouge}" stroke-width="1.5" stroke-dasharray="6 4"/>
    ${pts.filter((_, i) => i % pas === 0).map((p, k) => `<circle cx="${x(p[0]).toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="3.2" fill="${COUL.bleu}" fill-opacity=".55"><title>valeur ${nf(v[k * pas])} · centrée réduite ${nf(p[1])} · attendu si loi normale ${nf(p[0])}</title></circle>`).join('')}</svg>`
}
// Nuage de points avec droite des moindres carrés ; léger décalage (jitter) déterministe pour les variables discrètes.
function nuageSvg({ W, H, x: x0, y: y0, nomX, nomY }) {
  const pts = []; x0.forEach((v, i) => { if (Number.isFinite(v) && Number.isFinite(y0[i])) pts.push([v, y0[i]]) }); if (pts.length < 3) return vide('Pas assez de paires complètes.')
  const discret = (k) => new Set(pts.map((p) => p[k])).size <= 15, jit = (i, k) => (discret(k) ? (((i * 7919 + k * 104729) % 1000) / 1000 - 0.5) * 0.35 : 0)
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]), xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys)
  const ex = (xmax - xmin) * 0.04 || 0.5, ey = (ymax - ymin) * 0.06 || 0.5
  const { x, y, fond } = cadre({ W, H, xmin: xmin - ex, xmax: xmax + ex, ymin: ymin - ey, ymax: ymax + ey, titreX: nomX, titreY: nomY })
  const r = Sx.pearson(xs, ys), pas = Math.max(1, Math.floor(pts.length / 2500))
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${fond}
    ${pts.filter((_, i) => i % pas === 0).map((p, i) => `<circle cx="${x(p[0] + jit(i, 0)).toFixed(1)}" cy="${y(p[1] + jit(i, 1)).toFixed(1)}" r="3.4" fill="${COUL.bleu}" fill-opacity=".35"><title>${echapper(nomX)} : ${nf(p[0])} · ${echapper(nomY)} : ${nf(p[1])}</title></circle>`).join('')}
    ${Number.isFinite(r.pente) ? `<line x1="${x(xmin)}" y1="${y(r.ordonnee + r.pente * xmin)}" x2="${x(xmax)}" y2="${y(r.ordonnee + r.pente * xmax)}" stroke="${COUL.rouge}" stroke-width="2"/>` : ''}</svg>`
}
// Carte de chaleur d'une matrice (corrélations de −1 à 1, ou V de Cramér de 0 à 1).
function chaleurSvg({ W, noms, M, P, positif = false }) {
  // Échelle divergente : blanc (0) → bleu (+1) ou rouge (−1) ; |r|^0,6 pour que les liens faibles restent visibles.
  const k = noms.length, ml = Math.min(260, W * 0.34), c = Math.max(30, Math.min(72, (W - ml - 8) / k)), H = 24 + k * c + 46
  const melange = (a, b, t) => `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',')})`
  const BLANC = [246, 247, 249], BLEU = [11, 79, 214], ROUGE = [200, 30, 52]
  const couleur = (r) => (!Number.isFinite(r) ? '#eceef1' : melange(BLANC, r >= 0 ? BLEU : ROUGE, Math.min(1, Math.abs(r)) ** 0.6))
  const largeur = Math.min(W, Math.max(ml + k * c + 8, ml + 560)), lx = ml, ll = Math.min(260, Math.max(160, k * c)), ly = 24 + k * c + 14
  const pas = Array.from({ length: 41 }, (_, i) => (positif ? i / 40 : -1 + i / 20))
  return `<svg width="${largeur}" height="${H}" viewBox="0 0 ${largeur} ${H}">
    ${noms.map((_, j) => `<text x="${ml + j * c + c / 2}" y="16" text-anchor="middle" font-size="11.5" font-weight="700" fill="#5a606a">${j + 1}</text>`).join('')}
    ${noms.map((nm, i) => `<text x="${ml - 8}" y="${24 + i * c + c / 2 + 4}" text-anchor="end" font-size="11.5" fill="#3d434c"><tspan font-weight="700">${i + 1}</tspan> · ${echapper(nm.length > 36 ? nm.slice(0, 35) + '…' : nm)}</text>`
      + noms.map((_, j) => { const r = i === j ? NaN : M[i][j], fort = Math.abs(r) ** 0.6 > 0.55; return `<rect x="${ml + j * c}" y="${24 + i * c}" width="${c - 2}" height="${c - 2}" rx="2" fill="${i === j ? '#d9dce1' : couleur(r)}"><title>${echapper(nm)} × ${echapper(noms[j])} : ${nf(M[i][j], 3)}${P && i !== j ? ` (p = ${fp(P[i][j])})` : ''}</title></rect>
        <text x="${ml + j * c + c / 2 - 1}" y="${24 + i * c + c / 2 + 3}" text-anchor="middle" font-size="${c < 40 ? 9.5 : c > 56 ? 12.5 : 11}" font-weight="${fort ? 700 : 400}" fill="${fort ? '#fff' : '#17181a'}" pointer-events="none">${i === j ? '' : nf(r, 2)}${P && i !== j ? `<tspan font-size="9">${etoiles(P[i][j])}</tspan>` : ''}</text>` }).join('')).join('')}
    ${pas.map((v, i) => `<rect x="${lx + i * ll / pas.length}" y="${ly}" width="${ll / pas.length + 0.6}" height="10" fill="${couleur(v)}"/>`).join('')}
    <rect x="${lx}" y="${ly}" width="${ll}" height="10" fill="none" stroke="#c9cdd3"/>
    ${(positif ? [[0, '0 : aucun lien'], [1, '1 : lien parfait']] : [[-1, '−1'], [0, '0'], [1, '+1']]).map(([v, t]) => `<text x="${lx + (positif ? v : (v + 1) / 2) * ll}" y="${ly + 24}" text-anchor="${v === (positif ? 0 : -1) ? 'start' : v === 1 ? 'end' : 'middle'}" font-size="11" fill="#5a606a">${t}</text>`).join('')}
</svg>${positif ? '' : '<div class="ind-legende"><span><b style="color:#c81e34">rouge</b> : les deux variables varient en sens inverse</span><span><b style="color:#0b4fd6">bleu</b> : elles varient ensemble</span><span>* p < 0,05 · ** p < 0,01 · *** p < 0,001</span></div>'}`
}
// Barres autour de zéro (ACF, PACF, corrélation croisée) avec la bande de significativité ±1,96/√n.
function barresZeroSvg({ W, H, valeurs, etiquettes, seuil, couleur = COUL.bleu, titreY = '' }) {
  const lim = Math.min(1, Math.max(seuil * 1.4, ...valeurs.filter(Number.isFinite).map(Math.abs)) * 1.12)
  const { y, fond } = cadre({ W, H, xmin: 0, xmax: 1, ymin: -lim, ymax: lim, titreY, mb: 30, sansX: true })
  const ml = 56, lg = (W - ml - 14) / valeurs.length, pasE = Math.max(1, Math.ceil(valeurs.length / Math.floor((W - ml) / 34)))
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${fond}
    <rect x="${ml}" y="${y(seuil)}" width="${W - ml - 14}" height="${y(-seuil) - y(seuil)}" fill="${COUL.orange}" fill-opacity=".09"/>
    <line x1="${ml}" x2="${W - 14}" y1="${y(seuil)}" y2="${y(seuil)}" stroke="${COUL.orange}" stroke-dasharray="5 4"/><line x1="${ml}" x2="${W - 14}" y1="${y(-seuil)}" y2="${y(-seuil)}" stroke="${COUL.orange}" stroke-dasharray="5 4"/>
    <line x1="${ml}" x2="${W - 14}" y1="${y(0)}" y2="${y(0)}" stroke="#5a606a"/>
    ${valeurs.map((v, i) => (Number.isFinite(v) ? `<rect x="${ml + i * lg + lg * 0.2}" y="${Math.min(y(v), y(0))}" width="${Math.max(1.5, lg * 0.6)}" height="${Math.abs(y(v) - y(0))}" fill="${Math.abs(v) > seuil ? couleur : '#b8bdc5'}"><title>${etiquettes[i]} : ${nf(v, 3)}</title></rect>` : '')
      + (i % pasE === 0 ? `<text x="${ml + i * lg + lg / 2}" y="${H - 14}" text-anchor="middle" font-size="10.5" fill="#5a606a">${etiquettes[i]}</text>` : '')).join('')}</svg>`
}

// ── Statistiques descriptives ─────────────────────────────────────────────────────────────
function rendreTableDescriptive(c, niv) {
  const vars = variablesNiveau(c, niv).filter((v) => !v.bin && v.k !== 't')
  if (!vars.length) return { html: vide(niv === 'j' ? 'Pas encore de série journalière.' : 'Aucune variable numérique renseignée.'), lecture: '' }
  const lignes = vars.map((v) => { const d = Sx.descriptif(v.x); return [v.nom, d.n, d.manquants, nf(d.moyenne), icTexte(d), nf(d.mediane), `${nf(d.mode)} <small class="text-muted">(${d.modeFreq}×)</small>`, nf(d.ecart), nf(d.variance), nf(d.se), nf(d.cv, 1), nf(d.min), nf(d.p5), nf(d.p10), nf(d.q1), nf(d.q3), nf(d.p90), nf(d.p95), nf(d.max), nf(d.etendue), nf(d.iqr), nf(d.mad), nf(d.asymetrie), nf(d.aplatissement), `${nf(d.jb, 1)}`, `${fp(d.pJb)} ${badge(d.pJb >= 0.05, 'normale', 'non normale')}`, d.aberrants, nf(d.somme, 0)] })
  return { html: tableau(['Variable', 'n', 'Manquants', 'Moyenne', 'IC 95 % de la moyenne', 'Médiane', 'Mode', 'Écart-type', 'Variance', 'Erreur-type', 'CV (%)', 'Min', 'P5', 'P10', 'Q1 (P25)', 'Q3 (P75)', 'P90', 'P95', 'Max', 'Étendue', 'IQR', 'MAD', 'Asymétrie', 'Aplatissement', 'Jarque-Bera', 'p (normalité)', 'Atypiques', 'Somme'], lignes),
    lecture: `${niv === 'p' ? 'une ligne par variable mesurée sur chaque patient' : 'une ligne par variable mesurée chaque jour'}. <b>Moyenne</b> et <b>médiane</b> (valeur du milieu) ; si elles diffèrent beaucoup, la distribution est asymétrique. <b>IC 95 %</b> : intervalle qui contient la vraie moyenne avec 95 % de confiance (x̄ ± t·s/√n). <b>Mode</b> : valeur la plus fréquente. <b>Écart-type</b>, <b>variance</b> et <b>CV</b> (écart-type ÷ moyenne) mesurent la dispersion ; l’<b>erreur-type</b> (s/√n) mesure la précision de la moyenne. <b>P5…P95</b> : percentiles (5 % des valeurs sont sous P5). <b>IQR</b> = Q3 − Q1 (les 50 % centraux) ; <b>MAD</b> = médiane des écarts à la médiane (dispersion robuste). <b>Asymétrie</b> > 0 : longue queue à droite ; <b>aplatissement</b> (excès) > 0 : plus de valeurs extrêmes qu’une loi normale. <b>Jarque-Bera</b> teste la normalité : p < 0,05 → la loi n’est pas normale (préférer médiane, Spearman et tests non paramétriques). <b>Atypiques</b> : valeurs hors de [Q1 − 1,5 IQR ; Q3 + 1,5 IQR], à vérifier dans le registre (erreur de saisie ?).` }
}
function rendreDistribution(c, W, H) {
  const opts = optionsNum(c, true); if (!opts.length) return { html: vide('Aucune variable numérique.'), lecture: '' }
  if (!opts.some(([k]) => k === c.opts.varDist)) c.opts.varDist = opts[0][0]
  const v = trouverVar(c, c.opts.varDist), d = Sx.descriptif(v.x), W2 = W >= 780 ? Math.floor((W - 14) / 2) : W
  return { options: libelle('Variable', choix('varDist', c.opts.varDist, opts)),
    avant: bandeauStats([['n', d.n], ['Moyenne', nf(d.moyenne)], ['Médiane', nf(d.mediane)], ['Écart-type', nf(d.ecart)], ['Q1 – Q3', `${nf(d.q1)} – ${nf(d.q3)}`], ['Min – max', `${nf(d.min)} – ${nf(d.max)}`], ['Asymétrie', nf(d.asymetrie)], ['Aplatissement', nf(d.aplatissement)], ['Normalité (Jarque-Bera)', `p = ${fp(d.pJb)}`]]),
    html: `<div class="ind-deux"><div>${histogrammeSvg({ W: W2, H, valeurs: v.x, nom: v.nom })}</div><div>${qqSvg({ W: W2, H, valeurs: v.x })}</div></div>${boitesSvg({ W, groupes: [{ nom: 'Toutes les valeurs', valeurs: v.x }], nom: v.nom })}`,
    lecture: `<b>histogramme</b> (à gauche) : combien de valeurs tombent dans chaque classe ; la courbe rouge est la loi normale de même moyenne et écart-type, pour juger la forme. <b>Droite de Henry</b> (à droite) : si les points suivent la diagonale rouge, la variable suit une loi normale ; une courbure en haut à droite signale une queue à droite (longs séjours, enfants plus âgés). <b>Boîte à moustaches</b> (en bas) : la boîte va de Q1 à Q3, le trait est la médiane, le losange rouge la moyenne ; les cercles orange sont les valeurs atypiques.` }
}
function rendreQualitatives(c) {
  if (!c.pat.quali.length) return { html: vide('Aucune variable qualitative renseignée.'), lecture: '' }
  const blocs = c.pat.quali.map((v) => {
    const cnt = {}; let n = 0; for (const e of v.x) if (e !== null) { cnt[e] = (cnt[e] ?? 0) + 1; n++ }
    const rangs = Object.entries(cnt).sort((a, b) => (v.k === 'jour' ? JOURS_SEMAINE.indexOf(a[0]) - JOURS_SEMAINE.indexOf(b[0]) : b[1] - a[1]))
    const ent = -rangs.reduce((a, [, k]) => a + (k / n) * Math.log(k / n), 0) / Math.log(Math.max(2, rangs.length))
    return `<div><h5 style="font-size:13px;margin:0 0 6px">${v.nom} <small>${rangs.length} modalités · ${v.x.length - n} manquant(s) · entropie ${nf(ent, 2)}</small></h5>
      ${tableau(['Modalité', 'n', '%', 'IC 95 % (Wilson)', '% cumulé'], (() => { let cum = 0; return rangs.map(([m, k]) => { cum += k; const [b, h] = Sx.wilson(k, n); return [echapper(m), k, nf(100 * k / n, 1), `${nf(100 * b, 1)} – ${nf(100 * h, 1)}`, nf(100 * cum / n, 1)] }) })(), { hauteur: 260 })}</div>`
  })
  return { html: `<div class="ind-deux">${blocs.join('')}</div>`,
    lecture: `pour chaque variable qualitative : l’<b>effectif</b>, le <b>pourcentage</b> (sur les lignes renseignées) et son <b>intervalle de confiance à 95 %</b> (méthode de Wilson, fiable même pour les petits effectifs) : la vraie proportion dans la population a 95 % de chances d’être dans cet intervalle. L’<b>entropie normalisée</b> va de 0 (une seule modalité) à 1 (toutes les modalités également fréquentes). Le premier rang est le <b>mode</b>.` }
}
function testsDeGroupes(valeurs, groupesX) {
  const g = {}; valeurs.forEach((v, i) => { if (Number.isFinite(v) && groupesX[i] !== null && groupesX[i] !== undefined) (g[groupesX[i]] ??= []).push(v) })
  const noms = Object.keys(g).filter((k) => g[k].length >= 3), listes = noms.map((k) => g[k])
  if (noms.length < 2) return null
  const kw = Sx.kruskal(listes), an = Sx.anova(listes)
  const deux = noms.length === 2 ? { mw: Sx.mannWhitney(listes[0], listes[1]), welch: Sx.welch(listes[0], listes[1]) } : null
  return { noms, listes, kw, an, deux, n: listes.reduce((a, b) => a + b.length, 0) }
}
function rendreParGroupe(c, W) {
  const nums = c.pat.num.filter((v) => !v.bin), qual = c.pat.quali
  if (!nums.length || !qual.length) return { html: vide('Il faut au moins une variable numérique et une variable qualitative.'), lecture: '' }
  if (!nums.some((v) => v.k === c.opts.grpVar)) c.opts.grpVar = nums[0].k
  if (!qual.some((v) => v.k === c.opts.grpPar)) c.opts.grpPar = qual[0].k
  const v = nums.find((e) => e.k === c.opts.grpVar), q = qual.find((e) => e.k === c.opts.grpPar), t = testsDeGroupes(v.x, q.x)
  const options = `${libelle('Variable', choix('grpVar', v.k, nums.map((e) => [e.k, e.nom])))}${libelle('selon', choix('grpPar', q.k, qual.map((e) => [e.k, e.nom])))}`
  if (!t) return { options, html: vide('Pas assez de valeurs par groupe (au moins 3 dans 2 groupes).'), lecture: '' }
  const lignes = t.noms.map((nm, i) => { const d = Sx.descriptif(t.listes[i]); return [echapper(nm), d.n, nf(d.moyenne), icTexte(d), nf(d.ecart), nf(d.mediane), `${nf(d.q1)} – ${nf(d.q3)}`, nf(d.min), nf(d.max), nf(d.cv, 1)] })
  const res = [['Kruskal-Wallis (non paramétrique)', `H = ${nf(t.kw.h)} · ddl ${t.kw.ddl}`, fp(t.kw.p), `ε² = ${nf(t.kw.epsilon2, 3)}`, badge(t.kw.p < 0.05, 'différence significative', 'pas de différence prouvée')],
    ['ANOVA à un facteur (paramétrique)', `F = ${nf(t.an.f)} · ddl ${t.an.d1}, ${t.an.d2}`, fp(t.an.p), `η² = ${nf(t.an.eta2, 3)}`, badge(t.an.p < 0.05, 'différence significative', 'pas de différence prouvée')],
    ...(t.deux ? [['Mann-Whitney (2 groupes)', `U = ${nf(t.deux.mw.u, 1)} · z = ${nf(t.deux.mw.z)}`, fp(t.deux.mw.p), `r = ${nf(t.deux.mw.r, 3)}`, badge(t.deux.mw.p < 0.05, 'significatif', 'non significatif')],
      ['t de Welch (2 groupes)', `t = ${nf(t.deux.welch.t)} · ddl ${nf(t.deux.welch.ddl, 1)}`, fp(t.deux.welch.p), `d de Cohen = ${nf(t.deux.welch.d, 3)}`, badge(t.deux.welch.p < 0.05, 'significatif', 'non significatif')]] : [])]
  return { options,
    html: `${tableau(['Groupe', 'n', 'Moyenne', 'IC 95 %', 'Écart-type', 'Médiane', 'Q1 – Q3', 'Min', 'Max', 'CV (%)'], lignes)}
      <div style="margin-top:10px">${tableau(['Test', 'Statistique', 'p-valeur', 'Taille d’effet', 'Conclusion (α = 5 %)'], res)}</div>
      <div style="margin-top:10px">${boitesSvg({ W, groupes: t.noms.map((nm, i) => ({ nom: nm, valeurs: t.listes[i] })), nom: v.nom })}</div>`,
    lecture: `la variable « ${v.nom} » est décrite séparément pour chaque groupe de « ${q.nom} » (groupes d’au moins 3 valeurs). Les tests disent si les écarts entre groupes peuvent être dus au hasard : <b>p < 0,05</b> → différence significative. <b>Kruskal-Wallis</b> et <b>Mann-Whitney</b> comparent les rangs (aucune hypothèse de normalité : à privilégier ici) ; <b>ANOVA</b> et <b>t de Welch</b> comparent les moyennes. La <b>taille d’effet</b> dit si la différence est importante en pratique (η² ou ε² : 0,01 petit, 0,06 moyen, 0,14 grand ; d de Cohen : 0,2 / 0,5 / 0,8 ; r : 0,1 / 0,3 / 0,5).` }
}

// Durée de séjour selon l'âge, sur TOUTES les lignes dont la durée est écrite (sortie ou nombre de jours) :
// ne dépend pas du calcul d'occupation, donc visible dès les premières pages saisies.
function rendreDureeAge(c, W, H) {
  const L = lignesPeriode().map((x) => ({ m: ageEnMois(x.l.age), d: dureeEcrite(x.l) })).filter((e) => e.m !== null && e.d !== null)
  if (L.length < 3) return { html: vide('Pas encore assez de lignes avec l’âge et la durée (sortie ou nombre de jours).'), lecture: '' }
  const tranches = ['0 – 11 mois', '12 – 59 mois', '5 – 14 ans', '15 ans et plus'], t = (m) => (m < 12 ? 0 : m < 60 ? 1 : m < 180 ? 2 : 3)
  const parT = tranches.map(() => []); for (const e of L) parT[t(e.m)].push(e.d)
  const ans = Math.min(15, Math.floor(Math.max(...L.map((e) => e.m)) / 12)), parAn = Array.from({ length: ans + 1 }, () => [])
  for (const e of L) parAn[Math.min(ans, Math.floor(e.m / 12))].push(e.d)
  const desc = parT.map((v) => (v.length ? Sx.descriptif(v) : null)), moy = desc.map((d) => (d ? d.moyenne : null))
  const W2 = W >= 780 ? Math.floor((W - 14) / 2) : W, test = testsDeGroupes(L.map((e) => e.d), L.map((e) => tranches[t(e.m)])), r = Sx.spearman(L.map((e) => e.m), L.map((e) => e.d))
  return {
    avant: bandeauStats([['Lignes utilisées', L.length], ...tranches.map((k, i) => [k, desc[i] ? `${nf(desc[i].moyenne, 1)} j (n = ${desc[i].n})` : '—']), ['Lien âge – durée (Spearman)', `${nf(r.r, 2)} · p ${fp(r.p)}`], ['Différence entre tranches (Kruskal-Wallis)', test ? `p ${fp(test.kw.p)}` : '—']]),
    html: `<div class="ind-deux"><div>${barresSvg({ W: W2, H, categories: tranches, series: [{ nom: 'Durée moyenne', valeurs: moy.map((v) => arrondi(v, 1)), couleur: COUL.violet }], erreurs: desc.map((d) => (d && d.n >= 5 ? { bas: Math.max(0, d.icBas), haut: d.icHaut } : { bas: null })), titreY: 'Jours en moyenne' })}</div>
      <div>${barresSvg({ W: W2, H, categories: parAn.map((_, i) => (i === ans && ans === 15 ? '15+' : `${i}`)), series: [{ nom: 'Durée moyenne', valeurs: parAn.map((v) => (v.length ? arrondi(v.reduce((a, b) => a + b, 0) / v.length, 1) : null)), couleur: COUL.bleu }, { nom: 'Médiane', valeurs: parAn.map((v) => (v.length ? Sx.descriptif(v).mediane : null)), couleur: COUL.orange }], titreY: 'Jours (âge en années révolues)' })}</div></div>`,
    lecture: `durée de séjour (en jours, telle qu’écrite : sortie − entrée, ou « nombre de jours ») selon l’âge, calculée sur <b>toutes les lignes</b> où l’âge et la durée sont renseignés (${L.length} lignes), contrairement à la rubrique « Flux et séjours » qui ne garde que les séjours terminés pendant la période de calcul de l’occupation. <b>À gauche</b> : moyenne par tranche d’âge du récapitulatif mensuel, avec son <b>intervalle de confiance à 95 %</b> (trait noir : plus il est long, moins la moyenne est sûre ; il n’est pas tracé pour un groupe de moins de 5 enfants, dont la moyenne est trop fragile). <b>À droite</b> : moyenne et médiane année d’âge par année d’âge (0 = moins d’un an). Le coefficient de <b>Spearman</b> dit si la durée augmente (positif) ou diminue (négatif) avec l’âge ; <b>Kruskal-Wallis</b> p < 0,05 → les tranches ont des durées réellement différentes.`,
  }
}

// ── Corrélations et tests ─────────────────────────────────────────────────────────────────
const METHODES = [['pearson', 'Pearson (linéaire)'], ['spearman', 'Spearman (rangs)'], ['kendall', 'Kendall τ-b (rangs)']]
// Moins de 8 patients ayant les deux valeurs : corrélation non calculée (« — »), elle serait trompeuse.
// Pour une variable oui/non : au moins 3 patients de chaque côté (sinon un seul cas atypique fait r ≈ 1).
function pairesSuffisantes(a, b) {
  const x = [], y = []; a.forEach((v, i) => { if (Number.isFinite(v) && Number.isFinite(b[i])) { x.push(v); y.push(b[i]) } })
  if (x.length < 8) return false
  const ok = (z) => { const m = new Map(); z.forEach((v) => m.set(v, (m.get(v) ?? 0) + 1)); return m.size > 2 || Math.min(...m.values()) >= 3 }
  return ok(x) && ok(y)
}
const correler = (m, a, b) => { if (!pairesSuffisantes(a, b)) return { r: NaN, p: NaN, n: 0 }; const r = Sx[m](a, b); return { r: m === 'kendall' ? r.tau : r.r, p: r.p, n: r.n } }
function rendreMatrice(c, W, niv) {
  const vars = variablesNiveau(c, niv); if (vars.length < 2) return { html: vide('Pas assez de variables.'), lecture: '' }
  const nJours = Math.max(...vars.map((v) => v.x.filter(Number.isFinite).length))
  if (nJours < 8) return { html: vide(`Pas encore assez de jours saisis (${nJours}) pour calculer des corrélations : il en faut au moins 8.`), lecture: '' }
  const m = c.opts.corr, k = vars.length, M = [], P = []
  for (let i = 0; i < k; i++) { M.push([]); P.push([]); for (let j = 0; j < k; j++) { if (i === j) { M[i].push(1); P[i].push(0); continue } if (j < i) { M[i].push(M[j][i]); P[i].push(P[j][i]); continue } const r = correler(m, vars[i].x, vars[j].x); M[i].push(r.r); P[i].push(r.p) } }
  return { options: libelle('Méthode', choix('corr', m, METHODES)),
    html: chaleurSvg({ W, noms: vars.map((v) => v.nom), M, P }),
    lecture: `chaque case donne la corrélation entre la variable de la ligne et celle de la colonne (numéro en haut), de <b>−1</b> (rouge : quand l’une monte, l’autre baisse) à <b>+1</b> (bleu : elles montent ensemble) ; 0 = aucun lien. Les étoiles indiquent la significativité : * p < 0,05 · ** p < 0,01 · *** p < 0,001. <b>Pearson</b> mesure un lien linéaire ; <b>Spearman</b> et <b>Kendall</b> travaillent sur les rangs (liens monotones, robustes aux valeurs extrêmes). Avec une variable 0/1, Pearson est la corrélation <i>point-bisériale</i>. ${niv === 'j' ? `Calculé sur ${nJours} jours (${!c.d.message && c.d.presents.length >= 21 ? 'période de calcul de l’occupation' : 'toute la période saisie, en nombre d’arrivées par jour, car la période de calcul de l’occupation compte encore moins de 21 jours'}). ` : ''}${niv === 'j' ? 'Au niveau du jour, J−1 et J−7 mesurent la mémoire de la série : une corrélation forte entre présents et présents J−1 justifie les retards donnés au modèle.' : 'Survolez une case pour la valeur exacte et la p-valeur. « — » : pas assez de patients ayant les deux valeurs (moins de 8, ou moins de 3 « oui » ou 3 « non » pour une variable 0/1) : la corrélation n’est pas calculée car un seul cas suffirait à la fausser. Corrélation n’est pas causalité.'}` }
}
function rendrePaires(c) {
  const lignes = []
  for (const [niv, vars] of [['Patient', c.pat.num], ['Jour', c.jour]]) for (let i = 0; i < vars.length; i++) for (let j = i + 1; j < vars.length; j++) {
    const a = vars[i].x, b = vars[j].x, p = Sx.pearson(a, b); if (!Number.isFinite(p.r) || !pairesSuffisantes(a, b)) continue
    const s = Sx.spearman(a, b), kd = Sx.kendall(a, b)
    lignes.push({ fort: Math.abs(p.r), l: [niv, vars[i].nom, vars[j].nom, p.n, `${nf(p.r, 3)}<sup>${etoiles(p.p)}</sup>`, fp(p.p), `${nf(s.r, 3)}<sup>${etoiles(s.p)}</sup>`, fp(s.p), Number.isFinite(kd.tau) ? `${nf(kd.tau, 3)}<sup>${etoiles(kd.p)}</sup>` : '—', fp(kd.p), nf(100 * p.r * p.r, 1), forceLien(p.r), badge(p.p < 0.05, 'significatif', 'non')] })
  }
  lignes.sort((a, b) => b.fort - a.fort)
  return { html: lignes.length ? tableau(['Niveau', 'Variable A', 'Variable B', 'n', 'Pearson r', 'p', 'Spearman ρ', 'p', 'Kendall τ', 'p', 'R² (%)', 'Force', 'Conclusion'], lignes.map((e) => e.l), { hauteur: 420 }) : vide('Pas assez de variables.'),
    lecture: `toutes les paires de variables numériques, de la plus liée à la moins liée. <b>R²</b> = part de la variance de l’une expliquée linéairement par l’autre. La <b>force</b> suit l’échelle usuelle : |r| < 0,1 négligeable, < 0,3 faible, < 0,5 modéré, < 0,7 fort, au-delà très fort. Avec beaucoup de lignes, un lien faible peut être « significatif » : regardez la force autant que la p-valeur. Les tests sont faits sans correction pour comparaisons multiples (avec ${lignes.length} paires, environ ${Math.round(lignes.length * 0.05)} seraient significatives par hasard au seuil de 5 %).` }
}
function rendreNuage(c, W, H) {
  const opts = optionsNum(c, false); if (opts.length < 2) return { html: vide('Pas assez de variables.'), lecture: '' }
  if (!opts.some(([k]) => k === c.opts.nuX)) c.opts.nuX = opts[0][0]
  if (!opts.some(([k]) => k === c.opts.nuY)) c.opts.nuY = opts[1][0]
  const options = `${libelle('X', choix('nuX', c.opts.nuX, opts))}${libelle('Y', choix('nuY', c.opts.nuY, opts))}`
  if (c.opts.nuX[0] !== c.opts.nuY[0]) return { options, html: vide('Choisissez deux variables du même niveau (deux variables « Patient » ou deux variables « Jour »).'), lecture: '' }
  const vx = trouverVar(c, c.opts.nuX), vy = trouverVar(c, c.opts.nuY), p = Sx.pearson(vx.x, vy.x), s = Sx.spearman(vx.x, vy.x)
  return { options,
    avant: bandeauStats([['n (paires complètes)', p.n], ['Pearson r', `${nf(p.r, 3)} (p ${fp(p.p)})`], ['Spearman ρ', `${nf(s.r, 3)} (p ${fp(s.p)})`], ['R²', `${nf(100 * p.r * p.r, 1)} %`], ['Droite', `Y = ${nf(p.ordonnee, 3)} ${p.pente >= 0 ? '+' : '−'} ${nf(Math.abs(p.pente), 4)} × X`], ['Force du lien', forceLien(p.r)]]),
    html: nuageSvg({ W, H, x: vx.x, y: vy.x, nomX: vx.nom, nomY: vy.nom }),
    lecture: `chaque point est ${c.opts.nuX[0] === 'p' ? 'un patient' : 'un jour'} ; la droite rouge est celle des <b>moindres carrés</b> (elle minimise la somme des carrés des écarts verticaux). La <b>pente</b> dit de combien Y change en moyenne quand X augmente de 1. Pour les variables à peu de valeurs (0/1, nombres entiers), les points sont légèrement écartés pour rester visibles.` }
}
function rendreCramer(c, W) {
  const q = c.pat.quali; if (q.length < 2) return { html: vide('Pas assez de variables qualitatives.'), lecture: '' }
  const k = q.length, M = q.map(() => new Array(k).fill(1)), P = q.map(() => new Array(k).fill(0)), lignes = []
  for (let i = 0; i < k; i++) for (let j = i + 1; j < k; j++) {
    const a = [], b = []; q[i].x.forEach((v, t) => { if (v !== null && q[j].x[t] !== null) { a.push(v); b.push(q[j].x[t]) } })
    const r = a.length >= 5 ? Sx.khi2(a, b) : null; M[i][j] = M[j][i] = r?.v ?? NaN; P[i][j] = P[j][i] = r?.p ?? NaN
    if (r) lignes.push({ v: r.v, l: [q[i].nom, q[j].nom, r.n, nf(r.chi2, 2), r.ddl, fp(r.p), nf(r.v, 3), forceLien(r.v), `${nf(100 * r.faibles, 0)} %`, badge(r.p < 0.05, 'liées', 'indépendance non rejetée')] })
  }
  lignes.sort((a, b) => b.v - a.v)
  return { html: `${chaleurSvg({ W, noms: q.map((v) => v.nom), M, P, positif: true })}<div style="margin-top:10px">${tableau(['Variable A', 'Variable B', 'n', 'χ²', 'ddl', 'p', 'V de Cramér', 'Force', 'Cases E < 5', 'Conclusion'], lignes.map((e) => e.l), { hauteur: 360 })}</div>`,
    lecture: `le <b>test du khi-deux</b> compare le tableau croisé observé à celui qu’on aurait si les deux variables étaient <b>indépendantes</b> : χ² = Σ (observé − attendu)² ÷ attendu. p < 0,05 → les variables sont liées. Le <b>V de Cramér</b> (de 0 à 1) mesure la force du lien, quelle que soit la taille du tableau. Si plus de 20 % des cases ont un effectif attendu inférieur à 5 (colonne « Cases E < 5 »), la p-valeur est approximative : regroupez des modalités.` }
}
function rendreContingence(c) {
  const q = c.pat.quali; if (q.length < 2) return { html: vide('Pas assez de variables qualitatives.'), lecture: '' }
  if (!q.some((v) => v.k === c.opts.ctA)) c.opts.ctA = q[0].k
  if (!q.some((v) => v.k === c.opts.ctB) || c.opts.ctB === c.opts.ctA) c.opts.ctB = q.find((v) => v.k !== c.opts.ctA).k
  const A = q.find((v) => v.k === c.opts.ctA), B = q.find((v) => v.k === c.opts.ctB), a = [], b = []
  A.x.forEach((v, t) => { if (v !== null && B.x[t] !== null) { a.push(v); b.push(B.x[t]) } })
  const options = `${libelle('Lignes', choix('ctA', A.k, q.map((v) => [v.k, v.nom])))}${libelle('Colonnes', choix('ctB', B.k, q.map((v) => [v.k, v.nom])))}`
  if (a.length < 5) return { options, html: vide('Pas assez de lignes renseignées pour les deux variables.'), lecture: '' }
  const r = Sx.khi2(a, b), cell = (o, i, j) => { const z = r.residus[i][j], coul = z > 2 ? 'color:#0047d1;font-weight:700' : z < -2 ? 'color:#c01f33;font-weight:700' : ''; return `<span style="${coul}">${o}</span> <small class="text-muted">${nf(100 * o / r.totLignes[i], 0)} %</small>` }
  const lignes = r.lignes.map((l, i) => [echapper(l), ...r.O[i].map((o, j) => cell(o, i, j)), `<b>${r.totLignes[i]}</b>`])
  lignes.push(['<b>Total</b>', ...r.totColonnes.map((t) => `<b>${t}</b>`), `<b>${r.n}</b>`])
  return { options, avant: bandeauStats([['n', r.n], ['χ²', nf(r.chi2, 2)], ['ddl', r.ddl], ['p-valeur', fp(r.p)], ['V de Cramér', nf(r.v, 3)], ['Cases E < 5', `${nf(100 * r.faibles, 0)} %`]]),
    html: tableau([`${A.nom} \\ ${B.nom}`, ...r.colonnes.map(echapper), 'Total'], lignes),
    lecture: `chaque case : effectif et <b>pourcentage de la ligne</b>. En <b style="color:#0047d1">bleu</b> : nettement plus fréquent que si les variables étaient indépendantes (résidu standardisé > 2) ; en <b style="color:#c01f33">rouge</b> : nettement moins fréquent (< −2). Ce sont ces cases qui « font » le lien mesuré par le khi-deux.` }
}
function rendreTestsGroupes(c) {
  const lignes = []
  for (const v of c.pat.num.filter((e) => !e.bin)) for (const q of c.pat.quali) {
    if (q.k === 'mois' && v.k === 'age') continue
    const t = testsDeGroupes(v.x, q.x); if (!t || t.noms.length > 12) continue
    const p = t.deux ? t.deux.mw.p : t.kw.p
    lignes.push({ p, l: [v.nom, q.nom, t.noms.length, t.n, t.deux ? 'Mann-Whitney' : 'Kruskal-Wallis', t.deux ? `z = ${nf(t.deux.mw.z)}` : `H = ${nf(t.kw.h)}`, `${fp(p)}<sup>${etoiles(p)}</sup>`, t.deux ? `r = ${nf(t.deux.mw.r, 3)}` : `ε² = ${nf(t.kw.epsilon2, 3)}`, t.deux ? fp(t.deux.welch.p) : fp(t.an.p), badge(p < 0.05, 'différence', 'non')] })
  }
  lignes.sort((a, b) => a.p - b.p)
  return { html: lignes.length ? tableau(['Variable', 'Selon', 'Groupes', 'n', 'Test (rangs)', 'Statistique', 'p', 'Taille d’effet', 'p paramétrique', 'Conclusion'], lignes.map((e) => e.l), { hauteur: 420 }) : vide('Pas assez de données.'),
    lecture: `chaque variable numérique est comparée entre les groupes de chaque variable qualitative, du lien le plus net au moins net. Test sur les rangs : <b>Mann-Whitney</b> pour 2 groupes, <b>Kruskal-Wallis</b> au-delà ; la colonne « p paramétrique » donne le t de Welch ou l’ANOVA, pour comparaison. Le détail d’un croisement (moyennes par groupe, boîtes) est dans « Statistiques descriptives → Comparaison d’une variable entre groupes ». Attention aux comparaisons multiples : sur ${lignes.length} tests, environ ${Math.round(lignes.length * 0.05)} seraient significatifs par hasard.` }
}
// Jours fériés et vacances scolaires : les admissions (et l'occupation, si elle est calculée) changent-elles ?
// Tests de Mann-Whitney (jours fériés contre jours ordinaires), avec deux corrections :
//   · « attendu » d'un férié = moyenne des admissions des jours ordinaires du même jour de la semaine
//     (un férié tombé un dimanche ne se compare pas à un mardi) ;
//   · vacances contre classe « à mois égal » : seulement les mois qui contiennent les deux, pour ne pas
//     confondre l'effet des vacances avec la saison (les grandes vacances tombent quand le paludisme recule).
// Nuage de points en 3D : trois variables numériques des patients, couleur selon une variable qualitative.
function rendreNuage3D(c, W, H) {
  const vars = c.pat.num; if (vars.length < 3) return { html: vide('Il faut au moins trois variables numériques renseignées.'), lecture: '' }
  const ks = vars.map((v) => v.k), def = ['age', 'duree', 'prix'].filter((k) => ks.includes(k))
  const pris = (cle, i) => { if (!ks.includes(c.opts[cle])) c.opts[cle] = def[i] ?? ks[i]; return vars.find((v) => v.k === c.opts[cle]) }
  const X = pris('n3x', 0), Y = pris('n3y', 1), Z = pris('n3z', 2), q = c.pat.quali.find((v) => v.k === c.opts.n3g)
  const mods = q ? [...new Set(q.x.filter((e) => e !== null))].map((m) => [m, q.x.filter((e) => e === m).length]).sort((a, b) => b[1] - a[1]).slice(0, PALETTE.length).map((e) => e[0]) : []
  const groupes = mods.map((m, i) => ({ nom: String(m), couleur: PALETTE[i], n: q.x.filter((e) => e === m).length }))
  const { id, n } = nuage3D({ x: X.x, y: Y.x, z: Z.x, noms: [X.nom, Y.nom, Z.nom], groupes, groupesDe: q ? q.x.map((m) => mods.indexOf(m)) : null, infos: X.x.map((_, i) => `${q && q.x[i] !== null ? `${q.x[i]} · ` : ''}${X.nom} : ${nf(X.x[i])} · ${Y.nom} : ${nf(Y.x[i])} · ${Z.nom} : ${nf(Z.x[i])}`) })
  const opts = vars.map((v) => [v.k, v.nom])
  return { options: `${libelle('X', choix('n3x', X.k, opts))}${libelle('Y (hauteur)', choix('n3y', Y.k, opts))}${libelle('Z (profondeur)', choix('n3z', Z.k, opts))}${libelle('Couleur selon', choix('n3g', c.opts.n3g ?? '', [['', 'aucune'], ...c.pat.quali.map((v) => [v.k, v.nom])]))}`,
    avant: bandeauStats([['Patients ayant les trois valeurs', n], ['r (X, Y)', nf(Sx.pearson(X.x, Y.x).r, 2)], ['r (X, Z)', nf(Sx.pearson(X.x, Z.x).r, 2)], ['r (Y, Z)', nf(Sx.pearson(Y.x, Z.x).r, 2)]]),
    html: cadre3D(id, Math.max(460, H), ['X × Y', 'X × Z', 'Y × Z']),
    lecture: `chaque point est un patient placé selon trois variables à la fois ; chaque axe va du minimum au maximum observé (valeurs écrites au bout). <b>Glissez</b> pour tourner, <b>molette</b> pour zoomer, <b>double-clic</b> pour revenir ; les boutons donnent les trois nuages « à plat » (X × Y, X × Z, Y × Z). Un nuage allongé dans une direction montre que les trois variables varient ensemble ; un groupe de couleur à l’écart signale un profil particulier (son ellipse et son barycentre le montrent ; cliquez-le dans la légende pour l’isoler). Les variables à peu de valeurs (0/1, nombres entiers) sont légèrement écartées pour rester visibles.` }
}
// Régression à deux variables explicatives : nuage 3D (X1, X2, Y) et plan des moindres carrés Y = β₀ + β₁X₁ + β₂X₂.
function rendreRegression3D(c, W, H) {
  const vars = c.pat.num.filter((v) => !v.bin); if (vars.length < 3) return { html: vide('Il faut au moins trois variables numériques (non binaires).'), lecture: '' }
  const ks = vars.map((v) => v.k), def = ['duree', 'age', 'prix'].filter((k) => ks.includes(k))
  const pris = (cle, i) => { if (!ks.includes(c.opts[cle])) c.opts[cle] = def[i] ?? ks[i]; return vars.find((v) => v.k === c.opts[cle]) }
  const Y = pris('r3y', 0), X1 = pris('r3a', 1), X2 = pris('r3b', 2), opts = vars.map((v) => [v.k, v.nom])
  const options = `${libelle('Y expliquée', choix('r3y', Y.k, opts))}${libelle('X₁', choix('r3a', X1.k, opts))}${libelle('X₂', choix('r3b', X2.k, opts))}`
  if (new Set([Y.k, X1.k, X2.k]).size < 3) return { options, html: vide('Choisissez trois variables différentes.'), lecture: '' }
  const r = Sx.regression(X1.x.map((v, i) => [v ?? NaN, X2.x[i] ?? NaN]), Y.x.map((v) => v ?? NaN), [X1.nom, X2.nom]); if (!r) return { options, html: vide('Régression impossible (trop peu de lignes complètes).'), lecture: '' }
  const [b0, b1, b2] = r.coef.map((e) => e.b)
  // Plan : grille 9 × 9 sur l'étendue de X₁ et X₂ (coordonnées normalisées comme le nuage), Y du plan bornée à son axe.
  const plan = (norm, bornes) => { const seg = [], pts = (a, b) => [norm(0, a), Math.max(-1.3, Math.min(1.3, norm(1, b0 + b1 * a + b2 * b))), norm(2, b)]
    const [a0, a1] = bornes[0], [c0, c1] = bornes[2]
    for (let i = 0; i <= 8; i++) { const a = a0 + (a1 - a0) * i / 8, b = c0 + (c1 - c0) * i / 8; seg.push([pts(a, c0), pts(a, c1)], [pts(a0, b), pts(a1, b)]) }
    return seg.flatMap(([u, v]) => Array.from({ length: 8 }, (_, k) => [u.map((e, j) => e + (v[j] - e) * k / 8), u.map((e, j) => e + (v[j] - e) * (k + 1) / 8)])) }
  const res = r.y.map((v, i) => v - r.yhat[i])
  const { id } = nuage3D({ x: r.X.map((l) => l[0]), y: r.y, z: r.X.map((l) => l[1]), noms: [X1.nom, Y.nom, X2.nom], plan,
    halos: false, groupes: [{ nom: 'Au-dessus du plan', couleur: COUL.bleu, n: res.filter((e) => e >= 0).length }, { nom: 'En dessous du plan', couleur: COUL.orange, n: res.filter((e) => e < 0).length }],
    groupesDe: res.map((e) => (e >= 0 ? 0 : 1)), infos: r.y.map((v, i) => `${Y.nom} : ${nf(v)} (prédit ${nf(r.yhat[i])}) · ${X1.nom} : ${nf(r.X[i][0])} · ${X2.nom} : ${nf(r.X[i][1])}`) })
  return { options,
    avant: bandeauStats([['n', r.n], ['Équation', `Y = ${nf(b0, 2)} ${b1 >= 0 ? '+' : '−'} ${nf(Math.abs(b1), 4)}·X₁ ${b2 >= 0 ? '+' : '−'} ${nf(Math.abs(b2), 4)}·X₂`], ['R²', nf(r.r2, 3)], ['p de X₁', fp(r.coef[1].p)], ['p de X₂', fp(r.coef[2].p)]]),
    html: cadre3D(id, Math.max(460, H), [`${X1.nom.split(' (')[0]} × Y`, `${X1.nom.split(' (')[0]} × ${X2.nom.split(' (')[0]}`, `Y × ${X2.nom.split(' (')[0]}`]),
    lecture: `avec <b>deux</b> variables explicatives, la régression n’est plus une droite mais un <b>plan</b> : Y = β₀ + β₁X₁ + β₂X₂ (grille rouge). Tournez la vue : de côté, on voit si les points collent au plan (bon R²) ou s’en écartent ; vue « ${X1.nom.split(' (')[0]} × Y », la pente du plan est β₁ ; vue « Y × ${X2.nom.split(' (')[0]} », c’est β₂. Les points bleus sont au-dessus du plan, les orange en dessous : s’ils forment des zones séparées, le lien n’est pas linéaire. Pour plus de deux variables, voir « Régression linéaire multiple ».` }
}
function rendreCalendrier(c) {
  if (!CAL) return { html: vide('Calendrier camerounais non chargé (calendrier.js).'), lecture: '' }
  const occ = !c.d.message && c.d.presents?.length >= 21, deb = occ ? c.d.debutNum : c.brut?.debutNum, adm = occ ? c.d.adm : c.brut?.x, pres = occ ? c.d.presents : null
  if (!adm?.length) return { html: vide('Pas encore de jours saisis.'), lecture: '' }
  const n = adm.length, J = Array.from({ length: n }, (_, i) => ({ i, j: deb + i, f: ferieDe(deb + i), lend: !!ferieDe(deb + i - 1) && !ferieDe(deb + i), v: vacancesDe(deb + i), ws: jourSemaine(deb + i) }))
  const ordinaires = J.filter((x) => !x.f && !x.lend)
  const moy = (v) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : NaN)
  const moyJour = Array.from({ length: 7 }, (_, w) => moy(ordinaires.filter((x) => x.ws === w).map((x) => adm[x.i])))
  const ligne = (nom, grp, ref) => {
    const a = grp.map((x) => adm[x.i]), b = ref.map((x) => adm[x.i]), mw = a.length >= 3 && b.length >= 3 ? Sx.mannWhitney(a, b) : null
    const att = grp.reduce((s, x) => s + moyJour[x.ws], 0), obs = a.reduce((s, v) => s + v, 0)
    const pa = pres ? grp.map((x) => pres[x.i]) : [], pb = pres ? ref.map((x) => pres[x.i]) : [], mwp = pres && pa.length >= 3 && pb.length >= 3 ? Sx.mannWhitney(pa, pb) : null
    return [nom, grp.length, nf(moy(a), 2), nf(a.length ? Sx.descriptif(a).mediane : NaN, 1), nf(moy(b), 2), ref === ordinaires ? nf(att ? obs / att : NaN, 2) : '—', mw ? `${fp(mw.p)}<sup>${etoiles(mw.p)}</sup>` : '—',
      ...(pres ? [nf(moy(pa), 2), nf(moy(pb), 2), mwp ? `${fp(mwp.p)}<sup>${etoiles(mwp.p)}</sup>` : '—'] : []),
      badge(mw ? mw.p < 0.05 : null, 'différence', grp.length < 10 ? 'trop peu de jours' : 'pas de différence')]
  }
  const feries = J.filter((x) => x.f), lend = J.filter((x) => x.lend), connus = J.filter((x) => x.v !== null)
  const vac = connus.filter((x) => x.v === 1 && !x.f), cls = connus.filter((x) => x.v === 0 && !x.f)
  const lignes = [ligne('Jours fériés', feries, ordinaires), ligne('Lendemains de jours fériés', lend, ordinaires), ligne('Vacances scolaires (hors fériés)', vac, cls)]
  // Vacances contre classe à l'intérieur des mêmes mois : écarts mois par mois, pondérés par le nombre de jours de vacances.
  const parMois = {}; for (const x of [...vac, ...cls]) (parMois[versDate(x.j).slice(0, 7)] ??= { v: [], c: [] })[x.v ? 'v' : 'c'].push(adm[x.i])
  const mixtes = Object.values(parMois).filter((g) => g.v.length >= 3 && g.c.length >= 3)
  const poids = mixtes.reduce((s, g) => s + g.v.length, 0), ecart = poids ? mixtes.reduce((s, g) => s + g.v.length * (moy(g.v) - moy(g.c)), 0) / poids : NaN
  const entetes = ['Jours comparés', 'Nombre de jours', 'Admissions / jour', 'Médiane', 'Référence : admissions / jour', 'Observé ÷ attendu (même jour de semaine)', 'p (Mann-Whitney)', ...(pres ? ['Présents (moyenne)', 'Présents référence', 'p présents'] : []), 'Conclusion']
  const liste = feries.map((x) => [fmtDate(versDate(x.j)), echapper(x.f), JOURS_SEMAINE[x.ws], adm[x.i], nf(moyJour[x.ws], 2), pres ? nf(pres[x.i], 1) : '—', x.v === null ? '—' : x.v ? 'oui' : 'non'])
  return {
    avant: bandeauStats([['Jours étudiés', `${n} (${fmtDate(versDate(deb))} → ${fmtDate(versDate(deb + n - 1))})`], ['Jours fériés', feries.length], ['Jours de vacances scolaires', vac.length], ['Jours de classe', cls.length],
      ['Vacances − classe, à mois égal', `${Number.isFinite(ecart) ? `${ecart >= 0 ? '+' : ''}${nf(ecart, 2)} admission / jour` : '—'} (${mixtes.length} mois)`]]),
    html: `${tableau(entetes, lignes)}
      <div style="margin-top:12px">${liste.length ? tableau(['Date', 'Fête', 'Jour', 'Admissions', 'Attendu (même jour, jours ordinaires)', 'Présents', 'Vacances'], liste, { hauteur: 320 }) : vide('Aucun jour férié dans la période saisie.')}</div>`,
    lecture: `les <b>jours fériés</b> camerounais (fêtes fixes ; Vendredi saint et Ascension calculés à partir de Pâques ; Aïd el-Fitr et Tabaski recopiés des communiqués de la Commission nationale du croissant lunaire) et les <b>vacances scolaires</b> (arrêtés MINEDUB/MINESEC) sont comparés aux jours ordinaires. <b>Observé ÷ attendu</b> : admissions des fériés divisées par celles d’un jour ordinaire du même jour de la semaine (1 = aucun effet ; 0,6 = 40 % d’admissions en moins). Le <b>lendemain</b> montre un éventuel rattrapage. Pour les vacances, la comparaison brute mélange l’effet des vacances et celui de la saison (les grandes vacances tombent quand le paludisme recule) : l’écart <b>à mois égal</b> (en haut) ne compare que des jours d’un même mois. ${occ ? 'Les présents à minuit réagissent plus lentement que les admissions, car un enfant reste plusieurs jours.' : 'L’occupation n’est pas encore calculable : seules les admissions sont comparées.'} <b>Prudence</b> : il y a peu de jours fériés par an ; un test non significatif veut souvent dire « pas assez de jours », pas « aucun effet ». Les mêmes jours sont donnés au modèle de prévision (variables « férié », « veille fériée », « vacances »).` }
}
function rendreRegression(c) {
  const niv = c.opts.regNiv === 'j' && c.jour.length ? 'j' : 'p', vars = variablesNiveau(c, niv).filter((v) => v.k !== 't' || niv === 'j')
  if (vars.length < 2) return { html: vide('Pas assez de variables.'), lecture: '' }
  const cleY = niv === 'p' ? 'regY' : 'regYj', cleX = niv === 'p' ? 'regX' : 'regXj'
  if (!vars.some((v) => v.k === c.opts[cleY])) c.opts[cleY] = vars.find((v) => !v.bin)?.k ?? vars[0].k
  const Y = vars.find((v) => v.k === c.opts[cleY]), candidats = vars.filter((v) => v !== Y)
  if (!Array.isArray(c.opts[cleX])) c.opts[cleX] = candidats.filter((v) => v.x.filter(Number.isFinite).length >= 0.6 * Y.x.filter(Number.isFinite).length).map((v) => v.k).slice(0, 8)
  const X = candidats.filter((v) => c.opts[cleX].includes(v.k))
  const options = `${libelle('Niveau', choix('regNiv', niv, [['p', 'Patients'], ...(c.jour.length ? [['j', 'Jours']] : [])]))}${libelle('Variable expliquée Y', choix(cleY, Y.k, vars.map((v) => [v.k, v.nom])))}
    <span class="text-muted">Variables explicatives :</span>${candidats.map((v) => `<label class="ind-case"><input type="checkbox" data-ox="${cleX}" value="${v.k}" ${c.opts[cleX].includes(v.k) ? 'checked' : ''}>${v.nom}</label>`).join('')}`
  if (!X.length) return { options, html: vide('Cochez au moins une variable explicative.'), lecture: '' }
  const n = Y.x.length, r = Sx.regression(Array.from({ length: n }, (_, i) => X.map((v) => v.x[i] ?? NaN)), Y.x.map((v) => v ?? NaN), X.map((v) => v.nom))
  if (!r) return { options, html: vide('Régression impossible : trop peu de lignes complètes, ou variables redondantes (colinéaires).'), lecture: '' }
  // VIF_j = 1 / (1 − R²_j), R²_j : régression de X_j sur les autres explicatives (colinéarité).
  const vif = X.map((v, j) => { if (X.length < 2) return 1; const autres = X.filter((_, k) => k !== j), rr = Sx.regression(Array.from({ length: n }, (_, i) => autres.map((a) => a.x[i] ?? NaN)), v.x.map((e) => e ?? NaN), autres.map((a) => a.nom)); return rr ? 1 / Math.max(1e-9, 1 - rr.r2) : NaN })
  const tc = Sx.tCritique(r.n - X.length - 1)
  // Graphiques : observé contre prédit (la droite des moindres carrés y est la diagonale y = ŷ),
  // résidus contre prédit (doivent former une bande horizontale sans forme) et coefficients standardisés.
  const W = c.W, W2 = W >= 780 ? Math.floor((W - 14) / 2) : W, residus = r.y.map((v, i) => v - r.yhat[i])
  const sdY = Sx.descriptif(r.y).ecart, std = r.coef.slice(1).map((e, j) => { const s = Sx.descriptif(r.X.map((l) => l[j])).ecart * (sdY ? 1 / sdY : NaN); return { nom: e.nom, b: e.b * s, bas: (e.b - tc * e.se) * s, haut: (e.b + tc * e.se) * s, p: e.p } })
  return { options,
    avant: bandeauStats([['n (lignes complètes)', r.n], ['R²', nf(r.r2, 3)], ['R² ajusté', nf(r.r2a, 3)], ['F global', `${nf(r.f, 2)} (p ${fp(r.pF)})`], ['RMSE', nf(r.rmse, 3)]]),
    html: `<div class="ind-deux"><div>${nuageSvg({ W: W2, H: 300, x: r.yhat, y: r.y, nomX: `${Y.nom} prédit par le modèle`, nomY: `${Y.nom} observé` })}</div>
      <div>${nuageSvg({ W: W2, H: 300, x: r.yhat, y: residus, nomX: `${Y.nom} prédit par le modèle`, nomY: 'Résidu (observé − prédit)' })}</div></div>
      ${coefficientsSvg({ W, coefs: std })}
      <div style="margin-top:10px">${tableau(['Terme', 'Coefficient β', 'Erreur-type', 'IC 95 %', 't', 'p', '', 'β standardisé', 'VIF'], r.coef.map((e, j) => [echapper(e.nom), nf(e.b, 4), nf(e.se, 4), `${nf(e.b - tc * e.se, 3)} – ${nf(e.b + tc * e.se, 3)}`, nf(e.t, 2), fp(e.p), etoiles(e.p), j ? nf(std[j - 1].b, 3) : '', j ? nf(vif[j - 1], 2) : '']))}</div>`,
    lecture: `modèle linéaire Y = β₀ + β₁X₁ + … + ε estimé par <b>moindres carrés ordinaires</b> (β = (XᵀX)⁻¹Xᵀy) sur les lignes où toutes les variables sont renseignées. <b>À gauche</b> : chaque point est ${niv === 'p' ? 'un patient' : 'un jour'}, valeur observée contre valeur prédite ; la droite rouge est la diagonale « prédit = observé » : plus les points s’en approchent, meilleur est le modèle (R² = part de la variance expliquée). <b>À droite</b> : les résidus doivent former une bande horizontale autour de 0 ; un entonnoir signale une variance non constante, une courbe un lien non linéaire. <b>Coefficients standardisés</b> (en dessous) : effet d’une hausse d’un écart-type de X, en écarts-types de Y, ce qui rend les variables comparables entre elles ; trait = IC 95 %, en couleur s’il ne coupe pas 0 (effet significatif). Un coefficient se lit « toutes choses égales par ailleurs ». <b>R² ajusté</b> pénalise le nombre de variables. <b>VIF</b> > 5 : la variable est très corrélée aux autres (colinéarité), son coefficient est instable. Modèle exploratoire, distinct du SVR du mémoire.` }
}
// Coefficients standardisés avec leur intervalle de confiance (graphique en forêt).
function coefficientsSvg({ W, coefs }) {
  const k = coefs.length; if (!k) return ''
  const ml = Math.min(260, Math.max(150, W * 0.28)), lh = 30, H = 16 + k * lh + 40
  const tous = coefs.flatMap((e) => [e.bas, e.haut, e.b]).filter(Number.isFinite), lim = Math.max(0.1, ...tous.map(Math.abs)) * 1.1
  const { x, fond } = cadre({ W, H, ml, mr: 18, mt: 8, mb: 40, xmin: -lim, xmax: lim, ymin: 0, ymax: 1, titreX: 'Coefficient standardisé (écarts-types de Y par écart-type de X)', sansY: true })
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${fond}<line x1="${x(0)}" x2="${x(0)}" y1="8" y2="${H - 40}" stroke="#5a606a" stroke-dasharray="4 3"/>
    ${coefs.map((e, i) => { const y = 8 + i * lh + lh / 2, sig = e.p < 0.05, coul = !sig ? '#9ca2ab' : e.b > 0 ? COUL.bleu : COUL.rouge, nom = e.nom.length > 34 ? e.nom.slice(0, 33) + '…' : e.nom
      return `${i % 2 ? `<rect x="${ml}" y="${y - lh / 2}" width="${W - ml - 18}" height="${lh}" fill="#f7f8fa"/>` : ''}
        <text x="${ml - 10}" y="${y + 4}" text-anchor="end" font-size="12" fill="#17181a">${echapper(nom)}</text>
        ${Number.isFinite(e.bas) ? `<line x1="${x(e.bas)}" x2="${x(e.haut)}" y1="${y}" y2="${y}" stroke="${coul}" stroke-width="2.2"/>` : ''}
        <circle cx="${x(e.b)}" cy="${y}" r="5.5" fill="${coul}"><title>${echapper(e.nom)} : β standardisé ${nf(e.b, 3)} (IC 95 % ${nf(e.bas, 3)} à ${nf(e.haut, 3)}), p ${fp(e.p)}</title></circle>` }).join('')}</svg>`
}

// ── Analyse en composantes principales (ACP) ──────────────────────────────────────────────
// Les variables des patients sont souvent peu corrélées deux à deux ; l'ACP cherche les quelques
// directions (axes) qui résument le mieux leurs variations communes. ACP normée sur les patients
// ayant toutes les variables actives ; variables très asymétriques passées en log(1 + x) si demandé.
const PALETTE = [COUL.bleu, COUL.orange, COUL.vert, COUL.rouge, COUL.violet, COUL.cyan, '#b8860b', '#e05fa0', '#2f4f9e', '#6b8e23', '#8a5a44', '#5a606a']
function preparerAcp(c) {
  const vars = c.pat.num, n = c.pat.n
  if (!Array.isArray(c.opts.acpX)) c.opts.acpX = vars.filter((v) => !v.bin && v.x.filter(Number.isFinite).length >= 0.5 * n).map((v) => v.k)
  const cle = JSON.stringify([n, vars.map((v) => v.k), c.opts.acpX, c.opts.acpLog])
  if (c.pat._acp?.cle === cle) return c.pat._acp
  const res = { cle }; c.pat._acp = res
  const transformer = (v) => { if (v.bin || !c.opts.acpLog) return null; const p = v.x.filter(Number.isFinite); return p.every((e) => e >= 0) && Math.abs(Sx.descriptif(p).asymetrie) > 1 ? (e) => Math.log1p(e) : null }
  const act = vars.filter((v) => c.opts.acpX.includes(v.k)).map((v) => { const f = transformer(v); return { k: v.k, nom: f ? `log(1 + ${v.nom})` : v.nom, court: v.nom, log: !!f, bin: v.bin, brut: v.x, x: f ? v.x.map((e) => (Number.isFinite(e) ? f(e) : NaN)) : v.x } })
  res.act = act
  if (act.length < 2) { res.erreur = 'Cochez au moins deux variables actives.'; return res }
  const lignes = []; for (let i = 0; i < n; i++) if (act.every((v) => Number.isFinite(v.x[i]))) lignes.push(i)
  res.lignes = lignes
  if (lignes.length < Math.max(15, act.length + 5)) { res.erreur = `Seulement ${lignes.length} patient(s) ont toutes les variables cochées : il en faut au moins ${Math.max(15, act.length + 5)}. Décochez les variables les moins renseignées.`; return res }
  const A = Sx.acp(lignes.map((i) => act.map((v) => v.x[i])), act.map((v) => v.nom))
  if (!A) { res.erreur = 'ACP impossible : une variable cochée est constante sur les patients complets.'; return res }
  res.A = A; res.axes = Math.min(A.p, Math.max(2, Math.min(4, A.retenus)))
  // Variables numériques supplémentaires (non actives) : corrélation avec les axes, sans peser dans leur construction.
  res.sup = vars.filter((v) => !c.opts.acpX.includes(v.k)).map((v) => {
    const r = A.valeurs.map((_, k) => { const a = [], b = []; lignes.forEach((i, t) => { if (Number.isFinite(v.x[i])) { a.push(v.x[i]); b.push(A.scores[t][k]) } }); return a.length >= 8 ? Sx.pearson(a, b).r : NaN })
    return { nom: v.nom, r }
  }).filter((s) => Number.isFinite(s.r[0]))
  // Variables qualitatives supplémentaires : barycentre de chaque modalité sur les axes et valeur-test
  // v = moyenne_g ÷ √(λ/n_g · (n − n_g)/(n − 1)) ; |v| > 1,96 : la modalité est significativement d'un côté de l'axe.
  res.quali = c.pat.quali.map((q) => {
    const g = new Map(); lignes.forEach((i, t) => { const m = q.x[i]; if (m === null || m === undefined) return; if (!g.has(m)) g.set(m, []); g.get(m).push(t) })
    const N = A.n, mods = [...g.entries()].filter(([, t]) => t.length >= 3).map(([m, t]) => {
      const coord = A.valeurs.map((_, k) => t.reduce((s, j) => s + A.scores[j][k], 0) / t.length)
      return { m, n: t.length, t, coord, vtest: coord.map((v, k) => (t.length < N ? v / Math.sqrt(A.valeurs[k] / t.length * (N - t.length) / (N - 1)) : NaN)) }
    }).sort((a, b) => b.n - a.n)
    return { k: q.k, nom: q.nom, mods }
  }).filter((q) => q.mods.length >= 2)
  return res
}
const axesChoisis = (c, A) => { const [a, b] = String(c.opts.acpAxes ?? '0-1').split('-').map(Number); return a < A.p && b < A.p && a !== b ? [a, b] : [0, 1] }
const optionsAxes = (c, A) => libelle('Plan', choix('acpAxes', axesChoisis(c, A).join('-'), [[0, 1], [0, 2], [1, 2], [0, 3], [2, 3]].filter(([a, b]) => b < A.p).map(([a, b]) => [`${a}-${b}`, `F${a + 1} × F${b + 1}`])))
const nomAxe = (A, k) => `F${k + 1} (${nf(A.inertie[k], 1)} %)`
function optionsAcp(c, R) {
  return `<span class="text-muted">Variables actives :</span>${c.pat.num.map((v) => `<label class="ind-case"><input type="checkbox" data-ox="acpX" value="${v.k}" ${c.opts.acpX.includes(v.k) ? 'checked' : ''}>${v.nom} <small class="text-muted">(${v.x.filter(Number.isFinite).length})</small></label>`).join('')}
    <label class="ind-case"><input type="checkbox" data-opt="acpLog" ${c.opts.acpLog ? 'checked' : ''}>log(1 + x) pour les variables très asymétriques</label>${R?.A ? ` <span class="text-muted">· ${R.A.n} patients complets</span>` : ''}`
}
const KAISER = (v) => (!Number.isFinite(v) ? '—' : v >= 0.9 ? 'excellent' : v >= 0.8 ? 'très bon' : v >= 0.7 ? 'bon' : v >= 0.6 ? 'moyen' : v >= 0.5 ? 'médiocre' : 'inacceptable')

function rendreAcpDonnees(c) {
  const R = preparerAcp(c), options = optionsAcp(c, R); if (R.erreur) return { options, html: vide(R.erreur), lecture: '' }
  const A = R.A, cum = A.inertie.map((_, k) => A.inertie.slice(0, k + 1).reduce((a, b) => a + b, 0))
  return { options,
    avant: bandeauStats([['Patients (lignes complètes)', `${A.n} / ${c.pat.n}`], ['Variables actives', A.p], ['KMO', `${nf(A.kmo, 3)} · ${KAISER(A.kmo)}`], ['Bartlett', `χ² = ${nf(A.bartlett.chi2, 1)} · ddl ${A.bartlett.ddl} · p ${fp(A.bartlett.p)}`], ['Axes retenus (analyse parallèle)', A.retenus], [`Inertie des ${R.axes} premiers axes`, `${nf(cum[R.axes - 1], 1)} %`]]),
    html: `<div class="ind-deux"><div>${tableau(['Variable active', 'Moyenne', 'Écart-type', 'Transformation', 'MSA (KMO)', 'Adéquation'], R.act.map((v, j) => [echapper(v.court), nf(A.moy[j], 3), nf(A.et[j], 3), v.log ? 'log(1 + x)' : v.bin ? 'binaire 0/1' : '—', nf(A.msa[j], 3), KAISER(A.msa[j])]))}</div>
      <div>${tableau(['Axe', 'Valeur propre λ', 'Inertie (%)', 'Cumul (%)', 'Seuil analyse parallèle (95 %)', 'Bâton brisé', 'Retenu'], A.valeurs.map((v, k) => [`F${k + 1}`, nf(v, 3), nf(A.inertie[k], 1), nf(cum[k], 1), nf(A.parallele[k], 3), nf(A.baton[k], 3), badge(v > A.parallele[k], 'oui', 'non')]))}</div></div>`,
    lecture: `l’<b>ACP</b> remplace les ${A.p} variables, souvent peu corrélées deux à deux, par quelques <b>axes</b> (composantes) qui résument leurs variations communes. Elle est <b>normée</b> : chaque variable est centrée-réduite, donc l’âge en mois ne pèse pas plus que le nombre d’examens. Seuls les patients ayant <b>toutes</b> les variables cochées sont utilisés (${A.n} sur ${c.pat.n}) ; décochez une variable peu renseignée pour en garder davantage. <b>Avant d’interpréter</b> : le test de <b>Bartlett</b> doit être significatif (p < 0,05 : les variables ne sont pas indépendantes, il y a quelque chose à résumer) et le <b>KMO</b> au moins 0,5 (au-delà de 0,7, l’ACP est bien adaptée) ; une variable dont le MSA est inférieur à 0,5 partage peu avec les autres et peut être retirée. La <b>valeur propre</b> λ est la variance portée par l’axe (la moyenne vaut 1) ; un axe est <b>retenu</b> s’il dépasse le seuil de l’<b>analyse parallèle de Horn</b> (95e centile des valeurs propres obtenues en mélangeant au hasard chaque colonne, 100 tirages) : c’est la règle la plus fiable, plus prudente que « λ > 1 » (Kaiser). Les variables très asymétriques et positives (montant, densité parasitaire, durée…) sont passées en <b>log(1 + x)</b> pour qu’une poignée de valeurs extrêmes ne fabrique pas un axe à elle seule.` }
}
function rendreAcpEboulis(c, W, H) {
  const R = preparerAcp(c); if (R.erreur) return { html: vide(R.erreur), lecture: '' }
  const A = R.A, p = A.p, ymax = Math.max(...A.valeurs, ...A.parallele, ...A.baton, 1) * 1.15
  const items = [{ nom: 'valeur propre (axe retenu)', couleur: COUL.bleu, barre: true }, { nom: 'axe non retenu', couleur: '#b8bdc5', barre: true }, { nom: 'analyse parallèle (95 %)', couleur: COUL.orange, pointille: '6 4' }, { nom: 'bâton brisé', couleur: COUL.violet, pointille: '2 3' }, { nom: 'λ = 1 (Kaiser)', couleur: '#5a606a', pointille: '4 4', epaisseur: 1.2 }]
  const legH = lignesLegende(items, 56, W - 14), { x, y, fond } = cadre({ W, H, xmin: 0.5, xmax: p + 0.5, ymin: 0, ymax, mb: 40 + 17 * legH, titreY: 'Valeur propre λ', sansX: true })
  const lg = (x(2) - x(1)) * 0.6, ligne = (v, coul, tir) => `<path d="${v.map((e, k) => `${k ? 'L' : 'M'}${x(k + 1).toFixed(1)},${y(e).toFixed(1)}`).join('')}" fill="none" stroke="${coul}" stroke-width="2" stroke-dasharray="${tir}"/>${v.map((e, k) => `<circle cx="${x(k + 1)}" cy="${y(e)}" r="3" fill="${coul}"/>`).join('')}`
  return { html: `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${fond}
    ${A.valeurs.map((v, k) => `<rect x="${x(k + 1) - lg / 2}" y="${y(v)}" width="${lg}" height="${y(0) - y(v)}" rx="3" fill="${v > A.parallele[k] ? COUL.bleu : '#b8bdc5'}" fill-opacity=".85"><title>F${k + 1} : λ = ${nf(v, 3)} · ${nf(A.inertie[k], 1)} % de l’inertie · seuil du hasard ${nf(A.parallele[k], 3)}</title></rect>
      <text x="${x(k + 1)}" y="${y(v) - 6}" text-anchor="middle" font-size="11" font-weight="700" fill="#3d434c">${nf(A.inertie[k], 1)} %</text>
      <text x="${x(k + 1)}" y="${y(0) + 16}" text-anchor="middle" font-size="11.5" fill="#5a606a">F${k + 1}</text>`).join('')}
    <line x1="${x(0.5)}" x2="${x(p + 0.5)}" y1="${y(1)}" y2="${y(1)}" stroke="#5a606a" stroke-width="1.2" stroke-dasharray="4 4"/>
    ${ligne(A.parallele, COUL.orange, '6 4')}${ligne(A.baton, COUL.violet, '2 3')}
    ${legendeSvg(items, 56, H - 6, W - 14)}</svg>`,
    lecture: `l’<b>éboulis</b> montre la part de l’information (inertie) portée par chaque axe, de la plus grande à la plus petite. On garde les axes dont la barre dépasse la courbe orange de l’<b>analyse parallèle</b> : au-delà, l’axe résume un vrai lien entre variables ; en dessous, il n’est pas plus fort que ce que donneraient des données sans aucun lien. Ici : <b>${A.retenus} axe(s)</b> retenu(s), soit ${nf(A.inertie.slice(0, A.retenus).reduce((a, b) => a + b, 0), 1)} % de l’inertie. Le <b>coude</b> de l’éboulis et le <b>bâton brisé</b> (part attendue si l’inertie était répartie au hasard) donnent des avis complémentaires. Avec des variables cliniques hétérogènes, un premier axe à 25–35 % est courant ; ce n’est pas un défaut.` }
}
// Écarte verticalement les étiquettes trop proches (même côté du graphique).
function espacerEtiquettes(etq, ecart = 13) {
  for (const cote of [1, -1]) {
    const l = etq.filter((e) => e.cote === cote).sort((a, b) => a.y - b.y)
    for (let i = 1; i < l.length; i++) if (l[i].y - l[i - 1].y < ecart) l[i].y = l[i - 1].y + ecart
  }
  return etq
}
function rendreAcpCercle(c, W) {
  const R = preparerAcp(c); if (R.erreur) return { html: vide(R.erreur), lecture: '' }
  // Largeur : le cercle au centre, la place des étiquettes de chaque côté (rayon réduit si l'écran est étroit).
  const A = R.A, [a, b] = axesChoisis(c, A), noms0 = [...R.act.map((v) => v.court), ...R.sup.map((s) => s.nom)]
  const lEtq = Math.min(30, Math.max(...noms0.map((t) => t.length))) * 6.6 + 18, Lg = Math.min(W, 900)
  const r = Math.max(90, Math.min(250, Lg / 2 - lEtq)), S = 2 * r + 80, cx = Lg / 2, cy = S / 2
  const melange = (t) => { const d = [156, 162, 171], f = [0, 85, 247]; return `rgb(${d.map((v, i) => Math.round(v + (f[i] - v) * t)).join(',')})` }
  const fleches = R.act.map((v, j) => ({ nom: v.court, x: A.charges[j][a], y: A.charges[j][b], q: A.cos2[j][a] + A.cos2[j][b], sup: false }))
    .concat(R.sup.map((s) => ({ nom: s.nom, x: s.r[a], y: s.r[b], q: s.r[a] ** 2 + s.r[b] ** 2, sup: true })))
  const etq = espacerEtiquettes(fleches.map((f) => { const L = Math.hypot(f.x, f.y) || 1, px = cx + r * f.x + 10 * f.x / L, py = cy - r * f.y - 10 * f.y / L; return { f, x: px, y: py + 4, cote: f.x >= 0 ? 1 : -1 } }))
  const id = `fl${a}${b}`
  const html = `<svg width="${Lg}" height="${S}" viewBox="0 0 ${Lg} ${S}">
    <defs><marker id="${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="context-stroke"/></marker></defs>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="#fbfcfd" stroke="#c9cdd3"/><circle cx="${cx}" cy="${cy}" r="${r / 2}" fill="none" stroke="#e3e6ea" stroke-dasharray="4 4"/>
    <line x1="${cx - r - 8}" x2="${cx + r + 8}" y1="${cy}" y2="${cy}" stroke="#c9cdd3"/><line x1="${cx}" x2="${cx}" y1="${cy - r - 8}" y2="${cy + r + 8}" stroke="#c9cdd3"/>
    <text x="${cx + r + 6}" y="${cy - 8}" text-anchor="end" font-size="12" font-weight="700" fill="#3d434c">${nomAxe(A, a)}</text>
    <text x="${cx + 8}" y="${cy - r - 10}" font-size="12" font-weight="700" fill="#3d434c">${nomAxe(A, b)}</text>
    ${etq.map(({ f, x, y }) => { const coul = f.sup ? '#8a9099' : melange(Math.min(1, f.q))
      return `<line x1="${cx}" y1="${cy}" x2="${cx + r * f.x}" y2="${cy - r * f.y}" stroke="${coul}" stroke-width="${f.sup ? 1.4 : 2.2}" ${f.sup ? 'stroke-dasharray="5 4"' : ''} marker-end="url(#${id})"><title>${echapper(f.nom)}${f.sup ? ' (supplémentaire)' : ''} : r = ${nf(f.x, 3)} avec F${a + 1}, ${nf(f.y, 3)} avec F${b + 1} · qualité (cos²) ${nf(f.q, 3)}</title></line>
        <text x="${x}" y="${y}" text-anchor="${f.x >= 0 ? 'start' : 'end'}" font-size="11.5" ${f.sup ? 'font-style="italic" fill="#8a9099"' : 'font-weight="600" fill="#17181a"'}>${echapper(f.nom.length > 30 ? f.nom.slice(0, 29) + '…' : f.nom)}</text>` }).join('')}</svg>
    <div class="ind-legende"><span><b style="color:#0055f7">flèche bleue</b> : variable active bien représentée (cos² proche de 1)</span><span><b style="color:#9ca2ab">grise</b> : mal représentée sur ce plan</span><span><i>pointillés en italique</i> : variable supplémentaire (ne construit pas les axes)</span></div>`
  return { options: optionsAxes(c, A), html,
    lecture: `chaque flèche est une variable ; ses coordonnées sont ses <b>corrélations</b> avec les deux axes. Une flèche <b>longue</b>, proche du cercle, est bien résumée par ce plan ; une flèche courte (dans le cercle pointillé de rayon 0,5) l’est mal et ne doit pas être interprétée ici. Deux flèches qui pointent <b>dans le même sens</b> : variables corrélées positivement ; <b>opposées</b> : corrélées négativement ; à <b>angle droit</b> : indépendantes. Une variable proche d’un axe donne son sens à cet axe. Les variables <b>supplémentaires</b> (en pointillés) sont seulement projetées : elles aident à interpréter les axes sans les influencer.` }
}
// Ellipse de confiance à 95 % du barycentre d'un groupe : covariance des coordonnées ÷ n_g, rayon √5,991 (χ² à 2 ddl).
function ellipse(pts, x, y) {
  const n = pts.length; if (n < 4) return ''
  const mx = pts.reduce((s, p) => s + p[0], 0) / n, my = pts.reduce((s, p) => s + p[1], 0) / n
  let sxx = 0, syy = 0, sxy = 0; for (const [u, v] of pts) { sxx += (u - mx) ** 2; syy += (v - my) ** 2; sxy += (u - mx) * (v - my) }
  sxx /= (n - 1) * n; syy /= (n - 1) * n; sxy /= (n - 1) * n
  const t = (sxx + syy) / 2, d = Math.sqrt(((sxx - syy) / 2) ** 2 + sxy ** 2), l1 = t + d, l2 = Math.max(0, t - d), th = Math.atan2(l1 - sxx, sxy || 1e-12), k = Math.sqrt(5.991)
  return Array.from({ length: 49 }, (_, i) => { const w = i / 48 * 2 * Math.PI, u = k * Math.sqrt(l1) * Math.cos(w), v = k * Math.sqrt(l2) * Math.sin(w); return `${i ? 'L' : 'M'}${x(mx + u * Math.cos(th) - v * Math.sin(th)).toFixed(1)},${y(my + u * Math.sin(th) + v * Math.cos(th)).toFixed(1)}` }).join('') + 'Z'
}
function rendreAcpIndividus(c, W, H) {
  const R = preparerAcp(c); if (R.erreur) return { html: vide(R.erreur), lecture: '' }
  const A = R.A, [a, b] = axesChoisis(c, A)
  if (!R.quali.some((q) => q.k === c.opts.acpGroupe)) c.opts.acpGroupe = R.quali[0]?.k ?? ''
  const Q = R.quali.find((q) => q.k === c.opts.acpGroupe), mods = Q ? Q.mods.slice(0, PALETTE.length) : []
  const couleurDe = new Map(); mods.forEach((m, i) => m.t.forEach((t) => couleurDe.set(t, i)))
  // À gauche : tous les patients (même échelle sur les deux axes). À droite : zoom sur les barycentres des
  // groupes et leurs ellipses de confiance, qui sont sinon tassés près du centre.
  const xs = A.scores.map((s) => s[a]), ys = A.scores.map((s) => s[b]), lx = Math.max(...xs.map(Math.abs)) * 1.08 || 1, ly = Math.max(...ys.map(Math.abs)) * 1.08 || 1
  const W2 = W >= 780 ? Math.floor((W - 14) / 2) : W, H2 = Math.max(H, 420), pas = Math.max(1, Math.floor(A.n / 3000))
  const g1 = cadre({ W: W2, H: H2, xmin: -lx, xmax: lx, ymin: -ly, ymax: ly, titreX: nomAxe(A, a), titreY: nomAxe(A, b) })
  const croix = (x, y, lx2, ly2, Hh, Ww) => `<line x1="${x(0)}" x2="${x(0)}" y1="12" y2="${Hh - 40}" stroke="#9ca2ab" stroke-dasharray="4 3"/><line x1="${x(-lx2)}" x2="${x(lx2)}" y1="${y(0)}" y2="${y(0)}" stroke="#9ca2ab" stroke-dasharray="4 3"/>`
  const ellipses = (x, y, opa) => mods.map((m, i) => `<path d="${ellipse(m.t.map((t) => [A.scores[t][a], A.scores[t][b]]), x, y)}" fill="${PALETTE[i]}" fill-opacity="${opa}" stroke="${PALETTE[i]}" stroke-width="1.6"/>`).join('')
  const nuage = `<svg width="${W2}" height="${H2}" viewBox="0 0 ${W2} ${H2}">${g1.fond}${croix(g1.x, g1.y, lx, ly, H2)}
    ${A.scores.filter((_, t) => t % pas === 0).map((s, i) => { const t = i * pas, g = couleurDe.get(t), coul = g === undefined ? '#b8bdc5' : PALETTE[g]
      return `<circle cx="${g1.x(s[a]).toFixed(1)}" cy="${g1.y(s[b]).toFixed(1)}" r="3.1" fill="${coul}" fill-opacity=".45"><title>${g === undefined ? '' : `${echapper(String(mods[g].m))} · `}${R.act.map((v) => `${echapper(v.court)} : ${nf(v.brut[R.lignes[t]])}`).join(' · ')}</title></circle>` }).join('')}
    ${ellipses(g1.x, g1.y, 0.06)}</svg>`
  // Zoom : bornes = barycentres et ellipses ; étiquettes écartées verticalement si elles se touchent.
  const ext = mods.flatMap((m) => { const n0 = m.t.length, sx = Math.sqrt(A.valeurs[a] / n0) * 2.6, sy = Math.sqrt(A.valeurs[b] / n0) * 2.6; return [[m.coord[a] - sx, m.coord[b] - sy], [m.coord[a] + sx, m.coord[b] + sy]] })
  const zx = Math.max(0.3, ...ext.map((p) => Math.abs(p[0]))) * 1.15, zy = Math.max(0.3, ...ext.map((p) => Math.abs(p[1]))) * 1.15
  const g2 = cadre({ W: W2, H: H2, mr: 120, xmin: -zx, xmax: zx, ymin: -zy, ymax: zy, titreX: `${nomAxe(A, a)} — zoom`, titreY: nomAxe(A, b) })
  const etq = mods.map((m, i) => ({ i, x: g2.x(m.coord[a]) + 11, y: g2.y(m.coord[b]) - 6, t: String(m.m).length > 24 ? String(m.m).slice(0, 23) + '…' : String(m.m) })).sort((p, q) => p.y - q.y)
  for (let it = 0; it < 30; it++) for (let i = 0; i < etq.length; i++) for (let j = i + 1; j < etq.length; j++) { const p = etq[i], q = etq[j]; if (Math.abs(p.y - q.y) < 14 && Math.min(p.x + p.t.length * 6.8, q.x + q.t.length * 6.8) > Math.max(p.x, q.x)) { if (p.y <= q.y) { p.y -= 3; q.y += 4 } else { q.y -= 3; p.y += 4 } } }
  const zoom = `<svg width="${W2}" height="${H2}" viewBox="0 0 ${W2} ${H2}">${g2.fond}${croix(g2.x, g2.y, zx, zy, H2)}${ellipses(g2.x, g2.y, 0.1)}
    ${mods.map((m, i) => `<path d="M${g2.x(m.coord[a])},${g2.y(m.coord[b]) - 8}l8,8l-8,8l-8,-8z" fill="${PALETTE[i]}" stroke="#fff" stroke-width="1.5"><title>${echapper(String(m.m))} (n = ${m.n}) · v-test F${a + 1} = ${nf(m.vtest[a], 2)} · F${b + 1} = ${nf(m.vtest[b], 2)}</title></path>`).join('')}
    ${etq.map((e) => { const m = mods[e.i], ancre = g2.y(m.coord[b]); return `${Math.abs(e.y + 6 - ancre) > 8 ? `<line x1="${g2.x(m.coord[a]) + 6}" y1="${ancre}" x2="${e.x - 2}" y2="${e.y - 4}" stroke="${PALETTE[e.i]}" stroke-width=".8"/>` : ''}<text x="${e.x}" y="${e.y}" font-size="11.5" font-weight="700" fill="${PALETTE[e.i]}" paint-order="stroke" stroke="#fff" stroke-width="3">${echapper(e.t)}</text>` }).join('')}</svg>`
  const html = `<div class="ind-deux"><div>${nuage}</div><div>${mods.length ? zoom : ''}</div></div>
    ${mods.length ? `<div class="ind-legende">${mods.map((m, i) => `<span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${PALETTE[i]};margin-right:4px"></i>${echapper(String(m.m))} (${m.n})</span>`).join('')}${Q.mods.length > mods.length || A.n > couleurDe.size ? '<span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#b8bdc5;margin-right:4px"></i>non renseigné / autres</span>' : ''}</div>` : ''}`
  return { options: `${optionsAxes(c, A)}${R.quali.length ? libelle('Couleur selon', choix('acpGroupe', c.opts.acpGroupe, R.quali.map((q) => [q.k, q.nom]))) : ''}`, html,
    lecture: `<b>à gauche</b>, chaque point est un <b>patient</b>, placé selon ses coordonnées sur les deux axes ; deux patients proches ont des profils semblables pour l’ensemble des variables actives. Le sens des axes se lit sur le <b>cercle des corrélations</b> (un patient à droite a des valeurs élevées des variables dont la flèche pointe à droite). <b>À droite</b>, zoom sur le centre : les <b>losanges</b> sont les barycentres des groupes (variable qualitative <b>supplémentaire</b>, qui ne construit pas les axes) et les <b>ellipses</b> leur zone de confiance à 95 % ; deux ellipses qui ne se recouvrent pas indiquent des groupes significativement différents sur ce plan. Les barycentres sont toujours plus proches du centre que les patients : c’est une moyenne. Survolez un point pour ses valeurs, un losange pour sa valeur-test.` }
}
// ── Vue 3D : patients et variables dans l'espace F1 × F2 × F3, que l'on fait tourner à la souris ──
// Projection orthogonale (pas de perspective : les distances restent comparables), dessinée sur un canvas ;
// tri par profondeur (les points du fond sont dessinés d'abord, plus petits et plus pâles).
// Les flèches des variables sont leurs corrélations avec les trois axes, à l'échelle du nuage (biplot).
const VUES3D = new Map()
function rendreAcp3D(c, W, H) {
  const R = preparerAcp(c); if (R.erreur) return { html: vide(R.erreur), lecture: '' }
  const A = R.A; if (A.p < 3) return { html: vide('Il faut au moins trois variables actives pour une vue en trois dimensions.'), lecture: '' }
  if (!R.quali.some((q) => q.k === c.opts.acp3dGroupe)) c.opts.acp3dGroupe = R.quali.find((q) => q.k === 'tranche')?.k ?? R.quali[0]?.k ?? ''
  const Q = R.quali.find((q) => q.k === c.opts.acp3dGroupe), mods = Q ? Q.mods.slice(0, PALETTE.length) : []
  const groupe = new Map(); mods.forEach((m, i) => m.t.forEach((t) => groupe.set(t, i)))
  // Échelle : 98e centile des distances au centre (quelques patients extrêmes ne doivent pas tout écraser).
  const r = A.scores.map((s) => Math.hypot(s[0], s[1], s[2])).sort((a, b) => a - b), L = r[Math.floor(0.98 * (r.length - 1))] || 1
  const id = `v3d${VUES3D.size}`
  VUES3D.set(id, {
    L, axes: [0, 1, 2].map((i) => `F${i + 1} (${nf(A.inertie[i], 1)} %)`),
    groupes: mods.map((m, i) => ({ nom: String(m.m), couleur: PALETTE[i], n: m.n })),
    points: A.scores.map((s, t) => ({ p: [s[0], s[1], s[2]], g: groupe.get(t) ?? -1, info: `${groupe.has(t) ? `${String(mods[groupe.get(t)].m)} · ` : ''}${R.act.map((v) => `${v.court} : ${nf(v.brut[R.lignes[t]])}`).join(' · ')}` })),
    fleches: c.opts.acp3dFleches !== false ? R.act.map((v, j) => ({ nom: v.court, p: [A.charges[j][0], A.charges[j][1], A.charges[j][2]].map((u) => u * L) })) : [],
    centres: mods.map((m, i) => ({ g: i, p: [m.coord[0], m.coord[1], m.coord[2]] })),
    pointsDefaut: false,
  })
  const H3 = Math.max(460, Math.min(H || 560, 680))
  // Lecture en clair : le sens de chaque axe (variable la plus corrélée de chaque côté) et la position de
  // chaque groupe (axes où sa valeur-test dépasse 1,96). Recalculée à chaque saisie.
  const sens = [0, 1, 2].map((k) => {
    const v = R.act.map((x, j) => ({ nom: x.court.split(' (')[0].toLowerCase(), r: A.charges[j][k] })).sort((a, b) => Math.abs(b.r) - Math.abs(a.r))
    const pos = v.find((x) => x.r > 0.3), neg = v.find((x) => x.r < -0.3)
    return { pos: pos?.nom, neg: neg?.nom }
  })
  // ↑ = valeurs plutôt élevées de la variable, ↓ = plutôt basses ; une variable n'est citée qu'une fois.
  const cote = (k, signe) => (signe > 0 ? sens[k].pos ? `${sens[k].pos} ↑` : sens[k].neg ? `${sens[k].neg} ↓` : null : sens[k].neg ? `${sens[k].neg} ↑` : sens[k].pos ? `${sens[k].pos} ↓` : null)
  const phrases = mods.map((m, i) => {
    const vus = new Set(), traits = [0, 1, 2].filter((k) => Math.abs(m.vtest[k]) > 1.96).sort((a, b) => Math.abs(m.vtest[b]) - Math.abs(m.vtest[a]))
      .map((k) => cote(k, m.vtest[k])).filter((t) => t && !vus.has(t.slice(0, -2)) && vus.add(t.slice(0, -2)))
    return `<li><i style="background:${PALETTE[i]}"></i><b>${echapper(String(m.m))}</b> (${m.n}) : ${traits.length ? traits.join(', ') : 'proche de la moyenne, aucun trait marqué'}</li>`
  })
  const axes = [0, 1, 2].map((k) => `<li><b>F${k + 1}</b> (${nf(A.inertie[k], 1)} %) : ${sens[k].pos ? `vers le haut / la droite, ${sens[k].pos}` : '—'}${sens[k].neg ? ` ; à l’opposé, ${sens[k].neg}` : ''}</li>`)
  const resume = `<div class="v3d-resume"><div><div class="v3d-resume-k">Ce que veulent dire les axes</div><ul>${axes.join('')}</ul></div>
    ${mods.length ? `<div><div class="v3d-resume-k">Ce qui distingue chaque groupe <span style="text-transform:none;font-weight:500">(↑ plutôt élevé · ↓ plutôt bas)</span></div><ul class="v3d-groupes">${phrases.join('')}</ul></div>` : ''}</div>`
  return { options: `${R.quali.length ? libelle('Groupes (couleur)', choix('acp3dGroupe', c.opts.acp3dGroupe, R.quali.map((q) => [q.k, q.nom]))) : ''}
      <label class="ind-case"><input type="checkbox" data-opt="acp3dFleches" ${c.opts.acp3dFleches !== false ? 'checked' : ''}>Flèches des variables</label>`,
    html: cadre3D(id, H3, ['F1 × F2', 'F1 × F3', 'F2 × F3']) + resume,
    lecture: `la vue s’ouvre <b>simplifiée</b> : seulement les <b>groupes</b> (ellipse et barycentre de chacun) et les <b>flèches</b> des variables ; le cadre sous la vue dit en clair ce que signifie chaque axe et ce qui distingue chaque groupe (seuls les écarts significatifs, valeur-test |v| > 1,96, sont cités). Le bouton <b>● Patients</b> ajoute les patients un par un. Chaque point est un <b>patient</b>, placé selon ses coordonnées sur les trois premiers axes (F1 ${nf(A.inertie[0], 1)} %, F2 ${nf(A.inertie[1], 1)} %, F3 ${nf(A.inertie[2], 1)} % : ${nf(A.inertie[0] + A.inertie[1] + A.inertie[2], 1)} % de l’information à eux trois). <b>Glissez</b> pour faire tourner le nuage, <b>molette</b> pour zoomer, <b>double-clic</b> pour revenir ; les boutons en haut à droite mettent le nuage « à plat » sur un des trois plans (ce sont ces vues qu’on met dans le mémoire imprimé). Les <b>flèches</b> sont les variables : un patient situé du côté d’une flèche a des valeurs élevées de cette variable. Chaque <b>groupe</b> (couleur) a son <b>ellipse</b> (où se trouvent la plupart de ses patients, sous l’angle choisi) et son <b>barycentre</b> (gros disque, relié au sol par un fil pour lire sa hauteur). Des ellipses séparées = des profils différents ; superposées = des groupes qui se ressemblent. <b>Cliquez un groupe dans la légende</b> pour l’isoler, <b>⟳ Rotation</b> pour faire tourner le nuage tout seul : la profondeur se lit bien mieux en mouvement. Les points du fond sont plus petits et plus pâles ; les patients des autres groupes restent en gris clair. Si le 3e axe n’est pas retenu par l’analyse parallèle (voir l’éboulis), la profondeur montre surtout du bruit : lisez alors d’abord le plan F1 × F2.` }
}
const VUES_FIXES = { iso: [-0.62, 0.38], face: [0, 0], dessus: [0, Math.PI / 2], cote: [Math.PI / 2, 0] }
// Cadre commun des vues 3D : canvas, bulle, barre d'outils (plans à plat, rotation, ellipses) et légende cliquable.
// Données (VUES3D) : { L (demi-étendue), axes [3 noms], bornes [[min, max] texte] facultatif,
//   points [{p, g, info}], groupes [{nom, couleur, n}], fleches [{nom, p}], centres [{p, g}],
//   plan [[p1, p2] segments], halos (ellipses des groupes, vrai par défaut) }.
function cadre3D(id, H, plans) {
  const d = VUES3D.get(id), outil = (attr, t, titre) => `<button type="button" class="v3d-btn" ${attr} title="${titre}">${t}</button>`
  return `<div class="v3d" data-vue3d="${id}"><div class="v3d-scene">
    <canvas style="height:${H}px" aria-label="Graphique en trois dimensions, à faire tourner à la souris"></canvas>
    <div class="ind-bulle" style="display:none"></div>
    <div class="v3d-outils">
      ${[['face', plans[0]], ['dessus', plans[1]], ['cote', plans[2]], ['iso', 'Vue 3D']].map(([k, t]) => outil(`data-vue3d-vue="${k}"`, t, `Vue ${t}`)).join('')}
      <span class="v3d-sep"></span>
      ${outil('data-vue3d-rot', '⟳ Rotation', 'Faire tourner le nuage tout seul (aide à voir la profondeur)')}
      ${d.groupes.length ? outil(`data-vue3d-pts aria-pressed="${d.pointsDefaut !== false}"`, '● Patients', 'Afficher ou masquer les patients (sans eux : seulement les groupes, plus lisible)') : ''}
      ${d.groupes.length && d.halos !== false ? outil('data-vue3d-halos aria-pressed="true"', '◯ Ellipses', 'Afficher ou masquer l’ellipse de chaque groupe') : ''}
    </div>
    <div class="v3d-aide">Glisser : tourner · molette : zoom · double-clic : vue de départ</div>
    </div>
    ${d.groupes.length ? `<div class="v3d-legende">${d.groupes.map((gr, i) => `<button type="button" data-vue3d-g="${i}" title="Cliquer pour isoler ce groupe ; recliquer pour tout revoir"><i style="background:${gr.couleur}"></i>${echapper(gr.nom)}${gr.n ? ` <small>${gr.n}</small>` : ''}</button>`).join('')}</div>` : ''}
  </div>`
}
// Nuage 3D de trois variables quelconques : chaque axe est ramené à [−1, 1] (min → −1, max → +1),
// avec ses bornes réelles écrites au bout ; léger décalage (jitter) pour les variables à peu de valeurs.
function nuage3D({ x, y, z, noms, groupesDe, groupes = [], infos, plan, halos }) {
  const idx = x.map((_, i) => i).filter((i) => [x, y, z].every((v) => Number.isFinite(v[i])))
  const bornes = [x, y, z].map((v) => { const p = idx.map((i) => v[i]); return [Math.min(...p), Math.max(...p)] })
  const discret = [x, y, z].map((v) => new Set(idx.map((i) => v[i])).size <= 15)
  const norm = (k, v) => { const [a, b] = bornes[k]; return b > a ? 2 * (v - a) / (b - a) - 1 : 0 }
  const jit = (i, k) => (discret[k] ? (((i * 7919 + k * 104729) % 1000) / 1000 - 0.5) * 0.07 : 0)
  const id = `v3d${VUES3D.size}`
  const points = idx.map((i) => ({ p: [norm(0, x[i]) + jit(i, 0), norm(1, y[i]) + jit(i, 1), norm(2, z[i]) + jit(i, 2)], g: groupesDe ? groupesDe[i] : 0, info: infos?.[i] ?? `${noms[0]} : ${nf(x[i])} · ${noms[1]} : ${nf(y[i])} · ${noms[2]} : ${nf(z[i])}` }))
  const centres = halos === false ? [] : groupes.map((_, gi) => { const m = points.filter((p) => p.g === gi); return m.length >= 5 ? { g: gi, p: [0, 1, 2].map((j) => m.reduce((s, q) => s + q.p[j], 0) / m.length) } : null }).filter(Boolean)
  VUES3D.set(id, { L: 1.15, axes: noms, bornes: bornes.map(([a, b]) => [nf(a, 1), nf(b, 1)]), points, groupes, fleches: [], centres, plan: plan ? plan(norm, bornes) : [], halos })
  return { id, n: idx.length }
}
// Dessin : légère perspective, boîte et sol quadrillé (repères de profondeur), ellipse de chaque groupe
// (1,5 écart-type des points projetés, recalculée à chaque angle), points triés par profondeur avec un
// liseré blanc, barycentres reliés au sol par un fil, étiquettes des groupes, flèches des variables.
function installer3D(racine) {
  racine.querySelectorAll('[data-vue3d]').forEach((bloc) => {
    const d = VUES3D.get(bloc.dataset.vue3d), cv = bloc.querySelector('canvas'), bulle = bloc.querySelector('.ind-bulle'); if (!d || !cv) return
    const etatV = { yaw: VUES_FIXES.iso[0], pitch: VUES_FIXES.iso[1], zoom: 1, focus: null, halos: d.halos !== false, rot: false, points: d.pointsDefaut !== false }
    const coul = (g) => (g >= 0 && d.groupes[g] ? d.groupes[g].couleur : d.groupes.length ? '#c3c7cd' : COUL.bleu)
    const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})` }
    let proj = []
    const dessiner = () => {
      const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr) }
      const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h)
      const cy = Math.cos(etatV.yaw), sy = Math.sin(etatV.yaw), cp = Math.cos(etatV.pitch), sp = Math.sin(etatV.pitch), L = d.L
      const k = etatV.zoom * Math.min(w * 0.82, h) * 0.36 / L, ox = w / 2, oy = h / 2 + 14
      // x → droite, y → haut, z → profondeur ; perspective douce : ce qui est devant est un peu plus grand.
      const P = ([x, y, z]) => { const x1 = x * cy - z * sy, z1 = x * sy + z * cy, y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp, s = 1 / (1 - 0.16 * z2 / (L * 1.8)); return [ox + k * x1 * s, oy - k * y2 * s, z2, s] }
      const ligne = (a, b, style, lw = 1, tirets = []) => { const p = P(a), q = P(b); g.strokeStyle = style; g.lineWidth = lw; g.setLineDash(tirets); g.beginPath(); g.moveTo(p[0], p[1]); g.lineTo(q[0], q[1]); g.stroke(); g.setLineDash([]) }
      // Sol quadrillé (y = −L) et arêtes de la boîte
      for (let i = 0; i <= 6; i++) { const t = -L + (2 * L * i) / 6; ligne([t, -L, -L], [t, -L, L], '#eef0f3'); ligne([-L, -L, t], [L, -L, t], '#eef0f3') }
      const C = [-L, L]; for (const a of C) for (const b of C) { ligne([-L, a, b], [L, a, b], '#e3e6ea'); ligne([a, -L, b], [a, L, b], '#e3e6ea'); ligne([a, b, -L], [a, b, L], '#e3e6ea') }
      // Axes passant par l'origine, nommés au bout positif
      g.textAlign = 'center'
      for (const [u, i] of [[[1, 0, 0], 0], [[0, 1, 0], 1], [[0, 0, 1], 2]]) {
        const a = u.map((v) => -v * L), b = u.map((v) => v * L), pa = P(a), pb = P(b)
        ligne(a, b, '#aeb3ba', 1.2)
        if (Math.hypot(pb[0] - pa[0], pb[1] - pa[1]) > 40) {
          const lx = pb[0] + (pb[0] - ox) * 0.06, ly = pb[1] + (pb[1] - oy) * 0.06
          g.font = '700 12px system-ui, sans-serif'; g.lineWidth = 4; g.strokeStyle = 'rgba(255,255,255,.95)'; g.strokeText(d.axes[i], lx, ly - 6); g.fillStyle = '#3d434c'; g.fillText(d.axes[i], lx, ly - 6)
          if (d.bornes) { g.font = '11px system-ui, sans-serif'; g.fillStyle = '#8a9099'; g.fillText(d.bornes[i][0], pa[0], pa[1] + 15); g.fillText(d.bornes[i][1], pb[0], pb[1] + 15) }
        }
      }
      if (d.plan?.length) for (const [a0, b0] of d.plan) ligne(a0, b0, 'rgba(215,38,61,.38)', 1)
      proj = d.points.map((pt) => { const [x, y, z, s] = P(pt.p); return { x, y, z, s, pt } })
      // Ellipses des groupes (sur les positions projetées)
      if (etatV.halos && d.groupes.length) d.groupes.forEach((gr, gi) => {
        if (etatV.focus !== null && etatV.focus !== gi) return
        const m = proj.filter((q) => q.pt.g === gi); if (m.length < 5) return
        const mx = m.reduce((s, q) => s + q.x, 0) / m.length, my = m.reduce((s, q) => s + q.y, 0) / m.length
        let a = 0, b = 0, c = 0; for (const q of m) { a += (q.x - mx) ** 2; b += (q.y - my) ** 2; c += (q.x - mx) * (q.y - my) } a /= m.length; b /= m.length; c /= m.length
        const t = (a + b) / 2, dd = Math.sqrt(((a - b) / 2) ** 2 + c * c), l1 = t + dd, l2 = Math.max(0, t - dd), th = 0.5 * Math.atan2(2 * c, a - b)
        g.beginPath(); g.ellipse(mx, my, 1.5 * Math.sqrt(l1), 1.5 * Math.sqrt(l2), th, 0, 2 * Math.PI)
        g.fillStyle = rgba(gr.couleur, 0.09); g.fill(); g.strokeStyle = rgba(gr.couleur, 0.55); g.lineWidth = 1.4; g.stroke()
      })
      // Points du fond vers l'avant ; « autres » d'abord, plus discrets ; groupe isolé : les autres s'effacent.
      const zs = proj.map((q) => q.z), zmin = Math.min(...zs), zmax = Math.max(...zs)
      proj.sort((p1, p2) => ((p2.pt.g < 0) - (p1.pt.g < 0)) || p1.z - p2.z)
      for (const q of etatV.points ? proj : []) {
        const f = zmax > zmin ? (q.z - zmin) / (zmax - zmin) : 0.5, autre = q.pt.g < 0 && d.groupes.length, eteint = etatV.focus !== null && q.pt.g !== etatV.focus
        g.globalAlpha = eteint ? 0.06 : autre ? 0.18 + 0.2 * f : 0.5 + 0.45 * f
        g.beginPath(); g.arc(q.x, q.y, (autre ? 2.4 : 3.4) * q.s, 0, 2 * Math.PI); g.fillStyle = coul(q.pt.g); g.fill()
        if (!autre && !eteint) { g.lineWidth = 0.7; g.strokeStyle = 'rgba(255,255,255,.9)'; g.stroke() }
      }
      g.globalAlpha = 1
      // Barycentres : fil vertical jusqu'au sol, ombre au sol, disque cerclé de blanc et nom du groupe.
      const etiquettes = []
      for (const c0 of d.centres) {
        if (etatV.focus !== null && etatV.focus !== c0.g) continue
        const [x, y] = P(c0.p), sol = P([c0.p[0], -L, c0.p[2]]), cc = coul(c0.g)
        g.strokeStyle = rgba(cc, 0.6); g.lineWidth = 1; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x, y); g.lineTo(sol[0], sol[1]); g.stroke(); g.setLineDash([])
        g.fillStyle = rgba(cc, 0.35); g.beginPath(); g.ellipse(sol[0], sol[1], 6, 2.5, 0, 0, 2 * Math.PI); g.fill()
        g.beginPath(); g.arc(x, y, 8, 0, 2 * Math.PI); g.fillStyle = cc; g.fill(); g.lineWidth = 2.5; g.strokeStyle = '#fff'; g.stroke()
        g.beginPath(); g.arc(x, y, 9.5, 0, 2 * Math.PI); g.lineWidth = 1; g.strokeStyle = rgba(cc, 0.8); g.stroke()
        if (d.groupes[c0.g]) etiquettes.push({ x: x + 13, y: y - 10, t: d.groupes[c0.g].nom, cc })
      }
      etiquettes.sort((a, b) => a.y - b.y); for (let i = 1; i < etiquettes.length; i++) if (etiquettes[i].y - etiquettes[i - 1].y < 17 && Math.abs(etiquettes[i].x - etiquettes[i - 1].x) < 140) etiquettes[i].y = etiquettes[i - 1].y + 17
      g.font = '700 11.5px system-ui, sans-serif'; g.textAlign = 'left'
      for (const e of etiquettes) { const t = e.t.length > 26 ? e.t.slice(0, 25) + '…' : e.t, lw = g.measureText(t).width; g.fillStyle = 'rgba(255,255,255,.92)'; g.beginPath(); g.roundRect(e.x - 4, e.y - 11, lw + 8, 16, 4); g.fill(); g.fillStyle = e.cc; g.fillText(t, e.x, e.y + 1) }
      // Flèches des variables (biplot)
      if (d.fleches.length) {
        g.font = '600 12px system-ui, sans-serif'
        const o = P([0, 0, 0])
        for (const v of d.fleches) {
          const b = P(v.p), ang = Math.atan2(b[1] - o[1], b[0] - o[0]); if (Math.hypot(b[0] - o[0], b[1] - o[1]) < 8) continue
          g.strokeStyle = '#17181a'; g.fillStyle = '#17181a'; g.lineWidth = 1.8; g.beginPath(); g.moveTo(o[0], o[1]); g.lineTo(b[0], b[1]); g.stroke()
          g.beginPath(); g.moveTo(b[0], b[1]); g.lineTo(b[0] - 10 * Math.cos(ang - 0.38), b[1] - 10 * Math.sin(ang - 0.38)); g.lineTo(b[0] - 10 * Math.cos(ang + 0.38), b[1] - 10 * Math.sin(ang + 0.38)); g.closePath(); g.fill()
          g.textAlign = Math.cos(ang) >= 0 ? 'left' : 'right'; g.lineWidth = 4; g.strokeStyle = 'rgba(255,255,255,.95)'
          const tx = b[0] + 9 * Math.cos(ang), ty = b[1] + 9 * Math.sin(ang) + 4; g.strokeText(v.nom, tx, ty); g.fillText(v.nom, tx, ty)
        }
      }
    }
    // Rotation automatique (lente) : la profondeur se lit bien mieux en mouvement.
    let anim = null
    const tourner = () => { if (!etatV.rot || !document.body.contains(cv)) { anim = null; return } etatV.yaw += 0.006; dessiner(); anim = requestAnimationFrame(tourner) }
    const arreter = () => { etatV.rot = false; bloc.querySelector('[data-vue3d-rot]')?.setAttribute('aria-pressed', 'false') }
    let glisse = null
    cv.addEventListener('pointerdown', (e) => { arreter(); glisse = { x: e.clientX, y: e.clientY, yaw: etatV.yaw, pitch: etatV.pitch }; cv.setPointerCapture(e.pointerId); cv.style.cursor = 'grabbing' })
    cv.addEventListener('pointerup', () => { glisse = null; cv.style.cursor = 'grab' })
    cv.addEventListener('pointermove', (e) => {
      if (glisse) { etatV.yaw = glisse.yaw + (e.clientX - glisse.x) * 0.01; etatV.pitch = Math.max(-1.55, Math.min(1.55, glisse.pitch + (e.clientY - glisse.y) * 0.01)); bulle.style.display = 'none'; dessiner(); return }
      const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top
      let best = null, dmin = 64; for (const q of etatV.points ? proj : []) { if (etatV.focus !== null && q.pt.g !== etatV.focus) continue; const dd = (q.x - mx) ** 2 + (q.y - my) ** 2; if (dd < dmin) { dmin = dd; best = q } }
      if (best) { bulle.textContent = best.pt.info; Object.assign(bulle.style, { display: 'block', whiteSpace: 'normal', maxWidth: '300px', left: `${Math.min(mx + 14, cv.clientWidth - 310)}px`, top: `${my + 14}px` }) } else bulle.style.display = 'none'
    })
    cv.addEventListener('pointerleave', () => { bulle.style.display = 'none' })
    cv.addEventListener('wheel', (e) => { e.preventDefault(); etatV.zoom = Math.max(0.4, Math.min(6, etatV.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12))); dessiner() }, { passive: false })
    cv.addEventListener('dblclick', () => { arreter(); Object.assign(etatV, { yaw: VUES_FIXES.iso[0], pitch: VUES_FIXES.iso[1], zoom: 1 }); dessiner() })
    bloc.querySelectorAll('[data-vue3d-vue]').forEach((b) => (b.onclick = () => { arreter(); const [y0, p0] = VUES_FIXES[b.dataset.vue3dVue]; Object.assign(etatV, { yaw: y0, pitch: p0 }); dessiner() }))
    const pts = bloc.querySelector('[data-vue3d-pts]'); if (pts) pts.onclick = () => { etatV.points = !etatV.points; pts.setAttribute('aria-pressed', String(etatV.points)); dessiner() }
    const rot = bloc.querySelector('[data-vue3d-rot]'); if (rot) rot.onclick = () => { etatV.rot = !etatV.rot; rot.setAttribute('aria-pressed', String(etatV.rot)); if (etatV.rot && !anim) tourner() }
    const hal = bloc.querySelector('[data-vue3d-halos]'); if (hal) hal.onclick = () => { etatV.halos = !etatV.halos; hal.setAttribute('aria-pressed', String(etatV.halos)); dessiner() }
    bloc.querySelectorAll('[data-vue3d-g]').forEach((b) => (b.onclick = () => {
      const gi = +b.dataset.vue3dG; etatV.focus = etatV.focus === gi ? null : gi
      bloc.querySelectorAll('[data-vue3d-g]').forEach((x) => x.classList.toggle('eteint', etatV.focus !== null && +x.dataset.vue3dG !== etatV.focus)); dessiner()
    }))
    requestAnimationFrame(dessiner)
  })
}
function rendreAcpVariables(c) {
  const R = preparerAcp(c); if (R.erreur) return { html: vide(R.erreur), lecture: '' }
  const A = R.A, K = R.axes, seuil = 100 / A.p, ent = ['Variable']
  for (let k = 0; k < K; k++) ent.push(`r F${k + 1}`, `cos² F${k + 1}`, `Contrib. F${k + 1} (%)`)
  ent.push(`Qualité sur F1–F${K} (Σ cos²)`)
  const fort = (v, s) => (v >= s ? `<b>${nf(v, s > 1 ? 1 : 3)}</b>` : nf(v, s > 1 ? 1 : 3))
  const lignes = R.act.map((v, j) => { const l = [echapper(v.nom)]; let q = 0; for (let k = 0; k < K; k++) { const r = A.charges[j][k]; q += A.cos2[j][k]; l.push(`<span style="color:${r > 0 ? '#0047d1' : '#c01f33'}">${nf(r, 3)}</span>`, fort(A.cos2[j][k], 0.5), fort(A.contrib[j][k], seuil)) } l.push(nf(q, 3)); return l })
  const supp = R.sup.map((s) => { const l = [`<i>${echapper(s.nom)} (suppl.)</i>`]; let q = 0; for (let k = 0; k < K; k++) { q += s.r[k] ** 2; l.push(`<i>${nf(s.r[k], 3)}</i>`, nf(s.r[k] ** 2, 3), '—') } l.push(nf(q, 3)); return l })
  return { html: tableau(ent, [...lignes, ...supp], { hauteur: 460 }),
    lecture: `pour chaque variable et chacun des ${K} premiers axes : <b>r</b> = corrélation avec l’axe (bleu positif, rouge négatif) ; <b>cos²</b> = r², part de la variable représentée par l’axe (en gras si ≥ 0,5) ; <b>contribution</b> = part de l’axe due à la variable (somme 100 % par axe ; en gras si elle dépasse la contribution moyenne de ${nf(seuil, 1)} %). Ce sont les variables à forte contribution qui <b>donnent leur nom</b> à l’axe. La <b>qualité</b> (somme des cos²) dit si la variable est bien résumée par les axes retenus. Les variables <i>supplémentaires</i> ne contribuent pas : leur corrélation sert seulement à l’interprétation.` }
}
function rendreAcpModalites(c) {
  const R = preparerAcp(c); if (R.erreur) return { html: vide(R.erreur), lecture: '' }
  const A = R.A, K = Math.min(R.axes, 3), lignes = []
  for (const q of R.quali) for (const m of q.mods) {
    const sig = m.vtest.slice(0, K).some((v) => Math.abs(v) > 1.96), l = [echapper(q.nom), echapper(String(m.m)), m.n]
    for (let k = 0; k < K; k++) { const v = m.vtest[k]; l.push(nf(m.coord[k], 3), `<span style="${Math.abs(v) > 1.96 ? `font-weight:700;color:${v > 0 ? '#0047d1' : '#c01f33'}` : ''}">${nf(v, 2)}</span>`) }
    l.push(badge(sig, 'caractéristique', 'non')); lignes.push({ sig, f: Math.max(...m.vtest.slice(0, K).map(Math.abs)), l })
  }
  lignes.sort((a, b) => b.f - a.f)
  const ent = ['Variable', 'Modalité', 'n']; for (let k = 0; k < K; k++) ent.push(`Coord. F${k + 1}`, `v-test F${k + 1}`); ent.push('Conclusion')
  return { html: lignes.length ? tableau(ent, lignes.map((e) => e.l), { hauteur: 460 }) : vide('Pas de variable qualitative exploitable.'),
    lecture: `chaque modalité (cause, issue, tranche d’âge, sexe, quartier, mois…) est placée au <b>barycentre</b> de ses patients. La <b>valeur-test</b> mesure si ce barycentre s’écarte significativement de 0 sur l’axe : |v| > 1,96 ⇔ p < 0,05 (en <b style="color:#0047d1">bleu</b> côté positif, en <b style="color:#c01f33">rouge</b> côté négatif). C’est ainsi qu’on relie les axes, construits sur les mesures (âge, durée, montant…), aux <b>profils cliniques</b> : par exemple, si « Transfusion : Oui » est très positive sur F1 et que la durée y pointe aussi, F1 décrit les séjours lourds. Les modalités sont classées de la plus à la moins marquée.` }
}
function rendreAcpInterpretation(c) {
  const R = preparerAcp(c); if (R.erreur) return { html: vide(R.erreur), lecture: '' }
  const A = R.A, K = R.axes, liste = (t) => (t.length > 1 ? `${t.slice(0, -1).join(', ')} et ${t.at(-1)}` : t[0] ?? '')
  const verdict = A.bartlett.p < 0.05 && A.kmo >= 0.5
    ? `Le test de Bartlett est significatif (p ${fp(A.bartlett.p)}) et le KMO vaut ${nf(A.kmo, 2)} (${KAISER(A.kmo)}) : les variables partagent assez d’information pour que l’ACP ait un sens${A.kmo < 0.6 ? ', mais tout juste : les liens entre variables restent modestes, l’ACP décrit des tendances plus que des groupes nets' : ''}.`
    : `Attention : ${A.bartlett.p >= 0.05 ? `le test de Bartlett n’est pas significatif (p ${fp(A.bartlett.p)}), les variables sont presque indépendantes` : `le KMO vaut seulement ${nf(A.kmo, 2)} (${KAISER(A.kmo)})`} ; les axes résument peu de chose et doivent être interprétés avec prudence.`
  const paras = [verdict, `L’analyse parallèle retient <b>${A.retenus} axe(s)</b>, qui résument ${nf(A.inertie.slice(0, A.retenus).reduce((s, v) => s + v, 0), 1)} % de la variabilité des ${A.p} variables sur ${A.n} patients.`]
  for (let k = 0; k < K; k++) {
    const vars = R.act.map((v, j) => ({ nom: v.court, r: A.charges[j][k], ctr: A.contrib[j][k] })).filter((v) => v.ctr >= 100 / A.p || Math.abs(v.r) >= 0.5).sort((a, b) => Math.abs(b.r) - Math.abs(a.r))
    const pos = vars.filter((v) => v.r > 0).map((v) => `${echapper(v.nom)} (r = ${nf(v.r, 2)})`), neg = vars.filter((v) => v.r < 0).map((v) => `${echapper(v.nom)} (r = ${nf(v.r, 2)})`)
    const mods = R.quali.flatMap((q) => q.mods.filter((m) => Math.abs(m.vtest[k]) > 1.96).map((m) => ({ t: `${echapper(q.nom)} = ${echapper(String(m.m))}`, v: m.vtest[k] })))
    const mp = mods.filter((m) => m.v > 0).sort((a, b) => b.v - a.v).slice(0, 4).map((m) => `${m.t} (v = ${nf(m.v, 1)})`), mn = mods.filter((m) => m.v < 0).sort((a, b) => a.v - b.v).slice(0, 4).map((m) => `${m.t} (v = ${nf(m.v, 1)})`)
    const sens = pos.length && neg.length ? `oppose les patients à valeurs élevées de ${liste(pos)} (côté positif) à ceux à valeurs élevées de ${liste(neg)} (côté négatif)`
      : pos.length ? `augmente avec ${liste(pos)} : c’est un axe d’« intensité », les patients du côté positif cumulent des valeurs élevées de ces variables` : `est porté par ${liste(neg)} (côté négatif)`
    const sup = R.sup.filter((s) => Math.abs(s.r[k]) >= 0.3).map((s) => `${echapper(s.nom)} (r = ${nf(s.r[k], 2)})`)
    paras.push(`<b>Axe F${k + 1}</b> (${nf(A.inertie[k], 1)} %${k >= A.retenus ? ', au-delà du seuil de l’analyse parallèle : à lire avec prudence' : ''}) : il ${sens}.${mp.length || mn.length ? ` Profils associés : ${mp.length ? `côté positif ${liste(mp)}` : ''}${mp.length && mn.length ? ' ; ' : ''}${mn.length ? `côté négatif ${liste(mn)}` : ''}.` : ' Aucune modalité qualitative ne s’y distingue significativement.'}${sup.length ? ` Variables supplémentaires liées : ${liste(sup)}.` : ''}`)
  }
  const faibles = R.act.filter((_, j) => A.cos2[j].slice(0, K).reduce((s, v) => s + v, 0) < 0.3).map((v) => echapper(v.court))
  if (faibles.length) paras.push(`Mal résumée(s) par les axes retenus (qualité < 0,3) : ${liste(faibles)}. Ces variables varient de façon propre, indépendamment des autres : à étudier séparément (tests de groupes, régression).`)
  return { html: `<div class="ind-interp">${paras.map((p) => `<p style="margin:0 0 10px;line-height:1.55">${p}</p>`).join('')}</div>`,
    lecture: `texte produit automatiquement à partir des tableaux précédents : une variable est citée si sa contribution dépasse la moyenne (${nf(100 / A.p, 1)} %) ou si |r| ≥ 0,5 ; une modalité si |valeur-test| > 1,96. Le <b>signe</b> d’un axe est arbitraire (seules les oppositions comptent). À reformuler avec vos mots dans le mémoire, en gardant les chiffres.` }
}
function rendreCcf(c, W, H) {
  const k = Math.min(14, c.d.presents.length - 3), r = Sx.ccf(c.d.adm, c.d.presents, k), seuil = 1.96 / Math.sqrt(c.d.presents.length)
  return { html: barresZeroSvg({ W, H, valeurs: r, etiquettes: r.map((_, i) => `${i} j`), seuil, couleur: COUL.violet, titreY: 'Corrélation' }),
    lecture: `corrélation entre les <b>admissions d’il y a k jours</b> et les <b>présents d’aujourd’hui</b>. Les retards au-delà de la bande orange (± 1,96/√n) sont significatifs : ils disent pendant combien de jours une admission « pèse » sur l’occupation (lié à la durée de séjour). C’est l’argument pour donner au modèle les admissions des jours précédents.` }
}

// ── Séries temporelles : volatilité ──────────────────────────────────────────────────────
function rendreVolatilite(c, W, H) {
  const sc = serieChoisie(c, c.opts.serie), x = sc.x, m30 = moyenneMobile(x, 30), s30 = ecartMobile(x, 30)
  return { html: lignesSvg({ W, H, debutNum: c.d.debutNum, series: [{ nom: 'Écart-type mobile 7 j', valeurs: ecartMobile(x, 7), couleur: COUL.orange, epaisseur: 1.8 }, { nom: 'Écart-type mobile 30 j', valeurs: s30, couleur: COUL.rouge, epaisseur: 2.2 }, { nom: 'CV mobile 30 j (× 0,1 %)', valeurs: m30.map((m, i) => (m ? 10 * s30[i] / m : null)), couleur: COUL.violet, epaisseur: 1.5, pointille: '5 3' }], titreY: `Dispersion — ${sc.nom}` }),
    lecture: `l’<b>écart-type mobile</b> mesure, jour après jour, l’agitation de la série (${sc.nom.toLowerCase()}, choisie dans « Courbe jour par jour ») sur les 7 ou 30 derniers jours. Une volatilité qui monte = période plus imprévisible : les intervalles de prévision doivent s’élargir. Le <b>CV mobile</b> (écart-type ÷ moyenne, en dixièmes de %) compare l’agitation à niveau égal.` }
}

// ── Modèles de prévision (exploratoires : le modèle du mémoire reste le SVR de NERA) ───────
const SERIES_MODELE = [['presents', 'Enfants présents à minuit', true], ['taux', 'Taux d’occupation (%)', true], ['adm', 'Admissions par jour', true], ['sor', 'Sorties par jour', true], ['brut', 'Arrivées par jour (toute la saisie)', false]]
function serieModele(c) {
  const dispo = SERIES_MODELE.filter(([k, , occ]) => (!occ || !c.d.message) && (k !== 'taux' || c.lits) && (k !== 'brut' || c.brut))
  if (!dispo.some(([k]) => k === c.opts.mSerie)) c.opts.mSerie = dispo[0]?.[0]
  const cle = c.opts.mSerie
  if (!cle) return null
  if (cle === 'brut') return { cle, x: c.brut.x.slice(), debutNum: c.brut.debutNum, nom: 'Arrivées par jour', unite: '', dispo, coupe: 0 }
  // Fin de série incomplète : un enfant est inscrit dans le registre quelques jours après son entrée. Les
  // derniers jours saisis manquent donc des enfants entrés juste avant mais inscrits après la dernière page :
  // l'occupation y chute artificiellement et tire toutes les prévisions vers le bas. On retire ces jours
  // (95e centile du délai entrée → inscription, au moins 2 jours), sauf si l'utilisateur garde tout.
  const sc = serieChoisie(c, cle), coupe = c.opts.mQueue === 'tout' ? 0 : delaiInscription(), x = sc.x.slice(0, Math.max(21, sc.x.length - coupe))
  return { cle, x, debutNum: c.d.debutNum, nom: sc.nom, unite: sc.unite, dispo, coupe: sc.x.length - x.length }
}
// 95e centile du délai (en jours) entre l'entrée et l'inscription dans le registre, entre 2 et 10 jours.
let cacheDelai = null
function delaiInscription() {
  const r = registre(), cle = `${etat.service}|${etat.lignes.length}`; if (cacheDelai?.cle === cle) return cacheDelai.v
  const lire = (v) => lireDate(String(v ?? '').replace(/\s*\?+\s*$/, '').trim()), d = []
  for (const l of lignesService()) { const a = lire(l[r.dateReference]), b = lire(l.date_entree); if (a && b) { const g = jourNum(a.d) - jourNum(b.d); if (g >= 0 && g <= 30) d.push(g) } }
  d.sort((a, b) => a - b); const v = Math.min(10, Math.max(2, d.length ? d[Math.floor(0.95 * (d.length - 1))] : 2))
  cacheDelai = { cle, v }; return v
}
const optionsModele = (c, s) => `${libelle('Série', choix('mSerie', s.cle, s.dispo.map(([k, l]) => [k, k === 'presents' ? nomPresents() : l])))}${libelle('Horizon', choix('h', c.opts.h, [[7, '7 jours'], [14, '14 jours'], [30, '30 jours']]))}${libelle('Validation', choix('pv', c.opts.pv, [[15, '15 % finaux'], [20, '20 % finaux'], [30, '30 % finaux']]))}${s.cle === 'brut' ? '' : libelle('Fin de série', choix('mQueue', c.opts.mQueue ?? 'auto', [['auto', `sans les ${delaiInscription()} derniers jours (inscriptions en retard)`], ['tout', 'jusqu’au dernier jour saisi']]))}`
const ORDRE_TXT = (o) => `(${o.p},${o.d},${o.q})(${o.P},${o.D},${o.Q})₇`
// Tous les modèles, estimés sur l'apprentissage (t < fin), évalués un pas en avant sur la validation (t ≥ fin).
// Famille des lissages exponentiels (statistiques.js) : du plus simple au plus complet.
const LISSAGES = ['ses', 'theta', 'holtLineaire', 'holt', 'sesSaisonnier', 'holtWinters', 'holtWintersMult']
function modelesDe(c) {
  if (c._mod) return c._mod
  const s = serieModele(c); if (!s) return (c._mod = { erreur: 'Aucune série disponible.' })
  const x = s.x, n = x.length, fin = Math.round(n * (1 - c.opts.pv / 100))
  if (n < 42) return (c._mod = { s, erreur: `Série trop courte (${n} jours) : il faut au moins 42 jours saisis pour estimer et valider des modèles.` })
  let somme = 0; for (let t = 7; t < fin; t++) somme += Math.abs(x[t] - x[t - 7]); const echelle = somme / Math.max(1, fin - 7)
  const res = []
  for (const k of ['naif', 'saisonnierNaif', 'moyenne', 'moyenneMobile', ...LISSAGES, 'ar']) {
    const m = Sx.modeles[k](x, fin); if (m) res.push({ cle: k, m, met: Sx.metriques(x.slice(fin), m.unPas.slice(fin), echelle) })
  }
  const sar = Sx.sarima(x, c.opts.sarima, fin); if (sar) res.push({ cle: 'sarima', m: sar, met: Sx.metriques(x.slice(fin), sar.unPas.slice(fin), echelle) })
  res.forEach((r) => { r.err = x.slice(fin).map((v, i) => v - r.m.unPas[fin + i]) })
  res.sort((a, b) => a.met.mae - b.met.mae)
  return (c._mod = { s, x, n, fin, res, echelle })
}
// Les mêmes modèles ré-estimés sur toute la série, pour prévoir les h jours suivants.
function previsionsDe(c) {
  if (c._prev) return c._prev
  const M = modelesDe(c); if (M.erreur) return (c._prev = M)
  const x = M.x, h = +c.opts.h, sorties = []
  for (const k of ['saisonnierNaif', ...LISSAGES, 'ar']) { const m = Sx.modeles[k](x); if (m) sorties.push({ cle: k, nom: m.nom, p: m.prevoir(h) }) }
  const sar = Sx.sarima(x, c.opts.sarima)
  return (c._prev = { ...M, h, sorties, sar, psar: sar?.prevoir(h), isar: sar?.intervalle(h) })
}
function rendreStationnarite(c) {
  const s = serieModele(c); if (!s) return { html: vide('Aucune série disponible.'), lecture: '' }
  const options = optionsModele(c, s), x = s.x
  if (x.length < 30) return { options, html: vide(`Série trop courte (${x.length} jours).`), lecture: '' }
  const diff = (z, k) => z.slice(k).map((v, i) => v - z[i])
  const variantes = [['Série brute yₜ', x], ['Différence première Δyₜ = yₜ − yₜ₋₁', diff(x, 1)], ['Différence saisonnière Δ₇yₜ = yₜ − yₜ₋₇', diff(x, 7)], ['Les deux : ΔΔ₇yₜ', diff(diff(x, 7), 1)]]
  const lignes = variantes.map(([nom, z]) => {
    const a = Sx.adf(z), k = Sx.kpss(z), lb7 = Sx.ljungBox(z, 7), lb14 = Sx.ljungBox(z, Math.min(14, Math.floor(z.length / 4)))
    return { a, k, l: [nom, z.length, a ? `${nf(a.stat, 2)} <small class="text-muted">(${a.retards} ret.)</small>` : '—', a ? badge(a.stationnaire5, 'stationnaire', 'racine unitaire') : '—', `${nf(k.stat, 3)}`, badge(k.stationnaire5, 'stationnaire', 'non stationnaire'), fp(lb7.p), fp(lb14.p)] }
  })
  const d0 = lignes[0].a?.stationnaire5 && lignes[0].k.stationnaire5
  const reco = d0 ? 'la série brute passe les deux tests : on peut la modéliser sans différenciation (d = 0).' : lignes[1].a?.stationnaire5 && lignes[1].k.stationnaire5 ? 'la série devient stationnaire après une différence première : d = 1 est conseillé.' : 'les tests ne concluent pas nettement : comparez les modèles avec d = 0 et d = 1 (recherche automatique du SARIMA).'
  const ds = Sx.descriptif(x)
  return { options,
    avant: bandeauStats([['Jours', x.length], ['Du', fmtDate(versDate(s.debutNum))], ['Au', fmtDate(versDate(s.debutNum + x.length - 1))], ['Moyenne', nf(ds.moyenne)], ['Médiane', nf(ds.mediane)], ['Écart-type', nf(ds.ecart)], ['Min – max', `${nf(ds.min)} – ${nf(ds.max)}`]]),
    html: `${tableau(['Série testée', 'n', 'ADF (τ)', 'ADF : conclusion', 'KPSS (η)', 'KPSS : conclusion', 'Ljung-Box 7 (p)', 'Ljung-Box 14 (p)'], lignes.map((e) => e.l))}
      <div class="alert info" style="display:block;margin-top:10px;font-size:13px"><b>Conclusion :</b> ${reco}</div>`,
    lecture: `une série est <b>stationnaire</b> si sa moyenne et sa variance ne dérivent pas dans le temps : c’est l’hypothèse des modèles ARMA. <b>ADF</b> (Dickey-Fuller augmenté) teste « la série a une racine unitaire (marche au hasard) » : τ inférieur à −2,86 (seuil 5 %) → on rejette, la série est stationnaire. <b>KPSS</b> teste l’inverse (« la série est stationnaire ») : η supérieur à 0,463 → non stationnaire. Les deux tests sont complémentaires ; quand ils sont d’accord, la conclusion est solide. <b>Ljung-Box</b> teste « aucune autocorrélation jusqu’au retard m » : p < 0,05 → la série a de la mémoire, donc elle est prévisible. On différencie (Δ) jusqu’à obtenir la stationnarité : le nombre de différences donne d et D du SARIMA.` }
}
function rendreTestsSerie(c) {
  const s = serieModele(c); if (!s || s.x.length < 21) return { html: vide('Série trop courte.'), lecture: '' }
  const x = s.x, n = x.length, t = x.map((_, i) => i), reg = Sx.regression(t.map((v) => [v]), x, ['Temps']), mk = Sx.kendall(t, x)
  const dc = decomposition(x, s.debutNum), f = Sx.forces(dc.tend, dc.saison, dc.residu)
  const parJour = [[], [], [], [], [], [], []]; x.forEach((v, i) => parJour[jourSemaine(s.debutNum + i)].push(v)); const kw = Sx.kruskal(parJour), an = Sx.anova(parJour)
  const ds = Sx.descriptif(x), disp = ds.variance / ds.moyenne, chiD = (n - 1) * disp, pD = 1 - Math.abs(1 - 2 * Sx.pKhi2(chiD, n - 1))
  const acf = Sx.acf(x, Math.min(14, n - 2)), lb = Sx.ljungBox(x, Math.min(14, Math.floor(n / 4)))
  const lignes = [
    ['Tendance linéaire (pente MCO)', `${nf(reg.coef[1].b * 30.4, 3)} ${s.unite || ''} par mois`, `t = ${nf(reg.coef[1].t, 2)}`, fp(reg.coef[1].p), badge(reg.coef[1].p < 0.05, 'tendance', 'pas de tendance')],
    ['Tendance monotone (Mann-Kendall)', `τ = ${nf(mk.tau, 3)}`, 'approx. normale', fp(mk.p), badge(mk.p < 0.05, mk.tau > 0 ? 'hausse' : 'baisse', 'pas de tendance')],
    ['Force de la tendance (décomposition)', nf(f.tendance, 3), '0 = nulle · 1 = forte', '—', badge(null)],
    ['Force de la saisonnalité hebdomadaire', nf(f.saisonnalite, 3), '0 = nulle · 1 = forte', '—', badge(null)],
    ['Effet du jour de la semaine (Kruskal-Wallis)', `H = ${nf(kw.h, 2)}`, `ddl ${kw.ddl}`, fp(kw.p), badge(kw.p < 0.05, 'effet jour', 'pas d’effet')],
    ['Effet du jour de la semaine (ANOVA)', `F = ${nf(an.f, 2)}`, `η² = ${nf(an.eta2, 3)}`, fp(an.p), badge(an.p < 0.05, 'effet jour', 'pas d’effet')],
    ['Indice de dispersion (variance ÷ moyenne)', nf(disp, 3), `χ² = ${nf(chiD, 1)}, ddl ${n - 1}`, fp(pD), badge(pD >= 0.05, 'compatible Poisson', disp > 1 ? 'surdispersion' : 'sous-dispersion')],
    ['Autocorrélation J−1 / J−7', `${nf(acf[1], 3)} / ${nf(acf[7], 3)}`, `seuil ± ${nf(1.96 / Math.sqrt(n), 3)}`, '—', badge(Math.abs(acf[1]) > 1.96 / Math.sqrt(n), 'mémoire', 'pas de mémoire')],
    [`Ljung-Box (${lb.ddl} retards)`, `Q = ${nf(lb.q, 1)}`, `ddl ${lb.ddl}`, fp(lb.p), badge(lb.p < 0.05, 'autocorrélée', 'bruit blanc')],
  ]
  return { html: tableau(['Test / indicateur', 'Valeur', 'Détail', 'p-valeur', 'Conclusion (α = 5 %)'], lignes),
    lecture: `<b>Pente MCO</b> : droite des moindres carrés de la série contre le temps (test t de la pente). <b>Mann-Kendall</b> : tendance monotone sans hypothèse de linéarité ni de normalité (τ de Kendall entre le temps et la série). <b>Forces</b> (Wang-Smith-Hyndman) = 1 − Var(résidu) ÷ Var(composante + résidu) : au-delà de 0,6 la composante est marquée. <b>Jour de la semaine</b> : les niveaux diffèrent-ils selon le jour ? si oui, le modèle doit en tenir compte (s = 7). <b>Indice de dispersion</b> : pour des arrivées « au hasard » (loi de Poisson, hypothèse des files d’attente M/M/c et d’Erlang), variance = moyenne ; un indice > 1 avec p < 0,05 signale une surdispersion (jours de rush, épidémies). <b>Ljung-Box</b> : p < 0,05 → la série n’est pas un bruit blanc, elle a une structure exploitable par un modèle.` }
}
function rendrePeriodogramme(c, W, H) {
  const s = serieModele(c); if (!s || s.x.length < 21) return { html: vide('Série trop courte.'), lecture: '' }
  const n = s.x.length, pmax = Math.min(60, n / 2)
  const per = Sx.periodogramme(s.x).filter((e) => e.periode >= 2 && e.periode <= pmax)
  // Seuil du hasard : pour un bruit blanc, I(f)/σ² suit une loi exponentielle de moyenne 1 ; sur K fréquences,
  // la plus grande dépasse σ²·ln(K/0,05) dans 5 % des cas seulement (seuil « tous pics confondus »).
  const m = s.x.reduce((a, b) => a + b, 0) / n, v = s.x.reduce((a, b) => a + (b - m) ** 2, 0) / n, seuil = v * Math.log(per.length / 0.05)
  const top = per.slice().sort((a, b) => b.puissance - a.puissance).slice(0, 3)
  return { options: optionsModele(c, s).split('</label>')[0] + '</label>',
    avant: bandeauStats([...top.map((e, i) => [`Cycle n° ${i + 1}`, `${nf(e.periode, 1)} jours${e.puissance > seuil ? ' ✓' : ''}`]), ['Seuil du hasard (95 %)', nf(seuil, 1)]]),
    html: periodogrammeSvg({ W, H, per, seuil, top, pmax }),
    lecture: `le <b>périodogramme</b> décompose la série en ondes (transformée de Fourier discrète : I(f) = |Σ (yₜ − ȳ)e^{−2iπft}|² ÷ n) et mesure la « puissance » de chaque période, en jours (axe horizontal, échelle logarithmique pour que les cycles courts restent lisibles). Un pic à <b>7 jours</b> (trait vert) signale un rythme hebdomadaire ; à <b>3,5 jours</b>, son harmonique ; vers <b>30 jours</b>, un rythme mensuel. La ligne orange est le <b>seuil du hasard</b> : un pic au-dessus (✓ en haut) a moins de 5 % de chances d’être dû au hasard si la série n’avait aucun cycle. Les longues périodes (à droite) dépassent souvent ce seuil à cause de la tendance et de la saison, pas d’un vrai cycle : regardez surtout la zone de 2 à 14 jours. C’est l’argument pour donner au modèle le jour de la semaine (et un terme saisonnier s = 7 au SARIMA).` }
}
// Périodogramme : bâtons sur une échelle logarithmique des périodes, repères à 3,5, 7, 14 et 30 jours, 3 plus grands pics nommés.
function periodogrammeSvg({ W, H, per, seuil, top, pmax }) {
  const max = Math.max(seuil, ...per.map((e) => e.puissance)) * 1.12, ml = margeY(0, max), mr = 16, mt = 14, mb = 56
  const lx = (p) => Math.log(p), x = (p) => ml + (lx(p) - lx(2)) / (lx(pmax) - lx(2)) * (W - ml - mr), y = (v) => mt + (1 - v / max) * (H - mt - mb)
  const reperes = [2, 3, 3.5, 5, 7, 10, 14, 21, 30, 45, 60].filter((p) => p <= pmax)
  const chemin = per.slice().sort((a, b) => a.periode - b.periode).map((e, i) => `${i ? 'L' : 'M'}${x(e.periode).toFixed(1)},${y(e.puissance).toFixed(1)}`).join('')
  const leg = [{ nom: 'puissance', couleur: COUL.cyan }, { nom: 'seuil du hasard (95 %)', couleur: COUL.orange, pointille: '6 4' }, { nom: 'semaine (7 j)', couleur: COUL.vert, pointille: '3 3' }]
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <text x="14" y="${(H - mb + mt) / 2}" transform="rotate(-90 14 ${(H - mb + mt) / 2})" text-anchor="middle" font-size="11.5" fill="#5a606a">Puissance</text>
    ${axesY(0, max, y, ml, W - mr, '')}
    ${reperes.map((p) => `<line x1="${x(p)}" x2="${x(p)}" y1="${mt}" y2="${y(0)}" stroke="#f1f2f4"/><text x="${x(p)}" y="${y(0) + 15}" text-anchor="middle" font-size="11" fill="#5a606a">${nf(p, 1)}</text>`).join('')}
    <text x="${(ml + W - mr) / 2}" y="${y(0) + 31}" text-anchor="middle" font-size="11.5" fill="#5a606a">Période du cycle (jours, échelle logarithmique)</text>
    ${pmax >= 7 ? `<line x1="${x(7)}" x2="${x(7)}" y1="${mt}" y2="${y(0)}" stroke="${COUL.vert}" stroke-width="1.4" stroke-dasharray="3 3"/>` : ''}
    ${per.map((e) => `<line x1="${x(e.periode).toFixed(1)}" x2="${x(e.periode).toFixed(1)}" y1="${y(0)}" y2="${y(e.puissance).toFixed(1)}" stroke="${COUL.cyan}" stroke-width="1.6" opacity=".55"><title>période ${nf(e.periode, 1)} j : puissance ${nf(e.puissance, 1)}</title></line>`).join('')}
    <path d="${chemin}" fill="none" stroke="${COUL.cyan}" stroke-width="1.4"/>
    <line x1="${ml}" x2="${W - mr}" y1="${y(seuil)}" y2="${y(seuil)}" stroke="${COUL.orange}" stroke-width="1.5" stroke-dasharray="6 4"/>
    ${top.map((e) => `<circle cx="${x(e.periode)}" cy="${y(e.puissance)}" r="4" fill="${e.puissance > seuil ? COUL.rouge : '#9ca2ab'}"/><text x="${x(e.periode)}" y="${y(e.puissance) - 8}" text-anchor="${x(e.periode) > W - mr - 40 ? 'end' : x(e.periode) < ml + 40 ? 'start' : 'middle'}" font-size="11" font-weight="700" fill="#17181a">${nf(e.periode, 1)} j</text>`).join('')}
    ${legendeSvg(leg, ml, H - 6, W - mr)}</svg>`
}
function rendreComparaison(c, W, H) {
  const M = modelesDe(c); if (M.erreur) return { options: M.s ? optionsModele(c, M.s) : '', html: vide(M.erreur), lecture: '' }
  const meilleur = M.res[0], naif = M.res.find((r) => r.cle === 'naif'), dm = naif && meilleur !== naif ? Sx.dieboldMariano(meilleur.err, naif.err) : null
  const lignes = M.res.map((r, i) => [`${i + 1}. ${echapper(r.m.nom)}`, nf(r.met.mae, 3), nf(r.met.rmse, 3), nf(r.met.mape, 1), nf(r.met.smape, 1), nf(r.met.mase, 3), nf(r.met.biais, 3), r.m.aic !== undefined ? nf(r.m.aic, 1) : '—', r.m.bic !== undefined ? nf(r.m.bic, 1) : '—'])
  const x = M.x, fenetre = Math.min(M.n, (M.n - M.fin) + 30), deb = M.n - fenetre, cou = [COUL.rouge, COUL.vert, COUL.violet]
  return { options: optionsModele(c, M.s),
    avant: bandeauStats([['Apprentissage', `${M.fin} jours`], ['Validation', `${M.n - M.fin} jours`], ['Meilleur (MAE)', meilleur.m.nom.split(' (')[0]], ['Gain vs naïf', naif ? `${nf(100 * (1 - meilleur.met.mae / naif.met.mae), 1)} %` : '—'], ['Diebold-Mariano vs naïf', dm ? `${nf(dm.stat, 2)} (p ${fp(dm.p)})` : '—']]),
    html: `${tableau(['Modèle (du meilleur au moins bon)', 'MAE', 'RMSE', 'MAPE (%)', 'sMAPE (%)', 'MASE', 'Biais', 'AIC', 'BIC'], lignes, { gras: (k) => k === 0 })}
      <div style="margin-top:12px">${lignesSvg({ W, H, debutNum: M.s.debutNum + deb, series: [{ nom: 'Observé', valeurs: x.slice(deb), couleur: COUL.bleu, epaisseur: 1.6 }, ...M.res.slice(0, 3).map((r, i) => ({ nom: r.m.nom.split(' (')[0], valeurs: r.m.unPas.slice(deb).map((v, t) => (deb + t >= M.fin ? v : null)), couleur: cou[i], epaisseur: 1.8, pointille: i ? '5 3' : null }))], verticales: [{ i: M.fin - deb, nom: 'début de la validation' }], titreY: M.s.nom })}</div>`,
    lecture: `chaque modèle est <b>estimé sur les ${M.fin} premiers jours</b> puis, sur les ${M.n - M.fin} derniers (jamais vus à l’estimation), prévoit <b>chaque soir le lendemain</b> avec les valeurs réellement observées : c’est le schéma de la validation glissante du mémoire. <b>MAE</b> = erreur absolue moyenne (dans l’unité de la série) ; <b>RMSE</b> pénalise davantage les grosses erreurs ; <b>MAPE / sMAPE</b> en pourcentage ; <b>MASE</b> < 1 → meilleur que le « même jour la semaine dernière » ; <b>biais</b> > 0 → le modèle sous-estime. <b>AIC/BIC</b> (SARIMA, AR) : qualité d’ajustement pénalisée par le nombre de paramètres. Le test de <b>Diebold-Mariano</b> (correction HLN) dit si l’écart entre le meilleur modèle et le naïf est significatif (p < 0,05). Le graphique montre les trois meilleurs sur la validation.` }
}
let rechercheSarima = {}
function rendreSarima(c, W, H) {
  const P = previsionsDe(c); if (P.erreur) return { html: vide(P.erreur), lecture: '' }
  const o = c.opts.sarima, champ = (k, max) => `<label class="ind-case">${k} <input type="number" min="0" max="${max}" data-o="sarima.${k}" value="${o[k]}" style="width:52px"></label>`
  const auto = rechercheSarima[`${etat.service}|${P.s.cle}|${P.n}`]
  const options = `<span class="text-muted">Ordres :</span>${champ('p', 3)}${champ('d', 1)}${champ('q', 3)}${champ('P', 2)}${champ('D', 1)}${champ('Q', 2)}<span class="text-muted">s = 7</span>
    <button type="button" class="btn btn-secondary btn-sm" data-action="sarimaAuto">Recherche automatique du meilleur SARIMA</button>`
  const m = P.sar
  if (!m) return { options, html: vide('Ordres trop élevés pour la longueur de la série : diminuez p, q, P ou Q.'), lecture: '' }
  const pr = m.params, coef = [...pr.phi.map((v, i) => [`φ${i + 1} (AR)`, v]), ...pr.theta.map((v, i) => [`θ${i + 1} (MA)`, v]), ...pr.Phi.map((v, i) => [`Φ${i + 1} (AR saisonnier)`, v]), ...pr.Theta.map((v, i) => [`Θ${i + 1} (MA saisonnier)`, v]), ['Constante c', pr.c]]
  const x = P.x, h = P.h, hist = Math.min(x.length, 70), deb = x.length - hist, vide0 = new Array(hist).fill(null)
  const prev = [...vide0.slice(0, -1), x.at(-1), ...P.psar.map((v) => Math.max(0, v))], bas = [...vide0.slice(0, -1), x.at(-1), ...P.psar.map((v, i) => Math.max(0, v - P.isar[i]))], haut = [...vide0.slice(0, -1), x.at(-1), ...P.psar.map((v, i) => v + P.isar[i])]
  return { options,
    avant: bandeauStats([['Modèle', m.nom], ['σ² des innovations', nf(m.sigma2, 3)], ['AIC', nf(m.aic, 1)], ['BIC', nf(m.bic, 1)], ['Prévision J+1', `${nf(Math.max(0, P.psar[0]), 1)} [${nf(Math.max(0, P.psar[0] - P.isar[0]), 1)} ; ${nf(P.psar[0] + P.isar[0], 1)}]`], [`Prévision J+${h}`, `${nf(Math.max(0, P.psar[h - 1]), 1)} [${nf(Math.max(0, P.psar[h - 1] - P.isar[h - 1]), 1)} ; ${nf(P.psar[h - 1] + P.isar[h - 1], 1)}]`]]),
    html: `<div class="ind-deux"><div>${tableau(['Paramètre', 'Estimation'], coef.map(([k, v]) => [k, nf(v, 4)]))}</div>
      <div>${auto ? `<b style="font-size:12.5px">Recherche automatique : ${auto.essais.length} modèles essayés</b>${tableau(['Modèle', 'AIC', 'BIC', 'MAE validation'], auto.essais.slice(0, 8).map((e) => [e.nom, nf(e.aic, 1), nf(e.bic, 1), nf(e.maeVal, 3)]), { hauteur: 230 })}` : '<p class="text-muted" style="font-size:12.5px;margin:0">La recherche automatique essaie 60 combinaisons (d, D ∈ {0, 1} ; p, q ≤ 2 ; P, Q ≤ 1), garde le meilleur BIC pour chaque différenciation puis départage sur la validation.</p>'}</div></div>
      <div style="margin-top:12px">${lignesSvg({ W, H, debutNum: P.s.debutNum + deb, series: [{ nom: 'Observé', valeurs: [...x.slice(deb), ...new Array(h).fill(null)], couleur: COUL.bleu, epaisseur: 1.6 }, { nom: `Prévision ${m.nom}`, valeurs: prev, couleur: COUL.rouge, epaisseur: 2.2 }], bandes: [{ nom: 'Intervalle à 95 %', bas, haut, couleur: COUL.rouge, opacite: 0.14 }], verticales: [{ i: hist - 1, nom: 'aujourd’hui' }], titreY: P.s.nom })}</div>`,
    lecture: `le <b>SARIMA(p,d,q)(P,D,Q)₇</b> combine : une partie <b>AR</b> (la valeur dépend des p jours précédents, coefficients φ), une partie <b>MA</b> (elle dépend des q dernières erreurs, θ), leurs équivalents <b>saisonniers</b> à 7 jours (Φ, Θ), et d, D différenciations (voir les tests de stationnarité). Équation : φ(B)Φ(B⁷)(1−B)ᵈ(1−B⁷)ᴰ yₜ = c + θ(B)Θ(B⁷) εₜ. Estimation par <b>somme conditionnelle des carrés</b> minimisée par l’algorithme de Nelder-Mead (coefficients contraints dans ]−1 ; 1[). La bande rouge est l’<b>intervalle de prévision à 95 %</b> (± 1,96·σ·√Σψⱼ², poids ψ de la forme MA(∞)) : il s’élargit avec l’horizon ; comme on compte des patients, il est coupé à 0 (une valeur négative n’a pas de sens). Modifiez les ordres ou lancez la recherche automatique ; ${ORDRE_TXT(o)} est utilisé aussi dans la comparaison des modèles.` }
}
function rendreResidus(c, W, H) {
  const P = previsionsDe(c); if (P.erreur || !P.sar) return { html: vide(P.erreur ?? 'Pas de SARIMA estimé.'), lecture: '' }
  const r = P.sar.residus, d = Sx.descriptif(r), o = c.opts.sarima, k = Math.min(21, Math.floor(r.length / 4)), lb = Sx.ljungBox(r, k, o.p + o.q + o.P + o.Q), acf = Sx.acf(r, k).slice(1)
  const W2 = W >= 780 ? Math.floor((W - 14) / 2) : W
  return { avant: bandeauStats([['Moyenne des résidus', nf(d.moyenne, 3)], ['Écart-type', nf(d.ecart, 3)], [`Ljung-Box (${k} ret.)`, `Q = ${nf(lb.q, 1)} · p ${fp(lb.p)}`], ['Bruit blanc ?', lb.p >= 0.05 ? 'oui' : 'non'], ['Normalité (Jarque-Bera)', `p ${fp(d.pJb)}`], ['Asymétrie', nf(d.asymetrie)], ['Aplatissement', nf(d.aplatissement)]]),
    html: `${lignesSvg({ W, H, debutNum: P.s.debutNum + (P.x.length - r.length), series: [{ nom: 'Résidus du SARIMA (erreur un pas en avant)', valeurs: r, couleur: COUL.gris, epaisseur: 1.3 }], refs: [{ nom: '0', valeur: 0, couleur: COUL.noir }], titreY: 'Résidu' })}
      <div class="ind-deux" style="margin-top:10px"><div>${barresZeroSvg({ W: W2, H, valeurs: acf, etiquettes: acf.map((_, i) => `${i + 1}`), seuil: 1.96 / Math.sqrt(r.length), titreY: 'ACF des résidus' })}</div><div>${histogrammeSvg({ W: W2, H, valeurs: r, nom: 'Résidu', couleur: COUL.gris })}</div></div>`,
    lecture: `un bon modèle laisse des résidus qui ressemblent à un <b>bruit blanc</b> : moyenne proche de 0, aucune autocorrélation (barres de l’ACF dans la bande orange, <b>Ljung-Box p ≥ 0,05</b>), variance stable dans le temps et, idéalement, distribution normale (Jarque-Bera p ≥ 0,05 ; sinon l’intervalle à 95 % est approximatif). Une barre significative à 7 jours → ajouter un terme saisonnier (P ou Q) ; à 1 jour → augmenter p ou q.` }
}
function rendrePrevisions(c, W, H) {
  const P = previsionsDe(c); if (P.erreur) return { html: vide(P.erreur), lecture: '' }
  const x = P.x, h = P.h, hist = Math.min(x.length, 60), deb = x.length - hist, avant = new Array(hist - 1).fill(null)
  const toutes = [...(P.sar ? [{ cle: 'sarima', nom: P.sar.nom, p: P.psar }] : []), ...P.sorties]
  // Modèles tracés (à cocher) ; le tableau donne toujours tous les modèles. Couleurs et pointillés distincts,
  // traits plus épais dessous : deux modèles qui prévoient la même chose restent visibles l'un sur l'autre.
  if (!Array.isArray(c.opts.prevModeles)) c.opts.prevModeles = ['sarima', 'ses', 'holt', 'holtWinters', 'theta']
  const PAL = [COUL.rouge, COUL.orange, COUL.vert, COUL.violet, COUL.cyan, COUL.noir, '#b8860b', '#e05fa0', '#2f4f9e', '#6b8e23', '#8a5a44'], TIRETS = [null, '6 3', '2 3', '8 3 2 3', '4 4', '10 4', '3 2']
  const traces = toutes.map((s, i) => ({ ...s, couleur: PAL[i % PAL.length], tiret: TIRETS[i % TIRETS.length] })).filter((s) => c.opts.prevModeles.includes(s.cle))
  const series = [{ nom: 'Observé', valeurs: [...x.slice(deb), ...new Array(h).fill(null)], couleur: COUL.bleu, epaisseur: 1.6 },
    ...traces.map((s, k) => ({ nom: s.nom.split(' (')[0], valeurs: [...avant, x.at(-1), ...s.p.map((v) => Math.max(0, v))], couleur: s.couleur, epaisseur: Math.max(1.4, 4 - 0.5 * k), pointille: s.tiret }))]
  const jours = Array.from({ length: h }, (_, i) => P.s.debutNum + x.length + i)
  const options = `${optionsModele(c, P.s)}<span class="text-muted">Tracer :</span>${toutes.map((s) => `<label class="ind-case"><input type="checkbox" data-ox="prevModeles" value="${s.cle}" ${c.opts.prevModeles.includes(s.cle) ? 'checked' : ''}>${s.nom.split(' (')[0]}</label>`).join('')}`
  return { options, html: `${lignesSvg({ W, H, debutNum: P.s.debutNum + deb, series, verticales: [{ i: hist - 1, nom: 'dernier jour retenu' }], titreY: P.s.nom, calendrier: !!c.opts.cal })}
      <div style="margin-top:10px">${tableau(['Jour', ...toutes.map((s) => s.nom.split(' (')[0]), 'Moyenne des modèles'], jours.map((j, i) => { const v = toutes.map((s) => s.p[i]); return [`${JOURS_SEMAINE[jourSemaine(j)].slice(0, 3)}. ${fmtDate(versDate(j))}${ferieDe(j) ? ` <small class="text-muted">(${ferieDe(j)})</small>` : ''}`, ...v.map((e) => nf(Math.max(0, e), 1)), `<b>${nf(Math.max(0, v.reduce((a, b) => a + b, 0) / v.length), 1)}</b>`] }), { hauteur: 340 })}</div>`,
    lecture: `les modèles sont ré-estimés sur <b>toute</b> la série retenue, puis prolongés de ${h} jours ; le tableau donne la prévision <b>jour par jour</b> de chaque modèle. ${P.s.coupe ? `Les <b>${P.s.coupe} derniers jours saisis</b> sont écartés (option « Fin de série ») : un enfant est inscrit en moyenne 1 jour, et jusqu’à ${P.s.coupe} jours, après son entrée ; ces jours manquent donc d’enfants pas encore inscrits et feraient chuter toutes les prévisions. ` : ''}<b>Lissages exponentiels</b> : simple (un niveau, prévision plate), Thêta (niveau + demi-pente de la tendance), Holt linéaire (tendance prolongée), Holt amorti (tendance qui s’éteint), saisonnier sans tendance, Holt-Winters additif et multiplicatif (niveau + tendance + rythme de la semaine). Une prévision <b>plate</b> est normale pour le lissage simple ; quand plusieurs modèles prévoient la même valeur, leurs traits se superposent (cochez-les un à un pour les voir). La <b>moyenne des modèles</b> est souvent plus fiable que chacun pris seul. Le modèle retenu dans le mémoire reste le SVR de NERA, comparé à ces références.` }
}

// ── Affichage : barre latérale (rubriques + sections) et contenu qui défile ─────────────────
const ICONES = {
  synthese: ['#0055f7', '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>'],
  sigma: ['#7b3fe4', '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M8 17v-4M13 17V6M18 17v-7"/>'],
  nuage: ['#0aa2c0', '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><circle cx="8" cy="15" r="1.4" fill="currentColor"/><circle cx="11" cy="10.5" r="1.4" fill="currentColor"/><circle cx="15" cy="12" r="1.4" fill="currentColor"/><circle cx="18" cy="6" r="1.4" fill="currentColor"/><path d="M7 17 19 5" stroke-dasharray="2 2.4"/>'],
  lit: ['#2e9e5b', '<path d="M2 4v16M2 8h17a3 3 0 0 1 3 3v9M2 17h20"/><circle cx="7" cy="12" r="2"/>'],
  courbe: ['#e07b00', '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="m7 15 4-5 3 3 5-6"/>'],
  prevision: ['#d7263d', '<path d="M2 17 8.5 10.5l4 4L18 9"/><path d="M15 9h4v4"/><path d="M2 21h20" stroke-dasharray="2 2.6"/>'],
  flux: ['#0aa2c0', '<path d="m8 3-4 4 4 4M4 7h16M16 13l4 4-4 4M20 17H4"/>'],
  patient: ['#7b3fe4', '<circle cx="9" cy="7" r="4"/><path d="M2 21v-1a6 6 0 0 1 12 0v1M16 3.3a4 4 0 0 1 0 7.4M22 21v-1a6 6 0 0 0-4-5.6"/>'],
  acp: ['#2e9e5b', '<path d="M12 3v18M3 12h18"/><ellipse cx="12" cy="12" rx="9" ry="4.2" transform="rotate(-32 12 12)"/><path d="m12 12 5.5-3.5"/>'],
  tableau: ['#5a606a','<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>'],
}
const icone = (k) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONES[k]?.[1] ?? ''}</svg>`
const OPTIONS_DEFAUT = { serie: 'presents', mm7: true, fourchette: true, cap: true, corr: 'spearman', varDist: 'p:age', grpVar: 'duree', grpPar: 'cause', nuX: 'p:age', nuY: 'p:duree',
  ctA: 'cause', ctB: 'issue', regNiv: 'p', regY: 'duree', regYj: 'presents', mSerie: 'presents', h: 14, pv: 20,
  acpLog: true, acpAxes: '0-1', acpGroupe: 'cause', cal: true, acp3dFleches: true }
let sectionsVue = [], contexteVue = null, modalK = null
let cacheIndicateurs = null, signatureIndicateurs = '', derniereMaj = null, nbLignesMaj = null, serviceMaj = null
const signatureSaisie = () => `${etat.service}|${etat.lignes.length}|${JSON.stringify(lignesService()).length}`
function afficherIndicateurs() {
  etat.lits ??= {}; etat.indOnglet ??= 'Synthèse'; etat.indOptions ??= {}
  const lits = +etat.lits[etat.service] || null
  $('#indLits').value = lits ?? ''
  etat.indMethode ??= {}
  const methode = { ...METHODE_DEFAUT, ...(etat.indMethode[etat.service] ?? {}) }
  $('#indSeuil').value = String(methode.seuil); $('#indInconnues').value = methode.inconnues; $('#indCensure').value = methode.censure; $('#indComptage').value = methode.comptage ?? 'minuit'; $('#indHEntree').value = methode.heureEntree ?? 12; $('#indHSortie').value = methode.heureSortie ?? 11; $('#indDMeme').value = methode.dureeMemeJour ?? 8; $('#indLitsPeriodes').value = methode.capacites ?? ''
  if (typeof resumerCalcul === 'function') resumerCalcul()
  const par = document.querySelector('input[name=indPar]:checked').value
  // « Toutes les méthodes » : les trois séries sont calculées ; chaque rubrique de l'occupation les montre l'une sous l'autre.
  const variantes = methode.comptage === 'tous' ? ['minuit', 'journee', 'pondere'].map((k) => ({ k, nom: NOMS_COMPTAGE[k], d: calculerIndicateurs(lits, par, { ...methode, comptage: k }) })) : null
  const d = variantes ? variantes[0].d : calculerIndicateurs(lits, par, methode), st = statistiquesSaisie()
  // Capacité affichée (repères, Erlang B, file d'attente) : celle du dernier jour calculé.
  cacheIndicateurs = { d, st, lits: d.litsJour?.length ? d.litsJour.at(-1) : lits, par, pat: donneesPatients(), brut: serieBrute() }
  cacheIndicateurs.jour = donneesJour(cacheIndicateurs)
  cacheIndicateurs.variantes = variantes
  const avant = nbLignesMaj; nbLignesMaj = st.n; derniereMaj = new Date(); signatureIndicateurs = signatureSaisie()
  cacheIndicateurs.ajout = avant === null || serviceMaj !== etat.service ? null : st.n - avant
  serviceMaj = etat.service
  $('#indPeriode').textContent = d.premierSaisi ? `saisie du ${fmtDate(d.premierSaisi)} au ${fmtDate(d.dernierSaisi)}${d.debut ? ` · occupation calculée du ${fmtDate(d.debut)} au ${fmtDate(d.fin)}` : ''}` : ''
  $('#indPeriode').textContent += ` · à jour à ${derniereMaj.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`
  $('#indPeriode').title = $('#indPeriode').textContent
  dessinerVue()
}
// Une section s'affiche si l'occupation est calculable (quand elle en a besoin) et, pour les vues 3D, si elles sont activées.
const visible = (sansOcc) => (s) => !(s.occ && sansOcc) && !(s.d3 && etat.ind3D === false)
function dessinerVue() {
  if (!cacheIndicateurs) return
  const { d, st, lits, par, pat, brut, jour } = cacheIndicateurs, sansOcc = !!d.message
  let onglet = ONGLETS.find((o) => o.nom === etat.indOnglet) ?? ONGLETS[0]
  if (onglet.occ && sansOcc) onglet = ONGLETS[0]
  const opts = (etat.indOptions[etat.service] = { ...OPTIONS_DEFAUT, ...(etat.indOptions[etat.service] ?? {}) })
  opts.sarima = { p: 1, d: 0, q: 1, P: 1, D: 0, Q: 1, ...(opts.sarima ?? {}) }
  const sections = onglet.sections.filter(visible(sansOcc))
  $('#indTitre').textContent = onglet.nom
  const heure = derniereMaj ? derniereMaj.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
  $('#indNav').innerHTML = ONGLETS.map((o) => { const off = o.occ && sansOcc, act = o === onglet
    return `<button type="button" class="ind-groupe ${act ? 'actif' : ''}" data-onglet="${o.nom}" title="${off ? 'Saisie encore insuffisante pour calculer l’occupation' : `${o.nom} : ${o.desc}`}" ${off ? 'disabled' : ''} ${act ? 'aria-current="page"' : ''}><span class="nom">${o.nom}</span><span class="nb">${o.sections.filter(visible(sansOcc)).length || '—'}</span></button>`
  }).join('')
  $('#indAide').checked = etat.indLecture !== false; $('#ind3D').checked = etat.ind3D !== false
  const zone = $('#indZone'), W = Math.max(320, zone.clientWidth - 40), c = { d, st, lits, par, pat, brut, jour, W, opts }
  sectionsVue = sections; contexteVue = c
  // Sous-statistiques en onglets : « Toutes » (empilées, avec défilement) ou une seule.
  etat.indSous ??= {}
  let sous = etat.indSous[onglet.nom] ?? 'tout'
  if (sous !== 'tout' && !sections[sous]) sous = 'tout'
  const libelleSous = sous === 'tout' ? `Toutes <span class="nb">${sections.length}</span>` : `<span class="nb">${sous + 1}</span>${sections[sous].t}`
  const prec = sous === 'tout' ? null : sous > 0 ? sous - 1 : 'tout', suiv = sous === 'tout' ? 0 : sous < sections.length - 1 ? sous + 1 : null
  $('#indFiltre').innerHTML = `<span class="ind-filtre-k">Statistique</span>
    <div class="ind-filtre-groupe">
      <button type="button" class="ind-fleche" ${prec === null ? 'disabled' : `data-sous="${prec}"`} title="Statistique précédente">‹</button>
      <div class="ind-menu">
        <button type="button" class="ind-menu-btn" id="indMenuBtn" aria-haspopup="listbox" aria-expanded="false" title="${sous === 'tout' ? 'Toutes les statistiques' : sections[sous].t.replace(/"/g, '&quot;')}"><span class="txt">${libelleSous}</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="m6 9 6 6 6-6"/></svg></button>
        <div class="ind-menu-liste" role="listbox" hidden>
          <button type="button" role="option" data-sous="tout" class="${sous === 'tout' ? 'actif' : ''}"><span class="nb">≡</span>Toutes les statistiques <small>(les unes sous les autres)</small></button>
          ${sections.map((s2, k) => `<button type="button" role="option" data-sous="${k}" class="${sous === k ? 'actif' : ''}"><span class="nb">${k + 1}</span>${s2.t}</button>`).join('')}
        </div>
      </div>
      <button type="button" class="ind-fleche" ${suiv === null ? 'disabled' : `data-sous="${suiv}"`} title="Statistique suivante">›</button>
    </div>`
  zone.innerHTML = (sous === 'tout' ? sections.map((s2, k) => [s2, k]) : [[sections[sous], sous]]).map(([s2, k]) => htmlSection(s2, k, c, W)).join('')
    + (sous === 'tout' ? '' : `<div class="ind-suite">${sous > 0 ? `<button type="button" class="btn btn-secondary btn-sm" data-sous="${sous - 1}">‹ ${sections[sous - 1].t}</button>` : '<span></span>'}${sous < sections.length - 1 ? `<button type="button" class="btn btn-secondary btn-sm" data-sous="${sous + 1}">${sections[sous + 1].t} ›</button>` : ''}</div>`)
  NOTES.length = 0; regrouperAlertes(zone); installer3D(zone)
  convertirTitres(zone); GRAPHES.size > 300 && cacherSurvol()
  suivreDefilement()
}

// ── Avertissements et remarques ───────────────────────────────────────────────────────────
// Les encadrés orange/rouges (avertissements) et bleus (remarques) d'une section ne s'affichent plus en
// entier : à leur place, deux boutons avec leur nombre ; un clic ouvre le détail dans un panneau à droite.
// Un encadré qui est à lui seul tout le contenu de la section (« Indiquez le nombre de lits ») reste visible.
const NOTES = []
const ICO_AVERT = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/></svg>'
const ICO_INFO = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>'
const pluriel = (n, mot) => `${mot}${n > 1 ? 's' : ''}`
function regrouperAlertes(racine) {
  racine.querySelectorAll('.ind-section').forEach((sec) => {
    const alertes = [...sec.querySelectorAll('.alert')].filter((a) => !(a.parentElement.classList.contains('ind-graphe') && a.parentElement.children.length === 1))
    if (!alertes.length) return
    const avert = alertes.filter((a) => a.classList.contains('warn') || a.classList.contains('crit')), rem = alertes.filter((a) => !avert.includes(a))
    const id = NOTES.push({ titre: sec.querySelector('h5 span')?.textContent || $('#indModalTitre')?.textContent || 'Section',
      avert: avert.map((a) => ({ html: a.innerHTML, crit: a.classList.contains('crit') })), rem: rem.map((a) => ({ html: a.innerHTML })) }) - 1
    const barre = document.createElement('div'); barre.className = 'ind-notes'
    barre.innerHTML = (avert.length ? `<button type="button" class="ind-note-btn avert ${avert.some((a) => a.classList.contains('crit')) ? 'crit' : ''}" data-notes="${id}" data-type="avert" aria-haspopup="dialog">${ICO_AVERT}${pluriel(avert.length, 'Avertissement')}<span class="nb">${avert.length}</span></button>` : '')
      + (rem.length ? `<button type="button" class="ind-note-btn rem" data-notes="${id}" data-type="rem" aria-haspopup="dialog">${ICO_INFO}${pluriel(rem.length, 'Remarque')}<span class="nb">${rem.length}</span></button>` : '')
    alertes[0].before(barre); alertes.forEach((a) => a.remove())
  })
}
let notesOuvertes = null, notesRetour = null
function ouvrirNotes(entree, type, retour) {
  fermerNotes(false)
  notesOuvertes = entree; notesRetour = retour ?? document.activeElement
  const fond = document.createElement('div'); fond.id = 'indNotesFond'; fond.onclick = () => fermerNotes()
  const p = document.createElement('aside'); p.id = 'indNotes'; p.setAttribute('role', 'dialog'); p.setAttribute('aria-modal', 'true'); p.setAttribute('aria-label', entree.titre)
  document.body.append(fond, p); afficherNotes(type)
  p.querySelector('.fermer').focus()
}
function afficherNotes(type) {
  const e = notesOuvertes, p = $('#indNotes'); if (!e || !p) return
  if (!e[type]?.length) type = e.avert.length ? 'avert' : 'rem'
  const onglet = (t, nom) => (e[t].length ? `<button type="button" role="tab" aria-selected="${type === t}" data-onglet-note="${t}">${pluriel(e[t].length, nom)} (${e[t].length})</button>` : '')
  p.innerHTML = `<header><b title="${echapper(e.titre)}">${echapper(e.titre)}</b><button type="button" class="fermer" aria-label="Fermer">×</button></header>
    <div class="onglets" role="tablist">${onglet('avert', 'Avertissement')}${onglet('rem', 'Remarque')}</div>
    <div class="liste">${e[type].map((n) => `<div class="note ${type === 'avert' ? (n.crit ? 'crit' : 'avert') : ''}">${n.html}</div>`).join('')}</div>`
  p.querySelector('.fermer').onclick = () => fermerNotes()
  p.querySelectorAll('[data-onglet-note]').forEach((b) => (b.onclick = () => afficherNotes(b.dataset.ongletNote)))
}
function fermerNotes(rendre = true) {
  $('#indNotes')?.remove(); $('#indNotesFond')?.remove()
  if (rendre && notesOuvertes) notesRetour?.focus?.()
  notesOuvertes = null
}
window.ouvrirNotes = ouvrirNotes
document.addEventListener('click', (e) => { const b = e.target.closest('[data-notes]'); if (b) ouvrirNotes(NOTES[+b.dataset.notes], b.dataset.type, b) })
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && notesOuvertes) { e.stopImmediatePropagation(); fermerNotes() } }, true)
// Une section : titre (+ bouton Agrandir), options, bandeau de chiffres, graphique, explication.
function htmlSection(s, k, c, W, agrandi = false) {
  const H = agrandi && s.h ? Math.max(s.h, Math.min(560, Math.round(s.h * 1.55))) : (s.h ?? 0); c.H = H; c.W = W
  const rendre1 = (cc) => { try { return s.rendre(cc, W, H) } catch (e) { console.error(e); return { html: vide(`Calcul impossible pour cette section (${echapper(e.message)}).`), lecture: '' } } }
  // « Toutes les méthodes » : la rubrique est rendue pour chaque méthode, l'une sous l'autre, avec un titre.
  if ((s.occ || s.comptage) && !s.sansComptage && cacheIndicateurs?.variantes && c.d === cacheIndicateurs.variantes[0].d) {
    const dOrigine = cacheIndicateurs.d, rs = []
    for (const v of cacheIndicateurs.variantes) {
      cacheIndicateurs.d = v.d                               // les libellés suivent la méthode rendue
      const cv = { ...c, d: v.d, lits: v.d.litsJour?.length ? v.d.litsJour.at(-1) : c.lits }
      cv.jour = donneesJour(cv)
      rs.push({ v, r: rendre1(cv) })
    }
    cacheIndicateurs.d = dOrigine
    s._survol = null
    const r0 = rs[0].r
    return `<section class="ind-section" ${agrandi ? '' : `id="ind-s${k}"`} data-k="${k}">${agrandi ? '' : `<h5><span>${s.t}</span><button type="button" class="ind-agrandir" data-agrandir="${k}" title="Afficher en grand, avec toutes ses statistiques">${ICONE_AGRANDIR} Agrandir</button></h5>`}${r0.options ? `<div class="ind-options">${r0.options}</div>` : ''}
      ${rs.map(({ v, r }) => `<div class="ind-variante ind-variante-${v.k}"><div class="ind-variante-titre">${v.nom}</div>${r.avant ?? ''}<div class="ind-graphe">${r.html}</div></div>`).join('')}
      ${(etat.indLecture === false && !agrandi) || !r0.lecture ? '' : `<div class="ind-lecture"><b>Comment lire :</b> la même rubrique est montrée pour les trois méthodes de comptage. ${rs.map(({ v, r }) => r.lecture && v.k !== 'minuit' ? '' : r.lecture).join('')}</div>`}</section>`
  }
  const r = rendre1(c)
  s._survol = r.survol
  // Mention de la méthode de comptage (et de la capacité variable) en tête de chaque graphe de l'occupation.
  const methodeTxt = (s.occ || s.comptage) && !s.sansComptage && c.d?.reglages ? `<div class="ind-methode">Comptage : ${NOMS_COMPTAGE[c.d.reglages.comptage] ?? ''}${c.d.changementsLits?.length ? ` · capacité variable : ${[c.d.litsJour?.[0], ...c.d.changementsLits.map((x) => `${x.lits} dès le ${fmtDate(versDate(x.j))}`)].join(' → ')}` : ''}</div>` : ''
  return `<section class="ind-section" ${agrandi ? '' : `id="ind-s${k}"`} data-k="${k}">${agrandi ? '' : `<h5><span>${s.t}</span><button type="button" class="ind-agrandir" data-agrandir="${k}" title="Afficher en grand, avec toutes ses statistiques">${ICONE_AGRANDIR} Agrandir</button></h5>`}${r.options ? `<div class="ind-options">${r.options}</div>` : ''}${r.avant ?? ''}
    ${methodeTxt}<div class="ind-graphe">${r.html}</div>${(etat.indLecture === false && !agrandi) || !r.lecture ? '' : `<div class="ind-lecture"><b>Comment lire :</b> ${r.lecture}</div>`}</section>`
}
const ICONE_AGRANDIR = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>'
// Fenêtre « Agrandir » : la section seule, en grand, avec navigation vers les sections voisines.
function ouvrirModal(k) {
  if (!sectionsVue[k] || !contexteVue) return
  modalK = k; const s = sectionsVue[k], corps = $('#indModalCorps')
  $('#indModalKicker').textContent = `${etat.indOnglet} · ${k + 1} / ${sectionsVue.length}`
  $('#indModalTitre').textContent = s.t
  $('#indModalPrec').disabled = k === 0; $('#indModalSuiv').disabled = k === sectionsVue.length - 1
  $('#indModal').classList.add('visible')
  const W = Math.max(320, corps.clientWidth - 12)
  corps.innerHTML = htmlSection(s, k, { ...contexteVue }, W, true)
  regrouperAlertes(corps); installer3D(corps)
  convertirTitres(corps)
}
const fermerModal = () => { $('#indModal').classList.remove('visible'); modalK = null }
$('#indModalFermer').onclick = fermerModal
$('#indModalPrec').onclick = () => { if (modalK > 0) { ouvrirModal(modalK - 1); $('#indModalCorps').scrollTop = 0 } }
$('#indModalSuiv').onclick = () => { if (modalK < sectionsVue.length - 1) { ouvrirModal(modalK + 1); $('#indModalCorps').scrollTop = 0 } }
$('#indModal').addEventListener('click', (e) => { if (e.target.id === 'indModal') fermerModal() })
document.addEventListener('keydown', (e) => {
  if (modalK === null) return
  if (e.key === 'Escape') fermerModal()
  else if (e.key === 'ArrowRight' && !/INPUT|SELECT/.test(e.target.tagName)) $('#indModalSuiv').click()
  else if (e.key === 'ArrowLeft' && !/INPUT|SELECT/.test(e.target.tagName)) $('#indModalPrec').click()
})
// Lecture d'une valeur au survol de la courbe (ligne verticale + étiquette).
function installerSurvol() { /* remplacé par le moteur d'infobulles global ci-dessous */ }
// ── Infobulles : la valeur pointée par la souris, sur tous les graphiques ─────────────────
// • courbes : ligne verticale + point sur chaque série + bulle avec la date et toutes les valeurs du jour ;
// • barres, cases, points, boîtes : le texte de leur <title> (le <title> natif est retiré pour éviter le doublon).
const GRAPHES = new Map(); let numeroGraphe = 0
function enregistrerGraphe(g) { numeroGraphe++; GRAPHES.set(numeroGraphe, g); if (GRAPHES.size > 400) GRAPHES.delete(GRAPHES.keys().next().value); return numeroGraphe }
const bulle = document.body.appendChild(Object.assign(document.createElement('div'), { className: 'ind-bulle-globale' }))
function placerBulle(e, html) {
  bulle.innerHTML = html; bulle.style.display = 'block'
  const r = bulle.getBoundingClientRect(), x = e.clientX + 16 + r.width > innerWidth - 8 ? e.clientX - r.width - 14 : e.clientX + 16
  bulle.style.left = `${Math.max(8, x)}px`; bulle.style.top = `${Math.max(8, Math.min(innerHeight - r.height - 8, e.clientY - r.height / 2))}px`
}
function cacherSurvol() { bulle.style.display = 'none'; document.querySelectorAll('.survol-marques').forEach((m) => m.remove()); document.querySelectorAll('.survole').forEach((el) => el.classList.remove('survole')) }
function convertirTitres(racine) {
  racine.querySelectorAll('svg title').forEach((t) => { const p = t.parentElement; p.dataset.info = t.textContent; p.classList.add('a-info'); t.remove() })
}
function survolCourbe(e, cible) {
  const g = GRAPHES.get(+cible.dataset.g); if (!g) return
  const svg = cible.ownerSVGElement, b = svg.getBoundingClientRect(), echelle = b.width / +svg.getAttribute('width')
  const ml = +cible.dataset.ml, mr = +cible.dataset.mr, W = +svg.getAttribute('width'), n = g.n
  const i = Math.round(((e.clientX - b.left) / echelle - ml) / (W - ml - mr) * (n - 1)); if (i < 0 || i >= n) return
  const xi = ml + (i / Math.max(1, n - 1)) * (W - ml - mr), y = (v) => g.mt + (1 - (v - g.ymin) / (g.ymax - g.ymin)) * (g.H - g.mt - g.mb)
  let m = svg.querySelector('.survol-marques'); if (!m) { m = document.createElementNS('http://www.w3.org/2000/svg', 'g'); m.setAttribute('class', 'survol-marques'); m.setAttribute('pointer-events', 'none'); svg.appendChild(m) }
  const lignes = [], points = []
  for (const s2 of g.series) {
    if (s2.valeurs) { const v = s2.valeurs[i]; if (v === null || v === undefined || !Number.isFinite(v)) continue; points.push(`<circle cx="${xi}" cy="${y(v)}" r="4.5" fill="${s2.couleur}" stroke="#fff" stroke-width="2"/>`); lignes.push(`<i style="background:${s2.couleur}"></i>${echapper(s2.nom)} : <b>${nf(v, 2)}${g.suffixe}</b>`) }
    else if (Number.isFinite(s2.bas?.[i]) && Number.isFinite(s2.haut?.[i])) lignes.push(`<i style="background:${s2.couleur};opacity:.4"></i>${echapper(s2.nom)} : <b>${nf(s2.bas[i], 1)} – ${nf(s2.haut[i], 1)}${g.suffixe}</b>`)
  }
  if (!lignes.length) { cacherSurvol(); return }
  m.innerHTML = `<line x1="${xi}" x2="${xi}" y1="${g.mt}" y2="${g.H - g.mb}" stroke="#17181a" stroke-dasharray="3 3"/>${points.join('')}`
  const j = g.jours ? g.jours[i] : g.debutNum + i, dj = versDate(j)
  const titre = g.pas === 'semaine' ? `Semaine du ${fmtDate(dj)} (moyenne)` : g.pas === 'mois' ? `${MOIS_COURTS[+dj.slice(5, 7) - 1]} ${dj.slice(0, 4)} (moyenne)`
    : g.pas === 'annee' ? `Année ${dj.slice(0, 4)} (moyenne)` : `${JOURS_SEMAINE[jourSemaine(j)]} ${fmtDate(dj)}`
  placerBulle(e, `<div class="t">${titre}</div>${lignes.map((l) => `<div class="l">${l}</div>`).join('')}`)
}
document.addEventListener('mousemove', (e) => {
  const zone = e.target.closest?.('.survol-zone')
  if (zone) { document.querySelectorAll('.survole').forEach((el) => el.classList.remove('survole')); survolCourbe(e, zone); return }
  const el = e.target.closest?.('.a-info')
  if (el) {
    document.querySelectorAll('.survol-marques').forEach((m) => m.remove())
    document.querySelectorAll('.survole').forEach((x) => { if (x !== el) x.classList.remove('survole') }); el.classList.add('survole')
    const [t, ...reste] = el.dataset.info.split(' : ')
    placerBulle(e, reste.length ? `<div class="t">${echapper(t)}</div><div class="l"><b>${echapper(reste.join(' : '))}</b></div>` : `<div class="l">${echapper(t)}</div>`); return
  }
  if (bulle.style.display === 'block') cacherSurvol()
}, { passive: true })
document.addEventListener('scroll', cacherSurvol, true)
// La section visible est surlignée dans la barre latérale.
function choisirSous(e) {
  const b = e.target.closest('[data-sous]'); if (!b) return
  etat.indSous ??= {}; etat.indSous[etat.indOnglet] = b.dataset.sous === 'tout' ? 'tout' : +b.dataset.sous
  sauver(); dessinerVue(); $('#indZone').scrollTop = 0
}
const menuStat = (ouvrir) => { const l = $('#indFiltre .ind-menu-liste'), b = $('#indMenuBtn'); if (!l) return; l.hidden = !ouvrir; b.setAttribute('aria-expanded', String(ouvrir)); if (ouvrir) l.querySelector('.actif')?.scrollIntoView({ block: 'nearest' }) }
$('#indFiltre').addEventListener('click', (e) => {
  if (e.target.closest('#indMenuBtn')) { menuStat($('#indFiltre .ind-menu-liste').hidden); return }
  if (e.target.closest('[data-sous]')) { menuStat(false); choisirSous(e) }
})
document.addEventListener('click', (e) => { if (!e.target.closest('#indFiltre')) menuStat(false) })
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') menuStat(false) })
$('#indZone').addEventListener('click', (e) => { if (e.target.closest('.ind-suite')) choisirSous(e) })
// Fait défiler un conteneur juste assez pour qu'un élément soit visible (sans toucher au reste de la page).
function rendreVisible(el, boite) {
  if (!el || !boite) return
  const b = boite.getBoundingClientRect(), r = el.getBoundingClientRect()
  if (r.top < b.top + 4) boite.scrollTop -= b.top + 4 - r.top
  else if (r.bottom > b.bottom - 4) boite.scrollTop += r.bottom - b.bottom + 4
}
let defilementClic = 0
function marquerLien(k) {
  const liens = [...document.querySelectorAll('#indFiltre .ind-menu-liste [data-sous]:not([data-sous="tout"])')]
  liens.forEach((a, i) => a.classList.toggle('vu', i === k))
}
function suivreDefilement() {
  if (Date.now() < defilementClic) return              // défilement lancé par un clic : le lien cliqué reste surligné
  const zone = $('#indZone'), liens = document.querySelectorAll('#indFiltre .ind-menu-liste [data-sous]:not([data-sous="tout"])'); if (!liens.length || (etat.indSous?.[etat.indOnglet] ?? 'tout') !== 'tout') return
  const haut = zone.getBoundingClientRect().top + 60
  let k = 0; zone.querySelectorAll('.ind-section').forEach((el, i) => { if (el.getBoundingClientRect().top <= haut) k = i })
  if (zone.scrollTop + zone.clientHeight >= zone.scrollHeight - 4) k = liens.length - 1
  if (!liens[k].classList.contains('vu')) marquerLien(k)
}
$('#indZone').addEventListener('scroll', suivreDefilement, { passive: true })
$('#indNav').addEventListener('click', (e) => {
  const a = e.target.closest('.ind-sous a')
  if (a) { e.preventDefault(); defilementClic = Date.now() + 900; marquerLien(+a.dataset.k); const el = $(`#ind-s${a.dataset.k}`), zone = $('#indZone'); zone.scrollTo({ top: el.getBoundingClientRect().top - zone.getBoundingClientRect().top + zone.scrollTop - 6, behavior: 'smooth' }); return }
  const b = e.target.closest('[data-onglet]'); if (!b || b.disabled) return
  etat.indOnglet = b.dataset.onglet; sauver(); dessinerVue(); $('#indZone').scrollTop = 0
})
$('#indAide').addEventListener('change', (e) => { etat.indLecture = e.target.checked; sauver(); redessinerSurPlace() })
// Vues 3D au choix : décochées, les sections 3D disparaissent de toutes les rubriques (les graphiques 2D restent).
$('#ind3D').addEventListener('change', (e) => { etat.ind3D = e.target.checked; for (const k in etat.indSous ?? {}) etat.indSous[k] = 'tout'; sauver(); dessinerVue() })
const redessinerSurPlace = () => { const z = $('#indZone'), haut = z.scrollTop; dessinerVue(); z.scrollTop = haut; if (modalK !== null) { const m = $('#indModalCorps'), h2 = m.scrollTop; ouvrirModal(Math.min(modalK, sectionsVue.length - 1)); m.scrollTop = h2 } }
function changerOption(e) {
  const o = etat.indOptions[etat.service], t = e.target
  if (t.classList.contains('ind-serie')) o.serie = t.value
  else if (t.dataset.opt) o[t.dataset.opt] = t.checked
  else if (t.dataset.ox) { const l = new Set(o[t.dataset.ox] ?? []); if (t.checked) l.add(t.value); else l.delete(t.value); o[t.dataset.ox] = [...l] }
  else if (t.dataset.o) {
    const [k, sous] = t.dataset.o.split('.'), v = t.type === 'number' ? Math.max(0, Math.min(+t.max || 9, Math.round(+t.value || 0))) : (/^\d+$/.test(t.value) ? +t.value : t.value)
    if (sous) o[k] = { ...o[k], [sous]: v }; else o[k] = v
  } else return
  sauver(); redessinerSurPlace()
}
$('#indZone').addEventListener('change', changerOption)
$('#indModalCorps').addEventListener('change', changerOption)
$('#indZone').addEventListener('click', (e) => { const g = e.target.closest('[data-agrandir]'); if (g) ouvrirModal(+g.dataset.agrandir) })
$('#indZone').addEventListener('click', (e) => lancerSarimaAuto(e))
$('#indModalCorps').addEventListener('click', (e) => lancerSarimaAuto(e))
function lancerSarimaAuto(e) {
  const b = e.target.closest('[data-action="sarimaAuto"]'); if (!b || !cacheIndicateurs) return
  const c = { ...cacheIndicateurs, opts: etat.indOptions[etat.service] }, s = serieModele(c); if (!s) return
  b.disabled = true; b.textContent = 'Recherche en cours… (60 modèles)'
  setTimeout(() => {
    const fin = Math.round(s.x.length * (1 - c.opts.pv / 100)), r = Sx.sarimaAuto(s.x, fin)
    rechercheSarima[`${etat.service}|${s.cle}|${s.x.length}`] = r
    if (r.meilleur) c.opts.sarima = { ...r.meilleur.ordre }
    sauver(); redessinerSurPlace()
  }, 30)
}
let minuterieRedim = null
window.addEventListener('resize', () => { clearTimeout(minuterieRedim); minuterieRedim = setTimeout(() => { if ($('#vueIndicateurs').classList.contains('visible')) redessinerSurPlace() }, 150) })
// Nombre de lits : recalcul dès la frappe (petit délai), sans attendre de quitter le champ.
let minuterieLits = null
function appliquerLits(e) {
  const v = +e.target.value > 0 ? Math.round(+e.target.value) : null
  etat.lits ??= {}; if (etat.lits[etat.service] === v) return
  etat.lits[etat.service] = v; sauver(); const z = $('#indZone'), haut = z.scrollTop; afficherIndicateurs(); z.scrollTop = haut
}
$('#indLits').addEventListener('input', (e) => { clearTimeout(minuterieLits); minuterieLits = setTimeout(() => appliquerLits(e), 350) })
$('#indLits').addEventListener('change', (e) => { clearTimeout(minuterieLits); appliquerLits(e) })
for (const [id, cle, conv] of [['#indSeuil', 'seuil', Number], ['#indInconnues', 'inconnues', String], ['#indCensure', 'censure', String], ['#indComptage', 'comptage', String], ['#indLitsPeriodes', 'capacites', String], ['#indHEntree', 'heureEntree', Number], ['#indHSortie', 'heureSortie', Number], ['#indDMeme', 'dureeMemeJour', Number]]) {
  $(id).addEventListener('change', (e) => { etat.indMethode ??= {}; etat.indMethode[etat.service] = { ...(etat.indMethode[etat.service] ?? {}), [cle]: conv(e.target.value) }; sauver(); afficherIndicateurs() })
}
document.querySelectorAll('input[name=indPar]').forEach((r) => r.addEventListener('change', afficherIndicateurs))
// Mise à jour automatique : toute sauvegarde qui change les lignes (ajout, correction, import, suppression)
// relance le calcul si l'onglet est affiché ; sinon il sera recalculé à son ouverture.
{
  const sauverInitial = sauver; let minuterieMaj = null
  sauver = function () {
    sauverInitial()
    if (!$('#vueIndicateurs').classList.contains('visible') || signatureSaisie() === signatureIndicateurs) return
    clearTimeout(minuterieMaj); minuterieMaj = setTimeout(() => { const z = $('#indZone'), haut = z.scrollTop; afficherIndicateurs(); z.scrollTop = haut }, 250)
  }
}
// Onglet Saisie : les règles et raccourcis s'ouvrent dans le même panneau que les remarques.
$('#aideSaisieBtn')?.addEventListener('click', (e) => ouvrirNotes({ titre: 'Saisie', avert: [], rem: [
  { html: $('#aideSaisie').innerHTML }] }, 'rem', e.currentTarget))
