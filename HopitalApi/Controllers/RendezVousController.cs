using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

[ApiController]
[Route("api/rendezvous")]
[Authorize]
public class RendezVousController : BaseController
{
    readonly AppDbContext _db;
    readonly AuditService _audit;
    readonly PrevisionCapaciteService _prev;
    public RendezVousController(AppDbContext db, AuditService audit, PrevisionCapaciteService prev)
    { _db = db; _audit = audit; _prev = prev; }

    static RendezVousDto Map(RendezVous r) => new(r.Id, r.Reference, r.PatientId,
        r.Patient is null ? "" : $"{r.Patient.Nom} {r.Patient.Prenom}", r.Patient?.Telephone,
        r.ServiceId, r.Service?.Nom ?? "", r.Date, r.Heure, r.Motif, r.Statut, r.Rappel,
        r.DemandeParPatient, r.EstChirurgie, r.DureeMinutes, r.LitAvalServiceId,
        r.DureeSejourJours, r.PerteDeChance, r.SalleBloc);

    [HttpGet]
    public async Task<ActionResult<List<RendezVousDto>>> Liste([FromQuery] string? statut, [FromQuery] bool blocSeul = false)
    {
        var q = _db.RendezVous.AsNoTracking().Include(r => r.Patient).Include(r => r.Service).AsQueryable();
        if (UserRole == "patient")
        {
            if (UserPatientId is null) return Ok(new List<RendezVousDto>());
            q = q.Where(r => r.PatientId == UserPatientId);
        }
        if (!string.IsNullOrWhiteSpace(statut) && statut != "Tous") q = q.Where(r => r.Statut == statut);
        if (blocSeul) q = q.Where(r => r.EstChirurgie);
        var list = await q.OrderBy(r => r.Date).ThenBy(r => r.Heure).ToListAsync();
        return Ok(list.Select(Map).ToList());
    }

    /// <summary>Créneaux disponibles avec le risque de saturation du service d'aval ce jour-là.</summary>
    [HttpGet("creneaux")]
    public async Task<IActionResult> Creneaux([FromQuery] int serviceId, [FromQuery] DateOnly date)
    {
        var svc = await _db.Services.AsNoTracking().FirstOrDefaultAsync(s => s.Id == serviceId);
        if (svc is null) return NotFound(new { message = "Service inconnu." });

        var heures = new[] { "08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "14:00", "14:30", "15:00", "15:30" };
        var pris = await _db.RendezVous.Where(r => r.ServiceId == serviceId && r.Date == date
            && r.Statut != "Annulé").Select(r => r.Heure).ToListAsync();

        var jours = Math.Max(1, date.DayNumber - DateOnly.FromDateTime(DateTime.UtcNow).DayNumber);
        var prevision = _prev.Prevoir(svc, Math.Max(jours, 7));
        var risque = PrevisionCapaciteService.RisqueSaturation(prevision.Points, jours);

        return Ok(new
        {
            serviceId, service = svc.Nom, date,
            risqueSaturation = risque,
            niveau = risque is null ? null : risque > 0.7 ? "crit" : risque > 0.4 ? "warn" : "ok",
            creneaux = heures.Select(h => new { heure = h, libre = !pris.Contains(h) })
        });
    }

    [HttpPost]
    public async Task<ActionResult<RendezVousDto>> Creer(RendezVousCreateDto dto)
    {
        if (UserRole == "patient")
        {
            if (UserPatientId is null) return Forbid();
            dto.PatientId = UserPatientId.Value;
            if (dto.EstChirurgie) return BadRequest(new { message = "Une intervention ne peut être programmée que par un médecin." });
        }
        if (!await _db.Patients.AnyAsync(p => p.Id == dto.PatientId)) return BadRequest(new { message = "Patient inconnu." });
        if (!await _db.Services.AnyAsync(s => s.Id == dto.ServiceId)) return BadRequest(new { message = "Service inconnu." });
        if (dto.Date < DateOnly.FromDateTime(DateTime.UtcNow.AddDays(-1)))
            return BadRequest(new { message = "La date doit être aujourd'hui ou plus tard." });
        if (await _db.RendezVous.AnyAsync(r => r.ServiceId == dto.ServiceId && r.Date == dto.Date
                && r.Heure == dto.Heure && r.Statut != "Annulé"))
            return Conflict(new { message = "Ce créneau vient d'être pris. Choisissez-en un autre." });

        var n = await _db.RendezVous.CountAsync();
        var r = new RendezVous
        {
            Reference = $"R-{3300 + n + 1}", PatientId = dto.PatientId, ServiceId = dto.ServiceId,
            Date = dto.Date, Heure = dto.Heure, Motif = dto.Motif,
            Statut = UserRole == "patient" ? "Demandé" : "Confirmé",
            Rappel = "SMS J-2 programmé", DemandeParPatient = UserRole == "patient",
            EstChirurgie = dto.EstChirurgie, DureeMinutes = dto.DureeMinutes,
            LitAvalServiceId = dto.LitAvalServiceId, DureeSejourJours = dto.DureeSejourJours,
            PerteDeChance = dto.PerteDeChance, SalleBloc = dto.SalleBloc
        };
        _db.RendezVous.Add(r);
        _db.Notifications.Add(new Notification
        {
            Destinataire = "Patient", PatientId = dto.PatientId, Canal = "SMS", Type = "Rappel RDV",
            Texte = $"Rendez-vous {r.Reference} le {dto.Date:dd/MM/yyyy} à {dto.Heure}. Répondez ANNULER ou REPORTER si besoin."
        });
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Création de rendez-vous", r.Reference);

        return Ok(Map(await _db.RendezVous.Include(x => x.Patient).Include(x => x.Service).FirstAsync(x => x.Id == r.Id)));
    }

    [HttpPost("{id:int}/statut")]
    public async Task<ActionResult<RendezVousDto>> Statut(int id, [FromBody] Dictionary<string, string> body)
    {
        var r = await _db.RendezVous.Include(x => x.Patient).Include(x => x.Service).FirstOrDefaultAsync(x => x.Id == id);
        if (r is null) return NotFound();
        if (UserRole == "patient" && r.PatientId != UserPatientId) return Forbid();
        if (!body.TryGetValue("statut", out var s)) return BadRequest(new { message = "Statut manquant." });
        if (UserRole == "patient" && s != "Annulé") return Forbid();
        r.Statut = s;
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Rendez-vous", r.Reference, s);
        return Ok(Map(r));
    }
}

[ApiController]
[Route("api/notifications")]
[Authorize]
public class NotificationsController : BaseController
{
    readonly AppDbContext _db;
    public NotificationsController(AppDbContext db) => _db = db;

