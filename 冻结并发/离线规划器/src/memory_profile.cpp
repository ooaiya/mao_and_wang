#include "memory_profile.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>

namespace ms::oracle {
namespace {
constexpr Bytes maxBytes=Bytes{1}<<60;
Bytes number(const std::string& s,Bytes maximum) {
    if(s.empty() || s.find_first_not_of("0123456789")!=std::string::npos)
        throw std::runtime_error("expected unsigned decimal");
    std::size_t end=0;const auto n=std::stoull(s,&end);
    if(end!=s.size() || n>maximum)throw std::runtime_error("profile number exceeds bound");
    return n;
}
void checkCurve(const Curve& c,unsigned slot) {
    if(c.empty() || c.front().ms!=0 || c.size()>20001)throw std::runtime_error("curve must start at zero and be bounded");
    for(std::size_t i=0;i<c.size();++i)
        if(c[i].ms>3600000 || c[i].ms%slot || c[i].bytes>maxBytes || (i && c[i].ms<=c[i-1].ms))
            throw std::runtime_error("curve points must be ordered, grid aligned and bounded");
}
}
bool validName(const std::string& s) {
    return !s.empty() && s.size()<=48 && s.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")==std::string::npos;
}
Bytes valueAt(const Curve& c,unsigned ms) {
    const auto it=std::upper_bound(c.begin(),c.end(),ms,[](unsigned t,const Point& p){return t<p.ms;});
    return it==c.begin()?0:std::prev(it)->bytes;
}
unsigned validate(const Problem& p) {
    if(p.slotMs<100 || p.slotMs>1000 || !p.safeBytes || p.safeBytes>maxBytes ||
       p.jobs.empty() || p.jobs.size()>maxJobs || !p.maxNodes || p.maxNodes>10000000 || !p.maxWallMs || p.maxWallMs>30000 ||
       (p.budgetSemantics!="physical_used" && p.budgetSemantics!="available_headroom_proxy" && p.budgetSemantics!="synthetic"))
        throw std::runtime_error("invalid Oracle settings");
    checkCurve(p.base,p.slotMs);checkCurve(p.foreground,p.slotMs);checkCurve(p.error,p.slotMs);
    unsigned horizon=std::max({p.base.back().ms,p.foreground.back().ms,p.error.back().ms});
    std::set<std::string> ids;
    for(const auto& j:p.jobs) {
        checkCurve(j.memoryCurve,p.slotMs);
        if(!validName(j.taskId) || !ids.insert(j.taskId).second || !j.durationMs || j.durationMs>1800000 ||
           j.durationMs%p.slotMs || j.notBeforeMs>1800000 || j.notBeforeMs%p.slotMs ||
           j.maxDelayMs>1800000 || j.maxDelayMs%p.slotMs || !j.priority || j.priority>1000000 ||
           !std::isfinite(j.confidence) || j.confidence<0 || j.confidence>1 || j.waitingResidentBytes>maxBytes ||
           j.memoryCurve.back().ms!=j.durationMs || (!j.identityVerified && j.controllable) ||
           (j.allocationMs && ((!j.modelAgeMs && j.allocationMs+j.holdMs+j.releaseMs!=j.durationMs) || !j.holdMs || !j.releaseMs)))
            throw std::runtime_error("invalid job metadata or missing terminal point");
        horizon=std::max(horizon,j.notBeforeMs+(j.canDelay?j.maxDelayMs:0)+j.durationMs);
    }
    if(horizon>3600000-p.slotMs || horizon/p.slotMs>19999)throw std::runtime_error("Oracle horizon exceeds bound");
    return horizon+p.slotMs;
}
Problem parseProfile(const std::string& text) {
    if(text.size()>1024*1024 || text.find('\0')!=std::string::npos)throw std::runtime_error("profile exceeds limit or contains NUL");
    Problem p;std::istringstream in(text);std::string line;
    if(!std::getline(in,line))throw std::runtime_error("missing Oracle schema");
    if(!line.empty() && line.back()=='\r')line.pop_back();
    if(line!="memshift-oracle-v1")throw std::runtime_error("unsupported Oracle schema");
    std::set<std::string> settings;std::map<std::string,std::size_t> ids;
    while(std::getline(in,line)) {
        if(line.empty() || line[0]=='#')continue;
        std::istringstream words(line);std::vector<std::string> v;std::string word;
        while(words>>word)v.push_back(word);
        if(v.empty())continue;
        const auto& k=v[0];
        if(k=="base" || k=="foreground" || k=="error") {
            if(v.size()!=3)throw std::runtime_error("curve field count");
            auto& c=k=="base"?p.base:k=="foreground"?p.foreground:p.error;
            c.push_back({static_cast<unsigned>(number(v[1],3600000)),number(v[2],maxBytes)});
        } else if(k=="job") {
            if(v.size()!=10 || p.jobs.size()>=maxJobs || ids.count(v[1]))throw std::runtime_error("job field count or duplicate");
            MemoryProfile j;j.taskId=v[1];j.durationMs=static_cast<unsigned>(number(v[2],1800000));
            j.notBeforeMs=static_cast<unsigned>(number(v[3],1800000));j.maxDelayMs=static_cast<unsigned>(number(v[4],1800000));
            j.canDelay=number(v[5],1)!=0;j.priority=static_cast<unsigned>(number(v[6],1000000));
            std::size_t end=0;j.confidence=std::stod(v[7],&end);
            if(end!=v[7].size())throw std::runtime_error("invalid confidence");
            j.waitingResidentBytes=number(v[8],maxBytes);
            if(v[9]!="incremental")throw std::runtime_error("job curve must be incremental");
            ids[j.taskId]=p.jobs.size();p.jobs.push_back(j);
        } else if(k=="state") {
            if((v.size()!=7 && v.size()!=8) || !ids.count(v[1]) || !settings.insert("state:"+v[1]).second)throw std::runtime_error("invalid job state");
            auto& j=p.jobs[ids.at(v[1])];j.controllable=number(v[2],1);j.identityVerified=number(v[3],1);
            j.running=number(v[4],1);j.modelAgeMs=static_cast<unsigned>(number(v[5],1800000));j.residentBytes=number(v[6],maxBytes);if(v.size()==8)j.residencyModel=number(v[7],1);
        } else if(k=="phase") {
            if(v.size()!=5 || !ids.count(v[1]) || !settings.insert("phase:"+v[1]).second)throw std::runtime_error("invalid phase durations");
            auto& j=p.jobs[ids.at(v[1])];j.allocationMs=static_cast<unsigned>(number(v[2],1800000));
            j.holdMs=static_cast<unsigned>(number(v[3],1800000));j.releaseMs=static_cast<unsigned>(number(v[4],1800000));
        } else if(k=="point") {
            if(v.size()!=4 || !ids.count(v[1]))throw std::runtime_error("unknown point job or field count");
            p.jobs[ids.at(v[1])].memoryCurve.push_back({static_cast<unsigned>(number(v[2],3600000)),number(v[3],maxBytes)});
        } else {
            if(v.size()!=2 || !settings.insert(k).second)throw std::runtime_error("duplicate or invalid setting");
            if(k=="slot_ms")p.slotMs=static_cast<unsigned>(number(v[1],1000));
            else if(k=="safe_bytes")p.safeBytes=number(v[1],maxBytes);
            else if(k=="max_nodes")p.maxNodes=number(v[1],10000000);
            else if(k=="max_wall_ms")p.maxWallMs=static_cast<unsigned>(number(v[1],30000));
            else if(k=="budget_semantics")p.budgetSemantics=v[1];
            else throw std::runtime_error("unknown profile setting");
        }
    }
    validate(p);return p;
}
std::string readProfileFile(const std::string& path) {
    std::ifstream in(path,std::ios::binary);if(!in)throw std::runtime_error("cannot open Oracle profile");
    std::string result;char data[8192];
    while(in) {in.read(data,sizeof(data));result.append(data,static_cast<std::size_t>(in.gcount()));
        if(result.size()>1024*1024)throw std::runtime_error("profile exceeds limit");}
    if(!in.eof())throw std::runtime_error("cannot read Oracle profile");
    return result;
}
} // namespace ms::oracle
