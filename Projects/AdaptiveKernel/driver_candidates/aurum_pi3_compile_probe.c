// SPDX-License-Identifier: GPL-2.0-only
/*
 * Compile-only Pi 3 USB-network API surface probe.
 *
 * This is deliberately not a device driver. It has no aliases, device table,
 * bus registration, network registration, parameters, callbacks, or I/O. The
 * init routine always refuses loading. Compilation against an exact header tree
 * is the sole supported use.
 */

#include <linux/build_bug.h>
#include <linux/errno.h>
#include <linux/module.h>
#include <linux/netdevice.h>
#include <linux/skbuff.h>
#include <linux/types.h>
#include <linux/usb.h>

enum aurum_pi3_rx_shape {
	AURUM_PI3_RX_COMPLETE = 0,
	AURUM_PI3_RX_SHORT,
	AURUM_PI3_RX_OVERRUN,
};

static_assert(__same_type(((struct sk_buff *)0)->len, unsigned int));
static_assert(__same_type(((struct urb *)0)->actual_length, u32));
static_assert(__same_type(((struct urb *)0)->transfer_buffer_length, u32));
static_assert(__same_type((netdev_features_t)0, (u64)0));
static_assert(sizeof(struct usb_device_descriptor) == 18);

static __always_inline enum aurum_pi3_rx_shape
aurum_pi3_classify_rx_length(unsigned int actual, unsigned int expected)
{
	if (actual < expected)
		return AURUM_PI3_RX_SHORT;
	if (actual > expected)
		return AURUM_PI3_RX_OVERRUN;
	return AURUM_PI3_RX_COMPLETE;
}

static int __init aurum_pi3_compile_probe_init(void)
{
	return -EPERM;
}

module_init(aurum_pi3_compile_probe_init);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Aurum Pi3 inert exact-header compile-only API probe");
MODULE_INFO(aurum_mode, "compile-only");
