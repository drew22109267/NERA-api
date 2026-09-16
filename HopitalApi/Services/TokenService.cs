using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using HopitalApi.Data;
using HopitalApi.Models;
using Microsoft.IdentityModel.Tokens;

namespace HopitalApi.Services;

public class TokenService
{
    readonly IConfiguration _cfg;
    public TokenService(IConfiguration cfg) => _cfg = cfg;

    public (string Token, DateTime Expire) Creer(Utilisateur u)
    {
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_cfg["Jwt:Key"]!));
        var expire = DateTime.UtcNow.AddHours(double.Parse(_cfg["Jwt:ExpiresHours"] ?? "12"));
        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, u.Id.ToString()),
            new(ClaimTypes.NameIdentifier, u.Id.ToString()),
            new(ClaimTypes.Name, u.Nom),
            new(ClaimTypes.Email, u.Email),
            new(ClaimTypes.Role, u.Role)
        };
        if (u.PatientId is int pid) claims.Add(new Claim("patientId", pid.ToString()));
        if (u.ServiceId is int sid) claims.Add(new Claim("serviceId", sid.ToString()));

        var jwt = new JwtSecurityToken(
            issuer: _cfg["Jwt:Issuer"], audience: _cfg["Jwt:Audience"],
            claims: claims, expires: expire,
            signingCredentials: new SigningCredentials(key, SecurityAlgorithms.HmacSha256));

        return (new JwtSecurityTokenHandler().WriteToken(jwt), expire);
    }
}

/// <summary>Journalise actions ET consultations de dossier (confidentialité).</summary>
public class AuditService
{
    readonly AppDbContext _db;
    readonly IHttpContextAccessor _ctx;
    public AuditService(AppDbContext db, IHttpContextAccessor ctx) { _db = db; _ctx = ctx; }

    public async Task LogAsync(string type, string action, string? cible = null, string? detail = null)
    {
        var user = _ctx.HttpContext?.User;
        _db.Audits.Add(new AuditLog
        {
            Type = type, Action = action, Cible = cible, Detail = detail,
            UtilisateurId = int.TryParse(user?.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var id) ? id : null,
            Utilisateur = user?.FindFirst(ClaimTypes.Name)?.Value ?? "anonyme",
            Role = user?.FindFirst(ClaimTypes.Role)?.Value ?? "-",
            AdresseIp = _ctx.HttpContext?.Connection.RemoteIpAddress?.ToString()
        });
        await _db.SaveChangesAsync();
    }
}
