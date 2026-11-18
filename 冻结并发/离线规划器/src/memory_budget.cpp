#include "memory_budget.hpp"
#include <algorithm>

namespace ms::oracle {
MemoryBudget::MemoryBudget(const Problem& p):problem_(p),horizonMs(validate(p)) {
    for(const auto& j:p.jobs)waitingBytes+=j.waitingResidentBytes+(j.residencyModel?j.residentBytes:0);
    for(unsigned t=0;t<horizonMs;t+=p.slotMs)
        reserved.push_back(valueAt(p.base,t)+valueAt(p.foreground,t)+valueAt(p.error,t)+waitingBytes);
}
bool MemoryBudget::feasible() const {
    return std::all_of(reserved.begin(),reserved.end(),[&](Bytes b){return b<=problem_.safeBytes;});
}
bool MemoryBudget::fits(std::size_t index,unsigned releaseMs,Bytes pendingResident) const {
    const auto& job=problem_.jobs.at(index);
    for(std::size_t slot=0;slot<reserved.size();++slot) {
        Bytes candidate=reserved[slot];
        if(slot>=releaseMs/problem_.slotMs) {
            const auto resident=job.residencyModel?job.residentBytes:0;
            if(candidate<resident)return false;
            candidate=candidate-resident+valueAt(job.memoryCurve,static_cast<unsigned>(slot)*problem_.slotMs-releaseMs);
        }
        // Unassigned resident curves can reduce this partial ledger. This is
        // only an optimistic pruning bound; completed assignments are checked
        // against the exact ledger before accepting a plan.
        if(candidate>problem_.safeBytes && candidate-problem_.safeBytes>pendingResident)return false;
    }
    return true;
}
void MemoryBudget::change(std::size_t index,unsigned releaseMs,bool add) {
    const auto& c=problem_.jobs.at(index).memoryCurve;
    for(std::size_t slot=releaseMs/problem_.slotMs;slot<reserved.size();++slot) {
        const auto delta=valueAt(c,static_cast<unsigned>(slot)*problem_.slotMs-releaseMs);
        const auto resident=problem_.jobs[index].residencyModel?problem_.jobs[index].residentBytes:0;
        if(add)reserved[slot]=reserved[slot]-resident+delta;else reserved[slot]=reserved[slot]+resident-delta;
    }
}
} // namespace ms::oracle
