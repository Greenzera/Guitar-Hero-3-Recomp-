// gh3 - Guitar Hero III: Legends of Rock (ReXGlue Recompiled Project)
//
// Ver rex_app.h para a lista completa de hooks virtuais.

#pragma once

#include <filesystem>
#include <memory>
#include <string>
#include <system_error>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/rex_app.h>
#include <rex/ui/keybinds.h>



#if defined(__ANDROID__)
#include <SDL3/SDL_system.h>
#endif

#if defined(GH3_SDK_081)
#include <rex/input/input_system.h>
#include <rex/runtime.h>
#include <rex/ui/overlay/simple_settings_overlay.h>
#include <rex/ui/window.h>
#endif

class Gh3App : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    // O nome do simbolo muda entre ramos do SDK: o codegen 0.8.x emite-o
    // prefixado com o nome do projeto (gh3_PPCImageConfig), o 0.9.0 emite-o sem
    // prefixo. O mesmo tropeco esta documentado no pes17_app.h do PES 2017.
    // Confirma em generated/<pasta>/gh3_init.h se voltares a mudar de ramo.
#if defined(GH3_SDK_081)
    return std::unique_ptr<Gh3App>(new Gh3App(ctx, "gh3recomp", gh3_PPCImageConfig));
#else
    return std::unique_ptr<Gh3App>(new Gh3App(ctx, "gh3recomp", PPCImageConfig));
