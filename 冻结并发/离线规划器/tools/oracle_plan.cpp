#include "../src/memory_planner.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
int main(int argc,char** argv) {
    try {
        std::string input,ledger;
        for(int i=1;i<argc;++i) {
            const std::string key=argv[i];
            if((key!="--input" && key!="--ledger") || ++i>=argc)throw std::runtime_error("usage: memshift_oracle_plan --input profile.tsv [--ledger ledger.tsv]");
            (key=="--input"?input:ledger)=argv[i];
        }
        if(input.empty() || input==ledger)throw std::runtime_error("input required; ledger must differ");
        const auto p=ms::oracle::parseProfile(ms::oracle::readProfileFile(input));const auto plan=ms::oracle::solve(p);
        if(!ledger.empty()){std::ofstream out(ledger);out<<ms::oracle::ledgerTsv(p,plan);out.close();if(!out)throw std::runtime_error("ledger write failed");}
        std::cout<<ms::oracle::planJson(p,plan)<<'\n';return plan.feasible?0:2;
    } catch(const std::exception& e){std::cerr<<"oracle: "<<e.what()<<'\n';return 1;}
}
