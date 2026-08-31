@echo off
REM Igual ao 2-BUILD.bat mas sem 'pause' nem cores, para correr sem interacao.
REM Usa-se para builds automatizados; para uso normal preferir o 2-BUILD.bat.
setlocal
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

set PATH=%VSWHERE_DIR%;%PATH%
call "%VCVARS%" >nul
set PATH=%CMAKE_BIN%;%LLVM_BIN%;%NINJA_BIN%;%PATH%
if not defined INCLUDE (
  echo [ERRO] vcvars64 nao configurou o ambiente MSVC.
  exit /b 1
)

echo [configure] inicio %TIME%
cmake -S . -B %BDIR% -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ ^
  -DREXSDK_DIR="%REXSDK%" ^
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 ^
  -DCMAKE_C_FLAGS="-msse4.1" -DCMAKE_CXX_FLAGS="-msse4.1" ^
  -DCMAKE_EXE_LINKER_FLAGS="-Wl,/MAP:gh3.map" > build090.log 2>&1
if errorlevel 1 (
  echo [configure] FALHOU
  exit /b 1
)
echo [configure] ok %TIME%

echo [build] inicio %TIME%  jobs=%JOBS%
cmake --build %BDIR% --target gh3 --parallel %JOBS% >> build090.log 2>&1
set RC=%errorlevel%
echo [build] fim %TIME%  rc=%RC%
exit /b %RC%
