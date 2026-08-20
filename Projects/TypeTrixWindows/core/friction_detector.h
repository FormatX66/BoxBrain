#pragma once

#include <cstdint>
#include <deque>
#include <string>
#include <vector>

namespace typetrix {

enum class EventType {
    Input,
    Backspace,
    DeleteKey,
    Navigation,
    SuggestionShown,
    SuggestionAccepted,
    SuggestionRejected,
    SuggestionUndone,
};

struct EditEvent {
    EventType type{EventType::Input};
    std::uint64_t timestamp_ms{0};

    // Ephemeral current-token snapshot when the integration surface permits it.
    // The core does not persist this outside its short rolling window.
    std::string token_snapshot;
};

struct FrictionSignal {
    double confidence{0.0};
    bool prepare_candidates{false};
    bool show_candidates{false};
    std::vector<std::string> reasons;
};

class FrictionDetector {
public:
    FrictionSignal observe(const EditEvent& event);
    void reset();

private:
    std::deque<EditEvent> events_;
    std::uint64_t last_active_ms_{0};

    void prune(std::uint64_t now_ms);
    FrictionSignal evaluate(std::uint64_t now_ms) const;
};

} // namespace typetrix
