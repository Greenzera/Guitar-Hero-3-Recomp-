# Guitar Hero III recompilado — Android

Port do `gh3recomp` para Android. Corre o **mesmo código recompilado** que a
build de PC: os 75 ficheiros em `generated/sdk081` são C++ portável com `simde`
(que vira NEON no ARM e SSE no x86), por isso **não há codegen específico de
Android** — quem já correu o `1-CODEGEN.bat` não repete nada.

**Estado (22/08/2026): JOGÁVEL.** Arranca em ~7 s, menus, Quickplay, e
**gameplay a sério** — autoestrada de notas, banda animada, rock meter, star
power — a 26–37 FPS no BlueStacks. O único defeito conhecido é que os vídeos
Bink saem pretos (ver *O que falta*).

---

## Como está feito

No Android o jogo não é um executável: é uma `.so` que a activity do SDL carrega
e onde procura `SDL_main`. Três peças novas:

| Peça | Onde | O que faz |
|---|---|---|
| `src/main_android.cpp` | novo | `SDL_main`: prepara o ambiente Android e corre a app registada sob `"gh3"` |
| `add_library(gh3 SHARED …)` | `CMakeLists.txt` | ramo `if(ANDROID)`; no desktop continua `add_executable` |
| `android/` | novo | projeto Gradle que só **empacota** as `.so` (não compila nada nativo) |

Tudo o resto — Vulkan, fibers, memória guest, overlay de toque — já vinha do
ramo **081** do SDK, partilhado com o `skate3recomp`, onde essas armadilhas já
foram pagas. O ramo **090 não serve**: pôs a emulação de GPU numa DLL
(`gpu_plugin`), que no Android não existe.

## Build

```bat
build-android.bat install
```

Compila as duas ABIs, empacota a APK, instala e arranca. Variantes: sem
argumento fica pela APK; `arm64` / `x86_64` para uma ABI só; `apk` para
reempacotar sem recompilar.

O build usa `-j 4` de propósito: são 8 GB de RAM e os ficheiros gerados são
gordos; com mais paralelismo o clang fica sem memória a meio. Cada ABI leva
~25 min de raiz.

### Duas ABIs numa só APK — e porquê

`arm64-v8a` **e** `x86_64`. O Android escolhe a nativa do aparelho: arm64 no
telemóvel, x86_64 no emulador. Isto não é conveniência, é necessidade:

> Num emulador x86 a `.so` arm64 corre através do tradutor **Houdini**. O
> rexglue depende de apanhar `SIGSEGV` para as suas guardas de memória do guest,
> mas o handler lê o `ucontext` como ARM64 enquanto o kernel entrega o do x86
> real — a falha nunca é tratada e o processo morre.

Medido no BlueStacks: a mesma build, mesmos dados, mesma configuração —
**arm64/Houdini morre em 16 s** com `SIGSEGV` numa `XThread` (o backtrace cai
sempre dentro de `libhoudini.so`, com endereços de falha diferentes a cada
arranque); **x86_64 nativo corre 3 minutos sem falhar**. Um telemóvel a sério
corre a arm64 nativa e não tem este problema.

### Tracy tem de ficar OFF

`REXGLUE_ENABLE_TRACY=OFF` nos dois presets. Com Tracy ligado a thread
"Tracy Symbol Worker" faz `SIGABRT` no arranque em x86_64 Android. Também poupa
uma `.so` de 5 MB e a sobrecarga do profiler, que aqui não serve para nada.

## Os dados do jogo

Ficam numa pasta **pública**, `/sdcard/gh3/game` — a única onde o utilizador os
consegue pôr sem root, e o `/sdcard/Android/data` está fechado ao `adb push`
desde o Android 11. São ~3,7 GB:

```bash
adb shell mkdir -p /sdcard/gh3/game/DATA
adb push game/default.xex /sdcard/gh3/game/
adb push game/DATA/COMPRESSED /sdcard/gh3/game/DATA/
adb push game/DATA/MUSIC     /sdcard/gh3/game/DATA/
adb push game/DATA/MOVIES    /sdcard/gh3/game/DATA/
adb push game/DATA/STREAMS   /sdcard/gh3/game/DATA/
adb push game/DATA/FXFILES   /sdcard/gh3/game/DATA/
adb push game/DATA/ANIMS     /sdcard/gh3/game/DATA/
adb push game/DATA/MEMCARD   /sdcard/gh3/game/DATA/
adb push game/DATA/SCRIPTS   /sdcard/gh3/game/DATA/
adb push game/DLCs           /sdcard/gh3/game/
```

