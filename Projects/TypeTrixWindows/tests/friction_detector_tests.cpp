#include "friction_detector.h"

#include <cstdlib>
#include <iostream>

using typetrix::EditEvent;
using typetrix::EventType;
using typetrix::FrictionDetector;

namespace {
void expect(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
}

int main() {
    {
        FrictionDetector detector;
        auto signal = detector.observe({EventType::Input, 100, "hello"});
        expect(!signal.prepare_candidates, "ordinary typing should stay quiet");
        expect(!signal.show_candidates, "ordinary typing should not show candidates");
    }

    {
        FrictionDetector detector;
        detector.observe({EventType::Input, 100, "pat"});
        detector.observe({EventType::Backspace, 300, "pa"});
        detector.observe({EventType::Input, 450, "par"});
        detector.observe({EventType::Backspace, 600, "pa"});
        detector.observe({EventType::Input, 750, "patt"});
        detector.observe({EventType::Backspace, 900, "pat"});
        detector.observe({EventType::Backspace, 1050, "pa"});
        auto signal = detector.observe({EventType::Input, 1200, "pattern"});
        expect(signal.prepare_candidates, "erase/retype cycle should prepare candidates");
        expect(signal.show_candidates, "strong word-search pattern should show candidates");
        expect(signal.confidence >= 0.70, "strong pattern should cross visible threshold");
    }

    {
        FrictionDetector detector;
        detector.observe({EventType::Input, 100, "nec"});
        detector.observe({EventType::Backspace, 300, "ne"});
        detector.observe({EventType::Backspace, 500, "n"});
        auto signal = detector.observe({EventType::Input, 2000, "ness"});
        expect(signal.prepare_candidates, "pause after repeated editing should raise friction confidence");
    }

    std::cout << "TypeTrix core detector tests passed\n";
    return 0;
}