    [HttpGet]
    public async Task<ActionResult<PageResult<NotificationDto>>> Liste(
        [FromQuery] string? destinataire, [FromQuery] string? recherche,
        [FromQuery] int page = 1, [FromQuery] int pageSize = 25)
    {
        page = Math.Max(1, page); pageSize = Math.Clamp(pageSize, 5, 100);
        var q = _db.Notifications.AsNoTracking().AsQueryable();
        if (!string.IsNullOrWhiteSpace(recherche))
        {
            var t = recherche.Trim().ToLower();
            q = q.Where(n => n.Texte.ToLower().Contains(t) || n.Type.ToLower().Contains(t)
                || n.Destinataire.ToLower().Contains(t));
        }
        if (UserRole == "patient")
            q = q.Where(n => n.PatientId == UserPatientId || n.Destinataire == "Patient");
        else if (!string.IsNullOrWhiteSpace(destinataire) && destinataire != "Tous")
            q = q.Where(n => n.Destinataire == destinataire);

        q = q.OrderByDescending(n => n.Date);
        var total = await q.CountAsync();
        var items = await q.Skip((page - 1) * pageSize).Take(pageSize).ToListAsync();
        return Ok(new PageResult<NotificationDto>(items.Select(n =>
            new NotificationDto(n.Id, n.Date, n.Destinataire, n.Type, n.Texte, n.Niveau, n.Canal, n.Lue)).ToList(),
            total, page, pageSize));
    }

    [HttpGet("destinataires")]
    public async Task<ActionResult<List<string>>> Destinataires() =>
        Ok(await _db.Notifications.Select(n => n.Destinataire).Distinct().OrderBy(d => d).ToListAsync());

    [HttpPost, Authorize(Roles = "infirmier,medecin,gestionnaire,direction,admin,accueil")]
    public async Task<ActionResult<NotificationDto>> Creer(NotificationCreateDto dto)
    {
        var n = new Notification
        {
            Destinataire = dto.Destinataire, Type = dto.Type, Texte = dto.Texte,
            Niveau = dto.Niveau, Canal = dto.Canal, PatientId = dto.PatientId
        };
        _db.Notifications.Add(n);
        await _db.SaveChangesAsync();
        return Ok(new NotificationDto(n.Id, n.Date, n.Destinataire, n.Type, n.Texte, n.Niveau, n.Canal, n.Lue));
    }

    [HttpPost("{id:int}/lue")]
    public async Task<IActionResult> Lue(int id)
    {
        var n = await _db.Notifications.FindAsync(id);
        if (n is null) return NotFound();
        n.Lue = true;
        await _db.SaveChangesAsync();
        return NoContent();
    }
}
