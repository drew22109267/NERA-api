using System.Text;
using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

[ApiController]
[Route("api/rapports")]
[Authorize(Roles = "direction,gestionnaire,data,admin")]
public class RapportsController : BaseController
{
    readonly AppDbContext _db;
    readonly PrevisionCapaciteService _prev;
    public RapportsController(AppDbContext db, PrevisionCapaciteService prev) { _db = db; _prev = prev; }

    [HttpGet("indicateurs")]
    public async Task<IActionResult> Indicateurs([FromQuery] int jours = 30)
    {
        var depuis = DateTime.UtcNow.AddDays(-Math.Clamp(jours, 1, 365));
        var passages = await _db.Passages.AsNoTracking().Where(p => p.Arrivee >= depuis).ToListAsync();
        var rdv = await _db.RendezVous.AsNoTracking().ToListAsync();
        var tries = passages.Count(p => p.Categorie != null);
        var corrections = passages.Count(p => p.CorrectionNouvelle != null);
        var services = await _db.Services.AsNoTracking().Where(s => s.Actif && s.Hospitalisation).ToListAsync();
        var armes = services.Sum(s => s.LitsArmes);

        return Ok(new
        {
            periodeJours = jours,
            passages = passages.Count,
            tries,
            corrections,
            tauxCorrection = tries > 0 ? Math.Round(100.0 * corrections / tries, 1) : 0,
            divergences = passages.Count(p => p.DecisionDivergence),
            tauxOccupationMoyen = armes > 0 ? Math.Round(100.0 * services.Sum(s => s.Occupes) / armes, 1) : 0,
            litsBloques = services.Sum(s => s.Bloques),
            rendezVousTotal = rdv.Count,
            rendezVousHonores = rdv.Count(r => r.Statut == "Honoré"),
            rendezVousManques = rdv.Count(r => r.Statut == "Manqué"),
            demandesNonSatisfaites = await _db.Demandes.CountAsync(d => d.Date >= depuis),
            sejoursEnCours = await _db.Sejours.CountAsync(s => s.Statut == "En cours"),
            dureeMoyenneSejour = await DureeMoyenneAsync(),
            attenteMoyenneMinutes = passages.Count(p => p.TriageLe != null) > 0
                ? Math.Round(passages.Where(p => p.TriageLe != null)
                    .Average(p => (p.TriageLe!.Value - p.Arrivee).TotalMinutes), 0)
                : (double?)null,
            parCategorie = Enumerable.Range(1, 4).Select(c => new
            {
                categorie = c,
                nombre = passages.Count(p => p.Categorie == c)
            })
        });
    }

    async Task<double?> DureeMoyenneAsync()
    {
        var termines = await _db.Sejours.AsNoTracking()
            .Where(s => s.Sortie != null).Select(s => new { s.Entree, s.Sortie }).ToListAsync();
        if (termines.Count == 0) return null;
        return Math.Round(termines.Average(s => (s.Sortie!.Value - s.Entree).TotalDays), 1);
    }

    [HttpGet("occupation.csv")]
    public async Task<IActionResult> OccupationCsv()
    {
        var services = await _db.Services.AsNoTracking().Where(s => s.Actif && s.Hospitalisation)
            .OrderBy(s => s.Ordre).ToListAsync();
        var sb = new StringBuilder();
        sb.AppendLine("Code;Service;Pole;Installes;Armes;Occupes;Bloques;Libres;Occupation %;Risque J+3 %");
        foreach (var s in services)
        {
            var libres = Math.Max(0, s.LitsArmes - s.Occupes - s.Bloques);
            var taux = s.LitsArmes > 0 ? 100.0 * s.Occupes / s.LitsArmes : 0;
            var risque = PrevisionCapaciteService.RisqueSaturation(_prev.Prevoir(s, 7).Points, 3) * 100;
            sb.AppendLine($"{s.Code};{s.Nom};{s.Pole};{s.LitsInstalles};{s.LitsArmes};{s.Occupes};{s.Bloques};{libres};{taux:F1};{risque:F1}");
        }
        return File(Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(sb.ToString())).ToArray(),
            "text/csv", $"occupation-{DateTime.UtcNow:yyyy-MM-dd}.csv");
    }

    /// <summary>Sauvegarde intégrale de la base, en JSON — prévue avant toute réinitialisation.</summary>
    [HttpGet("export-complet"), Authorize(Roles = "admin,direction")]
    public async Task<IActionResult> Export()
    {
        var dump = new
        {
            exporteLe = DateTime.UtcNow,
            services = await _db.Services.AsNoTracking().ToListAsync(),
            patients = await _db.Patients.AsNoTracking().ToListAsync(),
            passages = await _db.Passages.AsNoTracking().Include(p => p.Triage).ToListAsync(),
            sejours = await _db.Sejours.AsNoTracking().ToListAsync(),
            rendezVous = await _db.RendezVous.AsNoTracking().ToListAsync(),
            demandes = await _db.Demandes.AsNoTracking().ToListAsync(),
            predictions = await _db.Predictions.AsNoTracking().ToListAsync(),
            audits = await _db.Audits.AsNoTracking().ToListAsync()
        };
        return Ok(dump);
    }
}

