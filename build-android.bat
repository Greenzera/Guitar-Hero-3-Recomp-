@echo off
REM ===========================================================================
REM Build ANDROID do Guitar Hero III recompilado.
REM
REM Uma APK com DUAS ABIs: arm64-v8a (telemovel) e x86_64 (emulador). O Android
REM escolhe a nativa do aparelho. Nao e so conveniencia: correr a .so arm64
REM dentro de um emulador x86 passa pelo tradutor Houdini, e ai o rexglue morre
REM -- ele depende de apanhar SIGSEGV para as guardas de memoria do guest, mas o
REM handler le o ucontext como ARM64 enquanto o kernel entrega o do x86 real.
REM Ver ANDROID.md.
REM
REM Uso:
REM   build-android.bat              build das duas ABIs + APK
REM   build-android.bat install      idem + instalar e arrancar no adb
REM   build-android.bat arm64        so arm64-v8a + APK
REM   build-android.bat x86_64       so x86_64 + APK
REM   build-android.bat apk          so a APK (reutiliza as .so ja compiladas)
REM
REM So compila contra o ramo 081 do SDK: o 0.9.0 poe a emulacao de GPU numa DLL
REM (gpu_plugin), que no Android nao existe. O 081 traz Vulkan embutido, o
REM overlay de touch e o surface_android -- e e a mesma arvore que ja levou o
REM Skate 3 a correr num telemovel.
REM
REM Pre-requisito, uma vez: codegen deste ramo (~60 s), que produz
REM generated/sdk081. O codigo gerado e o MESMO do PC -- e C++ portavel com
REM simde, nao ha codegen especifico de ARM nem de x86:
REM   "<skate3>\third_party\rexglue-sdk\out\win-amd64\rexglue.exe" codegen gh3_manifest.sdk081.toml
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set CMAKE_BIN=C:\Program Files\CMake\bin
set NINJA_BIN=C:\Users\Luis\AppData\Local\Microsoft\WinGet\Links
set ADB=C:\Users\Luis\AppData\Local\Android\Sdk\platform-tools\adb.exe
set JAVA_HOME=C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot
set ANDROID_HOME=C:\Users\Luis\AppData\Local\Android\Sdk
set JNILIBS=android\app\src\main\jniLibs
REM O SDK nao escreve as suas .so no build dir do jogo: manda-as para a pasta de
REM saida propria, com um nome por plataforma. So a libgh3.so fica no build dir.
set SDKOUT=C:\Users\Luis\Desktop\projeto_CLAUDE\skate3recomp\third_party\rexglue-sdk\out
set PATH=%CMAKE_BIN%;%NINJA_BIN%;%PATH%

set MODE=%1
if "%MODE%"=="" set MODE=build

if "%MODE%"=="apk" goto :apk
if "%MODE%"=="arm64" (
    call :buildabi android-arm64 arm64-v8a linux-arm64 || exit /b 1
    goto :apk
)
if "%MODE%"=="x86_64" (
    call :buildabi android-x86_64 x86_64 linux-amd64 || exit /b 1
    goto :apk
)
call :buildabi android-arm64  arm64-v8a linux-arm64 || exit /b 1
call :buildabi android-x86_64 x86_64    linux-amd64 || exit /b 1
goto :apk

REM --- %1 = preset, %2 = ABI (pasta jniLibs), %3 = pasta de saida do SDK ------
:buildabi
echo.
echo === %2 ===
if not exist "out\build\%1\build.ninja" (
    echo [configure %2] inicio %TIME%
    cmake --preset %1 > configure-%2.log 2>&1
    if errorlevel 1 (
        echo [configure %2] FALHOU:
        powershell -NoProfile -Command "Get-Content configure-%2.log -Tail 25"
        exit /b 1
    )
)
REM -j 4 e nao -j 12: sao 8 GB de RAM e os ficheiros gerados sao gordos; com
REM mais paralelismo o clang fica sem memoria a meio.
echo [build %2] inicio %TIME%
cmake --build out\build\%1 --target gh3 -j 4 > build-%2.log 2>&1
if errorlevel 1 (
    echo [build %2] FALHOU:
    powershell -NoProfile -Command "Get-Content build-%2.log -Tail 30"
    exit /b 1
)
echo [build %2] ok %TIME%
if not exist "%JNILIBS%\%2" mkdir "%JNILIBS%\%2"
copy /y "out\build\%1\libgh3.so" "%JNILIBS%\%2\" >nul || exit /b 1
copy /y "%SDKOUT%\%3\librexruntimerd.so" "%JNILIBS%\%2\" >nul || exit /b 1
exit /b 0

:apk
echo.
echo [gradle] inicio %TIME%
pushd android
call gradlew.bat assembleDebug --no-daemon > ..\gradle-android.log 2>&1
set RC=!errorlevel!
popd
if not "!RC!"=="0" (
    echo [gradle] FALHOU:
    powershell -NoProfile -Command "Get-Content gradle-android.log -Tail 30"
    exit /b !RC!
)
echo [gradle] ok %TIME%
echo APK: android\app\build\outputs\apk\debug\app-debug.apk

if not "%MODE%"=="install" goto :eof

echo [adb] a instalar
"%ADB%" install -r android\app\build\outputs\apk\debug\app-debug.apk || exit /b 1
REM Android 11+: conceder o "Acesso a todos os ficheiros" sem passar pelas
REM Definicoes (a app fecha-se sozinha a pedi-lo se faltar). Ate ao Android 10 e
REM a permissao classica de leitura que conta.
"%ADB%" shell appops set --uid com.gh3recomp MANAGE_EXTERNAL_STORAGE allow 2>nul
"%ADB%" shell pm grant com.gh3recomp android.permission.READ_EXTERNAL_STORAGE 2>nul
"%ADB%" shell am start -n com.gh3recomp/.Gh3Activity
echo.
echo Logs:  adb logcat -s gh3recomp:V GH3DBG:V