#endif
  }

  // O titulo da janela nao leva o carimbo do SDK.
  //
  // Por omissao o ReXApp devolve "<nome> <versao do rexglue>", e a janela
  // ficava "gh3recomp [rexglue-v0.8.2.95-dev.gcdc6ca6-Release]" -- ruido de
  // build a mostra para quem so quer jogar. A versao continua no log, que e
  // onde faz falta.
  std::string GetWindowTitle() const override { return "Guitar Hero 3 Recomp"; }

  // --- Onde ficam as definicoes -------------------------------------------
  //
  // Em gh3recomp.toml, ao lado do executavel, dentro da pasta do jogo. Tudo o
  // que e preciso para jogar vive nessa pasta -- dados, DLCs, mods, definicoes.
  //
  // Ja estiveram em Documentos, porque o build escrevia por cima do ficheiro
  // que ficava junto ao exe e apagava as definicoes em silencio. Isso deixou de
  // ser um risco: o build copia para la a SEMENTE (gh3recomp.default.toml,
  // gerada a partir de config/gh3.toml) e nunca o ficheiro do jogador.
  //
  // Corre ANTES do LoadConfig (ver rex_app.cpp: OnConfigurePaths -> config_path_
  // -> LoadConfig), por isso o ficheiro semeado aqui ja e lido neste arranque.
  void OnConfigurePaths(rex::PathConfig& paths) override {
    // O config fica AO LADO do executavel, na pasta do jogo -- e o primeiro
    // sitio onde alguem o procura, e nao ha que andar as voltas no Documentos.
    //
    // Antes era desviado para a pasta de dados do utilizador porque o build
    // escrevia por cima do gh3.toml que estava junto ao exe. Isso deixou de
    // acontecer: o build so' copia a SEMENTE (gh3recomp.default.toml), nunca o
    // ficheiro do jogador.
    std::error_code ec;
    const auto seed = paths.config_path.parent_path() / "gh3recomp.default.toml";
    if (!std::filesystem::exists(paths.config_path, ec) &&
        std::filesystem::exists(seed, ec)) {
      std::filesystem::copy_file(seed, paths.config_path, ec);
      if (ec) {
        // Nao e fatal: sem ficheiro do utilizador ficam os valores compilados.
        REXLOG_WARN("Nao consegui semear {} a partir de {}: {}",
                    paths.config_path.string(), seed.string(), ec.message());
      }
    }
#if defined(__ANDROID__)
    // No Android nao ha "pasta do exe": o processo e o zygote e o executavel
    // esta em /system/bin. O GetAppRootFolder do SDK ja devolve /sdcard/gh3
    // (ver SetAndroidPublicFolderName em main_android.cpp), por isso o config
    // acima ja apontou para la; falta so a raiz dos dados, que fica ao lado.
    //
    // Publica de proposito: e a unica pasta onde o utilizador consegue largar
    // os 3,9 GB do jogo sem root ("adb push", gestor de ficheiros, cabo). O
    // /sdcard/Android/data e bloqueado ao adb push a partir do Android 11.
    if (paths.game_data_root.empty()) {
      std::error_code aec;
      for (const char* pub : {"/storage/emulated/0/gh3/game", "/sdcard/gh3/game"}) {
        if (std::filesystem::exists(std::filesystem::path(pub) / "default.xex", aec)) {
          paths.game_data_root = pub;
          break;
        }
      }
      // Recurso: a pasta externa da propria app, que funciona onde o push para
      // Android/data ainda e permitido (emuladores, Android <= 10).
      if (paths.game_data_root.empty()) {
        if (const char* external = SDL_GetAndroidExternalStoragePath()) {
          paths.game_data_root = std::filesystem::path(external) / "game";
        }
      }
    }
    REXLOG_INFO("Android: config={} game_data_root={}", paths.config_path.string(),
                paths.game_data_root.string());
#endif

    settings_path_ = paths.config_path;
    game_root_ = paths.game_data_root;

    // DLCs numa pasta "DLCs" ao lado dos dados do jogo, em vez do caminho por
    // perfil content/<xuid>/<title>/<tipo>/ que ninguem adivinha. So define o
    // padrao: quem ja tiver dlc_root no config ou na linha de comando mantem-no.
    if (rex::cvar::GetFlagByName("dlc_root").empty()) {
      const auto dlc_dir = game_root_ / "DLCs";
      std::filesystem::create_directories(dlc_dir, ec);
      rex::cvar::SetFlagByName("dlc_root", dlc_dir.string());
    }
  }



 private:
  // Raiz dos dados do jogo, guardada em OnConfigurePaths.
  std::filesystem::path game_root_;

  // Onde o menu grava as definicoes: o mesmo ficheiro que o arranque leu.
  std::filesystem::path settings_path_;

 public:
  void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override {
    (void)drawer;

#if defined(GH3_SDK_081)
    // --- Menu de definicoes estilizado -------------------------------------
    // O simple_settings_overlay deste ramo e navegavel por teclado, comando E
    // rato, e ao abrir repoe o cursor -- por isso aqui NAO e preciso o atalho
    // de libertar o rato que o ramo 090 exige.
    //
    // Escape recua nivel a nivel (linhas -> barra de categorias -> fechado),
    // como no Skate 3. F1 abre e fecha directamente.
    rex::ui::RegisterBind("bind_gh3_menu", "Escape", "Menu de definicoes", [this] {
      if (settings_ && settings_->visible()) {
        settings_->NavigateBack();
      } else {
        ToggleSettings();
      }
    });
    rex::ui::RegisterBind("bind_gh3_menu_alt", "F1", "Menu de definicoes (alternativa)",
                          [this] { ToggleSettings(); });
#else
    // --- ramo 090: libertar o rato -----------------------------------------
    // O driver de teclado (mnk_mode) usa o rato como stick direito: enquanto
    // estiver ligado, esconde o cursor, captura-o e recentra-o a cada frame
    // (mnk_input_driver.cpp, UpdateMouseCapture). O menu F4 deste ramo e
    // so-rato, por isso com o teclado ligado abre mas nao da para clicar.
    //
    // O SDK tem o mecanismo certo (InputSystem::SetActiveCallback) mas neste
    // ramo nao o liga a ninguem, e nem o InputSystem concreto nem o contexto
    // ImGui sao alcancaveis a partir da app. No ramo 081 isto esta resolvido de
    // origem; aqui fica um atalho explicito.
    //
    // Alternativa sem tecla nenhuma: consola (Backtick) -> "mnk_mode false".
    rex::ui::RegisterBind(
        "bind_toggle_keyboard", "F9",
        "Liga/desliga o teclado-como-comando (desligado = rato livre para o menu F4)",
        [] {
          const bool on = rex::cvar::GetFlagByName("mnk_mode") == "true";
          rex::cvar::SetFlagByName("mnk_mode", on ? "false" : "true");
          REXLOG_INFO("mnk_mode -> {} ({})", on ? "false" : "true",
                      on ? "rato libertado" : "teclado a controlar o jogo");
        });
#endif
  }

