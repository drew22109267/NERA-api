// ═══════════════════════════════════════════════════════════════════════════════════════════
// Afficher ou masquer chaque indicateur d'un graphe en cliquant sur sa légende (tous les graphes qui ont
// une légende : courbes, bandes, barres, repères). Un élément de légende porte sa couleur et son motif
// (ligne, bande, barre) ; le clic cache dans le même graphe tout ce qui est dessiné avec cette couleur et ce
// motif. Les choix sont gardés par rubrique (etat.legendesCachees) et réappliqués après chaque nouveau dessin.
// ═══════════════════════════════════════════════════════════════════════════════════════════
(function () {
  const cachees = () => (etat.legendesCachees ??= {})
  const titreDe = (el) => el.closest('.ind-section')?.querySelector('h5 span')?.textContent || $('#indModalTitre')?.textContent || ''
  const couleurDe = (el, attr) => (el.getAttribute(attr) || '').toLowerCase()

  // Éléments du graphe (hors légende) qui correspondent à un élément de légende.
  function cibles(svg, item) {
    const c = item.dataset.legCouleur.toLowerCase(), type = item.dataset.legType
    return [...svg.querySelectorAll('path, line, rect, circle, polyline, polygon')].filter((el) => {
      if (el.closest('.leg-item') || el.classList.contains('survol-zone')) return false
      const stroke = couleurDe(el, 'stroke'), fill = couleurDe(el, 'fill'), op = +(el.getAttribute('fill-opacity') ?? 1)
      if (type === 'bande') return fill === c && op < 0.6 && (stroke === '' || stroke === 'none')
      if (type === 'barre') return fill === c || (stroke === c && el.tagName === 'path')
      return stroke === c || (el.tagName === 'circle' && fill === c)
    })
  }
  function appliquer(svg) {
    const sec = titreDe(svg), noms = new Set(cachees()[sec] ?? [])
    svg.querySelectorAll('.leg-item').forEach((item) => {
      const cache = noms.has(item.dataset.legNom)
      item.style.opacity = cache ? '0.35' : ''
      cibles(svg, item).forEach((el) => { el.style.display = cache ? 'none' : '' })
    })
  }
  document.addEventListener('click', (e) => {
    const item = e.target.closest?.('.leg-item'); if (!item) return
    const svg = item.ownerSVGElement, sec = titreDe(svg), noms = new Set(cachees()[sec] ?? [])
    noms.has(item.dataset.legNom) ? noms.delete(item.dataset.legNom) : noms.add(item.dataset.legNom)
    cachees()[sec] = [...noms]; sauver()
    // tous les graphes de la rubrique (par exemple les trois méthodes de comptage) suivent le même choix
    ;(item.closest('.ind-section') ?? svg.parentElement).querySelectorAll('svg').forEach(appliquer)
  })
  // Réapplique les choix à chaque nouveau dessin (changement de rubrique, zoom, animation, recalcul).
  new MutationObserver((mutations) => {
    for (const m of mutations) for (const n of m.addedNodes) {
      if (n.nodeType !== 1) continue
      if (n.tagName === 'svg') appliquer(n); else n.querySelectorAll?.('svg').forEach((s) => s.querySelector('.leg-item') && appliquer(s))
    }
  }).observe(document.body, { childList: true, subtree: true })
})()
