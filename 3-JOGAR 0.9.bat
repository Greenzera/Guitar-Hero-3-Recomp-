@echo off
setlocal
title Guitar Hero III - Jogar

REM ===========================================================================
REM  PASSO 3 - Arranca o jogo.
REM
REM  --game_data_root e passado na linha de comando de proposito: na v0.9.0 esse
REM  caminho vem de um cvar e o .toml ao lado do exe ja nao o define, por isso
REM  abrir o exe as direito da o dialogo "--game_data_root was not provided".
REM
REM  Ao contrario do PES 2017, aqui NAO ha default.xexp: o GH3 nao traz title
REM  update no disco, e o codigo foi gerado a partir da imagem base. So o
REM  default.xex e a arvore DATA\ tem de estar na pasta do jogo.
REM
REM  A pasta do jogo sai da extracao completa do ISO:
REM    python tools\extract_xiso.py "<iso>" --extract-all --out ..\game
REM ===========================================================================

set GAME=C:\Users\Luis\Desktop\GUITAR HERO 3 RECOMP\game
set BDIR=%~dp0out\build\win-amd64-090

if not exist "%BDIR%\gh3.exe" (
  echo [ERRO] gh3.exe nao existe. Corre primeiro 1-CODEGEN.bat e 2-BUILD.bat
  pause & exit /b 1
)
if not exist "%GAME%\default.xex" ( echo [ERRO] falta default.xex em "%GAME%" & pause & exit /b 1 )
if not exist "%GAME%\DATA"        ( echo [ERRO] falta a pasta DATA em "%GAME%" & pause & exit /b 1 )

cd /d "%BDIR%"
echo A arrancar o jogo...
echo   dados : %GAME%
echo.
gh3.exe --game_data_root "%GAME%"
set RC=%errorlevel%

echo.
echo ===========================================================
if "%RC%"=="0" (
  echo  O jogo fechou normalmente.
) else (
  echo  O jogo terminou com codigo %RC%
  if "%RC%"=="-1073741819" echo   ^(0xC0000005 = acesso invalido a memoria^)
  if "%RC%"=="-1073740791" echo   ^(0xC0000409 = abort - normalmente um FATAL do runtime^)
)
echo ===========================================================
echo.
echo Ultimas linhas do log:
powershell -NoProfile -Command "$l=Get-ChildItem logs\*.log | Sort-Object LastWriteTime | Select-Object -Last 1; ''; \"log: $($l.Name)\"; ''; Get-Content $l.FullName -Tail 12"
echo.
echo Se aparecer 'Call to invalid or unregistered function at guest address 0xXXXXXXXX',
echo copia esse endereco e diz-me: e mais uma funcao orfa para acrescentar aos
echo hints em config\gh3_functions.toml (usa tools\xex_image.py --sweep 0xXXXXXXXX).
pause
