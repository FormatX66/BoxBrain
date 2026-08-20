#include "friction_detector.h"

#include <algorithm>
#include <cmath>
#include <set>

namespace typetrix {

namespace {
constexpr std::uint64_t kWindowMs = 8000;
constexpr std::uint64_t kBurstMs = 3000;
constexpr std::uint64_t kPauseMs = 1200;
}

void FrictionDetector::prune(std::uint64_t now_ms) {
    while (!events_.empty() && now_ms > events_.front().timestamp_ms &&
           now_ms - events_.front().timestamp_ms > kWindowMs) {
        events_.pop_front();
    }
}

FrictionSignal FrictionDetector::observe(const EditEvent& event) {
    prune(event.timestamp_ms);

    const auto previous_active_ms = last_active_ms_;
    events_.push_back(event);

    if (event.type != EventType::Navigation && event.type != EventType::SuggestionShown) {
        last_active_ms_ = event.timestamp_ms;
    }

    auto signal = evaluate(event.timestamp_ms);

    if (previous_active_ms != 0 && event.timestamp_ms > previous_active_ms &&
        event.timestamp_ms - previous_active_ms >= kPauseMs) {
        const auto backspaces = std::count_if(events_.begin(), events_.end(), [](const EditEvent& e) {
            return e.type == EventType::Backspace;
        });
        if (backspaces >= 2) {
            signal.confidence = std::min(1.0, signal.confidence + 0.15);
            signal.reasons.push_back("pause-after-editing");
        }
    }

    signal.prepare_candidates = signal.confidence >= 0.45;
    signal.show_candidates = signal.confidence >= 0.70;
    return signal;
}

FrictionSignal FrictionDetector::evaluate(std::uint64_t now_ms) const {
    FrictionSignal signal;
    int recent_backspaces = 0;
    int total_backspaces = 0;
    int retype_transitions = 0;
    bool saw_backspace = false;
    std::set<std::string> token_attempts;

    for (const auto& event : events_) {
        if (event.type == EventType::Backspace) {
            ++total_backspaces;
            if (now_ms >= event.timestamp_ms && now_ms - event.timestamp_ms <= kBurstMs) {
                ++recent_backspaces;
            }
            saw_backspace = true;
            continue;
        }

        if (event.type == EventType::Input && saw_backspace) {
            ++retype_transitions;
            saw_backspace = false;
        }

        if (!event.token_snapshot.empty()) {
            token_attempts.insert(event.token_snapshot);
        }
    }

    if (recent_backspaces >= 2) {
        signal.confidence += 0.25;
        signal.reasons.push_back("backspace-burst");
    }
    if (recent_backspaces >= 4) {
        signal.confidence += 0.20;
        signal.reasons.push_back("heavy-backspace-burst");
    }
    if (retype_transitions >= 2) {
        signal.confidence += 0.25;
        signal.reasons.push_back("erase-retype-cycles");
    }
    if (token_attempts.size() >= 3 && total_backspaces >= 2) {
        signal.confidence += 0.20;
        signal.reasons.push_back("multiple-token-attempts");
    }

    signal.confidence = std::clamp(signal.confidence, 0.0, 1.0);
    signal.prepare_candidates = signal.confidence >= 0.45;
    signal.show_candidates = signal.confidence >= 0.70;
    return signal;
}

void FrictionDetector::reset() {
    events_.clear();
    last_active_ms_ = 0;
}

} // namespace typetrix
