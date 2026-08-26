/* Aurum generated host-only smsc95xx register/interrupt candidate.
 * ZERO AUTHORITY: synthetic integer decode only; no device I/O or register writes.
 */
#include <stdint.h>

#define AURUM_KNOWN_STATUS_MASK 0x0007ffffu
#define AURUM_KNOWN_ENDPOINT_MASK 0x000bffffu
#define AURUM_W1C_STATUS_MASK 0x00077800u
#define AURUM_READ_ONLY_STATUS_MASK 0x000087ffu

typedef struct {
    uint32_t active_mask;
    uint32_t endpoint_reportable_mask;
    uint32_t read_only_mask;
    uint32_t w1c_ack_mask;
    uint32_t unknown_status_bits;
    uint32_t unknown_endpoint_bits;
} aurum_smsc95xx_interrupt_decode;

int aurum_smsc95xx_decode_interrupts(uint32_t int_status,
                                     uint32_t int_ep_ctl,
                                     aurum_smsc95xx_interrupt_decode *out) {
    if (!out) return -1;
    out->active_mask = int_status & AURUM_KNOWN_STATUS_MASK;
    out->endpoint_reportable_mask = 0u;
    if ((int_status & 0x00040000u) && (int_ep_ctl & 0x00080000u)) out->endpoint_reportable_mask |= 0x00040000u;
    if ((int_status & 0x00020000u) && (int_ep_ctl & 0x00020000u)) out->endpoint_reportable_mask |= 0x00020000u;
    if ((int_status & 0x00010000u) && (int_ep_ctl & 0x00010000u)) out->endpoint_reportable_mask |= 0x00010000u;
    if ((int_status & 0x00008000u) && (int_ep_ctl & 0x00008000u)) out->endpoint_reportable_mask |= 0x00008000u;
    if ((int_status & 0x00004000u) && (int_ep_ctl & 0x00004000u)) out->endpoint_reportable_mask |= 0x00004000u;
    if ((int_status & 0x00002000u) && (int_ep_ctl & 0x00002000u)) out->endpoint_reportable_mask |= 0x00002000u;
    if ((int_status & 0x00001000u) && (int_ep_ctl & 0x00001000u)) out->endpoint_reportable_mask |= 0x00001000u;
    if ((int_status & 0x00000800u) && (int_ep_ctl & 0x00000800u)) out->endpoint_reportable_mask |= 0x00000800u;
    if ((int_status & 0x000007ffu) && (int_ep_ctl & 0x000007ffu)) out->endpoint_reportable_mask |= 0x000007ffu;
    out->read_only_mask = int_status & AURUM_READ_ONLY_STATUS_MASK;
    out->w1c_ack_mask = int_status & AURUM_W1C_STATUS_MASK;
    out->unknown_status_bits = int_status & ~AURUM_KNOWN_STATUS_MASK;
    out->unknown_endpoint_bits = int_ep_ctl & ~AURUM_KNOWN_ENDPOINT_MASK;
    return 0;
}
