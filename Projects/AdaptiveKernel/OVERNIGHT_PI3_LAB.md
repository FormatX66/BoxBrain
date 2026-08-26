# Pi 3 Adaptive Kernel overnight laboratory

This laboratory runs for at most 330 minutes inside GitHub's six-hour job
ceiling. It targets only the pinned experimental Raspberry Pi 3 and requires a
fresh hash verification of the preserved rollback image before reversible
kernel or driver mutation is allowed.

The stages are time-ordered and monotonic:

1. `observe` — identity, reference driver, power, thermal, memory, load, disk,
   and network evidence.
2. `userspace-adaptation` — short kernel-tunable candidates, each protected by
   a Pi-local systemd rollback timer and restored after measurement.
3. `virtual-driver` — temporary `dummy` driver lifecycle canary, with timed
   local removal.
4. `exact-header-module` — build/load/unload a harmless custom module only when
   the exact running-kernel header tree and compiler are already present.
5. `smsc95xx-feature-canary` — late offload-feature toggle on the proven USB
   Ethernet driver, only when `ethtool`, passwordless authority, and a Pi-local
   timed restore are all available.
6. `adaptive-runtime-pressure-canary` — a self-expiring four-core pressure
   workload supplies a meaningfully different live evidence window to the
   Generation-3-capable governor. If the sealed result recommends change, the
   executor may briefly apply only the already-proven dirty-page sysctl mapping.
   A Pi-local timer is armed first; exact original values are then restored and
   verified. Temperature, throttle, Ethernet, and driver gates are polled every
   two seconds during pressure, independently of the slower governor evidence
   samples. Network-prefetch metadata is never executed.

A held prerequisite is an expected semantic state, not a reason to improvise a
less safe mutation. The workflow never installs a replacement kernel or writes
firmware or boot configuration. Its best honest success claim is a
generation-1 reversible adaptive runtime plus any independently proven driver
canaries. A trial boot of a new kernel remains a separate Guardian transition.

Hardware and kernel references:

- [Raspberry Pi 3 Model B revision 1.2 reduced schematic](https://pip.raspberrypi.com/documents/RP-008340-DS)
- [Official Raspberry Pi hardware documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
- [Raspberry Pi Linux `smsc95xx` source](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/net/usb/smsc95xx.c)
- [Linux device-tree overlay notes](https://docs.kernel.org/devicetree/overlay-notes.html)
- [Linux livepatch module ELF requirements](https://docs.kernel.org/livepatch/module-elf-format.html)
