// Ver gh3_framegen.hpp.
//
// Este ficheiro e' so' a fachada: decide se ha' frame gen (existe lsfg-cache?)
// e regista a implementacao. A mecanica de Vulkan/LSFG esta' em
// gh3_framegen_vk.cpp.

#include "gh3_framegen.hpp"

#include <rex/logging.h>

namespace gh3 {
namespace {
bool g_initialized = false;
}

#if defined(GH3_HAS_FRAMEGEN)

void Framegen::Init(const std::filesystem::path& cacheDir) {
  if (g_initialized) {
    return;
  }
  std::error_code ec;
  if (!std::filesystem::exists(cacheDir, ec)) {
    REXLOG_WARN("[framegen] sem lsfg-cache em {}; frame gen desligado", cacheDir.string());
    return;
  }
  // Registar apenas. O motor LSFG so' arranca quando o apresentador entregar o
  // device, ja' que e' preciso o GPU fisico dele para a memoria partilhada
  // cair no MESMO adaptador.
  RegisterFramegen(cacheDir);
  g_initialized = true;
}

void Framegen::Shutdown() {
  if (!g_initialized) {
    return;
  }
  UnregisterFramegen();
  g_initialized = false;
}

#else  // sem frame gen compilado

void Framegen::Init(const std::filesystem::path&) {}
void Framegen::Shutdown() {}

#endif

bool Framegen::IsInitialized() { return g_initialized; }

}  // namespace gh3
