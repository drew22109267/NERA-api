using System.Text;
using System.Text.Json.Serialization;
using HopitalApi.Data;
using HopitalApi.Services;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using Microsoft.OpenApi.Models;

var builder = WebApplication.CreateBuilder(args);

// Les secrets ne sont jamais dans appsettings.json (fichier versionné). En développement, ils viennent
// de appsettings.Development.json (ignoré par git, modèle : appsettings.exemple.json) ; en production,
// des variables d'environnement ConnectionStrings__Postgres et Jwt__Key.
var manquants = new List<string>();
if (string.IsNullOrWhiteSpace(builder.Configuration.GetConnectionString("Postgres")))
    manquants.Add("ConnectionStrings:Postgres (variable d'environnement ConnectionStrings__Postgres)");
if (Encoding.UTF8.GetByteCount(builder.Configuration["Jwt:Key"] ?? "") < 32)
    manquants.Add("Jwt:Key, au moins 32 caractères (variable d'environnement Jwt__Key)");
if (manquants.Count > 0)
    throw new InvalidOperationException(
        $"Configuration incomplète pour l'environnement « {builder.Environment.EnvironmentName} » : "
        + string.Join(" ; ", manquants)
        + ". Copiez HopitalApi/appsettings.exemple.json en appsettings.Development.json et remplissez-le.");

builder.Services.AddDbContext<AppDbContext>(o =>
    o.UseNpgsql(builder.Configuration.GetConnectionString("Postgres")));

builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<TokenService>();
builder.Services.AddScoped<AuditService>();
builder.Services.AddScoped<TriageScoreService>();
builder.Services.AddScoped<OrientationService>();
builder.Services.AddScoped<PrevisionCapaciteService>();
builder.Services.AddScoped<SynthesePatientService>();
builder.Services.AddScoped<HopitalApi.Services.Recherche.ImportRegistreService>();
builder.Services.AddScoped<HopitalApi.Services.Recherche.IndicateursService>();

// Les CSV enregistrés par Excel en français sont en Windows-1252.
System.Text.Encoding.RegisterProvider(System.Text.CodePagesEncodingProvider.Instance);

builder.Services.AddControllers().AddJsonOptions(o =>
{
    o.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
    o.JsonSerializerOptions.PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.CamelCase;
});

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
        o.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true, ValidateAudience = true,
            ValidateLifetime = true, ValidateIssuerSigningKey = true,
            ValidIssuer = builder.Configuration["Jwt:Issuer"],
            ValidAudience = builder.Configuration["Jwt:Audience"],
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(builder.Configuration["Jwt:Key"]!)),
            ClockSkew = TimeSpan.FromMinutes(1)
        };
    });
builder.Services.AddAuthorization();

var origins = builder.Configuration.GetSection("Cors:Origins").Get<string[]>() ?? Array.Empty<string>();
builder.Services.AddCors(o => o.AddDefaultPolicy(p =>
    p.WithOrigins(origins).AllowAnyHeader().AllowAnyMethod()));

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.SwaggerDoc("v1", new OpenApiInfo { Title = "API Triage & Lits", Version = "v1" });
    c.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
    {
        In = ParameterLocation.Header, Name = "Authorization", Type = SecuritySchemeType.Http,
        Scheme = "bearer", BearerFormat = "JWT", Description = "Coller le jeton renvoyé par /api/auth/login"
    });
    c.AddSecurityRequirement(new OpenApiSecurityRequirement
    {
        { new OpenApiSecurityScheme { Reference = new OpenApiReference { Type = ReferenceType.SecurityScheme, Id = "Bearer" } },
          Array.Empty<string>() }
    });
});

var app = builder.Build();

// Migration + amorçage des données de référence au démarrage.
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    var logger = scope.ServiceProvider.GetRequiredService<ILogger<Program>>();
    try
    {
        await db.Database.MigrateAsync();
        if (app.Configuration.GetValue("Seed:Enabled", true))
            await DbSeeder.SeedAsync(db, app.Configuration, logger);
    }
    catch (Exception ex)
    {
        logger.LogError(ex, "Base de données indisponible — vérifiez la chaîne de connexion PostgreSQL.");
    }
}

app.UseSwagger();
app.UseSwaggerUI(c => c.SwaggerEndpoint("/swagger/v1/swagger.json", "API Triage & Lits v1"));

app.UseCors();
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();
app.MapGet("/", () => Results.Redirect("/swagger"));
app.MapGet("/api/sante", async (AppDbContext db) => new
{
    statut = "ok",
    baseDeDonnees = await db.Database.CanConnectAsync() ? "connectée" : "indisponible",
    heure = DateTime.UtcNow
});

app.Run();
