/* Shim de android/log.h para builds fora do Android (Windows/PC).
   O motor framegen so usa __android_log_print com ANDROID_LOG_INFO/WARN.
   Mapeamos para stderr; num build a serio ligaria ao logging do rexglue. */
#pragma once
#include <cstdio>
#include <cstdarg>
enum { ANDROID_LOG_INFO = 4, ANDROID_LOG_WARN = 5 };
static inline void __android_log_print(int, const char* tag, const char* fmt, ...) {
    va_list ap; va_start(ap, fmt);
    fprintf(stderr, "[%s] ", tag); vfprintf(stderr, fmt, ap); fputc('\n', stderr);
    va_end(ap);
}
