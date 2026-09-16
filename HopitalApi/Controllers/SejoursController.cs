using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

[ApiController]
[Route("api/sejours")]
[Authorize(Roles = "gestionnaire,medecin,admin,infirmier,direction")]
public class SejoursController : BaseController
{
    readonly AppDbContext _db;
    readonly AuditService _audit;
    public SejoursController(AppDbContext db, AuditService audit) { _db = db; _audit = audit; }

    [HttpGet]
    public async Task<ActionResult<List<SejourDto>>> Liste([FromQuery] int? serviceId)
    {
        var q = _db.Sejours.AsNoTracking().Include(s => s.Patient).Include(s => s.Service).Include(s => s.Lit)
            .Where(s => s.Statut == "En cours");
        if (serviceId is int sid) q = q.Where(s => s.ServiceId == sid);

        var list = await q.OrderBy(s => s.Entree).ToListAsync();
        return Ok(list.Select(s =>
        {
            var jours = Math.Max(0, (int)(DateTime.UtcNow - s.Entree).TotalDays);
            var (j0, j1, j2) = PrevisionCapaciteService.ProbaSortie(s.Id, jours);
            return new SejourDto(s.Id, s.Reference, s.PatientId,
                s.Patient is null ? "" : $"{s.Patient.Nom} {s.Patient.Prenom}",
                s.ServiceId, s.Service?.Nom ?? "", s.Lit?.Code, s.Entree, jours, s.MotifBlocage, j0, j1, j2);
        }).ToList());
    }

    [HttpPost]
    public async Task<ActionResult<SejourDto>> Creer(SejourCreateDto dto)
    {
        var svc = await _db.Services.FindAsync(dto.ServiceId);
        if (svc is null) return BadRequest(new { message = "Service inconnu." });
        if (svc.Occupes + svc.Bloques >= svc.LitsArmes)
            return BadRequest(new { message = "Aucun lit armé disponible dans ce service." });

        var n = await _db.Sejours.CountAsync();
        var s = new Sejour
        {
            Reference = $"S-{800 + n + 1}", PatientId = dto.PatientId, ServiceId = dto.ServiceId,
            LitId = dto.LitId, MotifBlocage = dto.MotifBlocage, Entree = DateTime.UtcNow
        };
        svc.Occupes++;
        if (dto.LitId is int lid)
        {
            var lit = await _db.Lits.FindAsync(lid);
            if (lit is not null) lit.Statut = "Occupé";
        }
        _db.Sejours.Add(s);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Admission en hospitalisation", s.Reference);
        return Ok(new SejourDto(s.Id, s.Reference, s.PatientId, "", s.ServiceId, svc.Nom, null, s.Entree, 0, s.MotifBlocage, 0, 0, 0));
    }

    [HttpPost("{id:int}/sortie")]
    public async Task<IActionResult> Sortie(int id)
    {
        var s = await _db.Sejours.Include(x => x.Service).Include(x => x.Lit).FirstOrDefaultAsync(x => x.Id == id);
        if (s is null) return NotFound();
        s.Statut = "Terminé"; s.Sortie = DateTime.UtcNow;
        if (s.Service is not null && s.Service.Occupes > 0) s.Service.Occupes--;
        if (s.Lit is not null) s.Lit.Statut = "Libre";
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Sortie d'hospitalisation", s.Reference);
        return NoContent();
    }

    [HttpPost("{id:int}/blocage")]
    public async Task<IActionResult> Blocage(int id, [FromBody] Dictionary<string, string?> body)
    {
        var s = await _db.Sejours.Include(x => x.Service).FirstOrDefaultAsync(x => x.Id == id);
        if (s is null) return NotFound();
        var motif = body.GetValueOrDefault("motif");
        var avant = s.MotifBlocage;
        s.MotifBlocage = string.IsNullOrWhiteSpace(motif) ? null : motif;
        if (s.Service is not null)
        {
            if (avant is null && s.MotifBlocage is not null) s.Service.Bloques++;
            if (avant is not null && s.MotifBlocage is null && s.Service.Bloques > 0) s.Service.Bloques--;
        }
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Blocage de lit", s.Reference, s.MotifBlocage ?? "levé");
        return NoContent();
    }
}

[ApiController]
[Route("api/demandes")]
[Authorize]
public class DemandesController : BaseController
{
    readonly AppDbContext _db;
    readonly AuditService _audit;
    public DemandesController(AppDbContext db, AuditService audit) { _db = db; _audit = audit; }

    [HttpGet]
    public async Task<ActionResult<PageResult<DemandeDto>>> Liste(
        [FromQuery] string? recherche, [FromQuery] int page = 1, [FromQuery] int pageSize = 25)
    {
        page = Math.Max(1, page); pageSize = Math.Clamp(pageSize, 5, 100);
        var b = _db.Demandes.AsNoTracking().Include(d => d.Service).AsQueryable();
        if (!string.IsNullOrWhiteSpace(recherche))
        {
            var t = recherche.Trim().ToLower();
            b = b.Where(d => d.Reference.ToLower().Contains(t) || d.Motif.ToLower().Contains(t)
                || (d.Devenir != null && d.Devenir.ToLower().Contains(t))
                || (d.Service != null && d.Service.Nom.ToLower().Contains(t)));
        }
        var q = b.OrderByDescending(d => d.Date);
        var total = await q.CountAsync();
        var items = await q.Skip((page - 1) * pageSize).Take(pageSize).ToListAsync();
        return Ok(new PageResult<DemandeDto>(items.Select(d =>
            new DemandeDto(d.Id, d.Reference, d.Date, d.ServiceId, d.Service?.Nom ?? "", d.PatientId,
                d.Motif, d.Gravite, d.Devenir)).ToList(), total, page, pageSize));
    }

    [HttpPost, Authorize(Roles = "gestionnaire,medecin,admin,infirmier")]
    public async Task<ActionResult<DemandeDto>> Creer(DemandeCreateDto dto)
    {
        var n = await _db.Demandes.CountAsync();
        var d = new DemandeNonSatisfaite
        {
            Reference = $"D-{100 + n + 1}", ServiceId = dto.ServiceId, PatientId = dto.PatientId,
            Motif = dto.Motif, Gravite = dto.Gravite, Devenir = dto.Devenir
        };
        _db.Demandes.Add(d);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Demande non satisfaite", d.Reference, dto.Motif);
        var svc = await _db.Services.FindAsync(dto.ServiceId);
        return Ok(new DemandeDto(d.Id, d.Reference, d.Date, d.ServiceId, svc?.Nom ?? "", d.PatientId, d.Motif, d.Gravite, d.Devenir));
    }
}
