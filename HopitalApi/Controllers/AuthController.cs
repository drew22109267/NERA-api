using System.Security.Claims;
using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public abstract class BaseController : ControllerBase
{
    protected int UserId => int.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var v) ? v : 0;
    protected string UserNom => User.FindFirst(ClaimTypes.Name)?.Value ?? "-";
    protected string UserRole => User.FindFirst(ClaimTypes.Role)?.Value ?? "-";
    protected int? UserPatientId => int.TryParse(User.FindFirst("patientId")?.Value, out var v) ? v : null;
}

[ApiController]
[Route("api/auth")]
public class AuthController : BaseController
{
    readonly AppDbContext _db;
    readonly TokenService _tok;
    readonly AuditService _audit;
    public AuthController(AppDbContext db, TokenService tok, AuditService audit) { _db = db; _tok = tok; _audit = audit; }

    static readonly string[] RolesConnus =
        { "accueil", "infirmier", "medecin", "gestionnaire", "direction", "data", "admin", "patient" };

    static UtilisateurDto Map(Utilisateur u) =>
        new(u.Id, u.Nom, u.Email, u.Role, u.PatientId, u.Actif, u.DerniereConnexion, u.ServiceId, u.CreeLe);

    [HttpPost("login"), AllowAnonymous]
    public async Task<ActionResult<SessionDto>> Login(LoginDto dto)
    {
        var u = await _db.Utilisateurs.FirstOrDefaultAsync(x => x.Email.ToLower() == dto.Email.ToLower());
        if (u is null) return Unauthorized(new { message = "Aucun compte pour cette adresse." });
        if (!u.Actif) return Unauthorized(new { message = "Ce compte est désactivé." });
        if (!BCrypt.Net.BCrypt.Verify(dto.MotDePasse, u.MotDePasseHash))
            return Unauthorized(new { message = "Mot de passe incorrect." });

        u.DerniereConnexion = DateTime.UtcNow;
        await _db.SaveChangesAsync();
        var (token, exp) = _tok.Creer(u);

        _db.Audits.Add(new AuditLog
        {
            Type = "connexion", Action = "Connexion réussie", UtilisateurId = u.Id,
            Utilisateur = u.Nom, Role = u.Role,
            AdresseIp = HttpContext.Connection.RemoteIpAddress?.ToString()
        });
        await _db.SaveChangesAsync();

        return Ok(new SessionDto(token, exp, Map(u)));
    }

    [HttpPost("signup"), AllowAnonymous]
    public async Task<ActionResult<SessionDto>> Signup(SignupDto dto)
    {
        if (!RolesConnus.Contains(dto.Role)) return BadRequest(new { message = "Rôle inconnu." });
        if (await _db.Utilisateurs.AnyAsync(x => x.Email.ToLower() == dto.Email.ToLower()))
            return Conflict(new { message = "Cette adresse est déjà utilisée." });

        var u = new Utilisateur
        {
            Nom = dto.Nom, Email = dto.Email.Trim(), Role = dto.Role,
            MotDePasseHash = BCrypt.Net.BCrypt.HashPassword(dto.MotDePasse)
        };

        // Un compte patient se rattache à un dossier ; créé vide s'il n'existe pas encore.
        if (dto.Role == "patient")
        {
            var parts = dto.Nom.Split(' ', 2);
            var p = new Patient
            {
                Reference = await NextRefAsync(_db), Nom = parts[0],
                Prenom = parts.Length > 1 ? parts[1] : "", Email = dto.Email.Trim(), Consentement = false
            };
            _db.Patients.Add(p);
            await _db.SaveChangesAsync();
            u.PatientId = p.Id;
        }

        _db.Utilisateurs.Add(u);
        await _db.SaveChangesAsync();
        var (token, exp) = _tok.Creer(u);
        return Ok(new SessionDto(token, exp, Map(u)));
    }

    internal static async Task<string> NextRefAsync(AppDbContext db)
    {
        var n = await db.Patients.CountAsync();
        return $"P-{10000 + n + 1}";
    }

    [HttpGet("moi")]
    public async Task<ActionResult<UtilisateurDto>> Moi()
    {
        var u = await _db.Utilisateurs.FindAsync(UserId);
        return u is null ? NotFound() : Ok(Map(u));
    }

    [HttpGet("utilisateurs"), Authorize(Roles = "admin,direction")]
    public async Task<ActionResult<List<UtilisateurDto>>> Liste() =>
        Ok(await _db.Utilisateurs.OrderBy(u => u.Nom).Select(u =>
            new UtilisateurDto(u.Id, u.Nom, u.Email, u.Role, u.PatientId, u.Actif,
                u.DerniereConnexion, u.ServiceId, u.CreeLe)).ToListAsync());

    /// <summary>Fiche d'un compte — pour la page profil de l'administration.</summary>
    [HttpGet("utilisateurs/{id:int}"), Authorize(Roles = "admin,direction")]
    public async Task<ActionResult<UtilisateurDto>> Fiche(int id)
    {
        var u = await _db.Utilisateurs.FindAsync(id);
        if (u is null) return NotFound(new { message = "Compte introuvable." });
        await _audit.LogAsync("consultation", "Consultation de compte", $"U-{id}");
        return Ok(Map(u));
    }

