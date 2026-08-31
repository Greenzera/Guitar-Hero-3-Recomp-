# GH3 Launcher -- escolhe o executavel certo conforme os mods ativos.
#
# O problema que resolve: um recomp e codigo compilado de UM xex especifico. Um
# mod que altera o executavel (o GH3 Deluxe) tem o seu proprio xex e precisa do
# seu proprio build recompilado -- nao ha um exe que sirva os dois. Antes isso
# obrigava a escolher a mao entre dois atalhos.
#
# Este launcher decide sozinho: olha para os mods ATIVOS, e se algum trouxer um
# xex, procura o build que foi recompilado a partir DESSE xex (emparelha por
# hash SHA256, gravado em source-xex.sha256 dentro de cada build). Lanca esse.
# Sem mods de codigo ativos, lanca o build base.
#
# Isola tambem os settings: cada build corre com o seu proprio user_data_root,
# senao partilhavam Documents\gh3\gh3.toml e o mods_allow_xex de um estragava o
# outro.

$ErrorActionPreference = 'Stop'
$R         = "C:\Users\Luis\Desktop\GUITAR HERO 3 RECOMP"
$buildRoot = "$R\gh3recomp\out\build"
$modsRoot  = "$R\mods"
$gameData  = "$R\game"
$userBase  = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'gh3'

function Sha([string]$path) { (Get-FileHash $path -Algorithm SHA256).Hash }

# --- 1. builds disponiveis, indexados pelo hash do xex de origem -------------
$byHash = @{}
$baseDir = $null
Get-ChildItem $buildRoot -Directory -EA SilentlyContinue | ForEach-Object {
  $exe   = Join-Path $_.FullName 'gh3.exe'
  $stamp = Join-Path $_.FullName 'source-xex.sha256'
  if ((Test-Path $exe) -and (Test-Path $stamp)) {
    $h = (Get-Content $stamp -Raw).Trim().ToUpper()
    $byHash[$h] = $_
  }
}
# O build base e o que nasceu do xex do jogo original.
$origXex = "$R\extracted\default.xex"
$baseHash = if (Test-Path $origXex) { (Sha $origXex).ToUpper() } else { $null }
if ($baseHash -and $byHash.ContainsKey($baseHash)) { $baseDir = $byHash[$baseHash] }

# --- 2. mods ativos que trazem codigo (um default.xex) ----------------------
$codeMods = @()   # { name, hash }
if (Test-Path $modsRoot) {
  Get-ChildItem $modsRoot -Directory -EA SilentlyContinue | ForEach-Object {
    $disabled = Test-Path (Join-Path $_.FullName '.disabled')
    $xex      = Join-Path $_.FullName 'default.xex'
    if (-not $disabled -and (Test-Path $xex)) {
      $codeMods += [pscustomobject]@{ name = $_.Name; hash = (Sha $xex).ToUpper() }
    }
  }
}

# --- 3. decidir que build lancar --------------------------------------------
# @(...) obrigatorio: sem ele, um unico hash vira string e $distinct[0] indexaria
# o primeiro CARACTERE do hash em vez do hash inteiro (armadilha do PowerShell).
$distinct = @($codeMods | Select-Object -ExpandProperty hash -Unique)
$target = $null
$note   = $null

if ($distinct.Count -eq 0) {
  $target = $baseDir
  $note   = "Sem mods de codigo ativos -> jogo base."
}
elseif ($distinct.Count -eq 1) {
  $wanted = $distinct[0]
  $names  = ($codeMods | Where-Object hash -eq $wanted | ForEach-Object name) -join ', '
  if ($byHash.ContainsKey($wanted)) {
    $target = $byHash[$wanted]
    $note   = "Mod de codigo ativo ($names) -> build recompilado desse xex."
  } else {
    $target = $baseDir
    Write-Host ""
    Write-Host "  [AVISO] O mod '$names' altera o EXECUTAVEL do jogo, mas ainda"
    Write-Host "          nao foi recompilado. Vou jogar so com os DADOS dele."
    Write-Host "          Para aplicar tambem o codigo, arrasta o default.xex"
    Write-Host "          desse mod para o 'GH3 Mod Recompiler.exe' e volta a"
    Write-Host "          abrir o jogo."
    Write-Host ""
    $note = "Mod de codigo sem build ($names) -> base, so dados."
  }
}
else {
  Write-Host ""
  Write-Host "  [ERRO] Ha mais do que um mod ativo a alterar o executavel:"
  $codeMods | ForEach-Object { Write-Host "           - $($_.name)" }
  Write-Host "         Dois xex diferentes nao se combinam num so jogo."
  Write-Host "         Desativa todos menos um (mete um ficheiro .disabled na"
  Write-Host "         pasta, ou desliga-o no menu do jogo) e tenta outra vez."
  Write-Host ""
  Read-Host "Enter para sair"
  exit 1
}

if (-not $target) {
  Write-Host "  [ERRO] Nao encontrei nenhum build jogavel em:"
  Write-Host "         $buildRoot"
  Write-Host "         Compila primeiro com gh3recomp\build-081.bat"
  Read-Host "Enter para sair"
  exit 1
}

# --- 4. settings isolados por build -----------------------------------------
$variant  = $target.Name           # ex.: win-amd64-081-dx  (unico e estavel)
$userData = Join-Path $userBase $variant
New-Item -ItemType Directory -Force $userData | Out-Null

Write-Host "  $note"
Write-Host "  build : $($target.Name)"
Write-Host "  dados : $gameData"
Write-Host "  perfil: $userData"
Write-Host ""

# --game_data_root: os dados vem SEMPRE do jogo original (a pasta do mod so tem
# os ficheiros dele; o overlay trata de sobrepor). --user_data_root isola os
# settings desta variante.
$exe = Join-Path $target.FullName 'gh3.exe'
& $exe --game_data_root "$gameData" --user_data_root "$userData"
