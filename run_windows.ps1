# ==============================================================================
# KiCad Animator - Inicializador Automatico para Windows (PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"

# Garante execucao no diretorio do script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
[System.IO.Directory]::SetCurrentDirectory($ScriptDir)

Write-Host "[KiCad Animator] Verificando ambiente no Windows..." -ForegroundColor Cyan

# 1. Configura caminhos comuns de ferramentas locais no Windows
$UserScripts = Join-Path $env:APPDATA "Python\Scripts"
$UserLocalBin = Join-Path $env:USERPROFILE ".local\bin"
$PoetryBin = Join-Path $env:APPDATA "pypoetry\venv\Scripts"
$Python313Scripts = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\Scripts"
foreach ($p in @($UserScripts, $UserLocalBin, $PoetryBin, $Python313Scripts)) {
    if (Test-Path $p) { $env:Path = "$p;$env:Path" }
}

# 2. Localiza versao compativel do Python (>= 3.10 e < 3.14)
$PythonCmd = $null
$PythonExe = $null
$LocalVenvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"

$CheckScript = "import sys; sys.exit(0 if (3, 10) <= sys.version_info < (3, 14) else 1)"

if (Test-Path $LocalVenvPy) {
    try {
        & $LocalVenvPy -c $CheckScript
        if ($LASTEXITCODE -eq 0) {
            $PythonCmd = $LocalVenvPy
            $PythonExe = $LocalVenvPy
        }
    } catch {}
}

if (-not $PythonCmd) {
    $Candidates = @("py -3.13", "py -3.12", "py -3.11", "py -3.10", "python3.13", "python3.12", "python3.11", "python", "py")
    foreach ($Cand in $Candidates) {
        try {
            $parts = $Cand -split " "
            $cmd = $parts[0]
            $extraArgs = if ($parts.Length -gt 1) { $parts[1..($parts.Length - 1)] } else { @() }
            
            if (Get-Command $cmd -ErrorAction SilentlyContinue) {
                & $cmd $extraArgs -c $CheckScript
                if ($LASTEXITCODE -eq 0) {
                    $PythonCmd = $Cand
                    $PythonExe = (& $cmd $extraArgs -c "import sys; print(sys.executable)").Trim()
                    break
                }
            }
        } catch {}
    }
}

if (-not $PythonCmd) {
    Write-Host "[ERRO] Nenhuma versao compativel do Python (>= 3.10 e < 3.14) foi encontrada." -ForegroundColor Red
    Write-Host "[DICA] Instale o Python 3.11, 3.12 ou 3.13 em https://www.python.org/downloads/ (marque 'Add Python to PATH')." -ForegroundColor Yellow
    Exit 1
}

Write-Host "[Python] Detectado: $PythonCmd ($PythonExe)" -ForegroundColor Green

# 3. Verifica ou Instala o Poetry
if (-not (Get-Command "poetry" -ErrorAction SilentlyContinue)) {
    Write-Host "[Poetry] Instalando automaticamente via instalador oficial..." -ForegroundColor Yellow
    try {
        (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | & $PythonExe -
        
        $PossiblePoetry = @(
            (Join-Path $env:APPDATA "pypoetry\venv\Scripts"),
            (Join-Path $env:USERPROFILE ".local\bin"),
            (Join-Path $env:APPDATA "Python\Scripts"),
            (Join-Path (Split-Path $PythonExe) "Scripts")
        )
        foreach ($p in $PossiblePoetry) {
            if (Test-Path $p) { $env:Path = "$p;$env:Path" }
        }
    } catch {
        Write-Host "[Poetry] Instalador oficial falhou. Instalando via pip..." -ForegroundColor Yellow
        & $PythonExe -m pip install poetry
        $PipScripts = Join-Path (Split-Path $PythonExe) "Scripts"
        if (Test-Path $PipScripts) { $env:Path = "$PipScripts;$env:Path" }
    }
    
    if (Get-Command "poetry" -ErrorAction SilentlyContinue) {
        Write-Host "[Poetry] Instalado com sucesso!" -ForegroundColor Green
    } else {
        Write-Host "[ERRO] Falha ao localizar Poetry apos instalacao." -ForegroundColor Red
        Exit 1
    }
}

# 4. Garante uso do ambiente virtual local e instala dependencias
Write-Host "[Dependencias] Verificando dependencias do projeto..." -ForegroundColor Cyan
try {
    poetry config virtualenvs.in-project true --local
    if (-not (Test-Path (Join-Path $ScriptDir ".venv"))) {
        Write-Host "[Ambiente] Configurando ambiente virtual com $PythonExe..." -ForegroundColor Cyan
        poetry env use $PythonExe
    }
    poetry install --no-interaction
} catch {
    Write-Host "[ERRO] Falha ao instalar dependencias: $_" -ForegroundColor Red
    Exit 1
}

# 5. Inicia a Aplicacao
Write-Host "[KiCad Animator] Iniciando KiCad Animator..." -ForegroundColor Green
& poetry run python main.py $args
