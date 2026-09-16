using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

[ApiController]
[Route("api/tableau-bord")]
[Authorize]
public class TableauBordController : BaseController
{
    readonly AppDbContext _db;
    readonly PrevisionCapaciteService _prev;
    public TableauBordController(AppDbContext db, PrevisionCapaciteService prev) { _db = db; _prev = prev; }

    [HttpGet]
    public async Task<ActionResult<TableauBordDto>> Get()
    {
        var services = await _db.Services.AsNoTracking().Where(s => s.Actif && s.Hospitalisation).ToListAsync();
        var passages = await _db.Passages.AsNoTracking().ToListAsync();
        var aujourdhui = DateTime.UtcNow.Date;

        var enAttente = passages.Where(p => p.Statut == "En attente").ToList();
        var aTrier = passages.Count(p => p.Statut == "À trier");
        var delais = new Dictionary<int, int> { [1] = 0, [2] = 10, [3] = 60, [4] = 240 };
        var depasses = enAttente.Count(p => p.Categorie is int c
            && (DateTime.UtcNow - p.Arrivee).TotalMinutes > delais.GetValueOrDefault(c, 240));

        var armes = services.Sum(s => s.LitsArmes);
        var occ = services.Sum(s => s.Occupes);
        var bloq = services.Sum(s => s.Bloques);

        var attenteMoy = enAttente.Count > 0
            ? (int)enAttente.Average(p => (DateTime.UtcNow - p.Arrivee).TotalMinutes) : 0;

        var horizon = int.TryParse(
            (await _db.Parametres.FirstOrDefaultAsync(p => p.Cle == "seuil.horizonJours"))?.Valeur, out var h) ? h : 3;

        var risques = services
            .Select(s =>
            {
                var taux = s.LitsArmes > 0 ? (double)s.Occupes / s.LitsArmes : 0;
                var prev = _prev.Prevoir(s, Math.Max(horizon, 7));
                return new ServiceRisqueDto(s.Id, s.Nom, Math.Round(taux, 3),
                    PrevisionCapaciteService.RisqueSaturation(prev.Points, horizon),
                    PrevisionCapaciteService.Niveau(taux));
            })
            .OrderByDescending(r => r.Risque).Take(8).ToList();

        // Flux réel des arrivées, par tranche de 2 h sur les 16 dernières heures.
        var labels = new List<string>();
        var flux = new List<int>();
        for (var i = 7; i >= 0; i--)
        {
            var fin = DateTime.UtcNow.AddHours(-2 * i);
            var debut = fin.AddHours(-2);
            labels.Add(fin.ToString("HH:mm"));
            flux.Add(passages.Count(p => p.Arrivee > debut && p.Arrivee <= fin));
        }

        return Ok(new TableauBordDto(
            await _db.Patients.CountAsync(),
            passages.Count(p => p.Arrivee.Date == aujourdhui),
            enAttente.Count, aTrier, depasses,
            armes, occ, bloq, Math.Max(0, armes - occ - bloq),
            armes > 0 ? Math.Round((double)occ / armes, 3) : 0,
            attenteMoy,
            await _db.Sejours.CountAsync(s => s.Statut == "En cours"),
            await _db.RendezVous.CountAsync(r => r.Date >= DateOnly.FromDateTime(aujourdhui) && r.Statut != "Annulé"),
            await _db.Demandes.CountAsync(),
            risques, flux, labels));
    }

    /// <summary>Recherche globale (Ctrl+K) : patients, passages, services.</summary>
    [HttpGet("recherche")]
    public async Task<ActionResult<List<RechercheResultatDto>>> Recherche([FromQuery] string q)
    {
        var res = new List<RechercheResultatDto>();
        if (string.IsNullOrWhiteSpace(q) || q.Trim().Length < 2) return Ok(res);
        var t = q.Trim().ToLower();

        res.AddRange(await _db.Patients.AsNoTracking()
            .Where(p => p.Nom.ToLower().Contains(t) || p.Prenom.ToLower().Contains(t)
                || p.Reference.ToLower().Contains(t) || (p.Telephone != null && p.Telephone.Contains(t)))
            .Take(6)
            .Select(p => new RechercheResultatDto("Patient", p.Id, p.Nom + " " + p.Prenom,
                p.Reference + " · " + p.Age + " ans", "/patients/" + p.Id)).ToListAsync());

        res.AddRange(await _db.Passages.AsNoTracking().Include(p => p.Patient)
            .Where(p => p.Reference.ToLower().Contains(t) || p.Motif.ToLower().Contains(t))
            .Take(5)
            .Select(p => new RechercheResultatDto("Passage", p.Id, p.Reference + " — " + p.Motif,
                p.Patient!.Nom + " " + p.Patient.Prenom + " · " + p.Statut, "/file")).ToListAsync());

        res.AddRange(await _db.Services.AsNoTracking()
            .Where(s => s.Actif && (s.Nom.ToLower().Contains(t) || s.Code.ToLower().Contains(t)))
            .Take(5)
            .Select(s => new RechercheResultatDto("Service", s.Id, s.Nom, s.Pole, "/lits")).ToListAsync());

        return Ok(res);
    }
}
