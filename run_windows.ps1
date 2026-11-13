# ==============================================================================
# KiCad Animator - Inicializador Automático para Windows (PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"

# Garante execução no diretório do script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "⚡ [KiCad Animator] Verificando ambiente no Windows..." -ForegroundColor Cyan

# 1. Configura caminhos comuns de ferramentas locais no Windows
$UserScripts = Join-Path $env:APPDATA "Python\Scripts"
$UserLocalBin = Join-Path $env:USERPROFILE ".local\bin"
if (Test-Path $UserScripts) { $env:Path = "$UserScripts;$env:Path" }
if (Test-Path $UserLocalBin) { $env:Path = "$UserLocalBin;$env:Path" }

# 2. Localiza versão compatível do Python (>= 3.10 e < 3.14)
$PythonCmd = $null
$LocalVenvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"

$CheckScript = "import sys; sys.exit(0 if (3, 10) <= sys.version_info < (3, 14) else 1)"

if (Test-Path $LocalVenvPy) {
    try {
        & $LocalVenvPy -c $CheckScript
        if ($LASTEXITCODE -eq 0) {
            $PythonCmd = $LocalVenvPy
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
                    break
                }
            }
        } catch {}
    }
}

if (-not $PythonCmd) {
    Write-Host "❌ Erro: Nenhuma versão compatível do Python (>= 3.10 e < 3.14) foi encontrada." -ForegroundColor Red
    Write-Host "💡 Baixe e instale o Python 3.11, 3.12 ou 3.13 em https://www.python.org/downloads/ (marque 'Add Python to PATH')." -ForegroundColor Yellow
    Exit 1
}

Write-Host "🐍 Python detectado: $PythonCmd" -ForegroundColor Green

# 3. Verifica ou Instala o Poetry
if (-not (Get-Command "poetry" -ErrorAction SilentlyContinue)) {
    Write-Host "📦 Poetry não encontrado. Instalando automaticamente via instalador oficial..." -ForegroundColor Yellow
    try {
        $parts = $PythonCmd -split " "
        $cmd = $parts[0]
        $extraArgs = if ($parts.Length -gt 1) { $parts[1..($parts.Length - 1)] } else { @() }
        (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | & $cmd $extraArgs -
        
        if (Test-Path $UserLocalBin) { $env:Path = "$UserLocalBin;$env:Path" }
        if (Test-Path $UserScripts) { $env:Path = "$UserScripts;$env:Path" }
        Write-Host "✅ Poetry instalado com sucesso!" -ForegroundColor Green
    } catch {
        Write-Host "❌ Falha ao instalar o Poetry automaticamente: $_" -ForegroundColor Red
        Write-Host "💡 Tente instalar manualmente via: pip install poetry" -ForegroundColor Yellow
        Exit 1
    }
}

# 4. Garante uso do ambiente virtual local e instala dependências
Write-Host "📦 Verificando dependências do projeto..." -ForegroundColor Cyan
try {
    poetry config virtualenvs.in-project true --local
    if (-not (Test-Path (Join-Path $ScriptDir ".venv"))) {
        Write-Host "🔧 Configurando ambiente virtual com $PythonCmd..." -ForegroundColor Cyan
        $parts = $PythonCmd -split " "
        poetry env use $parts[0]
    }
    poetry install --no-interaction
} catch {
    Write-Host "❌ Erro ao instalar dependências: $_" -ForegroundColor Red
    Exit 1
}

# 5. Inicia a Aplicação
Write-Host "🚀 Iniciando KiCad Animator..." -ForegroundColor Green
& poetry run python main.py $args
