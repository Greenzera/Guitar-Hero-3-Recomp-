// Implementacao de frame generation do gh3 sobre o motor LSFG.
//
// O LSFG corre num VkDevice PROPRIO. A partilha e' portanto por memoria
// externa: aqui criam-se imagens no device do apresentador, exportam-se como
// HANDLEs opacos Win32, e o LSFG importa-as do lado dele. O apresentador so'
// ve' VkImage do seu proprio device -- toda a mecanica de partilha fica deste
// lado da fronteira.

#include "gh3_framegen.hpp"

#if defined(GH3_HAS_FRAMEGEN)

#define VK_USE_PLATFORM_WIN32_KHR
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
// vulkan_win32.h nao se basta a si proprio: conta com windows.h (HANDLE,
// HINSTANCE) e vulkan_core.h ja incluidos. vulkan.h puxa ambos os lados
// Vulkan quando VK_USE_PLATFORM_WIN32_KHR esta definido.
#include <windows.h>
#include <vulkan/vulkan.h>

#include <rex/graphics/native_framegen.h>
#include <rex/logging.h>

#include <array>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <type_traits>
#include <utility>
#include <vector>

#include "gh3_shader_loader.hpp"
#include "lsfg_3_1p.hpp"

namespace gh3 {
namespace {

using rex::graphics::framegen::DeviceInfo;

// Formato das imagens partilhadas. O swapchain e' B8G8R8A8_UNORM, que raramente
// suporta STORAGE em NVIDIA; os shaders do LSFG escrevem por storage image, por
// isso as partilhadas sao RGBA8 e o apresentador faz blit com conversao de
// componentes (vkCmdBlitImage converte por componente de cor, nao por bytes).
constexpr VkFormat kSharedFormat = VK_FORMAT_R8G8B8A8_UNORM;

// Um semaforo binario nao pode ser assinalado outra vez enquanto a espera
// anterior nao tiver executado -- e o apresentador nao tem como saber quando
// isso acontece do outro lado da fronteira. Dai um anel: cada frame usa um
// semaforo diferente, e so se volta ao mesmo passadas kSemaphoreRing rondas,
// muito depois de a espera correspondente ter corrido. Reutilizar um unico
// semaforo trava o jogo ao fim de poucos frames.
constexpr size_t kSemaphoreRing = 4;

// x2. Manter em 1 ate o caminho de apresentacao estar afinado.
constexpr size_t kGenerationCount = 1;

class LsfgFramegen final : public rex::graphics::framegen::IFramegen {
 public:
  explicit LsfgFramegen(std::filesystem::path cache_dir) : cache_dir_(std::move(cache_dir)) {}

