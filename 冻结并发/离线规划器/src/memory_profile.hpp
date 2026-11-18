#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace ms::oracle {
using Bytes = std::uint64_t;
inline constexpr std::size_t maxJobs = 5;
struct Point { unsigned ms=0; Bytes bytes=0; };
// Values are upper envelopes on [ms, next_ms); the last value persists.
using Curve = std::vector<Point>;
struct MemoryProfile {
    std::string taskId;
    Curve memoryCurve;
    unsigned durationMs=0, notBeforeMs=0, maxDelayMs=20000;
    bool canDelay=true;
    unsigned priority=1;
    double confidence=1;
    Bytes waitingResidentBytes=0;
    bool controllable=true, identityVerified=true, running=false, residencyModel=false;
    unsigned modelAgeMs=0, allocationMs=0, holdMs=0, releaseMs=0;
    Bytes residentBytes=0;
};
struct Problem {
    unsigned slotMs=500, maxWallMs=2000;
    std::uint64_t maxNodes=1000000;
    Bytes safeBytes=0;
    std::string budgetSemantics;
    Curve base, foreground, error;
    std::vector<MemoryProfile> jobs;
};
bool validName(const std::string& value);
Bytes valueAt(const Curve& curve,unsigned ms);
unsigned validate(const Problem& problem); // Returns full horizon, including terminal slot.
Problem parseProfile(const std::string& text);
std::string readProfileFile(const std::string& path);
} // namespace ms::oracle
