using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

[ApiController]
[Route("api/patients")]
public class PatientsController : BaseController
{
    readonly AppDbContext _db;
    readonly AuditService _audit;
    public PatientsController(AppDbContext db, AuditService audit) { _db = db; _audit = audit; }

    internal static PatientDto Map(Patient p) => new(p.Id, p.Reference, p.Nom, p.Prenom, p.Sexe, p.Age,
        p.Telephone, p.Email, p.Quartier, p.Arrondissement, p.Milieu, p.ModePaiement, p.ContactUrgence,
        p.Antecedents, p.Allergies, p.Consentement, p.CreeLe);

    [HttpGet]
    [Authorize(Roles = "accueil,infirmier,medecin,gestionnaire,admin,direction")]
    public async Task<ActionResult<PageResult<PatientDto>>> Liste(
        [FromQuery] string? q, [FromQuery] int page = 1, [FromQuery] int pageSize = 20,
        [FromQuery] string tri = "nom", [FromQuery] string sens = "asc")
    {
        page = Math.Max(1, page); pageSize = Math.Clamp(pageSize, 5, 100);
        var query = _db.Patients.AsNoTracking();

        if (!string.IsNullOrWhiteSpace(q))
        {
            var t = q.Trim().ToLower();
            query = query.Where(p =>
                p.Nom.ToLower().Contains(t) || p.Prenom.ToLower().Contains(t) ||
                p.Reference.ToLower().Contains(t) ||
                (p.Telephone != null && p.Telephone.Contains(t)) ||
                (p.Quartier != null && p.Quartier.ToLower().Contains(t)));
        }

        var desc = sens.Equals("desc", StringComparison.OrdinalIgnoreCase);
        query = tri switch
        {
            "age" => desc ? query.OrderByDescending(p => p.Age) : query.OrderBy(p => p.Age),
            "reference" => desc ? query.OrderByDescending(p => p.Reference) : query.OrderBy(p => p.Reference),
            "creeLe" => desc ? query.OrderByDescending(p => p.CreeLe) : query.OrderBy(p => p.CreeLe),
            _ => desc ? query.OrderByDescending(p => p.Nom) : query.OrderBy(p => p.Nom)
        };

        var total = await query.CountAsync();
        var items = await query.Skip((page - 1) * pageSize).Take(pageSize).ToListAsync();
        return Ok(new PageResult<PatientDto>(items.Select(Map).ToList(), total, page, pageSize));
    }

    [HttpGet("{id:int}")]
    public async Task<ActionResult<PatientDto>> Detail(int id)
    {
        if (UserRole == "patient" && UserPatientId != id) return Forbid();
        var p = await _db.Patients.FindAsync(id);
        if (p is null) return NotFound(new { message = "Dossier introuvable." });
        // Confidentialité : toute consultation de dossier est journalisée.
        await _audit.LogAsync("consultation", "Consultation de dossier patient", p.Reference, $"{p.Nom} {p.Prenom}");
        return Ok(Map(p));
    }

    /// <summary>Rapprochement approché : même nom, même sexe, âge à ±3 ans.</summary>
    [HttpGet("doublons"), Authorize(Roles = "accueil,infirmier,medecin,admin")]
    public async Task<ActionResult<List<PatientDto>>> Doublons([FromQuery] string nom, [FromQuery] string sexe, [FromQuery] int age)
    {
        if (string.IsNullOrWhiteSpace(nom)) return Ok(new List<PatientDto>());
        var n = nom.Trim().ToLower();
        var list = await _db.Patients.AsNoTracking()
            .Where(p => p.Nom.ToLower() == n && p.Sexe == sexe && p.Age >= age - 3 && p.Age <= age + 3)
            .Take(5).ToListAsync();
        return Ok(list.Select(Map).ToList());
    }

    [HttpPost, Authorize(Roles = "accueil,infirmier,medecin,admin")]
    public async Task<ActionResult<PatientDto>> Creer(PatientUpsertDto dto)
    {
        var p = new Patient { Reference = await AuthController.NextRefAsync(_db) };
        Appliquer(p, dto);
        _db.Patients.Add(p);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Création de dossier patient", p.Reference);
        return CreatedAtAction(nameof(Detail), new { id = p.Id }, Map(p));
    }

