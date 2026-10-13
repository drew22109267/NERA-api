/*
  Registres des services : les colonnes à recopier pour chaque service.

  Chaque service tient son registre à sa manière : on décrit ici, service par service,
  les colonnes telles qu'elles apparaissent dans le cahier (sans les colonnes qui
  identifient le patient : nom, prénom, contact, ainsi que médecin et facture).

  Pour ajouter un service : copier le bloc PED, changer le code (clé), le nom et les colonnes.

  Champs d'une colonne :
    k        identifiant interne (minuscules, sans espace ni accent)
    l        intitulé, tel qu'il sera écrit dans le fichier CSV exporté
    aide     explication affichée sous le champ
    date     true si la case contient une date (contrôle jj/mm/aa, raccourcis « = » et jour seul)
    court    true pour un champ étroit (deux par ligne)
    tableau  true pour l'afficher dans le tableau « Lignes de cette photo »
    raccourcis  termes proposés en boutons sous le champ : un clic, ou Alt + son numéro, l'ajoute à la case
    separateur  ce qui sépare deux termes ajoutés (espace par défaut ; « + » pour les traitements)
    rare     true si la case est presque toujours vide : la touche Entrée la saute (on peut cliquer dessus)
*/
// Réglages communs : période de test final (jamais comptée dans les indicateurs), fenêtre de censure.
window.CONFIG_SAISIE = { dateVerrou: '2026-09-01', fenetreCensure: 30 }

// Abréviations fréquentes des registres : affichées en bulle d'aide sur les boutons de saisie rapide
// et dans le lexique de « Comment ça marche ? ». À compléter au fur et à mesure.
// Quartiers écrits de plusieurs façons : abréviation → nom complet. Les variantes d'écriture (majuscules,
// accents, tirets, « ? » final) sont regroupées automatiquement ; ici, seulement les abréviations.
window.ALIAS_QUARTIERS = {
  CV: 'Cité verte',
  Oyomabang: 'Oyom-Abang', 'Ojom-Abang': 'Oyom-Abang',
}

