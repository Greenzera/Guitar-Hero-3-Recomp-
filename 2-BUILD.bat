@echo off
setlocal
title Guitar Hero III - Build

REM ===========================================================================
REM  PASSO 2 - Compila o gh3.exe a partir do codigo gerado.
REM
REM  Compila com 4 processos em paralelo de proposito: a maquina tem 8 GB de
REM  RAM e cada ficheiro gerado sao ~2 MB de C++, com o clang a gastar 1-2 GB
REM  por processo. Com mais jobs fica sem memoria. Passa outro numero como
REM  argumento se quiseres mudar:   2-BUILD.bat 6
REM
REM  Notas de ambiente (herdadas do PES 2017, mesmo SDK 0.9.0):
REM   - o CMake nativo tem de vir antes do MSYS2/devkitPro no PATH, senao os
REM     presets aparecem como "disabled";
REM   - o vcvars64 precisa do vswhere.exe no PATH;
REM   - CMake 4 precisa de -DCMAKE_POLICY_VERSION_MINIMUM=3.5 para os
REM     thirdparty antigos do SDK;
REM   - -msse4.1 e obrigatorio (o SDK usa intrinsecos SSSE3 e o clang, ao
REM     contrario do MSVC, exige a flag).
REM ===========================================================================

cd /d "%~dp0"

set VSWHERE_DIR=C:\Program Files (x86)\Microsoft Visual Studio\Installer
set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat
set CMAKE_BIN=C:\Program Files\CMake\bin
set LLVM_BIN=C:\Program Files\LLVM\bin
set NINJA_BIN=C:\Users\Luis\AppData\Local\Microsoft\WinGet\Links
set REXSDK=C:/Users/Luis/Desktop/PES 2017 RECOMP/rexglue-sdk-090
set BDIR=out/build/win-amd64-090
set JOBS=%1
if "%JOBS%"=="" set JOBS=4

if not exist generated\default\sources.cmake (
  echo [ERRO] nao ha codigo gerado. Corre primeiro o 1-CODEGEN.bat
  pause & exit /b 1
)

set PATH=%VSWHERE_DIR%;%PATH%
call "%VCVARS%" >nul
set PATH=%CMAKE_BIN%;%LLVM_BIN%;%NINJA_BIN%;%PATH%
if not defined INCLUDE (
  echo [ERRO] o vcvars64 nao configurou o ambiente MSVC.
  pause & exit /b 1
)

echo ===========================================================
echo  BUILD - Guitar Hero III      jobs: %JOBS%
echo  inicio : %TIME%
echo ===========================================================
echo.

echo [1/2] configure...
cmake -S . -B %BDIR% -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ ^
  -DREXSDK_DIR="%REXSDK%" ^
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 ^
  -DCMAKE_C_FLAGS="-msse4.1" -DCMAKE_CXX_FLAGS="-msse4.1" ^
  -DCMAKE_EXE_LINKER_FLAGS="-Wl,/MAP:gh3.map" > build090.log 2>&1
if errorlevel 1 (
  echo.
  echo [ERRO] configure falhou:
  powershell -NoProfile -Command "Get-Content build090.log -Tail 20"
  pause & exit /b 1
)

echo [2/2] a compilar (podes minimizar esta janela)...
echo.
cmake --build %BDIR% --target gh3 --parallel %JOBS% >> build090.log 2>&1
set RC=%errorlevel%

echo ===========================================================
if not "%RC%"=="0" (
  echo  BUILD FALHOU  ^(codigo %RC%^)   fim: %TIME%
  echo ===========================================================
  echo.
  powershell -NoProfile -Command "Select-String -Path 'build090.log' -Pattern 'error:|FAILED:' | Select-Object -First 10 | ForEach-Object { $_.Line }"
  echo.
  echo Log completo: build090.log
  pause & exit /b 1
)

echo  BUILD OK   fim: %TIME%
echo ===========================================================

REM Valores de fabrica, colocados ao lado do exe como gh3.DEFAULT.toml.
REM Nao e este o ficheiro que o jogo le: o Gh3App::OnConfigurePaths aponta as
REM definicoes para Documentos\gh3\gh3.toml, e so usa este para semear esse
REM ficheiro na primeira vez. Assim o botao "Save to config" do menu F4
REM sobrevive aos rebuilds, em vez de ser apagado por esta copia.
copy /y config\gh3.toml %BDIR%\gh3.default.toml >nul
if errorlevel 1 echo [AVISO] nao consegui copiar config\gh3.toml para %BDIR%

REM Restos de builds antigos, quando o jogo ainda lia daqui: se ficar, so
REM confunde quem for editar o ficheiro errado.
if exist %BDIR%\gh3.toml del /q %BDIR%\gh3.toml

powershell -NoProfile -Command "$f=Get-Item '%BDIR%/gh3.exe'; 'tamanho: {0:N1} MB' -f ($f.Length/1MB)"
echo.
echo Tudo pronto. Agora corre:  3-JOGAR.bat
pause
