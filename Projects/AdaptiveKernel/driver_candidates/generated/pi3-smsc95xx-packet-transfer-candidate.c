/* Aurum generated host-only smsc95xx packet-transfer candidate.
 * ZERO AUTHORITY: synthetic scalar transforms only; no USB, packet, or device I/O.
 */
#include <stdint.h>

#define AURUM_TX_FIRST 0x00002000u
#define AURUM_TX_LAST 0x00001000u
#define AURUM_TX_LEN_MASK 0x000007ffu
#define AURUM_TX_CSUM 0x00004000u
#define AURUM_RX_LEN_MASK 0x3fff0000u
#define AURUM_RX_ERROR 0x00008000u

typedef struct {
    uint32_t checksum_requested;
    uint32_t checksum_enabled;
    uint32_t software_checksum_fallback;
    uint32_t checksum_preamble;
    uint32_t tx_cmd_a;
    uint32_t tx_cmd_b;
    uint32_t usb_buffer_length;
    uint32_t framing_overhead_bytes;
} aurum_smsc95xx_tx_shadow;

typedef struct {
    uint32_t frame_length;
    uint32_t error_summary;
    uint32_t status_and_align_prefix_bytes;
    uint32_t next_frame_padding_bytes;
    uint32_t payload_length_valid;
} aurum_smsc95xx_rx_shadow;

int aurum_smsc95xx_model_tx(uint32_t frame_length,
                            uint32_t checksum_requested,
                            uint32_t checksum_start_offset,
                            uint32_t checksum_field_offset,
                            aurum_smsc95xx_tx_shadow *out) {
    uint32_t payload_after_start;
    uint32_t checksum_enabled = 0u;
    if (!out || frame_length < 1u || frame_length > AURUM_TX_LEN_MASK || checksum_requested > 1u)
        return -1;
    if (checksum_start_offset > 0xffffu || checksum_field_offset > 0xffffu ||
        checksum_start_offset + checksum_field_offset > 0xffffu)
        return -2;
    payload_after_start = frame_length >= checksum_start_offset ? frame_length - checksum_start_offset : 0u;
    if (checksum_requested && frame_length > 45u &&
        payload_after_start > 5u &&
        checksum_field_offset < payload_after_start - 5u)
        checksum_enabled = 1u;
    out->checksum_requested = checksum_requested;
    out->checksum_enabled = checksum_enabled;
    out->software_checksum_fallback = checksum_requested && !checksum_enabled;
    out->checksum_preamble = checksum_enabled
        ? ((checksum_start_offset + checksum_field_offset) << 16) | checksum_start_offset
        : 0u;
    out->tx_cmd_a = frame_length | AURUM_TX_FIRST | AURUM_TX_LAST;
    out->tx_cmd_b = frame_length;
    out->framing_overhead_bytes = 8u;
    if (checksum_enabled) {
        out->tx_cmd_a += 4u;
        out->tx_cmd_b += 4u;
        out->tx_cmd_b |= AURUM_TX_CSUM;
        out->framing_overhead_bytes += 4u;
    }
    out->usb_buffer_length = frame_length + out->framing_overhead_bytes;
    return 0;
}

int aurum_smsc95xx_decode_rx(uint32_t status_word,
                             uint32_t available_payload_bytes,
                             aurum_smsc95xx_rx_shadow *out) {
    uint32_t frame_length;
    if (!out) return -1;
    frame_length = (status_word & AURUM_RX_LEN_MASK) >> 16u;
    out->frame_length = frame_length;
    out->error_summary = (status_word & AURUM_RX_ERROR) != 0u;
    out->status_and_align_prefix_bytes = 6u;
    out->next_frame_padding_bytes = (4u -
        ((frame_length + 2u) % 4u)) %
        4u;
    out->payload_length_valid = frame_length <= available_payload_bytes;
    return 0;
}
