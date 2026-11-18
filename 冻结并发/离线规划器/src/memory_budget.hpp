#pragma once
#include "memory_profile.hpp"

namespace ms::oracle {
// Future-slot ledger. Waiting overhead is constant and is never shifted away.
class MemoryBudget {
    const Problem& problem_;
public:
    unsigned horizonMs;
    std::vector<Bytes> reserved;
    Bytes waitingBytes=0;
    explicit MemoryBudget(const Problem& p);
    bool feasible() const;
    bool fits(std::size_t job,unsigned releaseMs,Bytes pendingResident=0) const;
    void change(std::size_t job,unsigned releaseMs,bool add);
};
} // namespace ms::oracle
