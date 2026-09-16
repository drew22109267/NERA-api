using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

/// <summary>
/// Pièces jointes au dossier : photo de plaie, résultat de laboratoire, imagerie.
/// Stockage sur disque local (dossier « stockage ») ; remplacer par un bucket S3
/// ou MinIO pour un déploiement multi-sites.
/// </summary>
[ApiController]
[Route("api/pieces-jointes")]
[Authorize]
public class PiecesJointesController : BaseController
{
    const long TailleMax = 12 * 1024 * 1024;
    static readonly string[] TypesAutorises = { "image/jpeg", "image/png", "image/webp", "application/pdf" };
    static readonly string[] Categories = { "Photo de plaie", "Résultat de laboratoire", "Imagerie", "Compte rendu", "Autre" };

    readonly AppDbContext _db;
    readonly AuditService _audit;
    readonly IWebHostEnvironment _env;
    public PiecesJointesController(AppDbContext db, AuditService audit, IWebHostEnvironment env)
    { _db = db; _audit = audit; _env = env; }

    string Dossier => Path.Combine(_env.ContentRootPath, "stockage");

    [HttpGet("patient/{patientId:int}")]
    public async Task<ActionResult<List<PieceJointeDto>>> Liste(int patientId)
    {
        if (UserRole == "patient" && UserPatientId != patientId) return Forbid();
        var list = await _db.PiecesJointes.AsNoTracking()
            .Where(p => p.PatientId == patientId).OrderByDescending(p => p.DeposeLe).ToListAsync();
        return Ok(list.Select(p => new PieceJointeDto(p.Id, p.PatientId, p.PassageId, p.NomFichier,
            p.TypeMime, p.Taille, p.Categorie, p.DeposeLe, p.DeposePar)).ToList());
    }

    [HttpPost, Authorize(Roles = "infirmier,medecin,accueil,admin")]
    [RequestSizeLimit(TailleMax)]
    public async Task<ActionResult<PieceJointeDto>> Deposer(
        [FromForm] IFormFile fichier, [FromForm] int patientId,
        [FromForm] string categorie = "Autre", [FromForm] int? passageId = null)
    {
        if (fichier is null || fichier.Length == 0) return BadRequest(new { message = "Aucun fichier reçu." });
        if (fichier.Length > TailleMax) return BadRequest(new { message = "Fichier trop volumineux (12 Mo maximum)." });
        if (!TypesAutorises.Contains(fichier.ContentType))
            return BadRequest(new { message = "Format non accepté : JPEG, PNG, WebP ou PDF uniquement." });
        if (!Categories.Contains(categorie)) categorie = "Autre";
        if (!await _db.Patients.AnyAsync(p => p.Id == patientId))
            return BadRequest(new { message = "Patient inconnu." });

        Directory.CreateDirectory(Dossier);
        var nom = $"{Guid.NewGuid():N}{Path.GetExtension(fichier.FileName)}";
        var chemin = Path.Combine(Dossier, nom);
        await using (var fs = System.IO.File.Create(chemin)) await fichier.CopyToAsync(fs);

        var pj = new PieceJointe
        {
            PatientId = patientId, PassageId = passageId, NomFichier = Path.GetFileName(fichier.FileName),
            TypeMime = fichier.ContentType, Taille = fichier.Length, Categorie = categorie,
            CheminStockage = nom, DeposePar = UserNom
        };
        _db.PiecesJointes.Add(pj);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Dépôt de pièce jointe", pj.NomFichier, categorie);

        return Ok(new PieceJointeDto(pj.Id, pj.PatientId, pj.PassageId, pj.NomFichier, pj.TypeMime,
            pj.Taille, pj.Categorie, pj.DeposeLe, pj.DeposePar));
    }

    [HttpGet("{id:int}/contenu")]
    public async Task<IActionResult> Contenu(int id)
    {
        var pj = await _db.PiecesJointes.FindAsync(id);
        if (pj is null) return NotFound();
        if (UserRole == "patient" && UserPatientId != pj.PatientId) return Forbid();
        var chemin = Path.Combine(Dossier, pj.CheminStockage);
        if (!System.IO.File.Exists(chemin)) return NotFound(new { message = "Fichier absent du stockage." });
        await _audit.LogAsync("consultation", "Consultation de pièce jointe", pj.NomFichier);
        return PhysicalFile(chemin, pj.TypeMime, pj.NomFichier);
    }

    [HttpDelete("{id:int}"), Authorize(Roles = "medecin,admin")]
    public async Task<IActionResult> Supprimer(int id)
    {
        var pj = await _db.PiecesJointes.FindAsync(id);
        if (pj is null) return NotFound();
        var chemin = Path.Combine(Dossier, pj.CheminStockage);
        if (System.IO.File.Exists(chemin)) System.IO.File.Delete(chemin);
        _db.PiecesJointes.Remove(pj);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("suppression", "Suppression de pièce jointe", pj.NomFichier);
        return NoContent();
    }
}
