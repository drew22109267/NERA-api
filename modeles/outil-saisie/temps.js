// ═══════════════════════════════════════════════════════════════════════════════════════════
// Navigation dans le temps pour TOUS les graphes jour par jour (ceux dessinés par lignesSvg) :
//   - regroupement : jour, semaine (lundi → dimanche), mois, année — chaque point est la MOYENNE des jours
//     de la période (présents moyens, admissions moyennes par jour…), pour garder la même unité ;
//   - zoom : boutons − / + , molette de la souris à l'endroit pointé ; déplacement : ‹ › ou glisser ;
//   - animation : la courbe avance dans le temps, jour après jour (ou semaine, mois…), comme un graphique
//     de cours en direct ; « Tout » revient à la période entière.
// La vue de chaque rubrique est gardée (etat.vuesTemps) et s'applique aussi aux trois méthodes de comptage.
// ═══════════════════════════════════════════════════════════════════════════════════════════
(function () {
  let vueCourante = null                       // vue de la rubrique en cours de dessin
  const vues = () => (etat.vuesTemps ??= {})
  const PAS = [['jour', 'Jour'], ['semaine', 'Semaine'], ['mois', 'Mois'], ['annee', 'Année']]
  const cleDe = (pas, j) => (pas === 'semaine' ? Math.floor((j + 3) / 7) : pas === 'mois' ? versDate(j).slice(0, 7) : pas === 'annee' ? versDate(j).slice(0, 4) : j)

  // Fenêtre et regroupement appliqués aux données d'un graphe, avant de le dessiner.
  function appliquerVue(p) {
    const v = vueCourante
    if (!v || !p.series) return p
    const N = Math.max(...p.series.map((s) => s.valeurs.length), p.barres ? p.barres.valeurs.length : 0)
    if (N < 3) return p
    v.n = N
    let i0 = Math.max(0, Math.min(v.i0 ?? 0, N - 2)), i1 = Math.min(N - 1, v.i1 ?? N - 1)
    if (v.anim !== undefined && v.anim !== null) i1 = Math.min(i1, i0 + v.anim)
    if (i1 <= i0) i1 = Math.min(N - 1, i0 + 1)
    v.vu = [i0, i1]
    const groupes = []; let der = null
    for (let i = i0; i <= i1; i++) { const k = cleDe(v.pas ?? 'jour', p.debutNum + i); if (k !== der) { groupes.push([]); der = k } groupes.at(-1).push(i) }
    const moy = (t) => groupes.map((g) => { const x = g.map((i) => t[i]).filter((z) => z !== null && z !== undefined && Number.isFinite(z)); return x.length ? x.reduce((a, b) => a + b, 0) / x.length : null })
    return { ...p, debutNum: p.debutNum + i0, jours: groupes.map((g) => p.debutNum + g[0]), pas: v.pas ?? 'jour',
      series: p.series.map((s) => ({ ...s, valeurs: moy(s.valeurs) })), bandes: (p.bandes ?? []).map((b) => ({ ...b, bas: moy(b.bas), haut: moy(b.haut) })),
      barres: p.barres ? { ...p.barres, valeurs: moy(p.barres.valeurs) } : null,
      verticales: (p.verticales ?? []).map((x) => ({ ...x, i: groupes.findIndex((g) => g.includes(x.i)) })).filter((x) => x.i >= 0) }
  }
  const lignesOrigine = lignesSvg
  lignesSvg = (p) => lignesOrigine(appliquerVue(p))      // eslint-disable-line no-global-assign

  // Barre d'outils au-dessus des graphes jour par jour d'une rubrique.
  function barre(titre, v) {
    const [i0, i1] = v.vu ?? [0, v.n - 1], d0 = contexteVue?.d?.debutNum
    const periode = d0 !== undefined ? `${fmtDate(versDate(d0 + i0))} → ${fmtDate(versDate(d0 + i1))}` : ''
    return `<div class="ind-temps" data-vue="${echapper(titre)}">
      <span class="ind-temps-seg">${PAS.map(([k, l]) => `<button type="button" data-tz-pas="${k}" class="${(v.pas ?? 'jour') === k ? 'actif' : ''}">${l}</button>`).join('')}</span>
      <span class="ind-temps-seg"><button type="button" data-tz="moins" title="Dézoomer (voir plus de jours)">−</button><button type="button" data-tz="plus" title="Zoomer (voir moins de jours, plus de détail)">+</button>
        <button type="button" data-tz="gauche" title="Reculer dans le temps">‹</button><button type="button" data-tz="droite" title="Avancer dans le temps">›</button>
        <button type="button" data-tz="tout" title="Toute la période">Tout</button></span>
      <button type="button" data-tz="anim" class="ind-temps-anim ${v.anim !== undefined && v.anim !== null ? 'actif' : ''}" title="Faire avancer la courbe dans le temps">${v.anim !== undefined && v.anim !== null ? 'Pause' : 'Animation'}</button>
      <span class="ind-temps-periode">${periode}${(v.pas ?? 'jour') !== 'jour' ? ` · moyenne par ${{ semaine: 'semaine', mois: 'mois', annee: 'année' }[v.pas]}` : ''} · molette : zoom, glisser : déplacer</span>
    </div>`
  }
  const sectionOrigine = htmlSection
  htmlSection = function (s, k, c, W, agrandi = false) {      // eslint-disable-line no-global-assign
    vueCourante = vues()[s.t] ?? (vues()[s.t] = { pas: 'jour' })
    vueCourante.n = null
    let html
    try { html = sectionOrigine(s, k, c, W, agrandi) } finally { var v = vueCourante; vueCourante = null }
    if (!v.n || !html.includes('survol-zone')) return html
    const i = html.indexOf('<div class="ind-graphe">') >= 0 && html.indexOf('<div class="ind-variante') >= 0 ? html.indexOf('<div class="ind-variante') : html.indexOf('<div class="ind-graphe">')
    return i < 0 ? html : html.slice(0, i) + barre(s.t, v) + html.slice(i)
  }

  // Redessine une seule rubrique (rapide : l'animation ne redessine pas toute la page).
  function redessiner(sec) {
    if (sec.closest('#indModalCorps')) { const m = $('#indModalCorps'), h = m.scrollTop; ouvrirModal(modalK); m.scrollTop = h; return }
    const k = +sec.dataset.k, s = sectionsVue[k]; if (!s || !contexteVue) return
    const W = contexteVue.W, tmp = document.createElement('div')
    tmp.innerHTML = htmlSection(s, k, contexteVue, W)
    const nouv = tmp.firstElementChild; if (!nouv) return
    sec.replaceWith(nouv)
    if (typeof convertirTitres === 'function') convertirTitres(nouv)
  }
  const vueDe = (el) => { const b = el.closest('.ind-section')?.querySelector('.ind-temps'); return b ? vues()[b.dataset.vue] : null }
  function changer(sec, f) { const b = sec.querySelector('.ind-temps'); if (!b) return; const v = vues()[b.dataset.vue]; if (!v?.n) return; f(v, v.n); sauver(); redessiner(sec) }
  const fenetre = (v, N) => { const i0 = v.i0 ?? 0, i1 = v.i1 ?? N - 1; return [i0, i1, i1 - i0] }
  function zoomer(v, N, facteur, centre = 0.5) {
    const [i0, i1, l] = fenetre(v, N), nl = Math.max(14, Math.min(N - 1, Math.round(l * facteur))), c = i0 + centre * l
    v.i0 = Math.max(0, Math.round(c - centre * nl)); v.i1 = Math.min(N - 1, v.i0 + nl); v.i0 = Math.max(0, v.i1 - nl)
  }
  const animations = new Map()
  function arreterAnim(sec, v) { clearInterval(animations.get(v)); animations.delete(v); v.anim = null }

  document.addEventListener('click', (e) => {
    const bt = e.target.closest('.ind-temps button'); if (!bt) return
    const sec = bt.closest('.ind-section'), v = vueDe(bt); if (!v) return
    if (bt.dataset.tzPas) return changer(sec, (vv) => { vv.pas = bt.dataset.tzPas })
    const a = bt.dataset.tz
    if (a === 'anim') {
      if (animations.has(v)) { arreterAnim(sec, v); sauver(); return redessiner(sec) }
      const N = v.n, [i0, i1] = fenetre(v, N), pasAnim = Math.max(1, Math.round((i1 - i0) / 160))
      v.anim = 0
      animations.set(v, setInterval(() => {
        const s2 = document.querySelector(`.ind-temps[data-vue="${CSS.escape(bt.closest('.ind-temps').dataset.vue)}"]`)?.closest('.ind-section')
        if (!s2) { arreterAnim(null, v); return }
        v.anim += pasAnim
        if (i0 + v.anim >= i1) { arreterAnim(s2, v); redessiner(s2); return }
        redessiner(s2)
      }, 90))
      return redessiner(sec)
    }
    changer(sec, (vv, N) => {
      const [i0, i1, l] = fenetre(vv, N)
      if (a === 'tout') { vv.i0 = null; vv.i1 = null }
      if (a === 'plus') zoomer(vv, N, 0.6)
      if (a === 'moins') zoomer(vv, N, 1 / 0.6)
      const dec = Math.max(1, Math.round(l * 0.4))
      if (a === 'gauche') { vv.i0 = Math.max(0, i0 - dec); vv.i1 = vv.i0 + l }
      if (a === 'droite') { vv.i1 = Math.min(N - 1, i1 + dec); vv.i0 = vv.i1 - l }
    })
  })
  // Molette : zoom autour du point visé ; glisser : déplacement.
  document.addEventListener('wheel', (e) => {
    const z = e.target.closest?.('.survol-zone'); if (!z || !z.closest('.ind-section')?.querySelector('.ind-temps')) return
    e.preventDefault()
    const r = z.getBoundingClientRect(), centre = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))
    changer(z.closest('.ind-section'), (v, N) => zoomer(v, N, e.deltaY < 0 ? 0.8 : 1.25, centre))
  }, { passive: false })
  let glisse = null
  document.addEventListener('mousedown', (e) => {
    const z = e.target.closest?.('.survol-zone'); if (!z || e.button !== 0) return
    const sec = z.closest('.ind-section'), v = vueDe(z); if (!v?.n) return
    glisse = { sec, v, x: e.clientX, l: z.getBoundingClientRect().width, f: fenetre(v, v.n) }
  })
  document.addEventListener('mouseup', (e) => {
    if (!glisse) return
    const { sec, v, x, l, f } = glisse; glisse = null
    const dj = Math.round(-(e.clientX - x) / l * f[2]); if (Math.abs(dj) < 1) return
    changer(sec, (vv, N) => { vv.i0 = Math.max(0, Math.min(N - 1 - f[2], f[0] + dj)); vv.i1 = vv.i0 + f[2] })
  })
})()
