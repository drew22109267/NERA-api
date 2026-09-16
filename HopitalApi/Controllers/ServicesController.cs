using HopitalApi.Data;
using HopitalApi.Dtos;
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
        return new ServiceDto(s.Id, s.Code, s.Nom, s.Pole, s.Hospitalisation, s.UrgencesCompatible,
            s.AgeMin, s.AgeMax, s.LitsInstalles, s.LitsArmes, s.Occupes, s.Bloques, s.Programmes,
            libres, Math.Round(taux, 3), PrevisionCapaciteService.Niveau(taux));
    }

    [HttpGet]
    public async Task<ActionResult<List<ServiceDto>>> Liste([FromQuery] bool hospitalisationSeule = false)
    {
        var q = _db.Services.AsNoTracking().Where(s => s.Actif);
        if (hospitalisationSeule) q = q.Where(s => s.Hospitalisation);
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

    [HttpGet("{id:int}/prevision")]
    public async Task<ActionResult<PrevisionDto>> Prevision(int id, [FromQuery] int horizon = 30,
        [FromQuery] double hausseAdmissions = 0, [FromQuery] double reductionBlocage = 0, [FromQuery] int litsSupp = 0)
    {
        var s = await _db.Services.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id);
        if (s is null) return NotFound();
        horizon = Math.Clamp(horizon, 1, 90);
        var p = _prev.Prevoir(s, horizon, hausseAdmissions, reductionBlocage, litsSupp);
        return Ok(new PrevisionDto(p.ServiceId, p.Nom, p.Capacite,
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
    public OrientationController(OrientationService svc) => _svc = svc;

    [HttpGet("motifs")]
    public async Task<ActionResult<List<string>>> Motifs() => Ok(await _svc.MotifsAsync());

    /// <summary>Redistribution : propose les services d'accueil compatibles, classés.</summary>
    [HttpGet]
    public async Task<ActionResult<ResultatOrientation>> Orienter(
        [FromQuery] string motif, [FromQuery] int age, [FromQuery] string sexe = "F",
        [FromQuery] int? categorie = null, [FromQuery] string? antecedents = null)
    {
        if (string.IsNullOrWhiteSpace(motif)) return BadRequest(new { message = "Motif requis." });
        var ant = string.IsNullOrWhiteSpace(antecedents)
            ? new List<string>()
            : antecedents.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(x => x.Trim()).ToList();
        return Ok(await _svc.OrienterAsync(motif, age, sexe, categorie, ant));
    }
}
