@echo off
chcp 65001 >nul
title Registro WILLEM - servidor local
cd /d "%~dp0"
REM 1) Python portátil dentro de la carpeta (no requiere instalación)
if exist "python\python.exe" ( set "PY=python\python.exe" & goto :arrancar )
REM 2) Python instalado en el equipo
where py >nul 2>nul && ( set "PY=py -3" & goto :arrancar )
where python >nul 2>nul && ( set "PY=python" & goto :arrancar )
echo.
echo  No se ha encontrado Python en este ordenador.
echo  Lea el archivo LEEME.md, apartado "Si el ordenador no tiene Python".
echo.
pause
exit /b 1
:arrancar
%PY% servidor.py %*
pause
