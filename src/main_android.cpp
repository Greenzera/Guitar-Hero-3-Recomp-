// Ponto de entrada Android do Guitar Hero III recompilado.
//
// No Android o jogo nao e um executavel: e uma biblioteca partilhada que a
// activity do SDL carrega e onde procura SDL_main (modo XE_UI_WINDOWED_APPS_IN_LIBRARY).
// O main.cpp regista a app sob o identificador "gh3" via REX_DEFINE_APP;
// aqui vai-se buscar essa app ao registo e corre-se pelo contexto SDL, que e o
// que o windowed_app_main_sdl.cpp faz no desktop.
//
// Incluir <SDL3/SDL_main.h> faz o SDL reescrever main() para SDL_main() e
// fornecer o verdadeiro entry JNI que a activity invoca.
//
// Estrutura decalcada do skate3recomp/src/main_android.cpp -- e o mesmo SDK
// (ramo 081) e as mesmas armadilhas de arranque, todas ja pagas la.

#include <algorithm>
#include <cstdlib>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/logging.h>
#include <rex/memory/utils.h>
#include <rex/thread.h>
#include <rex/ui/windowed_app.h>
#include <rex/ui/windowed_app_context_sdl.h>

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#if defined(__ANDROID__)
#include <unistd.h>
#include <android/log.h>
// Canal de diagnostico que sobrevive a tudo: sai no logcat mesmo que o
// logging do rex ainda nao esteja de pe ou ja tenha ido abaixo.
//   adb logcat -s GH3DBG:V gh3recomp:V
#define GH3DBG(...) __android_log_print(ANDROID_LOG_INFO, "GH3DBG", __VA_ARGS__)
#else
#define GH3DBG(...) ((void)0)
#endif

int main(int argc, char** argv) {
  GH3DBG("main() entry argc=%d", argc);
#if defined(__ANDROID__)
  // O directorio de trabalho do processo no Android e /system/bin, so de
  // leitura; tudo o que escreve relativo a current_path() (logs, cvars, cache)
  // falharia la. Mudar ja para o armazenamento privado da app.
  if (const char* internal_storage = SDL_GetAndroidInternalStoragePath()) {
    (void)chdir(internal_storage);
    GH3DBG("chdir to internal_storage=%s", internal_storage);
    // GetUserFolder() (config/cache/saves/DLC) segue XDG_DATA_HOME e depois
    // $HOME/.local/share -- que no Android da /data/.local, so de leitura.
    setenv("XDG_DATA_HOME", internal_storage, 1);
  } else {
    GH3DBG("SDL_GetAndroidInternalStoragePath returned null");
  }

  // O SDK procura /sdcard/<nome> para o config e os dados do jogo; como serve
  // varios titulos, e cada jogo que da o nome da sua pasta. Tem de ser antes de
  // alguem ler o config -- GetAppRootFolder e quem o encontra.
  rex::filesystem::SetAndroidPublicFolderName("gh3");

  // Ligacao tardia dos pontos de entrada da libc/libandroid (o upstream faz
  // isto no seu proprio entry Android, que o modo-biblioteca substitui). Sem
  // isto o rex::memory nao tem ASharedMemory_create e cai em silencio num
  // memfd para a heap guest de ~4,8GB: paginas tmpfs, que nao podem ser
  // purgadas, levaram um telefone de 4GB abaixo com o sistema todo.
  rex::memory::AndroidInitialize();
  rex::thread::AndroidInitialize();
  rex::filesystem::AndroidInitialize();
  GH3DBG("Android subsystems initialized");
#endif

  auto remaining = rex::cvar::Init(argc, argv);
  rex::cvar::ApplyEnvironment();
  GH3DBG("cvar init done");
  rex::InitLoggingEarly();
  GH3DBG("InitLoggingEarly done");

  if (!SDL_Init(SDL_INIT_VIDEO)) {
    GH3DBG("SDL_Init(VIDEO) FAILED: %s", SDL_GetError());
    REXLOG_ERROR("Failed to initialize SDL video: {}", SDL_GetError());
    return EXIT_FAILURE;
  }
  GH3DBG("SDL_Init(VIDEO) ok");

  int result = EXIT_FAILURE;
  {
    // "gh3" e o IDENTIFICADOR do REX_DEFINE_APP em main.cpp (nao confundir com
    // o NOME da app, "gh3recomp", que e o que da nome ao gh3recomp.toml e a
    // pasta de logs -- esse e passado ao ReXApp em Gh3App::Create).
    rex::ui::WindowedApp::Creator creator = rex::ui::WindowedApp::GetCreator("gh3");
    if (!creator) {
      GH3DBG("GetCreator('gh3') returned null");
      REXLOG_ERROR("No windowed app registered under identifier 'gh3'");
      SDL_Quit();
      return EXIT_FAILURE;
    }
    GH3DBG("creator ok, creating app");

    rex::ui::SDLWindowedAppContext app_context;
    std::unique_ptr<rex::ui::WindowedApp> app = creator(app_context);

    const auto& option_names = app->GetPositionalOptions();
    std::map<std::string, std::string> parsed;
    size_t count = std::min(remaining.size(), option_names.size());
    for (size_t i = 0; i < count; ++i) {
      parsed[option_names[i]] = remaining[i];
    }
    app->SetParsedArguments(std::move(parsed));

    GH3DBG("calling OnInitialize");
    bool initialized = app->OnInitialize();
    GH3DBG("OnInitialize returned %d; entering main loop", initialized ? 1 : 0);
    result = initialized ? app_context.RunMainLoop() : EXIT_FAILURE;
    GH3DBG("main loop exited, result=%d", result);
    app->InvokeOnDestroy();
  }

  rex::ShutdownLogging();
  SDL_Quit();
  return result;
}