  bool Initialize(const DeviceInfo& info) override {
    info_ = info;

    // Nomeia a entrada em falta: sem isso resta adivinhar qual das oito nao
    // resolveu, e a causa habitual (extensao nao ativada no device) fica
    // indistinguivel de um driver antigo.
    const char* missing = nullptr;
    auto load = [&](auto& pfn, const char* name) {
      pfn = reinterpret_cast<std::remove_reference_t<decltype(pfn)>>(
          info.get_device_proc_addr(info.device, name));
      if (pfn == nullptr && missing == nullptr) {
        missing = name;
      }
      return pfn != nullptr;
    };
    const bool all_loaded =
        load(fn_.create_image, "vkCreateImage") & load(fn_.destroy_image, "vkDestroyImage") &
        load(fn_.get_image_memory_requirements, "vkGetImageMemoryRequirements") &
        load(fn_.allocate_memory, "vkAllocateMemory") & load(fn_.free_memory, "vkFreeMemory") &
        load(fn_.bind_image_memory, "vkBindImageMemory") &
        load(fn_.device_wait_idle, "vkDeviceWaitIdle") &
        load(fn_.get_memory_win32_handle, "vkGetMemoryWin32HandleKHR") &
        load(fn_.create_semaphore, "vkCreateSemaphore") &
        load(fn_.destroy_semaphore, "vkDestroySemaphore") &
        load(fn_.get_semaphore_win32_handle, "vkGetSemaphoreWin32HandleKHR");
    if (!all_loaded) {
      REXLOG_WARN(
          "[framegen] o device do apresentador nao expoe {}; frame gen desligado "
          "(a extensao correspondente nao foi ativada na criacao do device?)",
          missing ? missing : "uma entrada necessaria");
      return false;
    }

    auto get_mem_props = reinterpret_cast<PFN_vkGetPhysicalDeviceMemoryProperties>(
        info.get_instance_proc_addr(info.instance, "vkGetPhysicalDeviceMemoryProperties"));
    auto get_props = reinterpret_cast<PFN_vkGetPhysicalDeviceProperties>(
        info.get_instance_proc_addr(info.instance, "vkGetPhysicalDeviceProperties"));
    if (!get_mem_props || !get_props) {
      REXLOG_WARN("[framegen] nao consegui consultar as propriedades do device");
      return false;
    }
    get_mem_props(info.physical_device, &mem_props_);

    // O LSFG escolhe o device fisico por vendorID<<32|deviceID. O sentinela
    // "qualquer device" apanharia o primeiro enumerado, que num portatil pode
    // ser a iGPU -- e a memoria partilhada tem de estar no MESMO GPU.
    VkPhysicalDeviceProperties props{};
    get_props(info.physical_device, &props);
    const uint64_t device_id = (static_cast<uint64_t>(props.vendorID) << 32) | props.deviceID;

    try {
      LSFG_3_1P::initialize(device_id, /*isHdr=*/false, /*flowScale=*/1.0F, kGenerationCount,
                            gh3::lsfg::MakeShaderLoader(cache_dir_, false));
    } catch (const std::exception& e) {
      REXLOG_WARN("[framegen] motor LSFG nao inicializou: {}", e.what());
      return false;
    }
    engine_ready_ = true;
    REXLOG_INFO("[framegen] motor LSFG ligado ao GPU {} (vendor {:#06x} device {:#06x})",
                props.deviceName, props.vendorID, props.deviceID);
    return true;
  }

  uint32_t Configure(VkExtent2D extent, VkFormat /*format*/) override {
    if (!engine_ready_) {
      return 0;
    }
    if (context_valid_ && extent.width == extent_.width && extent.height == extent_.height) {
      return uint32_t(kGenerationCount);
    }

    ReleaseContext();
    extent_ = extent;

    // Entradas: destino de blit vindo do swapchain, e lidas pelos shaders.
    for (auto& image : inputs_) {
      if (!CreateShared(image, VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT |
                                   VK_IMAGE_USAGE_STORAGE_BIT)) {
        ReleaseContext();
        return 0;
      }
    }
    // Saidas: escritas pelos shaders, lidas de volta para o swapchain.
    for (auto& image : outputs_) {
      if (!CreateShared(image, VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_SAMPLED_BIT |
                                   VK_IMAGE_USAGE_STORAGE_BIT)) {
        ReleaseContext();
        return 0;
      }
    }

    for (auto& semaphore : capture_complete_) {
      if (!CreateSharedSemaphore(semaphore)) {
        ReleaseContext();
        return 0;
      }
    }
    for (auto& slot : generated_ready_) {
      for (auto& semaphore : slot) {
        if (!CreateSharedSemaphore(semaphore)) {
          ReleaseContext();
          return 0;
        }
      }
    }

    std::vector<void*> out_handles;
    out_handles.reserve(outputs_.size());
    for (const auto& image : outputs_) {
      out_handles.push_back(image.handle);
    }

    try {
      context_ = LSFG_3_1P::createContextFromWin32(inputs_[0].handle, inputs_[1].handle,
                                                   out_handles, extent_, kSharedFormat);
    } catch (const std::exception& e) {
      REXLOG_WARN("[framegen] o LSFG rejeitou as imagens partilhadas: {}", e.what());
      ReleaseContext();
      return 0;
    }
    context_valid_ = true;
    frames_seen_ = 0;
    REXLOG_INFO("[framegen] contexto criado a {}x{}; {} frame(s) gerado(s) por frame real",
                extent_.width, extent_.height, kGenerationCount);
    return uint32_t(kGenerationCount);
  }