window.ABREVIATIONS = {
  APG: 'Accès palustre grave (paludisme grave)',
  ATB: 'Antibiotiques ; dans « Bilan demandé » : antibiogramme (culture d’un prélèvement pour savoir quel antibiotique est efficace)',
  LCR: 'Liquide céphalo-rachidien, prélevé par ponction lombaire (recherche de méningite)',
  'GS/Rh': 'Groupe sanguin et rhésus (demandé avant une transfusion)',
  'Rx tho': 'Radiographie du thorax (poumons et cœur)',
  EEG: 'Électroencéphalogramme : enregistrement de l’activité électrique du cerveau (convulsions, épilepsie)',
  BU: 'Bandelette urinaire (recherche d’infection urinaire)',
  CRP: 'Protéine C réactive (marqueur d’inflammation, d’infection)',
  SG: 'Sérum glucosé (perfusion)',
  NFS: 'Numération formule sanguine (anémie, infection, plaquettes)',
  TDR: 'Test de diagnostic rapide du paludisme',
  GE: 'Goutte épaisse (recherche du paludisme au microscope)',
  SCAM: 'Sortie contre avis médical',
  'SG10%': 'Sérum glucosé à 10 % (perfusion)',
  'Artesun inj': 'Artésunate injectable (traitement du paludisme grave)',
  'PCM inj': 'Paracétamol injectable',
  Ceftri: 'Ceftriaxone (antibiotique)',
  Genta: 'Gentamicine (antibiotique)',
  'Métro inj': 'Métronidazole injectable (même produit que le Flagyl)',
  Saforelle: 'Soin intime (toilette)',
  Diazepam: 'Anticonvulsivant (convulsions)',
  'Phéno': 'Phénobarbital (anticonvulsivant)',
  'Dexa inj': 'Dexaméthasone injectable (corticoïde)',
  'Oxygène': 'Oxygénothérapie',
  Coartem: 'Artéméther-luméfantrine en comprimés (paludisme, relais de l’Artesun injectable)',
  Artefan: 'Artéméther-luméfantrine, autre marque (même rôle que Coartem)',
  Dexorange: 'Sirop de fer et d’acide folique (anémie)',
  'PCM sp': 'Paracétamol sirop',
  Efferalgan: 'Paracétamol (comprimé effervescent ou sirop)',
  OMA: 'Otite moyenne aiguë (infection de l’oreille moyenne) ; bilatérale = les deux oreilles',
  GEF: 'Gastro-entérite fébrile (diarrhée, vomissements avec fièvre) — à confirmer avec le service',
  Shigellose: 'Dysenterie bactérienne (diarrhée avec sang, fièvre) due aux Shigella',
  Rhinobronchite: 'Infection du nez et des bronches (nez qui coule, toux), le plus souvent virale',
  'Érysipèle': 'Infection bactérienne de la peau (plaque rouge, chaude, gonflée), souvent au streptocoque',
  'Coartem sp': 'Artéméther-luméfantrine en suspension buvable (paludisme)',
  'Cefixime sp': 'Céfixime en sirop (antibiotique)',
  Amoxicilline: 'Antibiotique (1er choix de l’otite, de nombreuses infections ORL et respiratoires)',
  Clamoxyl: 'Amoxicilline (marque)',
  Augmentin: 'Amoxicilline + acide clavulanique (antibiotique)',
  Zinnat: 'Céfuroxime (antibiotique)',
  Orelox: 'Cefpodoxime (antibiotique)',
  'Ibuprofène': 'Anti-inflammatoire contre la douleur et la fièvre',
  Doliprane: 'Paracétamol (marque)',
  'Salbu en nébu': 'Salbutamol en nébulisation (aérosol qui ouvre les bronches : asthme, bronchiolite)',
  'Solumédrol inj': 'Méthylprednisolone injectable (corticoïde : crise d’asthme sévère…)',
  'Ventoline spray': 'Salbutamol en inhalateur (asthme)',
  'Taxim-O': 'Céfixime par la bouche (antibiotique)',
  'Fleming inj': 'Amoxicilline + acide clavulanique injectable (antibiotique)',
  'Azicure sp': 'Azithromycine en sirop (antibiotique)',
  Desanol: 'Médicament noté ainsi dans le registre (molécule à préciser avec le service)',
  Ixine: 'Médicament noté ainsi dans le registre (molécule à préciser ; peut-être une céfixime)',
  Fixine: 'Médicament noté ainsi dans le registre (molécule à préciser ; peut-être une céfixime)',
  Physiodose: 'Sérum physiologique en unidoses (lavage du nez)',
  Zymaduo: 'Gouttes de vitamine D + fluor (nourrissons)',
  Otipax: 'Gouttes auriculaires contre la douleur de l’oreille',
  Azithromycine: 'Antibiotique (infections respiratoires notamment)',
  Algofene: 'Médicament noté ainsi dans le registre (molécule à préciser avec le service)',
  Cetafor: 'Médicament noté ainsi dans le registre (molécule à préciser avec le service)'
}

