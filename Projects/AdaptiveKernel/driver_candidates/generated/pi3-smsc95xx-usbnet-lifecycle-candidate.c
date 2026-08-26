/* Aurum generated host-only USBNet lifecycle candidate.
 * ZERO AUTHORITY: table lookup over synthetic state/action indexes only.
 */
#include <stdint.h>

#define AURUM_STATE_COUNT 13u
#define AURUM_ACTION_COUNT 13u

typedef struct {
    uint32_t next_state;
    uint32_t accepted;
} aurum_usbnet_transition_result;

static const uint8_t AURUM_NEXT_STATE[13][13] = {
    {2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0},
    {2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1},
    {2, 4, 2, 2, 2, 2, 2, 2, 2, 2, 3, 2, 1},
    {3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 1},
    {4, 4, 2, 8, 4, 6, 4, 5, 4, 4, 12, 4, 1},
    {5, 5, 2, 9, 5, 7, 5, 5, 4, 4, 12, 5, 1},
    {6, 6, 2, 10, 6, 6, 4, 7, 6, 4, 12, 6, 1},
    {7, 7, 2, 11, 7, 7, 5, 7, 6, 4, 12, 7, 1},
    {8, 8, 2, 8, 4, 10, 8, 9, 8, 8, 12, 8, 1},
    {9, 9, 2, 9, 5, 11, 9, 9, 8, 8, 12, 9, 1},
    {10, 10, 2, 10, 6, 10, 8, 11, 10, 8, 12, 10, 1},
    {11, 11, 2, 11, 7, 11, 9, 11, 10, 8, 12, 11, 1},
    {12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 4, 1}
};

static const uint8_t AURUM_ACCEPTED[13][13] = {
    {1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0},
    {1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0},
    {0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1},
    {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1},
    {0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 1},
    {0, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0, 1},
    {0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1},
    {0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1},
    {0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 1},
    {0, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0, 1},
    {0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1},
    {0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1},
    {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1}
};

int aurum_usbnet_transition(uint32_t state,
                            uint32_t action,
                            aurum_usbnet_transition_result *out) {
    if (!out || state >= AURUM_STATE_COUNT || action >= AURUM_ACTION_COUNT)
        return -1;
    out->next_state = AURUM_NEXT_STATE[state][action];
    out->accepted = AURUM_ACCEPTED[state][action];
    return 0;
}