  VkImage GetInputImage(uint64_t frame_index) override {
    if (!context_valid_) {
      return VK_NULL_HANDLE;
    }
    // O LSFG alterna qual das duas entradas considera a MAIS RECENTE conforme a
    // paridade do contador interno dele, que conta despachos -- e o despacho d
    // acontece depois da captura d+1 (a primeira captura so enche o historico).
    // Dai o +1: sem ele as duas sequencias ficam desfasadas em um e a
    // interpolacao correria com os frames trocados, andando para tras no tempo.
    last_input_slot_ = (frame_index + 1) % inputs_.size();
    return inputs_[last_input_slot_].image;
  }

  uint32_t Generate(uint64_t /*frame_index*/) override {
    if (!context_valid_) {
      return 0;
    }
    // A interpolacao precisa de dois frames reais; o primeiro so preenche o
    // historico.
    if (++frames_seen_ < 2) {
      return 0;
    }

    try {
      // Nada de esperas do lado do CPU: entrega-se o trabalho e volta-se logo.
      // O gerador espera no GPU pelo semaforo da captura, e o apresentador
      // espera no GPU pelos de saida antes de ler as imagens. Foi a versao
      // anterior, que sincronizava com dois vkDeviceWaitIdle, que custava os
      // ~15 ms por frame medidos.
      // frames_seen_ ja foi incrementado acima, por isso a ronda deste frame
      // e a anterior -- a mesma que o apresentador viu ao pedir o semaforo de
      // captura, antes de chamar Generate.
      const size_t slot = (frames_seen_ - 1) % kSemaphoreRing;

      // Handle estavel, exportado uma vez. Exportar um novo a cada frame foi
      // tentado e piorou -- trava ainda mais cedo.
      std::vector<void*> out_semaphores;
      out_semaphores.reserve(generated_ready_[slot].size());
      for (const auto& semaphore : generated_ready_[slot]) {
        out_semaphores.push_back(semaphore.handle);
      }
      LSFG_3_1P::presentContextWin32(context_, capture_complete_[slot].handle, out_semaphores);
    } catch (const std::exception& e) {
      REXLOG_WARN("[framegen] geracao falhou, desligando: {}", e.what());
      ReleaseContext();
      return 0;
    }
    return uint32_t(outputs_.size());
  }

  VkImage GetGeneratedImage(uint32_t index) override {
    if (!context_valid_ || index >= outputs_.size()) {
      return VK_NULL_HANDLE;
    }
    // Diagnostico (GH3_FRAMEGEN_DEBUG_PRESENT_INPUT=1): devolve o frame real
    // recem-capturado em vez do interpolado. Separa duas causas de tremura que
    // de fora parecem iguais -- se com isto a imagem estabilizar, a captura e o
    // caminho de apresentacao estao bons e o problema esta no que o LSFG
    // devolve; se tremer na mesma, o problema esta antes disso.
    static const bool present_input =
        std::getenv("GH3_FRAMEGEN_DEBUG_PRESENT_INPUT") != nullptr;
    if (present_input) {
      return inputs_[last_input_slot_].image;
    }
    return outputs_[index].image;
  }

  VkSemaphore GetCaptureCompleteSemaphore() override {
    // Nulo enquanto a proxima Generate nao for despachar: a primeira captura so
    // enche o historico. Um semaforo binario assinalado sem ninguem a esperar
    // fica assinalado e estraga o frame seguinte, por isso o apresentador tem
    // de saber nao o assinalar de todo.
    if (!context_valid_ || frames_seen_ < 1) {
      return VK_NULL_HANDLE;
    }
    // Chamado ANTES de Generate, portanto frames_seen_ ainda e o desta ronda.
    return capture_complete_[frames_seen_ % kSemaphoreRing].semaphore;
  }

