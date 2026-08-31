@echo off
setlocal
title Guitar Hero III - Codegen

REM ===========================================================================
REM  PASSO 1 - Gera o codigo C++ a partir do XEX do jogo.
REM
REM  Usa o rexglue 0.9.0 do projeto PES 2017 (nao ha copia local do SDK).
REM
REM  A fase "GapFill" nao escreve nada no log durante bastante tempo: e NORMAL,
REM  nao esta bloqueado. Para confirmar que esta vivo, abre outra janela e corre:
REM      python tools\codegen_watch.py
REM
REM  Sem hints de fronteiras de funcao nesta primeira ronda -- eles saem dos
REM  UnresolvedCall que a fase Validate listar, e vao para config\gh3_functions.toml
REM  na ronda seguinte.
REM ===========================================================================

set REXGLUE=C:\Users\Luis\Desktop\PES 2017 RECOMP\rexglue-sdk-090\out\win-amd64\Release\rexglue.exe
cd /d "%~dp0"

if not exist "%REXGLUE%" (
  echo [ERRO] rexglue.exe nao encontrado:
  echo        %REXGLUE%
  echo        Constroi a ferramenta com "PES 2017 RECOMP\rexglue-sdk-090\build-tool.bat"
  pause & exit /b 1
)

if not exist "..\extracted\default.xex" (
  echo [ERRO] ..\extracted\default.xex nao existe.
  echo        Extrai-o primeiro do ISO:
  echo          python tools\extract_xiso.py "..\Guitar Hero III - Legends of Rock (USA) (En,Fr,De,Es,It) (Rev 1)\Guitar Hero III - Legends of Rock (USA) rev 1.iso" --extract default.xex --out ..\extracted
  pause & exit /b 1
)

if exist config\gh3_functions.toml (
  for /f %%i in ('powershell -NoProfile -Command "(Select-String -Path ''config\gh3_functions.toml'' -Pattern ''\" = \{'' | Measure-Object).Count"') do set NHINTS=%%i
) else (
  set NHINTS=0 ^(primeira ronda^)
)

echo ===========================================================
echo  CODEGEN - Guitar Hero III
echo  hints de funcoes : %NHINTS%
echo  inicio           : %TIME%
echo ===========================================================
echo.
echo A limpar codigo gerado anterior...
if exist generated\default rmdir /s /q generated\default
mkdir generated\default

echo A correr o codegen (podes minimizar esta janela)...
echo.
"%REXGLUE%" --log-level info codegen gh3_manifest.toml > codegen_090.log 2> codegen_090.err.log
set RC=%errorlevel%

echo.
echo ===========================================================
if not "%RC%"=="0" (
  echo  CODEGEN FALHOU  ^(codigo %RC%^)   fim: %TIME%
  echo ===========================================================
  echo.
  powershell -NoProfile -Command "Select-String -Path 'codegen_090.err.log' -Pattern 'Failed:|UnresolvedCall|not in any function|Total:' | Select-Object -Last 15 | ForEach-Object { $_.Line }"
  echo.
  echo Log completo: codegen_090.err.log
  pause & exit /b 1
)

echo  CODEGEN OK   fim: %TIME%
echo ===========================================================
powershell -NoProfile -Command "Select-String -Path 'codegen_090.err.log' -Pattern 'Done in' | ForEach-Object { $_.Line }"
for /f %%i in ('powershell -NoProfile -Command "(Get-ChildItem generated\default -Filter *.cpp).Count"') do echo  ficheiros gerados: %%i
echo.

REM Validar ANTES do build: um hint que declare como funcao aquilo que e so um
REM alvo de salto dentro de outra funcao gera 'goto loc_XXXX' cujo rotulo passou
REM a viver noutro sitio, e o clang so se queixa la ao fim de minutos a compilar.
REM Isto apanha o mesmo em segundos.
echo A validar rotulos do codigo gerado...
python tools\check_generated_labels.py
if errorlevel 1 (
  echo.
  echo [AVISO] ha hints que partem funcoes - ve a lista acima.
  echo         Acrescenta esses enderecos a config\gh3_orphans_denied.txt e
  echo         regenera com: python tools\find_orphans.py ..\extracted\default.xex
  pause & exit /b 1
)

echo.
echo Tudo pronto. Agora corre:  2-BUILD.bat
pause
