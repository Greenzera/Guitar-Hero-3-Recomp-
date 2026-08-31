@echo off
title Guitar Hero 3 Recomp - Launcher
cd /d "%~dp0"
if not exist "node_modules" (
  echo Primeira execucao: a instalar as dependencias...
  call npm install
)
call npx electron .