  VkSemaphore GetGeneratedReadySemaphore(uint32_t index) override {
    if (!context_valid_ || index >= kGenerationCount || frames_seen_ < 1) {
      return VK_NULL_HANDLE;
    }
    // LIMITACAO CONHECIDA. Fazer o apresentador esperar neste semaforo e o
    // correto -- garante que so lemos a imagem depois de o gerador a acabar --
    // mas neste driver prende o GPU do host ao fim de umas centenas de frames:
    // o jogo deixa de produzir frames e fica parado. Medido e isolado: sem esta
    // espera corre indefinidamente, com ela trava sempre.
    //
    // Por isso fica desligada por omissao. O custo e uma corrida: o
    // apresentador pode ler a imagem gerada enquanto ela ainda esta a ser
    // escrita, o que aparece como tremura ocasional. GH3_FRAMEGEN_CROSS_WAIT=1
    // volta a liga-la, para quem quiser retomar o problema.
    //
    // A solucao provavel nao e esta primitiva: semaforos binarios entre dois
    // devices sao fragil demais aqui. O caminho a tentar a seguir e' um
    // semaforo timeline, que nao tem o problema de "assinalar duas vezes sem
    // espera pelo meio" e e' o mecanismo pensado para isto.
    static const bool cross_wait = std::getenv("GH3_FRAMEGEN_CROSS_WAIT") != nullptr;
    if (!cross_wait) {
      return VK_NULL_HANDLE;
    }
    // Chamado DEPOIS de Generate, que ja incrementou frames_seen_: recua-se um
    // para cair na mesma ronda que a captura deste frame usou.
    const size_t slot = (frames_seen_ - 1) % kSemaphoreRing;
    return generated_ready_[slot][index].semaphore;
  }

  void Shutdown() override {
    ReleaseContext();
    if (engine_ready_) {
      try {
        LSFG_3_1P::finalize();
      } catch (const std::exception& e) {
        REXLOG_WARN("[framegen] falha ao finalizar o motor: {}", e.what());
      }
      engine_ready_ = false;
    }
  }

 private:
  struct SharedImage {
    VkImage image = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    void* handle = nullptr;  // HANDLE Win32, propriedade desta classe
  };

  struct Functions {
    PFN_vkCreateImage create_image = nullptr;
    PFN_vkDestroyImage destroy_image = nullptr;
    PFN_vkGetImageMemoryRequirements get_image_memory_requirements = nullptr;
    PFN_vkAllocateMemory allocate_memory = nullptr;
    PFN_vkFreeMemory free_memory = nullptr;
    PFN_vkBindImageMemory bind_image_memory = nullptr;
    PFN_vkDeviceWaitIdle device_wait_idle = nullptr;
    PFN_vkGetMemoryWin32HandleKHR get_memory_win32_handle = nullptr;
    PFN_vkCreateSemaphore create_semaphore = nullptr;
    PFN_vkDestroySemaphore destroy_semaphore = nullptr;
    PFN_vkGetSemaphoreWin32HandleKHR get_semaphore_win32_handle = nullptr;
  };

  // Semaforo do device do apresentador, exportado para o do gerador. E o que
  // permite aos dois GPUs ordenarem-se sem o CPU bloquear.
  struct SharedSemaphore {
    VkSemaphore semaphore = VK_NULL_HANDLE;
    void* handle = nullptr;
  };

