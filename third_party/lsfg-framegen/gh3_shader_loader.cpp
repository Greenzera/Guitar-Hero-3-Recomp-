// Ver gh3_shader_loader.hpp.
//
// A tabela nome->id-logico e a formula vêm do shader_registry.cpp do lsfg-vk;
// o patch do generate idem. Validados contra o Lossless Scaling 3.2.2.

#include "gh3_shader_loader.hpp"

#include <array>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <span>
#include <unordered_map>

namespace gh3::lsfg {
namespace {

// A formula do lsfg-vk (shader_registry.cpp).
constexpr int32_t BASE_OFFSET = 49;
constexpr int32_t OFFSET_PERF = 23;
constexpr int32_t OFFSET_FP32 = 49;

// nome-base -> id logico. Os arrays (alpha/beta/gamma/delta) indexam por [i].
// Extraido do registry: mipmaps=255, generate=256, e os grupos abaixo.
int32_t LogicalId(const std::string& base, int index) {
  static const std::unordered_map<std::string, int32_t> kSingles = {
      {"mipmaps", 255}, {"generate", 256}};
  static const std::array<int32_t, 4> kAlpha = {267, 268, 269, 270};
  static const std::array<int32_t, 5> kBeta = {275, 276, 277, 278, 279};
  static const std::array<int32_t, 5> kGamma = {257, 259, 260, 261, 262};
  static const std::array<int32_t, 10> kDelta = {257, 263, 264, 265, 266,
                                                 258, 271, 272, 273, 274};
  if (auto it = kSingles.find(base); it != kSingles.end())
    return it->second;
  if (base == "alpha" && index >= 0 && index < int(kAlpha.size()))
    return kAlpha[size_t(index)];
  if (base == "beta" && index >= 0 && index < int(kBeta.size()))
    return kBeta[size_t(index)];
  if (base == "gamma" && index >= 0 && index < int(kGamma.size()))
    return kGamma[size_t(index)];
  if (base == "delta" && index >= 0 && index < int(kDelta.size()))
    return kDelta[size_t(index)];
  return -1;
}

// Parte "p_alpha[3]" em (perf=true, base="alpha", index=3).
// "p_generate" -> (perf=true, base="generate", index=-1).
struct ParsedName {
  bool valid = false;
  bool perf = false;
  std::string base;
  int index = -1;
};

ParsedName ParseName(const std::string& name) {
  ParsedName p;
  std::string s = name;
  if (s.rfind("p_", 0) == 0) {  // performance variant
    p.perf = true;
    s = s.substr(2);
  }
  const auto lb = s.find('[');
  if (lb == std::string::npos) {
    p.base = s;
    p.index = -1;
  } else {
    const auto rb = s.find(']', lb);
    if (rb == std::string::npos)
      return p;  // invalido
    p.base = s.substr(0, lb);
    p.index = std::atoi(s.substr(lb + 1, rb - lb - 1).c_str());
  }
  p.valid = true;
  return p;
}

// v3.1p (performance) usa precisao reduzida (fp16). A formula distingue por
// fp16; para o caminho perf o palpite validado e fp16=true (os resource-ids
// resultantes existem todos no DLL). Se um driver reclamar, e' o primeiro sitio
// a experimentar fp16=false.
bool UsesFp16(bool perf) { return perf; }

// Patch do shader generate: remove a capability StorageImageWriteWithoutFormat
// (troca por Shader) e fixa o formato das storage images (RGBA16f no HDR,
// RGBA8 caso contrario). Copiado da logica de patchGenerateShader do lsfg-vk.
void PatchGenerate(std::vector<uint8_t>& data, bool hdr) {
  if (data.size() < 20 || data.size() % 4 != 0)
    return;
  std::span<uint32_t> words(reinterpret_cast<uint32_t*>(data.data()),
                            data.size() / sizeof(uint32_t));
  constexpr uint16_t kOpCapability = 17;
  constexpr uint16_t kOpTypeImage = 25;
  constexpr uint32_t kCapWriteWithoutFormat = 56;
  constexpr uint32_t kCapShader = 1;
  constexpr uint32_t kFmtRgba16f = 2;
  constexpr uint32_t kFmtRgba8 = 4;
  for (size_t i = 5; i < words.size();) {
    const uint32_t word = words[i];
    const uint16_t wc = uint16_t(word >> 16);
    const uint16_t op = uint16_t(word & 0xFFFF);
    if (op == kOpCapability && wc >= 2 && i + 1 < words.size()) {
      if (words[i + 1] == kCapWriteWithoutFormat)
        words[i + 1] = kCapShader;
    }
    if (op == kOpTypeImage && wc >= 9 && i + 8 < words.size()) {
      if (words[i + 7] == 2)  // storage image
        words[i + 8] = hdr ? kFmtRgba16f : kFmtRgba8;
    }
    i += wc ? wc : 1;
  }
}

std::vector<uint8_t> ReadFile(const std::filesystem::path& p) {
  std::ifstream f(p, std::ios::binary | std::ios::ate);
  if (!f)
    return {};
  const auto n = f.tellg();
  std::vector<uint8_t> buf(static_cast<size_t>(n), 0u);
  f.seekg(0);
  f.read(reinterpret_cast<char*>(buf.data()), n);
  return buf;
}

}  // namespace

int32_t ResolveResourceId(const std::string& name) {
  const ParsedName p = ParseName(name);
  if (!p.valid)
    return -1;
  const int32_t id = LogicalId(p.base, p.index);
  if (id < 0)
    return -1;
  const bool fp16 = UsesFp16(p.perf);
  return BASE_OFFSET + id + (p.perf ? OFFSET_PERF : 0) + (fp16 ? 0 : OFFSET_FP32);
}

std::function<std::vector<uint8_t>(const std::string&)>
MakeShaderLoader(const std::filesystem::path& cacheDir, bool hdr) {
  return [cacheDir, hdr](const std::string& name) -> std::vector<uint8_t> {
    const int32_t res = ResolveResourceId(name);
    if (res < 0) {
      fprintf(stderr, "[gh3-lsfg] nome de shader desconhecido: %s\n", name.c_str());
      return {};
    }
    char fn[32];
    std::snprintf(fn, sizeof(fn), "lsfg_%d.spv", res);
    std::vector<uint8_t> spirv = ReadFile(cacheDir / fn);
    if (spirv.empty()) {
      fprintf(stderr, "[gh3-lsfg] falta %s (para %s) em %s\n", fn, name.c_str(),
              cacheDir.string().c_str());
      return {};
    }
    // O generate precisa do patch de formato.
    if (name == "generate" || name == "p_generate")
      PatchGenerate(spirv, hdr);
    return spirv;
  };
}

}  // namespace gh3::lsfg
