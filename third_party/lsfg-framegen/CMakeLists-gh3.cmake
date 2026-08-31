# Compila o motor LSFG (v3.1p perf) como static lib para o gh3.
# Incluir do CMakeLists do 081 com: include(third_party/lsfg-framegen/CMakeLists-gh3.cmake)
# Requer o volk e os headers Vulkan do rexglue no include path.
#
# Verificado 2026-08-18: 25 objs, 0 erros, clang Windows/x64. Deps Android
# resolvidas por compat/android/log.h e forward-decl do AHardwareBuffer.
file(GLOB LSFG_FG_SRC
    "${CMAKE_CURRENT_LIST_DIR}/src/common/*.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/src/config/*.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/src/core/*.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/src/pool/*.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/src/*.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/v3.1p_src/core/*.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/v3.1p_src/pool/*.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/v3.1p_src/shaders/*.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/v3.1p_src/utils/*.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/v3.1p_src/*.cpp")
add_library(lsfg-framegen STATIC ${LSFG_FG_SRC})
set_target_properties(lsfg-framegen PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_compile_definitions(lsfg-framegen PRIVATE VK_USE_PLATFORM_WIN32_KHR)
target_include_directories(lsfg-framegen PUBLIC
    "${CMAKE_CURRENT_LIST_DIR}/include"
    "${CMAKE_CURRENT_LIST_DIR}/public"
    "${CMAKE_CURRENT_LIST_DIR}/compat"
    "${CMAKE_CURRENT_LIST_DIR}/v3.1p_include"
    "${REXSDK_DIR}/thirdparty/vulkan-headers/include"
    "${REXSDK_DIR}/thirdparty/volk")
