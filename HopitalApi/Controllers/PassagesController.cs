using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

[ApiController]
[Route("api/passages")]
public class PassagesController : BaseController
{
    readonly AppDbContext _db;
    readonly AuditService _audit;
    readonly TriageScoreService _score;
    public PassagesController(AppDbContext db, AuditService audit, TriageScoreService score)
    { _db = db; _audit = audit; _score = score; }

    static readonly Dictionary<int, int> DelaiMax = new() { [1] = 0, [2] = 10, [3] = 60, [4] = 240 };

    internal static PassageDto Map(Passage p)
    {
        var attente = (int)Math.Max(0, (DateTime.UtcNow - p.Arrivee).TotalMinutes);
        var depasse = p.Statut == "En attente" && p.Categorie is int c && attente > DelaiMax.GetValueOrDefault(c, 240);
        return new PassageDto(
            p.Id, p.Reference, p.PatientId,
            p.Patient is null ? "" : $"{p.Patient.Nom} {p.Patient.Prenom}",
            p.Patient?.Age ?? 0, p.Patient?.Sexe ?? "",
            p.Arrivee, attente, p.ModeEntree, p.Motif, p.MotifLibre,
            p.ServiceViseId, p.ServiceVise?.Nom, p.Statut,
            p.Categorie, p.CategorieModele, p.ValideePar, depasse,
            p.CorrectionNouvelle is null ? null
                : new CorrectionDto(p.CorrectionAncienne, p.CorrectionNouvelle, p.CorrectionMotif, p.CorrectionAuteur, p.CorrectionLe),
            p.DecisionAction is null ? null
                : new DecisionDto(p.DecisionAction, p.DecisionServiceId, null, p.DecisionMotif, p.DecisionRecommandation, p.DecisionDivergence, p.DecisionLe),
            p.Triage is null ? null : new TriageDto
            {
                Pas = p.Triage.Pas, Pad = p.Triage.Pad, Fc = p.Triage.Fc, Fr = p.Triage.Fr,
                Temperature = p.Triage.Temperature, Spo2 = p.Triage.Spo2, Glycemie = p.Triage.Glycemie,
                Poids = p.Triage.Poids, Avpu = p.Triage.Avpu, Glasgow = p.Triage.Glasgow,
                Eva = p.Triage.Eva, CategorieManuelle = p.Triage.CategorieManuelle
            });
    }

    IQueryable<Passage> Base() => _db.Passages
        .Include(p => p.Patient).Include(p => p.ServiceVise).Include(p => p.Triage);

    [HttpGet]
    public async Task<ActionResult<PageResult<PassageDto>>> Liste(
        [FromQuery] string? statut, [FromQuery] int? serviceId, [FromQuery] string? q,
        [FromQuery] int page = 1, [FromQuery] int pageSize = 25)
    {
        page = Math.Max(1, page); pageSize = Math.Clamp(pageSize, 5, 200);
        var query = Base().AsNoTracking();

        if (UserRole == "patient")
        {
            if (UserPatientId is null) return Ok(new PageResult<PassageDto>(Array.Empty<PassageDto>(), 0, 1, pageSize));
            query = query.Where(p => p.PatientId == UserPatientId);
        }
        if (!string.IsNullOrWhiteSpace(statut) && statut != "Tous") query = query.Where(p => p.Statut == statut);
        if (serviceId is int sid) query = query.Where(p => p.ServiceViseId == sid);
        if (!string.IsNullOrWhiteSpace(q))
        {
            var t = q.Trim().ToLower();
            query = query.Where(p => p.Reference.ToLower().Contains(t) ||
                p.Patient!.Nom.ToLower().Contains(t) || p.Patient.Prenom.ToLower().Contains(t));
        }

        var total = await query.CountAsync();
        var items = await query
            .OrderBy(p => p.Categorie ?? 9).ThenBy(p => p.Arrivee)
            .Skip((page - 1) * pageSize).Take(pageSize).ToListAsync();
        return Ok(new PageResult<PassageDto>(items.Select(Map).ToList(), total, page, pageSize));
    }

    [HttpGet("{id:int}")]
    public async Task<ActionResult<PassageDto>> Detail(int id)
    {
        var p = await Base().FirstOrDefaultAsync(x => x.Id == id);
        if (p is null) return NotFound(new { message = "Passage introuvable." });
        if (UserRole == "patient" && p.PatientId != UserPatientId) return Forbid();
        return Ok(Map(p));
    }

