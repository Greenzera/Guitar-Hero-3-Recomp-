@echo off
REM Build da variante DELUXE (XEX do mod) contra o ramo v0.8.1.19 do SDK (o do Skate 3), que traz o
REM menu de definicoes estilizado e o suporte a Android.
REM
REM Escreve para out/build/win-amd64-081, SEM tocar no build 090 que funciona.
REM Pre-requisito (codegen deste ramo, ~3 min):
REM   "<skate3>\third_party\rexglue-sdk\out\win-amd64\rexglue.exe" codegen gh3_manifest.sdk081.toml
setlocal
cd /d "%~dp0"

set VSWHERE_DIR=C:\Program Files (x86)\Microsoft Visual Studio\Installer
set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat
set CMAKE_BIN=C:\Program Files\CMake\bin
set LLVM_BIN=C:\Program Files\LLVM\bin
set NINJA_BIN=C:\Users\Luis\AppData\Local\Microsoft\WinGet\Links
set REXSDK=C:/Users/Luis/Desktop/projeto_CLAUDE/skate3recomp/third_party/rexglue-sdk
REM Headers do FidelityFX (tag v1.1.4 -- as 2.x reestruturaram para Kits/ e o
REM CMake do rexglue procura sdk/include e ffx-api/include). Apontar para ca
REM define REX_HAS_FIDELITYFX_SDK e destranca present_effect=cas/fsr/fsr2/fsr3;
REM sem isto so existe bilinear. O shader EASU ja vem compilado no rexglue,
REM por isso o FSR espacial nao precisa de mais nada alem destes headers.
set FFXSDK=C:/Users/Luis/Desktop/projeto_CLAUDE/FidelityFX-SDK
set BDIR=out/build/win-amd64-081-dx
set JOBS=%1
if "%JOBS%"=="" set JOBS=4

set PATH=%VSWHERE_DIR%;%PATH%
call "%VCVARS%" >nul
set PATH=%CMAKE_BIN%;%LLVM_BIN%;%NINJA_BIN%;%PATH%
if not defined INCLUDE ( echo [ERRO] vcvars64 falhou. & exit /b 1 )

echo [configure DX] inicio %TIME%
cmake -S . -B %BDIR% -G Ninja ^
  -DGH3_SDK=081 -DGH3_VARIANT=dx ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ ^
  -DREXSDK_DIR="%REXSDK%" ^
  -DREXGLUE_FIDELITYFX_SOURCE_DIR="%FFXSDK%" ^
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 ^
  -DCMAKE_C_FLAGS="-msse4.1" -DCMAKE_CXX_FLAGS="-msse4.1" > build081dx.log 2>&1
if errorlevel 1 (
  echo [configure DX] FALHOU - ultimas linhas:
  powershell -NoProfile -Command "Get-Content build081dx.log -Tail 25"
  exit /b 1
)
echo [configure DX] ok %TIME%

echo [build DX] inicio %TIME%  jobs=%JOBS%
cmake --build %BDIR% --target gh3 --parallel %JOBS% >> build081dx.log 2>&1
set RC=%errorlevel%
echo [build DX] fim %TIME%  rc=%RC%
exit /b %RC%
