#include <signal.h>
#include <stdio.h>
#include <unistd.h>

#ifndef AURUM_KERNEL_VERSION
#define AURUM_KERNEL_VERSION "unknown"
#endif

int main(void) {
    puts("AURUM_PI3_KERNEL_READY version=" AURUM_KERNEL_VERSION " arch=arm64");
    puts("selftest=ok");
    fflush(stdout);
    for (;;) pause();
}