    /// <summary>Synthèse de l'espace patient — calculée côté serveur, jamais dans le navigateur.</summary>
    [HttpGet("{id:int}/synthese")]
    public async Task<IActionResult> Synthese(int id, [FromServices] SynthesePatientService svc)
    {
        if (UserRole == "patient" && UserPatientId != id) return Forbid();
        var s = await svc.SyntheseAsync(id);
        return s is null ? NotFound(new { message = "Dossier introuvable." }) : Ok(s);
    }

    [HttpPut("{id:int}")]
    public async Task<ActionResult<PatientDto>> Modifier(int id, PatientUpsertDto dto)
    {
        if (UserRole == "patient" && UserPatientId != id) return Forbid();
        var p = await _db.Patients.FindAsync(id);
        if (p is null) return NotFound();
        Appliquer(p, dto);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Modification de dossier patient", p.Reference);
        return Ok(Map(p));
    }

    /// <summary>Droit à l'effacement : anonymisation, l'historique de soins reste chiffré côté audit.</summary>
    [HttpDelete("{id:int}")]
    public async Task<IActionResult> Anonymiser(int id)
    {
        if (UserRole == "patient" && UserPatientId != id) return Forbid();
        if (UserRole != "patient" && UserRole != "admin") return Forbid();
        var p = await _db.Patients.FindAsync(id);
        if (p is null) return NotFound();
        p.Nom = "ANONYMISÉ"; p.Prenom = p.Reference; p.Telephone = null; p.Email = null;
        p.Quartier = null; p.Arrondissement = null; p.ContactUrgence = null;
        p.Antecedents = new List<string>(); p.Allergies = null; p.Consentement = false;
        await _db.SaveChangesAsync();
        await _audit.LogAsync("suppression", "Anonymisation du dossier à la demande du patient", p.Reference);
        return NoContent();
    }

    /// <summary>
    /// Suppression définitive par un administrateur : le dossier et tout ce qui en dépend
    /// (passages, triages, séjours, rendez-vous, pièces jointes) disparaissent. Le compte
    /// utilisateur éventuellement rattaché est conservé mais détaché.
    /// </summary>
    [HttpDelete("{id:int}/definitif"), Authorize(Roles = "admin")]
    public async Task<IActionResult> SupprimerDefinitivement(int id, [FromServices] IWebHostEnvironment env)
    {
        var p = await _db.Patients.FindAsync(id);
        if (p is null) return NotFound(new { message = "Dossier introuvable." });

        var passages = await _db.Passages.Where(x => x.PatientId == id).ToListAsync();
        var idsPassages = passages.Select(x => x.Id).ToList();
        _db.Triages.RemoveRange(_db.Triages.Where(t => idsPassages.Contains(t.PassageId)));
        foreach (var pred in _db.Predictions.Where(x => x.PassageId != null && idsPassages.Contains(x.PassageId.Value)))
            pred.PassageId = null;
        _db.Passages.RemoveRange(passages);
        _db.Sejours.RemoveRange(_db.Sejours.Where(x => x.PatientId == id));
        _db.RendezVous.RemoveRange(_db.RendezVous.Where(x => x.PatientId == id));
        foreach (var d in _db.Demandes.Where(x => x.PatientId == id)) d.PatientId = null;
        foreach (var n in _db.Notifications.Where(x => x.PatientId == id)) n.PatientId = null;
        foreach (var u in _db.Utilisateurs.Where(x => x.PatientId == id)) u.PatientId = null;

        var pjs = await _db.PiecesJointes.Where(x => x.PatientId == id).ToListAsync();
        foreach (var pj in pjs)
        {
            var chemin = Path.Combine(env.ContentRootPath, "stockage", pj.CheminStockage);
            if (System.IO.File.Exists(chemin)) System.IO.File.Delete(chemin);
        }
        _db.PiecesJointes.RemoveRange(pjs);

        var reference = p.Reference;
        _db.Patients.Remove(p);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("suppression", "Suppression définitive du dossier patient", reference);
        return NoContent();
    }

    static void Appliquer(Patient p, PatientUpsertDto d)
    {
        p.Nom = d.Nom.Trim(); p.Prenom = d.Prenom.Trim(); p.Sexe = d.Sexe; p.Age = d.Age;
        p.Telephone = d.Telephone; p.Email = d.Email; p.Quartier = d.Quartier;
        p.Arrondissement = d.Arrondissement; p.Milieu = d.Milieu; p.ModePaiement = d.ModePaiement;
        p.ContactUrgence = d.ContactUrgence; p.Antecedents = d.Antecedents ?? new();
        p.Allergies = d.Allergies; p.Consentement = d.Consentement;
    }
}
