// gh3_framegen — a ponte entre o Guitar Hero III e o motor LSFG (frame gen).
//
// O motor corre num VkDevice próprio; a partilha com o device do apresentador
// é por memória externa (HANDLEs opacos Win32). A mecânica toda vive em
// gh3_framegen_vk.cpp, atrás da interface rex::graphics::framegen::IFramegen —
// o apresentador do SDK só vê VkImage do device dele.
//
// Só faz alguma coisa se a pasta lsfg-cache existir (compilado sob
// GH3_HAS_FRAMEGEN). Sem ela, todas as funções aqui são no-ops.

#pragma once

#include <filesystem>

namespace gh3 {

class Framegen {
 public:
  // cacheDir = pasta com os lsfg_<id>.spv extraídos do Lossless.dll.
  // Inicializa o motor. Loga sucesso/falha; não lança (frame gen é opcional).
  static void Init(const std::filesystem::path& cacheDir);

  // Liberta o motor. Seguro chamar mesmo sem Init.
  static void Shutdown();

  static bool IsInitialized();
};

// Regista a implementação de frame gen junto do apresentador do SDK. Tem de
// correr ANTES da configuração da apresentação, porque é aí que o apresentador
// entrega o device. Sem lsfg-cache, é no-op.
void RegisterFramegen(const std::filesystem::path& cache_dir);
void UnregisterFramegen();

}  // namespace gh3