window.REGISTRES = {
  PED: {
    nom: 'Pédiatrie',
    ordre: 'n_ordre',                   // numéro de ligne, incrémenté automatiquement
    maxLignesParPhoto: 15,              // une page du registre contient au plus 15 lignes
    dateReference: 'date_enregistrement', // date utilisée par « = » et par l'identifiant de ligne
    montant: { depuis: 'observation', vers: 'prix' }, // « 7500 Sortie » → Prix 7500 + Observation Sortie
    recopier: { date_entree: 'date_enregistrement' },   // le plus souvent la même date
    sortieCalculee: { sortie: 'date_sortie', entree: 'date_entree', jours: 'nb_jours' },  // affichée, calculée à l'import
    colonnes: [
      { k: 'n_ordre', l: "N° d'ordre", court: true, tableau: true,
        aide: 'Numéro de la ligne dans le registre (01, 02…).' },
      { k: 'date_enregistrement', l: 'Date (enregistrement)', date: true, court: true,
        aide: '2ᵉ colonne : jour où la ligne a été écrite.' },
      { k: 'ancien_nouveau', l: 'Ancien / Nouveau', court: true,
        aide: 'N = nouveau malade (1ʳᵉ hospitalisation ici) · A = ancien malade (déjà hospitalisé ici).' },
      { k: 'sexe', l: 'Sexe', court: true,
        aide: 'M (♂) ou F (♀).' },
      { k: 'age', l: 'Âge', court: true, tableau: true,
        aide: 'Avec l’unité, comme écrit : 4 ans, 9 mois, 5 j.' },
      { k: 'domicile', l: 'Domicile', court: true,
        aide: 'Quartier de résidence.' },
      { k: 'date_entree', l: "Date d'entrée", date: true, court: true, tableau: true,
        aide: 'Jour de l’admission réelle. Recopiée de la date d’enregistrement : à changer seulement si elle est différente.' },
      { k: 'date_sortie', l: 'Date de sortie', date: true, court: true, rare: true,
        aide: 'Seulement si elle est écrite dans le registre. Sinon, laissez vide : elle est calculée avec le nombre de jours.' },
      { k: 'diagnostic', l: 'Diagnostic', tableau: true, raccourcis: ['APG', 'Sepsis', 'Anémie sévère', 'Appendicite aiguë', 'Vaginite à E. coli', 'Érysipèle', 'OMA bilatérale', 'GEF', 'Shigellose', 'Rhinobronchite'],
        aide: 'Diagnostic à l’arrivée, recopié tel quel (APG, sepsis, sel infectieux…).' },
      { k: 'bilan', l: 'Bilan demandé', raccourcis: ['NFS', 'CRP', 'BU', 'GE', 'TDR', 'ATB', 'LCR', 'GS/Rh', 'Rx tho', 'EEG'],
        aide: 'Examens demandés (NFS, CRP, BU, GE, LCR…).' },
      { k: 't3_recu', l: 'T3 reçu', separateur: ' + ',
        raccourcis: ['SG10%', 'PCM inj', 'Artesun inj', 'Cetafor', 'Genta', 'Transfusion', 'Spasfon inj', 'Saforelle', 'Ceftri',
          'ES', 'Flagyl inj', 'Métro inj', 'Diazepam', 'Phéno', 'Dexa inj', 'Oxygène', 'Algofene',
          'Coartem', 'Artefan', 'Dexorange', 'PCM sp', 'Efferalgan', 'Azithromycine', 'Coartem sp', 'Cefixime sp',
          'Amoxicilline', 'Clamoxyl', 'Augmentin', 'Zinnat', 'Orelox', 'Ibuprofène', 'Doliprane', 'Otipax', 'Physiodose', 'Zymaduo', 'Salbu en nébu', 'Solumédrol inj', 'Ventoline spray', 'Taxim-O', 'Fleming inj', 'Azicure sp', 'Desanol', 'Ixine', 'Fixine'],
        aide: 'Traitement reçu (artésunate, transfusion, SG10 %…).' },
      { k: 'ge_tdr', l: 'GE / TDR palu', raccourcis: ['GE+', 'GE (−)', 'TDR+', 'TDR (−)'],
        aide: 'Résultat du test du paludisme, avec la densité si elle est écrite : GE+ puis tapez 72000. Pour un négatif, écrivez « GE (−) » (le bouton le fait).' },
      { k: 'diagnostic_sortie', l: 'Diagnostic de sortie', raccourcis: ['APG', 'Sepsis', 'Anémie sévère', 'Paludisme', 'Appendicite aiguë', 'Vaginite à E. coli', 'Érysipèle', 'OMA bilatérale', 'GEF', 'Shigellose', 'Rhinobronchite'],
        aide: 'Diagnostic retenu à la sortie.' },
      { k: 't3_sortie', l: 'T3 de sortie', separateur: ' + ',
        raccourcis: ['Coartem', 'Artefan', 'Dexorange', 'PCM sp', 'Efferalgan', 'Azithromycine', 'Coartem sp', 'Cefixime sp',
          'Amoxicilline', 'Clamoxyl', 'Augmentin', 'Zinnat', 'Orelox', 'Ibuprofène', 'Doliprane', 'Otipax', 'Physiodose', 'Zymaduo', 'Salbu en nébu', 'Solumédrol inj', 'Ventoline spray', 'Taxim-O', 'Fleming inj', 'Azicure sp', 'Desanol', 'Ixine', 'Fixine'],
        aide: 'Traitement prescrit à la sortie.' },
      { k: 'nb_jours', l: 'Nbre de jours', court: true,
        aide: 'Nombre de jours d’hospitalisation (3 jrs…).' },
      { k: 'prix', l: 'Prix', court: true,
        aide: 'Montant en FCFA. Rempli tout seul si vous tapez « 7500 Sortie » dans Observation.' },
      { k: 'observation', l: 'Observation', tableau: true,
        aide: 'Issue : Sortie, SCAM, Référé, Décès, Transféré en … (avec le service).' },
      { k: 'remarque', l: 'Remarque de saisie',
        aide: 'Pour vous : page abîmée, ligne barrée, doute… (facultatif).' }
    ]
  },

  // Registre des urgences n° 2 (septembre 2025 → janvier 2026) : la décision y est écrite.
  // Le nom n'est jamais saisi. Le diagnostic est écrit APRÈS l'examen : il ne servira pas à
  // prévoir la décision (fuite d'information), seulement à décrire les patients.
  URG: {
    nom: 'Urgences (registre 2)',
    ordre: 'n_ordre',
    dateReference: 'date_passage',
    colonnes: [
      { k: 'n_ordre', l: "N° d'ordre", court: true, tableau: true,
        aide: 'Numéro de la ligne s’il est écrit ; sinon laissez l’outil numéroter.' },
      { k: 'date_passage', l: 'Date de passage', date: true, court: true, tableau: true,
        aide: 'Jour où l’enfant ou l’adulte est passé aux urgences.' },
      { k: 'sexe', l: 'Sexe', court: true,
        aide: 'M (♂) ou F (♀).' },
      { k: 'age', l: 'Âge', court: true, tableau: true,
        aide: 'Avec l’unité, comme écrit : 4 ans, 9 mois, 35 ans.' },
      { k: 'residence', l: 'Résidence', court: true,
        aide: 'Quartier de résidence.' },
      { k: 'pouls', l: 'Pouls', court: true,
        aide: 'Battements par minute (ex. 112).' },
      { k: 'ta', l: 'TA', court: true,
        aide: 'Tension artérielle comme écrite : 120/80 ou 12/8.' },
      { k: 'glycemie', l: 'Glycémie', court: true,
        aide: 'Avec l’unité si elle est écrite : 0,95 g/L, 5,2 mmol/L, HI, LO.' },
      { k: 'poids', l: 'Poids', court: true,
        aide: 'En kg (ex. 14,5).' },
      { k: 'temperature', l: 'Température', court: true,
        aide: 'En °C, comme écrite (ex. 39,2).' },
      { k: 'symptomes', l: 'Symptômes', tableau: true, separateur: ', ',
        raccourcis: ['Fièvre', 'Toux', 'Vomissements', 'Diarrhée', 'Convulsions', 'Douleur abdominale', 'Céphalées', 'Dyspnée', 'Pâleur'],
        aide: 'Motif et symptômes, recopiés tels quels.' },
      { k: 'diagnostic', l: 'Diagnostic',
        aide: 'Diagnostic écrit par le médecin des urgences.' },
      { k: 'decision', l: 'Décision', court: true, tableau: true,
        raccourcis: ['Hospitalisé', 'MEO', 'Externe', 'Référé', 'Décédé', 'SCAM'],
        aide: 'Ce qui a été décidé : hospitalisé (préciser le service si écrit), MEO, externe/retour à domicile, référé…' },
      { k: 'remarque', l: 'Remarque de saisie',
        aide: 'Pour vous : ligne barrée, doute… (facultatif).' }
    ]
  }
}
