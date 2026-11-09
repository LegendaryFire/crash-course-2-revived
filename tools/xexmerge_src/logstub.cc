#include <cstdio>
#include <cstdarg>
extern "C" void xenia_log(const char* fmt, ...) {
  va_list a; va_start(a, fmt); vfprintf(stderr, fmt, a); va_end(a);
  fputc('\n', stderr);
}