[ApiController]
[Route("api/qualite")]
[Authorize(Roles = "data,admin,direction")]
public class QualiteController : BaseController
{
    readonly AppDbContext _db;
    public QualiteController(AppDbContext db) => _db = db;

    /// <summary>Complétude et équité calculées sur les données réelles, jamais illustratives.</summary>
    [HttpGet]
    public async Task<ActionResult<QualiteDto>> Get()
    {
        var preds = await _db.Predictions.AsNoTracking().ToListAsync();
        var triages = await _db.Triages.AsNoTracking().ToListAsync();
        var total = triages.Count;

        List<CompletudeDto> completude;
        if (total == 0) completude = new List<CompletudeDto>();
        else
        {
            (string, int)[] champs =
            {
                ("PA systolique", triages.Count(t => t.Pas != null)),
                ("Fréquence cardiaque", triages.Count(t => t.Fc != null)),
                ("Fréquence respiratoire", triages.Count(t => t.Fr != null)),
                ("SpO₂", triages.Count(t => t.Spo2 != null)),
                ("Température", triages.Count(t => t.Temperature != null)),
                ("Glycémie capillaire", triages.Count(t => t.Glycemie != null)),
                ("Niveau de conscience (AVPU)", triages.Count(t => t.Avpu != null && t.Avpu != "Non évalué")),
                ("Douleur EVA", triages.Count(t => t.Eva != null))
            };
            completude = champs.Select(c => new CompletudeDto(c.Item1, c.Item2, total,
                Math.Round(100.0 * c.Item2 / total, 1))).ToList();
        }

        var passages = await _db.Passages.AsNoTracking().Include(p => p.Patient).ToListAsync();
        var groupes = new (string Label, Func<Passage, bool> Test)[]
        {
            ("Milieu urbain", p => p.Patient?.Milieu == "Urbain"),
            ("Milieu rural", p => p.Patient?.Milieu == "Rural"),
            ("Moins de 15 ans", p => p.Patient?.Age < 15),
            ("15 à 64 ans", p => p.Patient?.Age >= 15 && p.Patient?.Age < 65),
            ("65 ans et plus", p => p.Patient?.Age >= 65),
            ("Femmes", p => p.Patient?.Sexe == "F"),
            ("Hommes", p => p.Patient?.Sexe == "M"),
            ("Indigent / gratuité", p => p.Patient?.ModePaiement == "Indigent")
        };

        var equite = groupes.Select(g =>
        {
            var sous = passages.Where(p => p.Categorie != null && g.Test(p)).ToList();
            var corr = sous.Count(p => p.CorrectionNouvelle != null);
            return new EquiteDto(g.Label, sous.Count,
                sous.Count > 0 ? Math.Round(100.0 * corr / sous.Count, 1) : 0,
                sous.Count > 0 ? Math.Round(sous.Average(p => p.Categorie!.Value), 2) : 0);
        }).Where(e => e.Effectif > 0).ToList();

        var ecarts = preds.Count(p => p.Ecart);
        return Ok(new QualiteDto(preds.Count, ecarts,
            preds.Count > 0 ? Math.Round(100.0 * ecarts / preds.Count, 1) : 0,
            completude, equite,
            "Chiffres calculés sur les données réellement saisies dans cette base. Aucune donnée synthétique n'entre dans ces indicateurs ; une performance obtenue après augmentation de données ne serait pas comparable et n'est pas affichée ici."));
    }

