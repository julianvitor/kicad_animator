#!/usr/bin/env bash
# ==============================================================================
# KiCad Animator - Inicializador Automático para Unix (macOS e Linux)
# ==============================================================================
set -e

# Garante execução no diretório do script
cd "$(dirname "$0")"

echo "⚡ [KiCad Animator] Verificando ambiente..."

# Configura PATH com diretórios padrão de ferramentas locais
export PATH="$HOME/.local/bin:$HOME/.poetry/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# 1. Localiza uma versão compatível do Python (>= 3.10 e < 3.14)
find_compatible_python() {
    # Se já existe .venv local compatível, aproveita diretamente
    if [ -x ".venv/bin/python" ]; then
        if .venv/bin/python -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info < (3, 14) else 1)' 2>/dev/null; then
            echo ".venv/bin/python"
            return 0
        fi
    fi

    # Varre executáveis de Python disponíveis
    for cand in python3.13 python3.12 python3.11 python3.10 \
                "$HOME/.local/share/uv/python/"*/bin/python3.13 \
                "$HOME/.local/share/uv/python/"*/bin/python3.12 \
                "$HOME/.local/share/uv/python/"*/bin/python3.11 \
                "/opt/homebrew/bin/python3.13" "/opt/homebrew/bin/python3.12" "/opt/homebrew/bin/python3.11" \
                "/usr/local/bin/python3.13" "/usr/local/bin/python3.12" "/usr/local/bin/python3.11" \
                python3 python; do
        if command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; then
            if "$cand" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info < (3, 14) else 1)' 2>/dev/null; then
                echo "$cand"
                return 0
            fi
        fi
    done
    return 1
}

PY_BIN="$(find_compatible_python || true)"
if [ -z "$PY_BIN" ]; then
    echo "❌ Erro: Nenhuma versão compatível do Python (>= 3.10 e < 3.14) foi encontrada."
    echo "💡 Instale o Python 3.11, 3.12 ou 3.13 (ex: brew install python@3.13 / apt install python3.12)."
    exit 1
fi

echo "🐍 Python detectado: $($PY_BIN -c 'import sys; print(sys.version.split()[0])') ($PY_BIN)"

# 2. Verifica ou Instala o Poetry
if ! command -v poetry >/dev/null 2>&1; then
    echo "📦 Poetry não encontrado. Instalando automaticamente via instalador oficial..."
    curl -sSL https://install.python-poetry.org | $PY_BIN -
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v poetry >/dev/null 2>&1; then
        echo "❌ Falha ao configurar o Poetry automaticamente no PATH."
        exit 1
    fi
    echo "✅ Poetry instalado com sucesso!"
fi

# 3. Garante que o Poetry utiliza a versão correta do Python
poetry config virtualenvs.in-project true --local >/dev/null 2>&1 || true
if [ ! -d ".venv" ]; then
    echo "🔧 Configurando ambiente virtual com $PY_BIN..."
    poetry env use "$PY_BIN" >/dev/null 2>&1 || true
fi

# 4. Instala ou Sincroniza Dependências
echo "📦 Verificando dependências do projeto..."
poetry install --no-interaction

# 5. Inicia a Aplicação
echo "🚀 Iniciando KiCad Animator..."
exec poetry run python main.py "$@"
