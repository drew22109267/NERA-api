using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using HopitalApi.Services.Recherche;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

/// <summary>
/// Hôpitaux de l'étude. Chacun a ses services, ses registres et son rôle :
/// « Développement » (hôpital A, où le modèle est construit) ou
/// « Validation externe » (hôpital B, données jamais vues par le modèle).
/// </summary>
[ApiController]
[Route("api/etablissements")]
[Authorize]
public class EtablissementsController : BaseController
{
    readonly AppDbContext _db;
    readonly AuditService _audit;
    public EtablissementsController(AppDbContext db, AuditService audit) { _db = db; _audit = audit; }

    [HttpGet]
    public async Task<ActionResult<List<EtablissementListeDto>>> Liste() =>
        Ok(await _db.Etablissements.AsNoTracking().OrderBy(e => e.Id)
            .Select(e => new EtablissementListeDto(e.Id, e.Code, e.Nom, e.Categorie, e.Ville, e.Region, e.Actif,
                e.RoleRecherche, e.Services.Count(s => s.Actif)))
            .ToListAsync());

    [HttpPost, Authorize(Roles = "admin")]
    public async Task<IActionResult> Creer(EtablissementDto dto)
    {
        var code = dto.Code.Trim().ToUpperInvariant();
        if (code.Length > 0 && await _db.Etablissements.AnyAsync(e => e.Code == code))
            return Conflict(new { message = $"Le code « {code} » est déjà utilisé par un autre hôpital." });
        var e = new Etablissement
        {
            Nom = dto.Nom.Trim(), Code = code, Categorie = dto.Categorie.Trim(),
            Ville = dto.Ville.Trim(), Region = dto.Region.Trim()
        };
        _db.Etablissements.Add(e);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Création d'hôpital", e.Nom);
        return Ok(new { e.Id });
    }

    [HttpPut("{id:int}"), Authorize(Roles = "admin")]
    public async Task<IActionResult> Modifier(int id, EtablissementDto dto)
    {
        var e = await _db.Etablissements.FindAsync(id);
        if (e is null) return NotFound(new { message = "Hôpital introuvable." });
        var code = dto.Code.Trim().ToUpperInvariant();
        if (code.Length > 0 && await _db.Etablissements.AnyAsync(x => x.Id != id && x.Code == code))
            return Conflict(new { message = $"Le code « {code} » est déjà utilisé par un autre hôpital." });
        e.Nom = dto.Nom.Trim(); e.Code = code; e.Categorie = dto.Categorie.Trim();
        e.Ville = dto.Ville.Trim(); e.Region = dto.Region.Trim();
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Modification d'hôpital", e.Nom);
        return NoContent();
    }

    /// <summary>Rôle dans l'étude. Un seul hôpital de développement à la fois.</summary>
    [HttpPut("{id:int}/role"), Authorize(Roles = "admin,data")]
    public async Task<IActionResult> Role(int id, RoleRechercheDto dto)
    {
        var e = await _db.Etablissements.FindAsync(id);
        if (e is null) return NotFound(new { message = "Hôpital introuvable." });
        var role = dto.Role?.Trim() ?? "";
        if (role.Length > 0 && !Dictionnaire.Roles.Contains(role))
            return BadRequest(new { message = $"Rôle inconnu. Valeurs : {string.Join(", ", Dictionnaire.Roles)}." });
        if (role == "Développement")
        {
            var autre = await _db.Etablissements.FirstOrDefaultAsync(x => x.Id != id && x.RoleRecherche == "Développement");
            if (autre is not null)
                return Conflict(new { message = $"« {autre.Nom} » est déjà l'hôpital de développement. Changez d'abord son rôle." });
        }
        e.RoleRecherche = role;
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Rôle de l'hôpital dans l'étude", e.Nom, role.Length > 0 ? role : "aucun");
        return NoContent();
    }

    /// <summary>Suppression d'un hôpital sans service ni donnée ; sinon il est désactivé.</summary>
    [HttpDelete("{id:int}"), Authorize(Roles = "admin")]
    public async Task<IActionResult> Supprimer(int id)
    {
        var e = await _db.Etablissements.FindAsync(id);
        if (e is null) return NotFound(new { message = "Hôpital introuvable." });
        if (await _db.Etablissements.CountAsync() == 1)
            return BadRequest(new { message = "L'application a besoin d'au moins un hôpital." });
        var utilise = await _db.Services.AnyAsync(s => s.EtablissementId == id)
            || await _db.LotsImport.AnyAsync(l => l.EtablissementId == id);
        if (utilise)
        {
            e.Actif = false;
            await _db.SaveChangesAsync();
            await _audit.LogAsync("modification", "Désactivation d'hôpital (historique conservé)", e.Nom);
            return Ok(new { message = "Cet hôpital a des services ou des données : il a été désactivé plutôt que supprimé.", desactive = true });
        }
        _db.ColonnesSource.RemoveRange(_db.ColonnesSource.Where(c => c.EtablissementId == id));
        _db.Correspondances.RemoveRange(_db.Correspondances.Where(c => c.EtablissementId == id));
        _db.Etablissements.Remove(e);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("suppression", "Suppression d'hôpital", e.Nom);
        return NoContent();
    }
}
