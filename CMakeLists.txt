# gh3 - Guitar Hero III: Legends of Rock (ReXGlue Recompiled Project)
#
# Suporta DOIS ramos do SDK, escolhidos por -DGH3_SDK=:
#
#   090 (omissao)  rexglue 0.9.0, o do projeto PES 2017.
#                  E o que arranca e chega in-game hoje.
#                  Menu de definicoes: settings_overlay (lista crua de cvars, F4).
#
#   081            ramo v0.8.1.19 que vive em skate3recomp/third_party.
#                  NAO e mais antigo, e uma arvore divergente com trabalho que o
#                  0.9.0 nao tem: simple_settings_overlay (menu estilizado,
#                  navegavel por teclado E comando), touch_controls_overlay,
#                  surface_android e o campo 'parent' na config de funcoes.
#                  Em contrapartida nao tem os overlays de achievements, e a
#                  emulacao de GPU e embutida (nao ha cvar gpu_plugin).
#
# Os dois usam os MESMOS hints em config/ -- o formato ({ end = ... }) e a
# verificacao de sobreposicoes sao identicos nos dois ramos, ja confirmado.
# So o codigo gerado difere, e por isso vive em pastas separadas.

cmake_minimum_required(VERSION 3.25)
project(gh3 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(GH3_SDK "090" CACHE STRING "Ramo do SDK: 090 (PES) ou 081 (Skate 3)")
set_property(CACHE GH3_SDK PROPERTY STRINGS 090 081)

if(GH3_SDK STREQUAL "081")
    # --- ramo Skate 3 -------------------------------------------------------
    set(REXSDK_DIR
        "C:/Users/Luis/Desktop/projeto_CLAUDE/skate3recomp/third_party/rexglue-sdk"
        CACHE PATH "Arvore do SDK rexglue")
    # Variante: "base" = jogo original, "dx" = XEX do GH3 Deluxe. Cada uma tem o
    # seu codigo gerado e o seu executavel, porque um recomp so corre o codigo
    # de que nasceu -- ver gh3_manifest.dx.toml.
    set(GH3_VARIANT "base" CACHE STRING "Variante: base ou dx")
    if(GH3_VARIANT STREQUAL "dx")
        set(GH3_GENERATED "${CMAKE_CURRENT_SOURCE_DIR}/generated/dx")
    else()
        set(GH3_GENERATED "${CMAKE_CURRENT_SOURCE_DIR}/generated/sdk081")
    endif()

    if(NOT EXISTS "${GH3_GENERATED}/sources.cmake")
        message(FATAL_ERROR
            "Falta ${GH3_GENERATED}/sources.cmake.\n"
            "Corre primeiro:\n"
            "  <skate3>/third_party/rexglue-sdk/out/win-amd64/rexglue.exe "
            "codegen gh3_manifest.sdk081.toml")
    endif()

    add_subdirectory("${REXSDK_DIR}" rexglue-sdk)

    if(ANDROID)
        # No Android o jogo nao e um executavel: e uma .so que a activity do SDL
        # carrega com System.loadLibrary e onde procura SDL_main. O
        # main_android.cpp fornece esse SDL_main e vai buscar a app registada
        # sob "gh3" ao registo de windowed apps (modo-biblioteca).
        add_library(gh3 SHARED src/main.cpp src/main_android.cpp)
    else()
        add_executable(gh3 WIN32 src/main.cpp)
    endif()

    include("${GH3_GENERATED}/sources.cmake")
    target_sources(gh3 PRIVATE ${GENERATED_SOURCES})
    target_include_directories(gh3 PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/src
        ${GH3_GENERATED})

    # rex::ui pela mesma razao do ramo 090: o configure_target compila
    # rex_app.cpp para dentro deste alvo e esse inclui imgui.h.
    target_link_libraries(gh3 PRIVATE rex::runtime rex::ui)
    rexglue_configure_target(gh3)

    if(WIN32)
        target_link_libraries(gh3 PRIVATE comdlg32 winhttp d3dcompiler gdiplus)
    endif()

    target_compile_definitions(gh3 PRIVATE GH3_SDK_081=1)

if(NOT ANDROID)
    # --- integracao com o launcher, centralizada aqui -----------------------
    # Faz-se no CMake (nao no .bat) para que QUALQUER build -- manual ou gerado
    # pelo GH3 Mod Recompiler -- fique correto e reconhecivel pelo launcher, sem
    # remendos a mao. Corre no configure; quando o build acaba, o gh3.exe e estes
    # ficheiros ja coexistem, que e o que o launcher verifica.
    if(GH3_VARIANT STREQUAL "base")
        set(GH3_SOURCE_XEX "${CMAKE_CURRENT_SOURCE_DIR}/../extracted/default.xex")
    else()
        set(GH3_SOURCE_XEX "${CMAKE_CURRENT_SOURCE_DIR}/../extracted-${GH3_VARIANT}/default.xex")
    endif()

    # Marcador de hash: e por aqui que o launcher emparelha um mod ao seu build.
    if(EXISTS "${GH3_SOURCE_XEX}")
        file(SHA256 "${GH3_SOURCE_XEX}" GH3_XEX_HASH)
        string(TOUPPER "${GH3_XEX_HASH}" GH3_XEX_HASH)
        file(WRITE "${CMAKE_BINARY_DIR}/source-xex.sha256" "${GH3_XEX_HASH}")
    else()
        message(WARNING "gh3: xex de origem nao encontrado (${GH3_SOURCE_XEX}); "
                        "o launcher nao vai reconhecer este build")
    endif()

    # --- pasta do jogo auto-suficiente ---------------------------------
    # Tudo o que e preciso para correr fica em ../game, ao lado dos dados: o
    # exe, as DLLs que ele importa e a semente das definicoes. Feito no build
    # (nao a mao) para nao ficar desatualizado a cada recompilacao -- era o que
    # aconteceria se fosse uma copia unica.
    #
    # amd_fidelityfx_dx12.dll e rexruntime.dll estao na tabela de imports do
    # exe: sem elas nem arranca. TracyClient.dll e carregada pelo runtime.
    # O executavel chama-se gh3recomp: e o nome que o jogador ve na janela,
    # no ficheiro de definicoes e no proprio .exe.
    # O que o jogador ve: nome do ficheiro, do processo no Gestor de Tarefas e
    # do atalho. O nome INTERNO da app continua "gh3recomp" -- e ele que da o
    # nome ao gh3recomp.toml e a pasta de logs, e nao convem ter espacos ai.
    set_target_properties(gh3 PROPERTIES OUTPUT_NAME "Guitar Hero 3 Recomp")

    # Icone e informacao de versao. So no Windows; noutras plataformas o .rc
    # nao significa nada.
    if(WIN32)
        target_sources(gh3 PRIVATE src/gh3recomp.rc)
    endif()

    set(GH3_GAME_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../game")
    add_custom_command(TARGET gh3 POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory "${GH3_GAME_DIR}"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different "$<TARGET_FILE:gh3>" "${GH3_GAME_DIR}/"
        COMMENT "gh3: a sincronizar a pasta do jogo")
    foreach(_dll rexruntime.dll TracyClient.dll amd_fidelityfx_dx12.dll)
        add_custom_command(TARGET gh3 POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    "${CMAKE_BINARY_DIR}/${_dll}" "${GH3_GAME_DIR}/")
    endforeach()
    add_custom_command(TARGET gh3 POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${CMAKE_BINARY_DIR}/gh3recomp.default.toml" "${GH3_GAME_DIR}/"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${CMAKE_BINARY_DIR}/source-xex.sha256" "${GH3_GAME_DIR}/")

    # gh3.default.toml: semente das definicoes. A variante base usa config/gh3.toml
    # tal e qual; qualquer variante de mod acrescenta mods_allow_xex=true, porque so
    # ela pode servir o xex do mod sem crashar (foi recompilada a partir dele).
    file(READ "${CMAKE_CURRENT_SOURCE_DIR}/config/gh3.toml" GH3_DEFAULT_TOML)
    if(NOT GH3_VARIANT STREQUAL "base")
        string(APPEND GH3_DEFAULT_TOML
            "\n# Acrescentado pelo build da variante '${GH3_VARIANT}': so uma build\n"
            "# recompilada do xex do mod pode servi-lo. Ver o launcher.\n"
            "mods_allow_xex = true\n")
    endif()
    file(WRITE "${CMAKE_BINARY_DIR}/gh3recomp.default.toml" "${GH3_DEFAULT_TOML}")
else()
    # --- Android ------------------------------------------------------------
    # Nada disto se aplica: nao ha pasta do jogo ao lado do exe (os dados vao
    # para /sdcard/gh3/game), nao ha DLLs para copiar (tudo sao .so empacotadas
    # na APK) e o launcher do Windows nao existe. O que E preciso e que o
    # ficheiro saia como libgh3.so -- por isso NAO se mexe no OUTPUT_NAME.
    #
    # A semente das definicoes e gerada na mesma, para se empurrar com os dados:
    #   adb push out/build/android-arm64/gh3recomp.default.toml /sdcard/gh3/
    file(READ "${CMAKE_CURRENT_SOURCE_DIR}/config/gh3.android.toml" GH3_ANDROID_TOML)
    file(WRITE "${CMAKE_BINARY_DIR}/gh3recomp.default.toml" "${GH3_ANDROID_TOML}")
endif()

else()
    # --- ramo 0.9.0 (o que funciona hoje) -----------------------------------
    include(generated/rexglue.cmake)

    add_executable(gh3 WIN32 src/main.cpp)

    # GPU_PLUGINS: o 0.9.0 tirou a emulacao de GPU do runtime e po-la num plugin
    # carregavel. Sem colocar o rexgpu-xenos ao lado do exe, todas as chamadas
    # de kernel Vd* sao ignoradas ("no GPU emulation loaded"), o ring buffer do
    # jogo nunca inicializa e rebenta num assert interno. Escolhido em runtime
    # pelo cvar gpu_plugin. (Diagnosticado no PES 2017 com este mesmo SDK.)
    rexglue_setup_target(gh3 GPU_PLUGINS xenos)

    # Lacuna do SDK 0.9.0: rexglue_configure_target() compila src/ui/rex_app.cpp
    # e windowed_app_main_sdl.cpp para dentro deste alvo, e esses incluem
    # imgui.h -- mas rexglue_setup_target() so liga rex::runtime, que nao
    # depende de rexui. Como o imgui e PUBLIC em rexui, ligar aqui fornece o
    # include path. Sem isto o build falha com "'imgui.h' file not found".
    target_link_libraries(gh3 PRIVATE rex::ui)

    target_compile_definitions(gh3 PRIVATE GH3_SDK_090=1)
endif()

message(STATUS "gh3: ramo do SDK = ${GH3_SDK}, variante = ${GH3_VARIANT}")