Não empurrar `DATA/_originais-antes-da-traducao` — é a cópia de segurança da
tradução, não serve ao jogo. `MODS`, `userdata` e `$SYSTEMUPDATE` também não são
precisos.

**Não tirar ficheiros da pasta `MOVIES`.** Faltar um vídeo dá *"Disc Read
Error — There's been an issue reading content from the game disc"* e o jogo
congela nessa caixa. Ou está lá tudo, ou (para diagnóstico) a pasta inteira
desaparece — o jogo tolera não haver `MOVIES` de todo até ao momento em que o
modo de atracção quer um vídeo.

A pasta `/sdcard/gh3` é também a **raiz da app**: é lá que fica o
`gh3recomp.toml`. Semeia-se dele o ficheiro que o build gera:

```bash
adb push out/build/android-arm64/gh3recomp.default.toml /sdcard/gh3/
```

Ler ficheiros dessa pasta precisa da permissão de armazenamento. O
`build-android.bat install` concede-a por adb; à mão, o Android 11+ pede
"Acesso a todos os ficheiros" (a app abre as Definições sozinha e fecha-se).

## Controlos

O overlay de toque do SDK (`touch_controls_overlay`) aparece sozinho no Android:
desenha um comando na tela e alimenta um **gamepad virtual SDL3**, que o driver
de input normal apanha como se fosse um comando a sério. Uma guitarra USB ou
Bluetooth entra pelo mesmo caminho, sem configuração.

O botão **ESC** do overlay abre o menu de definições do rexglue (tema dourado do
GH3, navegável por toque) — confirmado a funcionar.

O `mnk_mode` (teclado-como-comando) está **desligado**: não há teclado e,
ligado, ele captura e esconde o cursor.

## Definições forçadas para GPU móvel

Em dois sítios de propósito: `config/gh3.android.toml` (semente do ficheiro do
utilizador) e no `AndroidManifest.xml` como `SDL_ENV.REX_*` — a variável de
ambiente ganha ao ficheiro, e o ficheiro em `/sdcard` é do utilizador, pode não
existir ou estar velho.

Duas que interessam mesmo:

```toml
async_shader_compilation = false          # senão: ecrã preto permanente
vulkan_async_skip_incomplete_frames = false
draw_resolution_scale_x = 1               # senão: parser da GPU lê lixo
draw_resolution_scale_y = 1
```

**Os shaders.** Com compilação assíncrona os frames desenham com pipelines de
substituição e o presenter descarta-os. Numa GPU móvel a compilação é lenta o
suficiente para que praticamente *todos* os frames sejam descartados — preto
permanente com o jogo a correr por trás. (Custou uma sessão no port do Skate 3.)

**A escala de rasterização.** O valor de fábrica do rexglue é 2x, o que num
telemóvel é renderizar 2560x1440 para mostrar 1280x720. Pior: com 2x, o parser
de pacotes da GPU acabava sempre por ler lixo do ring buffer indireto — ora
`ExecutePacketType0 overflow`, ora `Unimplemented GPU OPCODE: 0x1F` — e a thread
da GPU morria, congelando a imagem no último frame. Com 1x desapareceu.
*Atenção: no Skate 3 NÃO se pode fazer isto* (o renderer nativo dele classifica
os passes a suprimir pelo pitch da superfície, e os limiares assumem o 2x); o
GH3 não tem renderer nativo.

**O nível de log também é uma definição de desempenho.** Com `log_level="debug"`
o logcat leva uma linha por PRESENT e várias por buffer de áudio, e o jogo
rebentava ao fim de ~80 s; em `"info"` passou a chegar ao ecrã do título.

## O que falta: os vídeos Bink saem pretos

O único defeito conhecido. Os vídeos Bink (`DATA/MOVIES/BIK/*.bik.xen`)
reproduzem-se — o jogo abre os ficheiros, avança e chega ao fim deles — mas o
que aparece no ecrã é preto.

