@echo off
setlocal
REM ==============================================================================
REM KiCad Animator - Inicializador Rapido de 1 Clique (Windows CMD / Explorer)
REM ==============================================================================
cd /d "%~dp0"
title KiCad Animator

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_windows.ps1" %*

if errorlevel 1 (
    echo.
    echo [KiCad Animator] Ocorreu um erro durante a execucao.
    pause
)
