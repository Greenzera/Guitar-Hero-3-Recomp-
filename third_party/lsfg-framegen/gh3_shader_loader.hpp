// gh3_shader_loader — o loader de shaders LSFG para o Guitar Hero III.
//
// O motor framegen (lsfg-vk-android) pede shaders por nome ("p_alpha[0]",
// "p_generate", ...) atraves de um callback passado a initialize(). Este loader
// implementa esse callback: mapeia o nome -> id logico -> resource-id do DLL ->
// le o .spv ja extraido de lsfg-cache/.
//
// PORQUE a formula e nao a tabela: o Lossless Scaling remapeia os resource-ids
// entre versoes. A tabela fixa do lsfg-vk-android e de uma versao antiga e nao
// bate no DLL 3.2.2 do utilizador (shaders em 303-400). O lsfg-vk (GPL) usa uma
// FORMULA que se adapta, validada contra o DLL 3.2.2:
//     resource = 49 + id_logico + (perf ? 23 : 0) + (fp16 ? 0 : 49)
// cobre 96/98 dos shaders, 0 em falta.
//
// O shader "generate" precisa de um patch (remover a capability
// StorageImageWriteWithoutFormat e fixar o formato da storage image), senao
// alguns drivers recusam-no. Ver PatchGenerateShader.

#pragma once

#include <cstdint>
#include <filesystem>
#include <functional>
#include <string>
#include <vector>

namespace gh3::lsfg {

// Devolve o callback que o framegen espera em initialize(...):
//   std::function<std::vector<uint8_t>(const std::string& name)>
// cacheDir e a pasta com os lsfg_<id>.spv extraidos do Lossless.dll.
// hdr controla o patch do shader generate (RGBA16f vs RGBA8).
std::function<std::vector<uint8_t>(const std::string&)>
MakeShaderLoader(const std::filesystem::path& cacheDir, bool hdr);

// Mapeamento nome -> resource-id, exposto para testes/diagnostico.
// Devolve -1 se o nome for desconhecido.
int32_t ResolveResourceId(const std::string& name);

}  // namespace gh3::lsfg