**Isto engana, e enganou-me durante horas.** Se ninguém tocar no ecrã, o GH3
entra em modo de atracção e fica a repetir vídeos **para sempre**. Resultado: um
jogo deixado quieto mostra preto indefinidamente e parece congelado, quando na
verdade está a correr a 60 FPS e a passar de vídeo em vídeo. Basta carregar num
botão para saltar o vídeo e aparece o ecrã "PRESS ANY BUTTON TO ROCK", depois os
menus, tudo perfeitamente visível.

**Não tirar os ficheiros de vídeo para contornar isto.** Faltar um único vídeo dá
*"Disc Read Error"* e congela o jogo — testado, e não chega remover só os dois de
introdução, porque o `loading_flying.bik.xen` é o ecrã de carregamento do menu.

Hipóteses já eliminadas, para não se repetir o trabalho:
- **Rampa de gama** — é escrita uma só vez no arranque, com valores normais
  (topo=1023). Não escurece.
- **`mprotect` a falhar** (limite de VMAs do Android, `vm.max_map_count=65530`,
  que as guardas de escrita da memória do guest poderiam esgotar por partirem um
  VMA por página) — instrumentei o retorno, que o código ignora: **zero falhas**.
- **Resolves a deixarem de chegar ao frontbuffer** — o perfil de GPU por frame
  (draws, texturas, resolves) é *igual* nos casos visível e preto.
- **Conteúdo do frontbuffer em memória do guest** — está sempre a zeros, mesmo
  quando a imagem aparece. A apresentação vem de uma textura do lado do host, por
  isso este sinal não serve para nada.

Pista que fica por seguir: a build de PC que funciona usa **D3D12**, esta usa
**Vulkan**. Forçar Vulkan na build de Windows (`gpu_backend`) e ver se os vídeos
também saem pretos lá. Se saírem, o bug é do backend Vulkan e não do Android — e
passa a ser depurável no PC, com um ciclo muito mais rápido.

## Como chegar ao jogo

1. Abrir a app e **carregar num botão do overlay** logo a seguir ao ecrã do
   título (o `=` é Start, o verde é A). Salta os vídeos de introdução.
2. "PRESS ANY BUTTON TO ROCK" → outro toque → menu principal.
3. Baixo, baixo → **QUICKPLAY** → A.
4. Dificuldade → A → setlist → A → A → e entra na música.

Sem tocar em nada fica no modo de atracção, ou seja, preto.

## Diagnóstico

```bash
adb logcat -s gh3recomp:V GH3DBG:V
```

`GH3DBG` é o canal cru do `main_android.cpp` (`__android_log_print`): sai mesmo
que o logging do rex ainda não esteja de pé. O log em ficheiro fica no
armazenamento privado da app, em `logs/`.

Para ligar categorias específicas sem afogar o resto, o toml aceita:

```toml
[log.levels]
fs = "debug"
krnl = "debug"
```

`adb screencap` **captura** a surface Vulkan neste port (ao contrário do que
acontecia no Skate 3), por isso serve para confirmar o que está no ecrã.

## Alterações no SDK partilhado

O SDK em `skate3recomp/third_party/rexglue-sdk` é partilhado com o Skate 3, por
isso as alterações são aditivas e o comportamento dele fica igual:

- **`rex::filesystem::SetAndroidPublicFolderName(name)`** (novo, em
  `filesystem.h` / `filesystem_posix.cpp`). O `GetAppRootFolder()` no Android
  tinha `/sdcard/skate3` escrito à mão; agora é o entry point de cada jogo que
  nomeia a sua pasta. O `main_android.cpp` do Skate 3 passou a chamá-la com
  `"skate3"`.
- **`REXGLUE_ANDROID_LOG_TAG`** (nova variável de CMake, omissão `"rexglue"`).
  A tag do logcat estava fixa em `"skate3"`. Tem de ser em tempo de compilação:
  o logging inicializa-se na **inicialização estática** (o primeiro registo de
  cvar já escreve no log), muito antes de qualquer entry point poder mudá-la —
  tentei primeiro um setter em runtime e ficou provado que nunca pega.
- **`libucontext` segue a ABI** (`thirdparty/CMakeLists.txt`). Estava a compilar
  as fontes aarch64 sempre; num alvo x86_64 rebenta logo no primeiro
  `str x0, [...]`. Agora escolhe a pasta de arquitectura a partir de
  `CMAKE_ANDROID_ARCH_ABI`.
- **Nome do comando virtual** passou de `"Skate 3 Touch Controls"` para
  `"Touch Controls"` (`touch_controls_overlay.cpp`).
