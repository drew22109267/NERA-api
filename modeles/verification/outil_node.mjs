// Exécute le VRAI code de calcul de l'outil de saisie (saisie.html, registres.js, statistiques.js) hors du
// navigateur, pour le comparer à Python. Aucune copie du code : les fonctions sont extraites des fichiers de
// l'outil à chaque lancement, donc toute modification de l'outil est vérifiée.
//
// Entrée (stdin, JSON) :
//   { "tache": "occupation", "csv": "<texte CSV de l'outil>", "lits": 20, "capacites": "01/03/25=20",
//     "comptages": ["minuit", "journee", "pondere"], "heures": [12, 11, 8] }
//   { "tache": "statistiques", "appels": [{ "id": "...", "f": "pearson", "args": [[...], [...]] }, ...] }
// Sortie (stdout, JSON) : les résultats, nombre par nombre.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import vm from 'node:vm'

const ici = dirname(fileURLToPath(import.meta.url)), outil = join(ici, '..', 'outil-saisie')
const lire = (f) => readFileSync(join(outil, f), 'utf-8')

// Portion de texte entre deux repères (le premier inclus, le second exclu).
function entre(texte, debut, fin) {
  const i = texte.indexOf(debut); if (i < 0) throw new Error(`Repère introuvable dans saisie.html : ${debut}`)
  const j = texte.indexOf(fin, i + debut.length); if (j < 0) throw new Error(`Repère introuvable dans saisie.html : ${fin}`)
  return texte.slice(i, j)
}

function contexte() {
  const html = lire('saisie.html')
  const code = [
    entre(html, 'const RE_DATE =', '/**'),
    entre(html, 'function erreurDate(v, fin) {', '/** Place les'),
    entre(html, 'function lireDate(v) {', 'const ecrireDate'),
    entre(html, 'const CONFIG = window.CONFIG_SAISIE', '// ── Statistiques descriptives de la saisie'),
    entre(html, 'function issueDe(l) {', '// Grandes causes'),
  ].join('\n')
  const ctx = { window: {}, console, etat: { service: 'PED', lignes: [] } }
  ctx.window.window = ctx.window
  vm.createContext(ctx)
  vm.runInContext(lire('registres.js'), ctx)
  vm.runInContext(lire('statistiques.js'), ctx)
  vm.runInContext(`const REGISTRES = window.REGISTRES, Stat = window.Stat
    const registre = () => REGISTRES[etat.service]
    const lignesService = () => etat.lignes.filter((l) => l.service === etat.service)
    ${code}
    globalThis.__outil = { calculerIndicateurs, issueDe, lireDate, Stat }`, ctx)
  return ctx
}

// CSV de l'outil (séparateur ; , ou tabulation, guillemets) → lignes avec les clés du registre.
function lireCsv(texte, registre) {
  const premiere = texte.split(/\r?\n/, 1)[0]
  const sep = [';', ',', '\t'].reduce((a, b) => (premiere.split(b).length > premiere.split(a).length ? b : a))
  const lignes = []; let champ = '', ligne = [], guil = false
  for (let i = 0; i < texte.length; i++) {
    const c = texte[i]
    if (guil) { if (c === '"' && texte[i + 1] === '"') { champ += '"'; i++ } else if (c === '"') guil = false; else champ += c; continue }
    if (c === '"') guil = true
    else if (c === sep) { ligne.push(champ); champ = '' }
    else if (c === '\n') { ligne.push(champ.replace(/\r$/, '')); lignes.push(ligne); ligne = []; champ = '' }
    else champ += c
  }
  if (champ || ligne.length) { ligne.push(champ); lignes.push(ligne) }
  const norme = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '')
  const parLibelle = new Map(registre.colonnes.flatMap((c) => [[norme(c.l), c.k], [norme(c.k), c.k]]))
  const cles = lignes[0].map((h) => parLibelle.get(norme(h)) ?? null)
  return lignes.slice(1).filter((v) => v.some((x) => x.trim())).map((v) => {
    const l = { service: 'PED' }; cles.forEach((k, i) => { if (k) l[k] = (v[i] ?? '').trim() }); return l
  })
}

const entreeJson = JSON.parse(readFileSync(0, 'utf-8'))
const ctx = contexte(), O = ctx.__outil
let res
if (entreeJson.tache === 'occupation') {
  ctx.etat.lignes = lireCsv(entreeJson.csv, ctx.window.REGISTRES.PED)
  const [he, hs, hm] = entreeJson.heures ?? [12, 11, 8]
  res = {}
  for (const comptage of entreeJson.comptages ?? ['minuit', 'journee', 'pondere']) {
    const r = O.calculerIndicateurs(entreeJson.lits ?? 20, 'mois', { comptage, capacites: entreeJson.capacites ?? '', heureEntree: he, heureSortie: hs, dureeMemeJour: hm })
    if (r.message) { res[comptage] = { message: r.message }; continue }
    const total = r.lignes.at(-1)
    res[comptage] = { debut: r.debut, fin: r.fin, extraction: r.extraction, presents: r.presents, bas: r.bas, haut: r.haut,
      picBas: r.picBas, picHaut: r.picHaut, adm: r.adm, litsJour: r.litsJour, statuts: r.statuts,
      total: { tom: total.tom, tomBas: total.tomBas, tomHaut: total.tomHaut, JH: total.JH, ns: total.ns, dms: total.dms, wComptage: total.wComptage, sur: total.sur, rot: total.rot, inter: total.inter, adm: total.adm },
      mois: r.lignes.slice(0, -1).map((x) => ({ periode: x.periode, tom: x.tom, JH: x.JH, J: x.J, lits: x.lits })) }
  }
} else if (entreeJson.tache === 'statistiques') {
  res = {}
  const S = O.Stat
  for (const a of entreeJson.appels) {
    try {
      const f = a.f.split('.').reduce((o, k) => o[k], S)
      let v = f(...a.args)
      if (a.f.startsWith('modeles.') || a.f === 'sarima') v = v && { unPas: v.unPas, params: v.params, aic: v.aic, coef: v.coef?.map((c) => c.b), prev: v.prevoir?.(a.horizon ?? 7) }
      res[a.id] = v
    } catch (e) { res[a.id] = { erreur: String(e) } }
  }
} else throw new Error('tache : « occupation » ou « statistiques »')
process.stdout.write(JSON.stringify(res, (k, v) => (typeof v === 'number' && !Number.isFinite(v) ? null : v)))