  bool CreateShared(SharedImage& out, VkImageUsageFlags usage) {
    VkExternalMemoryImageCreateInfo external_info{};
    external_info.sType = VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO;
    external_info.handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_WIN32_BIT;

    VkImageCreateInfo image_info{};
    image_info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    image_info.pNext = &external_info;
    image_info.imageType = VK_IMAGE_TYPE_2D;
    image_info.format = kSharedFormat;
    image_info.extent = {extent_.width, extent_.height, 1};
    image_info.mipLevels = 1;
    image_info.arrayLayers = 1;
    image_info.samples = VK_SAMPLE_COUNT_1_BIT;
    image_info.tiling = VK_IMAGE_TILING_OPTIMAL;
    image_info.usage = usage;
    image_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    image_info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    if (fn_.create_image(info_.device, &image_info, nullptr, &out.image) != VK_SUCCESS) {
      REXLOG_WARN("[framegen] nao consegui criar a imagem partilhada");
      return false;
    }

    VkMemoryRequirements requirements{};
    fn_.get_image_memory_requirements(info_.device, out.image, &requirements);
    uint32_t memory_type = UINT32_MAX;
    for (uint32_t i = 0; i < mem_props_.memoryTypeCount; ++i) {
      const bool allowed = (requirements.memoryTypeBits & (1u << i)) != 0;
      const bool device_local =
          (mem_props_.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) != 0;
      if (allowed && device_local) {
        memory_type = i;
        break;
      }
    }
    if (memory_type == UINT32_MAX) {
      REXLOG_WARN("[framegen] sem tipo de memoria device-local compativel");
      return false;
    }

    // NVIDIA prefere alocacao dedicada para imagens externas.
    VkMemoryDedicatedAllocateInfo dedicated_info{};
    dedicated_info.sType = VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO;
    dedicated_info.image = out.image;

    VkExportMemoryAllocateInfo export_info{};
    export_info.sType = VK_STRUCTURE_TYPE_EXPORT_MEMORY_ALLOCATE_INFO;
    export_info.pNext = &dedicated_info;
    export_info.handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_WIN32_BIT;

    VkMemoryAllocateInfo allocate_info{};
    allocate_info.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    allocate_info.pNext = &export_info;
    allocate_info.allocationSize = requirements.size;
    allocate_info.memoryTypeIndex = memory_type;
    if (fn_.allocate_memory(info_.device, &allocate_info, nullptr, &out.memory) != VK_SUCCESS) {
      REXLOG_WARN("[framegen] nao consegui alocar memoria exportavel");
      return false;
    }
    if (fn_.bind_image_memory(info_.device, out.image, out.memory, 0) != VK_SUCCESS) {
      REXLOG_WARN("[framegen] nao consegui ligar a memoria a imagem");
      return false;
    }

    VkMemoryGetWin32HandleInfoKHR handle_info{};
    handle_info.sType = VK_STRUCTURE_TYPE_MEMORY_GET_WIN32_HANDLE_INFO_KHR;
    handle_info.memory = out.memory;
    handle_info.handleType = VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_WIN32_BIT;
    HANDLE handle = nullptr;
    if (fn_.get_memory_win32_handle(info_.device, &handle_info, &handle) != VK_SUCCESS ||
        handle == nullptr) {
      REXLOG_WARN("[framegen] a exportacao do HANDLE falhou");
      return false;
    }
    out.handle = handle;
    return true;
  }

  bool CreateSharedSemaphore(SharedSemaphore& out) {
    VkExportSemaphoreCreateInfo export_info{};
    export_info.sType = VK_STRUCTURE_TYPE_EXPORT_SEMAPHORE_CREATE_INFO;
    export_info.handleTypes = VK_EXTERNAL_SEMAPHORE_HANDLE_TYPE_OPAQUE_WIN32_BIT;

    VkSemaphoreCreateInfo semaphore_info{};
    semaphore_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
    semaphore_info.pNext = &export_info;
    if (fn_.create_semaphore(info_.device, &semaphore_info, nullptr, &out.semaphore) !=
        VK_SUCCESS) {
      REXLOG_WARN("[framegen] nao consegui criar o semaforo partilhado");
      return false;
    }

    VkSemaphoreGetWin32HandleInfoKHR handle_info{};
    handle_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_GET_WIN32_HANDLE_INFO_KHR;
    handle_info.semaphore = out.semaphore;
    handle_info.handleType = VK_EXTERNAL_SEMAPHORE_HANDLE_TYPE_OPAQUE_WIN32_BIT;
    HANDLE handle = nullptr;
    if (fn_.get_semaphore_win32_handle(info_.device, &handle_info, &handle) != VK_SUCCESS ||
        handle == nullptr) {
      REXLOG_WARN("[framegen] a exportacao do HANDLE do semaforo falhou");
      return false;
    }
    out.handle = handle;
    return true;
  }