    [HttpPost, Authorize(Roles = "accueil,infirmier,medecin,admin")]
    public async Task<ActionResult<PassageDto>> Creer(PassageCreateDto dto)
    {
        if (!await _db.Patients.AnyAsync(x => x.Id == dto.PatientId))
            return BadRequest(new { message = "Patient inconnu." });

        var n = await _db.Passages.CountAsync();
        var p = new Passage
        {
            Reference = $"A-{5000 + n + 1}", PatientId = dto.PatientId, ModeEntree = dto.ModeEntree,
            Motif = dto.Motif, MotifLibre = dto.MotifLibre, ServiceViseId = dto.ServiceViseId,
            Arrivee = DateTime.UtcNow, Statut = "À trier"
        };
        _db.Passages.Add(p);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Enregistrement d'arrivée", p.Reference, dto.Motif);
        return CreatedAtAction(nameof(Detail), new { id = p.Id }, Map(await Base().FirstAsync(x => x.Id == p.Id)));
    }

    /// <summary>Évalue sans enregistrer — alimente l'aperçu temps réel de la fiche de triage.</summary>
    [HttpPost("{id:int}/evaluer"), Authorize(Roles = "infirmier,medecin,admin")]
    public async Task<ActionResult<EvaluationTriageDto>> Evaluer(int id, TriageDto dto)
    {
        var p = await Base().FirstOrDefaultAsync(x => x.Id == id);
        if (p?.Patient is null) return NotFound(new { message = "Passage introuvable." });
        return Ok(Evaluation(dto, p.Patient, p.Motif, p.ModeEntree));
    }

    EvaluationTriageDto Evaluation(TriageDto dto, Patient patient, string motif, string mode)
    {
        var t = new Triage
        {
            Pas = dto.Pas, Pad = dto.Pad, Fc = dto.Fc, Fr = dto.Fr, Temperature = dto.Temperature,
            Spo2 = dto.Spo2, Glycemie = dto.Glycemie, Poids = dto.Poids, Avpu = dto.Avpu,
            Glasgow = dto.Glasgow, Eva = dto.Eva, CategorieManuelle = dto.CategorieManuelle
        };
        var r = _score.Evaluer(t, patient, motif, mode);
        return new EvaluationTriageDto(r.Disponible, r.Raison, r.Score, r.Categorie, r.Confiance, r.Incertain, r.Manquants,
            r.Contributions.Select(c => new ContributionDto(c.Label, c.Poids)).ToList(),
            new ScoresDerivesDto(r.IndexChoc, r.Pam, r.QSofa, r.QSofaConnus, r.Mews), r.Modele);
    }

