#include "memory_planner.hpp"
#include <algorithm>
#include <chrono>
#include <functional>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace ms::oracle {
Plan solve(const Problem& p) {
    const auto start=std::chrono::steady_clock::now();
    MemoryBudget ledger(p);Plan best;best.horizonMs=ledger.horizonMs;
    bool limited=false;std::vector<unsigned> current(p.jobs.size());
    // Swapping equal-cost, equal-curve jobs cannot change feasibility or cost.
    // Keep their releases ordered to retain the lexicographically first optimum
    // without exploring every permutation. Waiting overhead is constant anyway.
    std::vector<int> previousEqual(p.jobs.size(),-1);
    for(std::size_t i=0;i<p.jobs.size();++i)for(std::size_t k=0;k<i;++k) {
        const auto& a=p.jobs[i];const auto& b=p.jobs[k];
        if(a.durationMs==b.durationMs && a.notBeforeMs==b.notBeforeMs && a.maxDelayMs==b.maxDelayMs &&
           a.canDelay==b.canDelay && a.controllable==b.controllable && a.identityVerified==b.identityVerified && a.residencyModel==b.residencyModel && a.running==b.running && a.residentBytes==b.residentBytes && a.priority==b.priority && a.memoryCurve.size()==b.memoryCurve.size() &&
           std::equal(a.memoryCurve.begin(),a.memoryCurve.end(),b.memoryCurve.begin(),
                      [](const Point& x,const Point& y){return x.ms==y.ms && x.bytes==y.bytes;}))
            previousEqual[i]=static_cast<int>(k);
    }
    std::vector<std::size_t> order(p.jobs.size());for(std::size_t i=0;i<order.size();++i)order[i]=i;
    std::stable_sort(order.begin(),order.end(),[&](auto a,auto b){
        const auto movable=[&](auto i){const auto& j=p.jobs[i];return j.canDelay && j.controllable && j.identityVerified;};
        if(movable(a)!=movable(b))return movable(a)<movable(b);
        if(p.jobs[a].running!=p.jobs[b].running)return p.jobs[a].running;
        return p.jobs[a].residentBytes>p.jobs[b].residentBytes;
    });
    std::vector<Bytes> pending(order.size()+1,0);
    for(std::size_t d=order.size();d>0;--d) {
        const auto& j=p.jobs[order[d-1]];
        pending[d-1]=pending[d]+(j.residencyModel?j.residentBytes:0);
    }
    auto elapsed=[&]{return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();};
    std::function<void(std::size_t,std::uint64_t)> search=[&](std::size_t depth,std::uint64_t cost) {
        if(depth==p.jobs.size()) {
            if(!ledger.feasible())return;
            if(!best.feasible || cost<best.weightedDelayMs || (cost==best.weightedDelayMs && current<best.releaseMs)) {
                best.feasible=true;best.weightedDelayMs=cost;best.releaseMs=current;best.reserved=ledger.reserved;
            }
            return;
        }
        const auto index=order[depth];const auto& j=p.jobs[index];const unsigned last=(j.canDelay && j.controllable && j.identityVerified)?j.maxDelayMs:0;
        const unsigned first=previousEqual[index]<0?0:current[static_cast<std::size_t>(previousEqual[index])]-j.notBeforeMs;
        for(unsigned d=first;d<=last;d+=p.slotMs) {
            const auto next=cost+static_cast<std::uint64_t>(j.priority)*d;
            if(best.feasible && next>best.weightedDelayMs)break;
            if(best.nodes>=p.maxNodes || elapsed()>=p.maxWallMs){limited=true;return;}
            ++best.nodes;const unsigned release=j.notBeforeMs+d;
            if(!ledger.fits(index,release,pending[depth+1]))continue;
            ledger.change(index,release,true);current[index]=release;search(depth+1,next);ledger.change(index,release,false);
            if(limited)return;
        }
    };
    search(0,0);
    best.status=limited?(best.feasible?"FEASIBLE_NOT_PROVEN":"SEARCH_LIMIT"):(best.feasible?"OPTIMAL":"INFEASIBLE");
    best.solveMs=elapsed();return best;
}
std::string planJson(const Problem& p,const Plan& plan,const std::string& id,bool planningOnly,unsigned version) {
    if(!validName(id))throw std::runtime_error("invalid plan id");
    std::ostringstream s;s<<std::setprecision(12);
    s<<"{\"schema\":\"memshift-oracle-plan-v1\",\"plan_id\":\""<<id<<"\",\"version\":"<<version<<",\"planning_only\":"<<(planningOnly?"true":"false")
     <<",\"status\":\""<<plan.status<<"\",\"feasible\":"<<(plan.feasible?"true":"false")
     <<",\"budget_semantics\":\""<<p.budgetSemantics<<"\",\"safe_bytes\":"<<p.safeBytes
     <<",\"slot_ms\":"<<p.slotMs<<",\"horizon_ms\":"<<plan.horizonMs<<",\"nodes\":"<<plan.nodes
     <<",\"solve_ms\":"<<plan.solveMs<<",\"weighted_delay_ms\":";
    if(plan.feasible)s<<plan.weightedDelayMs;else s<<"null";
    s<<",\"peak_reserved_bytes\":";
    if(plan.feasible)s<<*std::max_element(plan.reserved.begin(),plan.reserved.end());else s<<"null";
    s<<",\"known_tasks\":[";
    for(std::size_t i=0;i<p.jobs.size();++i){const auto& j=p.jobs[i];if(i)s<<',';
        s<<"{\"id\":\""<<j.taskId<<"\",\"controllable\":"<<(j.controllable?"true":"false")
         <<",\"identity_verified\":"<<(j.identityVerified?"true":"false")<<",\"running\":"<<(j.running?"true":"false")
         <<",\"can_delay\":"<<((j.canDelay && j.controllable && j.identityVerified)?"true":"false")
         <<",\"model_age_ms\":"<<j.modelAgeMs<<",\"resident_bytes\":"<<j.residentBytes<<'}';}
    s<<"],\"jobs\":[";
    if(plan.feasible)for(std::size_t i=0;i<p.jobs.size();++i) {
        if(i)s<<',';const auto& j=p.jobs[i];
        s<<"{\"id\":\""<<j.taskId<<"\",\"release_after_ms\":"<<plan.releaseMs[i]
         <<",\"delay_ms\":"<<plan.releaseMs[i]-j.notBeforeMs<<",\"priority\":"<<j.priority<<",\"confidence\":"<<j.confidence<<'}';
    }
    s<<"]}";return s.str();
}
std::string ledgerTsv(const Problem& p,const Plan& plan) {
    std::ostringstream s;s<<"time_ms\tbase_bytes\tforeground_bytes\twaiting_bytes\terror_bytes";
    for(const auto& j:p.jobs)s<<'\t'<<j.taskId<<"_increment_bytes";
    s<<"\tpredicted_total_bytes\treserved_bytes\theadroom_bytes\n";
    if(!plan.feasible)return s.str();
    Bytes waiting=0;for(const auto& j:p.jobs)waiting+=j.waitingResidentBytes+(j.residencyModel?j.residentBytes:0);
    for(std::size_t slot=0;slot<plan.reserved.size();++slot) {
        const unsigned t=static_cast<unsigned>(slot)*p.slotMs;const auto error=valueAt(p.error,t);
        s<<t<<'\t'<<valueAt(p.base,t)<<'\t'<<valueAt(p.foreground,t)<<'\t'<<waiting<<'\t'<<error;
        for(std::size_t i=0;i<p.jobs.size();++i) {s<<'\t';if(t<plan.releaseMs[i])s<<0;else s<<static_cast<std::int64_t>(valueAt(p.jobs[i].memoryCurve,t-plan.releaseMs[i]))-static_cast<std::int64_t>(p.jobs[i].residencyModel?p.jobs[i].residentBytes:0);}
        s<<'\t'<<plan.reserved[slot]-error<<'\t'<<plan.reserved[slot]<<'\t'<<p.safeBytes-plan.reserved[slot]<<'\n';
    }
    return s.str();
}
} // namespace ms::oracle
