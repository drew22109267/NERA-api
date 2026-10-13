using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

[ApiController]
[Route("api/services")]
public class ServicesController : BaseController
{
    readonly AppDbContext _db;
    readonly PrevisionCapaciteService _prev;
    readonly AuditService _audit;
    public ServicesController(AppDbContext db, PrevisionCapaciteService prev, AuditService audit)
    { _db = db; _prev = prev; _audit = audit; }

    internal static ServiceDto Map(Models.Service s)
    {
        var libres = Math.Max(0, s.LitsArmes - s.Occupes - s.Bloques);
        var taux = s.LitsArmes > 0 ? (double)s.Occupes / s.LitsArmes : 0;
        return new ServiceDto(s.Id, s.EtablissementId, s.Code, s.Nom, s.Pole, s.Hospitalisation, s.UrgencesCompatible,
            s.AgeMin, s.AgeMax, s.LitsInstalles, s.LitsArmes, s.Occupes, s.Bloques, s.Programmes,
            libres, Math.Round(taux, 3), PrevisionCapaciteService.Niveau(taux));
    }

    [HttpGet]
    public async Task<ActionResult<List<ServiceDto>>> Liste([FromQuery] bool hospitalisationSeule = false,
        [FromQuery] int? etablissementId = null)
    {
        var q = _db.Services.AsNoTracking().Where(s => s.Actif);
        if (hospitalisationSeule) q = q.Where(s => s.Hospitalisation);
        if (etablissementId is int eid) q = q.Where(s => s.EtablissementId == eid);
        var list = await q.OrderBy(s => s.Ordre).ToListAsync();
        return Ok(list.Select(Map).ToList());
    }

    [HttpGet("poles")]
    public async Task<ActionResult<List<string>>> Poles() =>
        Ok(await _db.Services.Where(s => s.Actif).Select(s => s.Pole).Distinct().OrderBy(p => p).ToListAsync());

    [HttpGet("{id:int}/lits"), Authorize(Roles = "gestionnaire,medecin,admin,direction")]
    public async Task<IActionResult> Lits(int id)
    {
        var lits = await _db.Lits.AsNoTracking().Where(l => l.ServiceId == id)
            .OrderBy(l => l.Code)
            .Select(l => new { l.Id, l.Code, l.Statut, l.MotifBlocage }).ToListAsync();
        return Ok(lits);
    }

    [HttpPut("{id:int}"), Authorize(Roles = "admin,gestionnaire")]
    public async Task<ActionResult<ServiceDto>> Modifier(int id, ServiceUpdateDto dto)
    {
        var s = await _db.Services.FindAsync(id);
        if (s is null) return NotFound();
        if (dto.LitsArmes > dto.LitsInstalles)
            return BadRequest(new { message = "Le nombre de lits armés ne peut pas dépasser les lits installés." });
        if (dto.Occupes + dto.Bloques > dto.LitsArmes)
            return BadRequest(new { message = "Occupés + bloqués ne peut pas dépasser les lits armés." });

        s.LitsInstalles = dto.LitsInstalles; s.LitsArmes = dto.LitsArmes; s.Occupes = dto.Occupes;
        s.Bloques = dto.Bloques; s.Programmes = dto.Programmes; s.Tendance = dto.Tendance; s.Actif = dto.Actif;
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Modification de capacité", s.Code);
        return Ok(Map(s));
    }

    /// <summary>Aligne les lits individuels sur le nombre de lits armés (ajout ou retrait de lits libres).</summary>
    async Task SynchroniserLitsAsync(Models.Service s)
    {
        var lits = await _db.Lits.Where(l => l.ServiceId == s.Id).OrderBy(l => l.Code).ToListAsync();
        for (var i = lits.Count + 1; i <= s.LitsArmes; i++)
            _db.Lits.Add(new Lit { ServiceId = s.Id, Code = $"{s.Code}-{i:D2}", Statut = "Libre" });
        if (lits.Count > s.LitsArmes)
        {
            var retirables = lits.Where(l => l.Statut == "Libre").Reverse().Take(lits.Count - s.LitsArmes).ToList();
            _db.Lits.RemoveRange(retirables);
        }
    }

