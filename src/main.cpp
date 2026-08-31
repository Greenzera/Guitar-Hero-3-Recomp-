// gh3 - ReXGlue Recompiled Project

// Sem prefixo de pasta de proposito: o CMake poe a pasta do codigo gerado no
// include path (generated/default no ramo 090, generated/sdk081 no 081), por
// isso o mesmo main.cpp serve os dois.
#include "gh3_init.h"

#include "gh3_app.h"

REX_DEFINE_APP(gh3, Gh3App::Create)