    [HttpGet("predictions")]
    public async Task<ActionResult<PageResult<PredictionDto>>> Predictions(
        [FromQuery] string? recherche, [FromQuery] int page = 1, [FromQuery] int pageSize = 25)
    {
        page = Math.Max(1, page); pageSize = Math.Clamp(pageSize, 5, 100);
        var b = _db.Predictions.AsNoTracking().AsQueryable();
        if (!string.IsNullOrWhiteSpace(recherche))
        {
            var t = recherche.Trim().ToLower();
            b = b.Where(p => p.Modele.ToLower().Contains(t) || p.TypeModele.ToLower().Contains(t));
        }
        var q = b.OrderByDescending(p => p.Date);
        var total = await q.CountAsync();
        var items = await q.Skip((page - 1) * pageSize).Take(pageSize).ToListAsync();
        return Ok(new PageResult<PredictionDto>(items.Select(p => new PredictionDto(p.Id, p.Date, p.PassageId,
            p.Modele, p.TypeModele, p.Score, p.Sortie, p.Confiance, p.DecisionHumaine, p.Ecart, p.ExplicationJson))
            .ToList(), total, page, pageSize));
    }

    [HttpGet("audit")]
    public async Task<ActionResult<PageResult<AuditDto>>> Audit(
        [FromQuery] string? type, [FromQuery] string? recherche,
        [FromQuery] int page = 1, [FromQuery] int pageSize = 30)
    {
        page = Math.Max(1, page); pageSize = Math.Clamp(pageSize, 5, 100);
        var q = _db.Audits.AsNoTracking().AsQueryable();
        if (!string.IsNullOrWhiteSpace(type) && type != "Tous") q = q.Where(a => a.Type == type);
        if (!string.IsNullOrWhiteSpace(recherche))
        {
            var t = recherche.Trim().ToLower();
            q = q.Where(a => a.Utilisateur.ToLower().Contains(t) || a.Action.ToLower().Contains(t)
                || (a.Cible != null && a.Cible.ToLower().Contains(t)));
        }
        q = q.OrderByDescending(a => a.Date);
        var total = await q.CountAsync();
        var items = await q.Skip((page - 1) * pageSize).Take(pageSize).ToListAsync();
        return Ok(new PageResult<AuditDto>(items.Select(a => new AuditDto(a.Id, a.Date, a.Utilisateur, a.Role,
            a.Type, a.Action, a.Cible, a.Detail)).ToList(), total, page, pageSize));
    }
}

[ApiController]
[Route("api/parametres")]
[Authorize]
public class ParametresController : BaseController
{
    readonly AppDbContext _db;
    readonly AuditService _audit;
    public ParametresController(AppDbContext db, AuditService audit) { _db = db; _audit = audit; }

    [HttpGet]
    public async Task<ActionResult<List<ParametreDto>>> Liste() =>
        Ok(await _db.Parametres.AsNoTracking().OrderBy(p => p.Cle)
            .Select(p => new ParametreDto(p.Cle, p.Valeur, p.Libelle)).ToListAsync());

    [HttpPut("{cle}"), Authorize(Roles = "admin,gestionnaire,direction")]
    public async Task<IActionResult> Modifier(string cle, [FromBody] Dictionary<string, string> body)
    {
        var p = await _db.Parametres.FirstOrDefaultAsync(x => x.Cle == cle);
        if (p is null) return NotFound();
        if (!body.TryGetValue("valeur", out var v)) return BadRequest(new { message = "Valeur manquante." });
        p.Valeur = v;
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Modification de paramètre", cle, v);
        return NoContent();
    }

    [HttpGet("etablissement")]
    public async Task<IActionResult> Etablissement()
    {
        var e = await _db.Etablissements.AsNoTracking().FirstOrDefaultAsync();
        return e is null ? NotFound(new { message = "Aucun établissement paramétré." })
            : Ok(new { e.Id, e.Code, e.Nom, e.Categorie, e.Ville, e.Region });
    }
}
