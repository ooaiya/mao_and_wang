#pragma once
#include "memory_budget.hpp"

namespace ms::oracle {
struct Plan {
    std::string status="INFEASIBLE";
    bool feasible=false;
    std::vector<unsigned> releaseMs;
    std::vector<Bytes> reserved;
    std::uint64_t weightedDelayMs=0,nodes=0;
    double solveMs=0;
    unsigned horizonMs=0;
};
Plan solve(const Problem& problem);
std::string planJson(const Problem& problem,const Plan& plan,const std::string& planId="offline",bool planningOnly=true,unsigned version=1);
std::string ledgerTsv(const Problem& problem,const Plan& plan);
} // namespace ms::oracle
