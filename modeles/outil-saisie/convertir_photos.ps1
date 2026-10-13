<#
  Convertit les photos du registre (HEIC, JPEG, PNG) en JPEG lisibles par la page de saisie.

  - Utilise le décodeur HEIF intégré à Windows : rien à installer.
  - Les originaux ne sont jamais modifiés : les copies vont dans un autre dossier.
  - Les métadonnées sont supprimées (position GPS, date, modèle du téléphone).
  - Une photo restée de côté se redresse ensuite dans la page de saisie (boutons ⟲ ⟳).

  Utilisation :
    powershell -ExecutionPolicy Bypass -File convertir_photos.ps1 -Source ..\pediatrie -Destination photos_pediatrie
  ou double-cliquer sur convertir_photos.bat.
#>
param(
  [Parameter(Mandatory = $true)][string]$Source,
  [Parameter(Mandatory = $true)][string]$Destination,
  [int]$TailleMax = 2600
)

Add-Type -AssemblyName PresentationCore
$ErrorActionPreference = 'Stop'

$src = (Resolve-Path $Source).Path
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$dst = (Resolve-Path $Destination).Path
if ($src -eq $dst) { throw "Le dossier de sortie doit être différent de celui des originaux." }

$photos = Get-ChildItem -Path $src -File | Where-Object { $_.Extension -match '^\.(heic|heif|jpe?g|png)$' } | Sort-Object Name
if (-not $photos) { throw "Aucune photo trouvée dans $src" }

$i = 0
foreach ($p in $photos) {
  $i++
  $cible = Join-Path $dst ($p.BaseName + '.jpg')
  if (Test-Path $cible) { Write-Host "[$i/$($photos.Count)] déjà converti : $($p.BaseName).jpg"; continue }

  $flux = [System.IO.File]::OpenRead($p.FullName)
  try {
    $decodeur = [System.Windows.Media.Imaging.BitmapDecoder]::Create($flux,
      [System.Windows.Media.Imaging.BitmapCreateOptions]::IgnoreColorProfile,
      [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad)
    $image = $decodeur.Frames[0]
    $echelle = [Math]::Min(1.0, $TailleMax / [Math]::Max($image.PixelWidth, $image.PixelHeight))
    # Une image transformée ne transporte aucune métadonnée de l'original.
    $reduite = New-Object System.Windows.Media.Imaging.TransformedBitmap($image,
      (New-Object System.Windows.Media.ScaleTransform($echelle, $echelle)))
    $encodeur = New-Object System.Windows.Media.Imaging.JpegBitmapEncoder
    $encodeur.QualityLevel = 88
    $encodeur.Frames.Add([System.Windows.Media.Imaging.BitmapFrame]::Create($reduite, $null, $null, $null))
    $sortie = [System.IO.File]::Create($cible)
    try { $encodeur.Save($sortie) } finally { $sortie.Close() }
    Write-Host "[$i/$($photos.Count)] $($p.Name) -> $($p.BaseName).jpg"
  } finally { $flux.Close() }
}
Write-Host ""
Write-Host "Terminé : $($photos.Count) photo(s) dans $dst"