    [HttpPost("{id:int}/triage"), Authorize(Roles = "infirmier,medecin,admin")]
    public async Task<ActionResult<PassageDto>> EnregistrerTriage(int id, TriageSubmitDto dto)
    {
        var p = await Base().FirstOrDefaultAsync(x => x.Id == id);
        if (p?.Patient is null) return NotFound(new { message = "Passage introuvable." });

        var c = dto.Constantes;
        var eval = Evaluation(c, p.Patient, p.Motif, p.ModeEntree);
        // Sans modèle, la catégorie est celle que l'infirmier fixe ; rien n'est proposé à sa place.
        if ((dto.CategorieRetenue ?? eval.Categorie) is not int retenue)
            return BadRequest(new { message = "Aucun modèle de triage n'est branché : choisissez la catégorie retenue." });
        var correction = eval.Categorie is not null && retenue != eval.Categorie;
        if (correction && string.IsNullOrWhiteSpace(dto.MotifCorrection))
            return BadRequest(new { message = "Le motif de correction est obligatoire lorsque vous modifiez la catégorie proposée." });

        p.Triage ??= new Triage { PassageId = p.Id };
        p.Triage.Pas = c.Pas; p.Triage.Pad = c.Pad; p.Triage.Fc = c.Fc; p.Triage.Fr = c.Fr;
        p.Triage.Temperature = c.Temperature; p.Triage.Spo2 = c.Spo2; p.Triage.Glycemie = c.Glycemie;
        p.Triage.Poids = c.Poids; p.Triage.Avpu = c.Avpu; p.Triage.Glasgow = c.Glasgow;
        p.Triage.Eva = c.Eva; p.Triage.CategorieManuelle = c.CategorieManuelle;
        p.Triage.EnregistreLe = DateTime.UtcNow; p.Triage.EnregistrePar = UserNom;

        p.Categorie = retenue; p.CategorieModele = eval.Categorie;
        p.ValideePar = UserNom; p.TriageLe = DateTime.UtcNow;
        if (p.Statut == "À trier") p.Statut = "En attente";
        if (correction)
        {
            p.CorrectionAncienne = eval.Categorie!.Value; p.CorrectionNouvelle = retenue;
            p.CorrectionMotif = dto.MotifCorrection; p.CorrectionAuteur = UserNom;
            p.CorrectionLe = DateTime.UtcNow;
        }

        // Le journal des prédictions ne reçoit que de vraies sorties de modèle.
        if (eval.Disponible && eval.Score is double score && eval.Categorie is int sortie && eval.Confiance is double confiance)
            _db.Predictions.Add(new PredictionLog
            {
                PassageId = p.Id, Modele = eval.Modele, TypeModele = "triage",
                Score = score, Sortie = sortie, Confiance = confiance,
                ExplicationJson = TriageScoreService.Serialiser(eval.Contributions),
                EntreeJson = TriageScoreService.Serialiser(c),
                DecisionHumaine = retenue, Ecart = correction
            });

        if (retenue <= 2)
            _db.Notifications.Add(new Notification
            {
                Destinataire = "Médecin", Type = "Réévaluation", Niveau = retenue == 1 ? "crit" : "warn",
                Texte = $"{p.Reference} — catégorie {retenue}, délai maximal {DelaiMax.GetValueOrDefault(retenue)} min."
            });

        try { await _db.SaveChangesAsync(); }
        catch (DbUpdateConcurrencyException)
        { return Conflict(new { message = "Ce passage vient d'être modifié depuis un autre poste. Rechargez la fiche." }); }

        await _audit.LogAsync("modification", correction ? "Correction de catégorie de triage" : "Validation de triage",
            p.Reference, $"catégorie {retenue}");
        return Ok(Map(await Base().FirstAsync(x => x.Id == id)));
    }

    [HttpPost("{id:int}/statut"), Authorize(Roles = "infirmier,medecin,accueil,admin")]
    public async Task<ActionResult<PassageDto>> Statut(int id, [FromBody] Dictionary<string, string> body)
    {
        var p = await Base().FirstOrDefaultAsync(x => x.Id == id);
        if (p is null) return NotFound();
        if (!body.TryGetValue("statut", out var s)) return BadRequest(new { message = "Statut manquant." });
        p.Statut = s;
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Changement de statut", p.Reference, s);
        return Ok(Map(p));
    }

    [HttpPost("{id:int}/decision"), Authorize(Roles = "medecin,admin")]
    public async Task<ActionResult<PassageDto>> Decision(int id, DecisionCreateDto dto)
    {
        var p = await Base().FirstOrDefaultAsync(x => x.Id == id);
        if (p is null) return NotFound();
        var divergence = dto.Action != dto.Recommandation;
        if (divergence && string.IsNullOrWhiteSpace(dto.Motif))
            return BadRequest(new { message = "Le motif est obligatoire lorsque la décision diverge de la recommandation." });

        p.DecisionAction = dto.Action; p.DecisionServiceId = dto.ServiceId; p.DecisionMotif = dto.Motif;
        p.DecisionRecommandation = dto.Recommandation; p.DecisionDivergence = divergence;
        p.DecisionLe = DateTime.UtcNow; p.Statut = "Vu";

        // Admission effective : le lit est décompté immédiatement.
        if (dto.Action.StartsWith("Admettre") && dto.ServiceId is int sid)
        {
            var svc = await _db.Services.FindAsync(sid);
            if (svc is not null && svc.Occupes < svc.LitsArmes)
            {
                svc.Occupes++;
                var n = await _db.Sejours.CountAsync();
                _db.Sejours.Add(new Sejour
                {
                    Reference = $"S-{800 + n + 1}", PatientId = p.PatientId,
                    ServiceId = sid, Entree = DateTime.UtcNow,
                    DiagnosticEntree = string.IsNullOrWhiteSpace(dto.DiagnosticEntree) ? null : dto.DiagnosticEntree.Trim()
                });
            }
        }

        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Décision clinique", p.Reference,
            dto.Action + (divergence ? " (divergence)" : ""));
        return Ok(Map(p));
    }
}