    /// <summary>Création d'un compte par un administrateur.</summary>
    [HttpPost("utilisateurs"), Authorize(Roles = "admin")]
    public async Task<ActionResult<UtilisateurDto>> Creer(CreerCompteDto dto)
    {
        if (!RolesConnus.Contains(dto.Role)) return BadRequest(new { message = "Rôle inconnu." });
        var email = dto.Email.Trim();
        if (await _db.Utilisateurs.AnyAsync(x => x.Email.ToLower() == email.ToLower()))
            return Conflict(new { message = "Cette adresse est déjà utilisée." });

        var u = new Utilisateur
        {
            Nom = dto.Nom.Trim(), Email = email, Role = dto.Role, ServiceId = dto.ServiceId,
            MotDePasseHash = BCrypt.Net.BCrypt.HashPassword(dto.MotDePasse)
        };

        // Un compte patient se rattache toujours à un dossier.
        if (dto.Role == "patient")
        {
            var parts = dto.Nom.Trim().Split(' ', 2);
            var p = new Patient
            {
                Reference = await NextRefAsync(_db), Nom = parts[0],
                Prenom = parts.Length > 1 ? parts[1] : "", Email = email, Consentement = false
            };
            _db.Patients.Add(p);
            await _db.SaveChangesAsync();
            u.PatientId = p.Id;
        }

        _db.Utilisateurs.Add(u);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("creation", "Création de compte", $"U-{u.Id}", u.Email);
        return CreatedAtAction(nameof(Fiche), new { id = u.Id }, Map(u));
    }

    /// <summary>Modification d'un compte — seuls les champs fournis sont appliqués.</summary>
    [HttpPatch("utilisateurs/{id:int}"), Authorize(Roles = "admin")]
    public async Task<ActionResult<UtilisateurDto>> Modifier(int id, [FromBody] MajCompteDto dto)
    {
        var u = await _db.Utilisateurs.FindAsync(id);
        if (u is null) return NotFound(new { message = "Compte introuvable." });

        if (dto.Role is { } role)
        {
            if (!RolesConnus.Contains(role)) return BadRequest(new { message = "Rôle inconnu." });
            // Ne jamais laisser l'établissement sans administrateur actif.
            if (u.Role == "admin" && role != "admin" && !await AutreAdminActifAsync(u.Id))
                return BadRequest(new { message = "C'est le dernier administrateur actif : changez d'abord un autre compte en administrateur." });
            u.Role = role;
        }

        if (dto.Actif is { } actif)
        {
            if (!actif && u.Id == UserId)
                return BadRequest(new { message = "Vous ne pouvez pas désactiver votre propre compte." });
            if (!actif && u.Role == "admin" && !await AutreAdminActifAsync(u.Id))
                return BadRequest(new { message = "C'est le dernier administrateur actif." });
            u.Actif = actif;
        }

        if (!string.IsNullOrWhiteSpace(dto.Nom)) u.Nom = dto.Nom.Trim();

        if (!string.IsNullOrWhiteSpace(dto.Email))
        {
            var email = dto.Email.Trim();
            if (await _db.Utilisateurs.AnyAsync(x => x.Id != id && x.Email.ToLower() == email.ToLower()))
                return Conflict(new { message = "Cette adresse est déjà utilisée." });
            u.Email = email;
        }

        if (!string.IsNullOrWhiteSpace(dto.MotDePasse))
        {
            if (dto.MotDePasse.Length < 8)
                return BadRequest(new { message = "Le mot de passe doit faire au moins 8 caractères." });
            u.MotDePasseHash = BCrypt.Net.BCrypt.HashPassword(dto.MotDePasse);
        }

        if (dto.ServiceId is { } sid) u.ServiceId = sid == 0 ? null : sid;

        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Modification de compte", $"U-{id}", u.Email);
        return Ok(Map(u));
    }

    /// <summary>Suppression définitive d'un compte. Le dossier patient éventuel est conservé.</summary>
    [HttpDelete("utilisateurs/{id:int}"), Authorize(Roles = "admin")]
    public async Task<IActionResult> Supprimer(int id)
    {
        var u = await _db.Utilisateurs.FindAsync(id);
        if (u is null) return NotFound(new { message = "Compte introuvable." });
        if (u.Id == UserId) return BadRequest(new { message = "Vous ne pouvez pas supprimer votre propre compte." });
        if (u.Role == "admin" && !await AutreAdminActifAsync(u.Id))
            return BadRequest(new { message = "C'est le dernier administrateur actif : il ne peut pas être supprimé." });

        var email = u.Email;
        _db.Utilisateurs.Remove(u);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("suppression", "Suppression de compte", $"U-{id}", email);
        return NoContent();
    }

    Task<bool> AutreAdminActifAsync(int saufId) =>
        _db.Utilisateurs.AnyAsync(x => x.Id != saufId && x.Role == "admin" && x.Actif);
}