    /// <summary>Création d'un service par l'administration ; ses lits sont créés dans la foulée.</summary>
    [HttpPost, Authorize(Roles = "admin")]
    public async Task<ActionResult<ServiceDto>> Creer(ServiceUpsertDto dto)
    {
        if (dto.LitsArmes > dto.LitsInstalles)
            return BadRequest(new { message = "Le nombre de lits armés ne peut pas dépasser les lits installés." });
        var code = dto.Code.Trim().ToUpperInvariant();
        // Avec plusieurs hôpitaux, le service doit dire auquel il appartient.
        var actifs = await _db.Etablissements.Where(e => e.Actif).ToListAsync();
        var etab = dto.EtablissementId is int eid ? actifs.FirstOrDefault(e => e.Id == eid)
            : actifs.Count == 1 ? actifs[0] : null;
        if (etab is null)
            return BadRequest(new { message = actifs.Count > 1 ? "Choisissez l'hôpital du service." : "Hôpital introuvable." });
        if (await _db.Services.AnyAsync(x => x.EtablissementId == etab.Id && x.Code == code))
            return Conflict(new { message = $"Le code « {code} » est déjà utilisé dans cet hôpital." });
        var s = new Models.Service
        {
            EtablissementId = etab.Id, Code = code, Nom = dto.Nom.Trim(), Pole = dto.Pole.Trim(),
            Hospitalisation = dto.Hospitalisation, UrgencesCompatible = dto.UrgencesCompatible,
            AgeMin = dto.AgeMin, AgeMax = dto.AgeMax, LitsInstalles = dto.LitsInstalles, LitsArmes = dto.LitsArmes,
            Ordre = dto.Ordre ?? (await _db.Services.MaxAsync(x => (int?)x.Ordre) ?? 0) + 1
        };
        _db.Services.Add(s);
        await _db.SaveChangesAsync();
        await SynchroniserLitsAsync(s);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Création de service", s.Code, s.Nom);
        return Ok(Map(s));
    }

    /// <summary>Modification de l'identité et de la capacité d'un service.</summary>
    [HttpPut("{id:int}/fiche"), Authorize(Roles = "admin")]
    public async Task<ActionResult<ServiceDto>> ModifierFiche(int id, ServiceUpsertDto dto)
    {
        var s = await _db.Services.FindAsync(id);
        if (s is null) return NotFound(new { message = "Service introuvable." });
        if (dto.LitsArmes > dto.LitsInstalles)
            return BadRequest(new { message = "Le nombre de lits armés ne peut pas dépasser les lits installés." });
        if (s.Occupes + s.Bloques > dto.LitsArmes)
            return BadRequest(new { message = $"{s.Occupes + s.Bloques} lits sont occupés ou bloqués : impossible de descendre en dessous." });
        var code = dto.Code.Trim().ToUpperInvariant();
        if (await _db.Services.AnyAsync(x => x.Id != id && x.EtablissementId == s.EtablissementId && x.Code == code))
            return Conflict(new { message = $"Le code « {code} » est déjà utilisé dans cet hôpital." });

        s.Code = code; s.Nom = dto.Nom.Trim(); s.Pole = dto.Pole.Trim();
        s.Hospitalisation = dto.Hospitalisation; s.UrgencesCompatible = dto.UrgencesCompatible;
        s.AgeMin = dto.AgeMin; s.AgeMax = dto.AgeMax;
        s.LitsInstalles = dto.LitsInstalles; s.LitsArmes = dto.LitsArmes;
        if (dto.Ordre is { } o) s.Ordre = o;
        await SynchroniserLitsAsync(s);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Modification de service", s.Code, s.Nom);
        return Ok(Map(s));
    }

    /// <summary>Suppression d'un service sans historique ; sinon il est désactivé.</summary>
    [HttpDelete("{id:int}"), Authorize(Roles = "admin")]
    public async Task<IActionResult> Supprimer(int id)
    {
        var s = await _db.Services.FindAsync(id);
        if (s is null) return NotFound(new { message = "Service introuvable." });
        var utilise = await _db.Passages.AnyAsync(p => p.ServiceViseId == id || p.DecisionServiceId == id)
            || await _db.Sejours.AnyAsync(x => x.ServiceId == id)
            || await _db.RendezVous.AnyAsync(x => x.ServiceId == id)
            || await _db.Demandes.AnyAsync(x => x.ServiceId == id)
            || await _db.Hospitalisations.AnyAsync(x => x.ServiceId == id)
            || await _db.Consultations.AnyAsync(x => x.ServiceId == id);
        if (utilise)
        {
            s.Actif = false;
            await _db.SaveChangesAsync();
            await _audit.LogAsync("modification", "Désactivation de service (historique conservé)", s.Code);
            return Ok(new { message = "Ce service a un historique : il a été désactivé plutôt que supprimé.", desactive = true });
        }
        _db.Lits.RemoveRange(_db.Lits.Where(l => l.ServiceId == id));
        _db.ReglesOrientation.RemoveRange(_db.ReglesOrientation.Where(r => r.ServiceCode == s.Code || r.ServiceAlternatifCode == s.Code));
        _db.Services.Remove(s);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("suppression", "Suppression de service", s.Code, s.Nom);
        return NoContent();
    }

    [HttpGet("{id:int}/prevision")]
    public async Task<ActionResult<PrevisionDto>> Prevision(int id, [FromQuery] int horizon = 30,
        [FromQuery] double hausseAdmissions = 0, [FromQuery] double reductionBlocage = 0, [FromQuery] int litsSupp = 0)
    {
        var s = await _db.Services.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id);
        if (s is null) return NotFound();
        horizon = Math.Clamp(horizon, 1, 90);
        var p = _prev.Prevoir(s, horizon, hausseAdmissions, reductionBlocage, litsSupp);
        return Ok(new PrevisionDto(p.ServiceId, p.Nom, p.Capacite, p.Disponible, p.Raison,
            p.Points.Select(x => new PrevisionPointDto(x.Jour, x.Bas, x.Median, x.Haut, x.Capacite)).ToList(),
            p.RisqueSaturation,
            p.Decomposition.Select(d => new DecompositionDto(d.Label, d.Valeur)).ToList(),
            PrevisionCapaciteService.Version));
    }
}

