// SPDX-License-Identifier: GPL-2.0-only
/*
 * Aurum Pi3 smsc95xx kernel-shaped shadow candidate.
 *
 * This is deliberately not a usable driver. It translates the already sealed
 * nonbinding LAN9514/smsc95xx semantics onto Linux kernel-native types so the
 * candidate can be compiled against the exact running Pi3 kernel interface.
 * There is no device table, alias, driver/netdev registration, callback table,
 * URB submission, control/bulk transfer, register access, DMA, firmware path,
 * sysfs path, network mutation, or successful module-load path. init is a hard
 * -EPERM boundary; compile-only verification is the sole supported use.
 */

#include <linux/build_bug.h>
#include <linux/errno.h>
#include <linux/module.h>
#include <linux/netdevice.h>
#include <linux/skbuff.h>
#include <linux/types.h>
#include <linux/usb.h>

#define AURUM_PARENT_VID 0x0424u
#define AURUM_PARENT_PID 0x9514u
#define AURUM_USB_VID 0x0424u
#define AURUM_USB_PID 0xec00u
#define AURUM_TX_OVERHEAD 8u
#define AURUM_TX_OVERHEAD_CSUM 12u

struct aurum_smsc95xx_shadow_state {
	bool identity_verified;
	bool carrier;
	u32 speed_mbps;
	bool full_duplex;
	bool rx_checksum_enabled;
};

static_assert(__same_type(((struct sk_buff *)0)->len, unsigned int));
static_assert(__same_type(((struct urb *)0)->actual_length, u32));
static_assert(__same_type(((struct urb *)0)->transfer_buffer_length, u32));
static_assert(__same_type((netdev_features_t)0, (u64)0));
static_assert(sizeof(struct usb_device_descriptor) == 18);
static_assert(sizeof(struct usb_ctrlrequest) == 8);

static __always_inline int
aurum_smsc95xx_init(struct aurum_smsc95xx_shadow_state *state,
		    u16 parent_vid, u16 parent_pid,
		    u16 usb_vid, u16 usb_pid)
{
	if (!state)
		return -EINVAL;
	if (parent_vid != AURUM_PARENT_VID || parent_pid != AURUM_PARENT_PID ||
	    usb_vid != AURUM_USB_VID || usb_pid != AURUM_USB_PID)
		return -ENODEV;
	state->identity_verified = true;
	state->carrier = false;
	state->speed_mbps = 0;
	state->full_duplex = false;
	state->rx_checksum_enabled = true;
	return 0;
}

static __always_inline int
aurum_smsc95xx_set_link(struct aurum_smsc95xx_shadow_state *state,
			bool carrier, u32 speed_mbps, bool full_duplex)
{
	if (!state || !state->identity_verified)
		return -EINVAL;
	if (!carrier) {
		state->carrier = false;
		state->speed_mbps = 0;
		state->full_duplex = false;
		return 0;
	}
	if (speed_mbps != 10u && speed_mbps != 100u)
		return -ERANGE;
	state->carrier = true;
	state->speed_mbps = speed_mbps;
	state->full_duplex = full_duplex;
	return 0;
}

static __always_inline int
aurum_smsc95xx_set_rx_checksum(struct aurum_smsc95xx_shadow_state *state,
			       bool enabled)
{
	if (!state || !state->identity_verified)
		return -EINVAL;
	state->rx_checksum_enabled = enabled;
	return 0;
}

static __always_inline size_t
aurum_smsc95xx_tx_frame_len(const struct aurum_smsc95xx_shadow_state *state,
			    size_t payload_len, bool checksum_partial)
{
	if (!state || !state->identity_verified || !state->carrier)
		return 0;
	return payload_len +
		(checksum_partial ? AURUM_TX_OVERHEAD_CSUM : AURUM_TX_OVERHEAD);
}

/* Compile all pure shadow helpers without giving them any runtime caller. */
static __maybe_unused int aurum_smsc95xx_compile_shape(void)
{
	struct aurum_smsc95xx_shadow_state state = { 0 };
	size_t framed;
	int rc;

	rc = aurum_smsc95xx_init(&state, AURUM_PARENT_VID, AURUM_PARENT_PID,
				 AURUM_USB_VID, AURUM_USB_PID);
	if (rc)
		return rc;
	rc = aurum_smsc95xx_set_link(&state, true, 100u, true);
	if (rc)
		return rc;
	rc = aurum_smsc95xx_set_rx_checksum(&state, true);
	if (rc)
		return rc;
	framed = aurum_smsc95xx_tx_frame_len(&state, 1500u, false);
	return framed == 1508u ? 0 : -EINVAL;
}

static int __init aurum_pi3_smsc95xx_kernel_shadow_init(void)
{
	return -EPERM;
}

module_init(aurum_pi3_smsc95xx_kernel_shadow_init);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Aurum Pi3 smsc95xx inert kernel-shaped compile-only shadow");
MODULE_INFO(aurum_mode, "kernel-shadow-compile-only");