#if defined(GH3_SDK_081)
 private:
  void ToggleSettings() {
    if (!settings_) {
      settings_ = std::make_unique<rex::ui::SimpleSettingsDialog>(
          imgui_drawer(), config_path_for_settings(), MakeLoadProfiles(),
          MakeSaveProfile(), MakeCloseSettings(), MakeCloseGame(),
          MakeRestartGame(), MakePollGamepad());
    }
    if (settings_->visible()) {
      settings_->Hide();
      SetCursorVisible(false);
    } else {
      SetCursorVisible(true);
      settings_->Show();
    }
  }

  std::filesystem::path config_path_for_settings() const { return settings_path_; }

  void SetCursorVisible(bool visible) {
    if (!window())
      return;
    window()->SetCursorVisibility(visible ? rex::ui::Window::CursorVisibility::kVisible
                                          : rex::ui::Window::CursorVisibility::kAutoHidden);
  }

  // Perfis: STUB deliberado. O menu tem uma aba "Profile" desenhada para os
  // perfis Xbox Live que o Skate 3 usa; o GH3 guarda o progresso nos seus
  // proprios saves e nao ha nada equivalente para mostrar aqui. Devolver uma
  // lista vazia deixa a aba inerte em vez de fingir que faz alguma coisa.
  static rex::ui::SimpleSettingsDialog::LoadProfilesCallback MakeLoadProfiles() {
    return []() { return rex::ui::SimpleProfileState{}; };
  }
  static rex::ui::SimpleSettingsDialog::SaveProfileCallback MakeSaveProfile() {
    return [](int, std::string, bool) {};
  }

  rex::ui::SimpleSettingsDialog::CloseSettingsCallback MakeCloseSettings() {
    return [this]() { SetCursorVisible(false); };
  }

  rex::ui::SimpleSettingsDialog::CloseGameCallback MakeCloseGame() {
    return [this]() {
      app_context().CallInUIThreadDeferred([this]() {
        if (window()) {
          window()->RequestClose();
        } else {
          app_context().QuitFromUIThread();
        }
      });
    };
  }

  rex::ui::SimpleSettingsDialog::RestartGameCallback MakeRestartGame() {
    // Sem reinicio por agora: relancar o processo implica replicar a linha de
    // comando (--game_data_root e o resto) e ainda nao vale a pena. O botao
    // fica sem efeito em vez de fazer algo a meio.
    return []() { REXLOG_INFO("Reiniciar: nao implementado no gh3"); };
  }

  // Leitura crua do comando para navegar o menu. Passa ao lado do gate
  // is_active, que zera o input virado ao jogo enquanto o menu esta aberto --
  // sem isto o menu abria e nao reagia a nada.
  rex::ui::SimpleSettingsDialog::PollGamepadCallback MakePollGamepad() {
    return [this]() {
      rex::ui::SimpleSettingsGamepad pad;
      // O dialogo pode ser pintado (e portanto sondar) num frame que apanhe o
      // runtime ja em derrube, ao fechar o jogo.
      auto* rt = runtime();
      auto* input =
          rt ? static_cast<rex::input::InputSystem*>(rt->input_system()) : nullptr;
      if (input) {
        rex::input::X_INPUT_GAMEPAD state;
        if (input->GetUiGamepadState(&state)) {
          pad.connected = true;
          pad.buttons = state.buttons;
          pad.thumb_lx = state.thumb_lx;
          pad.thumb_ly = state.thumb_ly;
        }
      }
      return pad;
    };
  }

  std::unique_ptr<rex::ui::SimpleSettingsDialog> settings_;
#endif

  // Outros hooks disponiveis:
  // void OnPostInitLogging() override {}
  // void OnPreSetup(rex::RuntimeConfig& config) override {}
  // void OnLoadXexImage(std::string& xex_image) override {}
  // void OnPostSetup() override {}
  // void OnShutdown() override {}
};