[ApiController]
[Route("api/orientation")]
public class OrientationController : BaseController
{
    readonly OrientationService _svc;
    readonly AppDbContext _db;
    readonly AuditService _audit;
    public OrientationController(OrientationService svc, AppDbContext db, AuditService audit)
    { _svc = svc; _db = db; _audit = audit; }

    static RegleOrientationDto MapRegle(RegleOrientation r) => new(r.Id, r.Motif, r.ServiceCode,
        r.ServiceAlternatifCode, r.AgeMin, r.AgeMax, r.SexeRequis, r.CategorieMax, r.Commentaire, r.Priorite);

    async Task<string?> VerifierCodesAsync(RegleOrientationUpsertDto dto)
    {
        var codes = await _db.Services.Select(x => x.Code).ToListAsync();
        if (!codes.Contains(dto.ServiceCode)) return $"Service « {dto.ServiceCode} » inconnu.";
        if (!string.IsNullOrWhiteSpace(dto.ServiceAlternatifCode) && !codes.Contains(dto.ServiceAlternatifCode))
            return $"Service de repli « {dto.ServiceAlternatifCode} » inconnu.";
        return null;
    }

    /// <summary>Règles motif → service, saisies par l'administration.</summary>
    [HttpGet("regles"), Authorize(Roles = "admin,direction,gestionnaire,medecin")]
    public async Task<ActionResult<List<RegleOrientationDto>>> Regles() =>
        Ok((await _db.ReglesOrientation.AsNoTracking().OrderBy(r => r.Priorite).ThenBy(r => r.Motif).ToListAsync())
            .Select(MapRegle).ToList());

    [HttpPost("regles"), Authorize(Roles = "admin")]
    public async Task<ActionResult<RegleOrientationDto>> CreerRegle(RegleOrientationUpsertDto dto)
    {
        if (await VerifierCodesAsync(dto) is { } err) return BadRequest(new { message = err });
        var r = new RegleOrientation();
        Appliquer(r, dto);
        _db.ReglesOrientation.Add(r);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Création de règle d'orientation", r.Motif, r.ServiceCode);
        return Ok(MapRegle(r));
    }

    [HttpPut("regles/{id:int}"), Authorize(Roles = "admin")]
    public async Task<ActionResult<RegleOrientationDto>> ModifierRegle(int id, RegleOrientationUpsertDto dto)
    {
        var r = await _db.ReglesOrientation.FindAsync(id);
        if (r is null) return NotFound(new { message = "Règle introuvable." });
        if (await VerifierCodesAsync(dto) is { } err) return BadRequest(new { message = err });
        Appliquer(r, dto);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Modification de règle d'orientation", r.Motif, r.ServiceCode);
        return Ok(MapRegle(r));
    }

    [HttpDelete("regles/{id:int}"), Authorize(Roles = "admin")]
    public async Task<IActionResult> SupprimerRegle(int id)
    {
        var r = await _db.ReglesOrientation.FindAsync(id);
        if (r is null) return NotFound(new { message = "Règle introuvable." });
        _db.ReglesOrientation.Remove(r);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("suppression", "Suppression de règle d'orientation", r.Motif);
        return NoContent();
    }

    static void Appliquer(RegleOrientation r, RegleOrientationUpsertDto d)
    {
        r.Motif = d.Motif.Trim(); r.ServiceCode = d.ServiceCode.Trim().ToUpperInvariant();
        r.ServiceAlternatifCode = string.IsNullOrWhiteSpace(d.ServiceAlternatifCode) ? null : d.ServiceAlternatifCode.Trim().ToUpperInvariant();
        r.AgeMin = d.AgeMin; r.AgeMax = d.AgeMax;
        r.SexeRequis = string.IsNullOrWhiteSpace(d.SexeRequis) ? null : d.SexeRequis;
        r.CategorieMax = d.CategorieMax; r.Commentaire = d.Commentaire; r.Priorite = d.Priorite;
    }

    [HttpGet("motifs")]
    public async Task<ActionResult<List<string>>> Motifs() => Ok(await _svc.MotifsAsync());

    /// <summary>Redistribution : propose les services d'accueil compatibles, classés.</summary>
    [HttpGet]
    public async Task<ActionResult<ResultatOrientation>> Orienter(
        [FromQuery] string motif, [FromQuery] int age, [FromQuery] string sexe = "F",
        [FromQuery] int? categorie = null, [FromQuery] string? antecedents = null, [FromQuery] int? etablissementId = null)
    {
        if (string.IsNullOrWhiteSpace(motif)) return BadRequest(new { message = "Motif requis." });
        var ant = string.IsNullOrWhiteSpace(antecedents)
            ? new List<string>()
            : antecedents.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(x => x.Trim()).ToList();
        return Ok(await _svc.OrienterAsync(motif, age, sexe, categorie, ant, etablissementId));
    }
}