  // Novo HANDLE para a mesma payload. Quem chama fica dono e tem de o fechar.
  void* ExportSemaphoreHandle(VkSemaphore semaphore) {
    if (semaphore == VK_NULL_HANDLE) {
      return nullptr;
    }
    VkSemaphoreGetWin32HandleInfoKHR handle_info{};
    handle_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_GET_WIN32_HANDLE_INFO_KHR;
    handle_info.semaphore = semaphore;
    handle_info.handleType = VK_EXTERNAL_SEMAPHORE_HANDLE_TYPE_OPAQUE_WIN32_BIT;
    HANDLE handle = nullptr;
    if (fn_.get_semaphore_win32_handle(info_.device, &handle_info, &handle) != VK_SUCCESS) {
      return nullptr;
    }
    return handle;
  }

  void DestroySharedSemaphore(SharedSemaphore& semaphore) {
    if (semaphore.semaphore != VK_NULL_HANDLE) {
      fn_.destroy_semaphore(info_.device, semaphore.semaphore, nullptr);
    }
    if (semaphore.handle != nullptr) {
      CloseHandle(static_cast<HANDLE>(semaphore.handle));
    }
    semaphore = SharedSemaphore{};
  }

  void DestroyShared(SharedImage& image) {
    if (image.image != VK_NULL_HANDLE) {
      fn_.destroy_image(info_.device, image.image, nullptr);
    }
    if (image.memory != VK_NULL_HANDLE) {
      fn_.free_memory(info_.device, image.memory, nullptr);
    }
    if (image.handle != nullptr) {
      CloseHandle(static_cast<HANDLE>(image.handle));
    }
    image = SharedImage{};
  }

  void ReleaseContext() {
    if (context_valid_) {
      try {
        LSFG_3_1P::deleteContext(context_);
      } catch (const std::exception& e) {
        REXLOG_WARN("[framegen] falha ao libertar o contexto: {}", e.what());
      }
      context_valid_ = false;
    }
    if (info_.device != VK_NULL_HANDLE && fn_.device_wait_idle != nullptr) {
      fn_.device_wait_idle(info_.device);
    }
    for (auto& image : inputs_) {
      DestroyShared(image);
    }
    for (auto& image : outputs_) {
      DestroyShared(image);
    }
    for (auto& semaphore : capture_complete_) {
      DestroySharedSemaphore(semaphore);
    }
    for (auto& slot : generated_ready_) {
      for (auto& semaphore : slot) {
        DestroySharedSemaphore(semaphore);
      }
    }
    frames_seen_ = 0;
  }

  std::filesystem::path cache_dir_;
  DeviceInfo info_{};
  Functions fn_{};
  VkPhysicalDeviceMemoryProperties mem_props_{};
  VkExtent2D extent_{};
  std::array<SharedImage, 2> inputs_{};
  std::array<SharedImage, kGenerationCount> outputs_{};
  std::array<SharedSemaphore, kSemaphoreRing> capture_complete_{};
  std::array<std::array<SharedSemaphore, kGenerationCount>, kSemaphoreRing> generated_ready_{};
  int32_t context_ = 0;
  bool context_valid_ = false;
  bool engine_ready_ = false;
  uint64_t frames_seen_ = 0;
  size_t last_input_slot_ = 0;
};

LsfgFramegen* g_framegen = nullptr;

}  // namespace

void RegisterFramegen(const std::filesystem::path& cache_dir) {
  if (g_framegen != nullptr) {
    return;
  }
  g_framegen = new LsfgFramegen(cache_dir);
  rex::graphics::framegen::SetFramegen(g_framegen);
  REXLOG_INFO("[framegen] registado; shaders de {}", cache_dir.string());
}

void UnregisterFramegen() {
  rex::graphics::framegen::SetFramegen(nullptr);
  if (g_framegen != nullptr) {
    g_framegen->Shutdown();
    delete g_framegen;
    g_framegen = nullptr;
  }
}

}  // namespace gh3

#endif  // GH3_HAS_FRAMEGEN
