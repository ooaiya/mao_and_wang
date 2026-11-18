"""Curve-informed, shape-independent forecasting and interruptible admission.

Pure Python policy: no PID, cgroup, GUI, or platform dependencies. Predictions
are sampled historical envelopes, not guarantees about an unseen workload.
"""
from bisect import bisect_right
from collections import deque
from dataclasses import dataclass, field
import math


class Curve:
    """Step-envelope range maxima, with no fabricated release past its tail."""
    def __init__(self, model):
        self.points=[(float(t)/1000,int(v)) for t,v in model['curve']]
        if not self.points or self.points[0][0]!=0 or any(not math.isfinite(t) for t,_ in self.points) or any(b[0]<=a[0] for a,b in zip(self.points,self.points[1:])):
            raise ValueError('ordered profile starting at zero required')
        self.times=[t for t,_ in self.points];self.values=[v for _,v in self.points]
        self.duration=float(model['duration_ms'])/1000
        self.level_scale=float(model.get('reference_level_scale',1.0))
        if not math.isfinite(self.level_scale) or self.level_scale<=0:raise ValueError('positive reference level scale required')
        if self.times[-1]!=self.duration or any(v<0 for v in self.values):raise ValueError('complete nonnegative profile required')
        self.peak=max(self.values);self.table=[self.values]
        width=2
        while width<=len(self.values):
            prev=self.table[-1];half=width//2
            self.table.append([max(prev[i],prev[i+half]) for i in range(len(self.values)-width+1)]);width*=2
    def value(self,t):return self.values[max(0,bisect_right(self.times,max(0,t))-1)]
    def maximum(self,left,right):
        i=max(0,bisect_right(self.times,max(0,left))-1);j=max(i,bisect_right(self.times,min(self.duration,right))-1)
        power=(j-i+1).bit_length()-1;width=1<<power
        return max(self.table[power][i],self.table[power][j-width+1])


@dataclass
class Forecast:
    growth_bytes: int
    remaining_growth_bytes: int
    reliable: bool
    reason: str
    phase_min_s: float
    phase_max_s: float
    recent_rate_bytes_s: float


class Forecaster:
    """Live-anchored positive increments across all plausible historical phases.

    Bounded phase uncertainty handles shifted peaks; a plateau never proves
    that a later peak is gone. Drops never grant memory-release credit.
    """
    def __init__(self,model,config,foreground=False):
        self.curve=Curve(model);self.c=config;self.foreground=foreground;self.history=deque()
    def observe(self,now,current):
        if current<0 or not math.isfinite(now):raise ValueError('invalid observation')
        if self.history and now<self.history[-1][0]:raise ValueError('observation clock reversed')
        if self.history and now==self.history[-1][0]:self.history[-1]=(now,int(current))
        else:self.history.append((now,int(current)))
        while len(self.history)>1 and now-self.history[0][0]>self.c['history_s']:self.history.popleft()
    def recent_rate(self):
        # A tile/page-accounting jump over one 200ms sample is not evidence
        # that the same rate persists throughout the stop-reaction interval.
        # Use sustained windows; the profile envelope still covers short peaks.
        rows=list(self.history);times=[t for t,_ in rows];rates=[0.0]
        for end,current in rows:
            at=bisect_right(times,end-self.c['rate_window_s'])-1
            if at>=0:
                start,prior=rows[at];rates.append((current-prior)/(end-start))
        return max(rates)*self.c['rate_multiplier']
    def predict(self,age,current,horizon,started=True):
        curve=self.curve;jitter=self.c['foreground_jitter_s' if self.foreground else 'background_jitter_s']
        tail_hold=curve.maximum(max(0,curve.duration-jitter),curve.duration) if self.foreground else curve.peak
        rate=self.recent_rate();floor=self.c['growth_uncertainty_bytes']
        low=max(0,age-jitter);high=age+jitter
        phases=[low]+[t for t in curve.times if low<t<=min(high,curve.duration)]+[min(high,curve.duration)] if low<=curve.duration else []
        raw=lambda phase:curve.value(phase)/curve.level_scale
        tolerance=max(self.c['level_tolerance_bytes'],int(max(current,raw(min(age,curve.duration)))*self.c['level_tolerance_fraction']))
        matched=[p for p in phases if abs(raw(p)-current)<=tolerance]
        if matched:
            # Inflation belongs in demand bounds, not in the observed level
            # used to align progress. Keep genuinely ambiguous near-best fits.
            best=min(abs(raw(p)-current) for p in matched)
            matched=[p for p in matched if abs(raw(p)-current)<=best+self.c['level_match_band_bytes']]
        if matched and len(self.history)>1:
            span=self.history[-1][0]-self.history[0][0];observed=current-self.history[0][1]
            if span>=self.c['rate_window_s']:
                consistent=[]
                for phase in matched:
                    expected=raw(phase)-raw(max(0,phase-span))
                    error=max(self.c['trend_tolerance_bytes'],self.c['trend_tolerance_fraction']*max(abs(expected),abs(observed)))
                    if abs(expected-observed)<=error:consistent.append(phase)
                matched=consistent
        # At first allocation, zero charged memory must not subtract an already
        # resident historical interpreter from the new allocation budget.
        if not started:
            matched=[0.0];reliable=True;reason='before_first_execution'
        else:
            within=age<=curve.duration+jitter if self.foreground else age+horizon<=curve.duration
            reliable=bool(matched) and within and current<=curve.peak+tolerance
            reason='matched_phase_envelope' if reliable else 'profile_mismatch_or_overrun'
        if not reliable:
            ceiling=curve.peak
            if self.foreground and age<=curve.duration+jitter and age+horizon>curve.duration:
                ceiling=max(tail_hold,curve.maximum(min(curve.duration,low),curve.duration))
            growth=max(0,ceiling-current,math.ceil(rate*horizon))+floor
            return Forecast(growth,max(growth,max(0,ceiling-current)+floor),False,reason,low,high,rate)
        short=remaining=0
        for phase in matched:
            anchor=curve.value(phase) if started else 0
            # A possible overrun cannot consume the terminal zero as a release.
            future=curve.maximum(phase,min(curve.duration,phase+horizon))
            if phase+horizon>curve.duration:future=max(future,tail_hold)
            short=max(short,future-anchor)
            # A parked allocation cannot be reclaimed by merely pausing it.
            # Keep the inflated absolute future ceiling for this long-lived
            # constraint; a low live sample must not cancel its safety margin.
            future_ceiling=max(curve.maximum(phase,curve.duration),tail_hold) if self.foreground else curve.maximum(phase,curve.duration)
            remaining=max(remaining,future_ceiling-current)
        short=max(0,math.ceil(short*self.c['growth_multiplier']),math.ceil(rate*horizon))+floor
        remaining=max(0,math.ceil(remaining*self.c['growth_multiplier']),math.ceil(rate*self.c['reaction_s']))+floor
        return Forecast(short,max(short,remaining),True,reason,min(matched),max(matched),rate)


@dataclass
class TaskClock:
    """Count thawed wall time; freezing does not reset progress or residency."""
    state: str='FROZEN'
    active_s: float=0.0
    since: float=0.0
    ever_started: bool=False
    frozen_since: float=0.0
    lease_until: float=0.0
    generation: int=0
    def age(self,now):return self.active_s+(max(0,now-self.since) if self.state=='RUNNING' else 0)
    def resumed(self,now,lease_until):
        if self.state!='FROZEN':raise ValueError('resume requires confirmed frozen state')
        self.state='RUNNING';self.since=now;self.ever_started=True;self.lease_until=lease_until;self.generation+=1
    def frozen(self,now):
        if self.state!='RUNNING':raise ValueError('pause requires running state')
        self.active_s=self.age(now);self.state='FROZEN';self.frozen_since=now;self.lease_until=0;self.generation+=1
    def finished(self,now):
        self.active_s=self.age(now);self.state='FINISHED';self.lease_until=0;self.generation+=1


@dataclass
class Decision:
    freeze: list=field(default_factory=list)
    resume: list=field(default_factory=list)
    leases: dict=field(default_factory=dict)
    evidence: dict=field(default_factory=dict)
    parking_deficit: bool=False
    retention_hold: bool=False
    emergency_deficit: bool=False


class SegmentPolicy:
    def __init__(self,models,config,reserve_bytes):
        self.c=config;self.reserve=reserve_bytes
        if reserve_bytes<=0 or not config['lease_choices_s'] or min(config['lease_choices_s'])<=0 or max(config['lease_choices_s'])>30:raise ValueError('positive budget and bounded leases (<=30 seconds) required')
        for key in ['decision_interval_s','reaction_s','freeze_timeout_s','watchdog_interval_s','history_s','rate_window_s']:
            if not math.isfinite(config[key]) or config[key]<=0:raise ValueError('invalid positive policy setting: '+key)
        for key in ['foreground_jitter_s','background_jitter_s','growth_uncertainty_bytes','resume_headroom_bytes','resume_stable_s','minimum_frozen_s','level_tolerance_bytes','level_tolerance_fraction','level_match_band_bytes','trend_tolerance_bytes','trend_tolerance_fraction']:
            if not math.isfinite(config[key]) or config[key]<0:raise ValueError('invalid nonnegative policy setting: '+key)
        if config['growth_multiplier']<1 or config['rate_multiplier']<1:raise ValueError('growth forecasts may not be discounted')
        if config['rate_window_s']>config['history_s'] or config['rate_window_s']<config['decision_interval_s']:raise ValueError('growth-rate window must fit observation history and sampling interval')
        self.fg=config['foreground_operation'];self.retention_hold=False
        self.forecaster={op:Forecaster(m,config,op==self.fg) for op,m in models.items()}
        if self.fg not in self.forecaster:raise ValueError('foreground role has no profile')
        early=set(config['early_backgrounds']);held=set(config['hold_until_foreground_done'])
        if early&held or self.fg in early|held or not (early|held)<=set(models):raise ValueError('invalid or ambiguous task roles')
    def observe(self,now,current):
        for op,value in current.items():
            if op in self.forecaster:self.forecaster[op].observe(now,value)
    def budget(self,now,elapsed,available,current,clocks,selected,horizon,foreground_done):
        guard=horizon+self.c['reaction_s'];fg=None
        if not foreground_done:fg=self.forecaster[self.fg].predict(elapsed,current[self.fg],guard)
        fg_short=fg.growth_bytes if fg else 0;fg_remaining=fg.remaining_growth_bytes if fg else 0
        growth={};background_forecasts={};reliable=fg.reliable if fg else True
        for op in selected:
            clock=clocks[op];f=self.forecaster[op].predict(clock.age(now),current[op],guard,clock.ever_started)
            growth[op]=f.growth_bytes;background_forecasts[op]=vars(f);reliable=reliable and (f.reliable or foreground_done)
        extra=sum(growth.values())
        short_required=self.reserve+fg_short+extra
        # MemAvailable already includes every frozen task's retained pages. The
        # parking constraint adds only future growth and grants no release credit.
        parking_required=self.reserve+fg_remaining+extra
        return dict(allowed=reliable and available>=max(short_required,parking_required),available_bytes=available,
            short_required_bytes=short_required,parking_required_bytes=parking_required,reserve_bytes=self.reserve,
            foreground_short_growth_bytes=fg_short,foreground_remaining_growth_bytes=fg_remaining,
            background_growth_bytes=growth,background_forecasts=background_forecasts,foreground_forecast=vars(fg) if fg else None,
            forecasts_reliable=reliable,horizon_s=horizon,reaction_s=self.c['reaction_s'])
    def decide(self,now,elapsed,available,current,clocks,foreground_done=False):
        result=Decision();active=[op for op,c in clocks.items() if c.state=='RUNNING'];selected=[]
        # Existing running tasks first: do not freeze/resume everyone each tick.
        order=active+[op for op,c in clocks.items() if c.state=='FROZEN']
        for op in order:
            clock=clocks[op]
            if not foreground_done and op not in self.c['early_backgrounds']:
                if clock.state=='RUNNING':result.freeze.append(op)
                result.evidence[op]=dict(allowed=False,reason='foreground_role_constraint');continue
            if clock.state=='FROZEN' and now-clock.frozen_since<self.c['minimum_frozen_s']:continue
            approved=None;check=None
            for horizon in sorted(self.c['lease_choices_s'],reverse=True):
                trial=self.budget(now,elapsed,available,current,clocks,selected+[op],horizon,foreground_done)
                margin=self.c['resume_headroom_bytes'] if clock.state=='FROZEN' else 0
                if trial['allowed'] and available>=max(trial['short_required_bytes'],trial['parking_required_bytes'])+margin:
                    approved=horizon;check=trial;break
                check=trial
            result.evidence[op]=check
            if approved is None:
                if clock.state=='RUNNING':result.freeze.append(op)
                continue
            selected.append(op);result.leases[op]=now+approved
            if clock.state=='FROZEN':result.resume.append(op)
        parked=self.budget(now,elapsed,available,current,clocks,[],0,foreground_done)
        result.parking_deficit=available<parked['parking_required_bytes']
        result.evidence['parking_after_all_paused']=parked
        # Every member of an admitted set gets the shortest approved lease. A
        # short candidate must not silently coexist with an older long lease.
        if result.leases:
            until=min(result.leases.values())
            result.leases={op:until for op in result.leases}
        # A changed future prediction is not evidence that RAM is exhausted.
        # Retained pages cannot be reclaimed by freezing: permanently close new
        # admissions until foreground exit, and watch the original reserve plus
        # the observed stop-reaction growth. This is a feedback fallback, not a
        # claim that an unrecognised future curve has become predictable.
        retained=any(c.ever_started for c in clocks.values())
        if not foreground_done and retained and result.parking_deficit:self.retention_hold=True
        result.retention_hold=self.retention_hold and not foreground_done
        if result.retention_hold:
            result.freeze=list(dict.fromkeys(result.freeze+active));result.resume=[];result.leases={}
        if not foreground_done and retained:
            rates={self.fg:self.forecaster[self.fg].recent_rate()}
            rates.update({op:self.forecaster[op].recent_rate() for op in active})
            required=self.reserve+sum(math.ceil(rate*self.c['reaction_s'])+self.c['growth_uncertainty_bytes'] for rate in rates.values())
            result.emergency_deficit=available<required
            result.evidence['live_reserve_guard']=dict(available_bytes=available,required_bytes=required,
                reserve_bytes=self.reserve,rates_bytes_s=rates,reaction_s=self.c['reaction_s'],
                uncertainty_per_growing_task_bytes=self.c['growth_uncertainty_bytes'],
                mode='retention_hold' if result.retention_hold else 'normal_admission',
                limitation='observed growth is not a hard bound on unseen allocation jumps')
            if result.emergency_deficit:
                result.freeze=list(dict.fromkeys(result.freeze+active));result.resume=[];result.leases={}
        return result


def audit_decisions(rows,models,config,reserve_bytes):
    """Replay logged observations; also check budget arithmetic independently.

    Reproducibility evidence, not proof that a historical predictor is correct.
    """
    policy=SegmentPolicy(models,config,reserve_bytes);errors=[];count=0
    for row in rows:
        count+=1;now=row['monotonic_s'];clocks={op:TaskClock(**{k:v for k,v in c.items() if k in TaskClock.__dataclass_fields__}) for op,c in row['clocks'].items()}
        policy.observe(now,row['current_bytes']);d=policy.decide(now,row['elapsed_s'],row['available_bytes'],row['current_bytes'],clocks,row['foreground_done'])
        for name,expected in [('freeze',d.freeze),('resume',d.resume),('leases',d.leases),('parking_deficit',d.parking_deficit),('retention_hold',d.retention_hold),('emergency_deficit',d.emergency_deficit)]:
            if row[name]!=expected:errors.append(dict(tick=row['tick'],field=name,reason='decision replay mismatch'))
        guard=row['evidence'].get('live_reserve_guard')
        if guard is not None and guard!=d.evidence.get('live_reserve_guard'):errors.append(dict(tick=row['tick'],field='live_reserve_guard',reason='live reserve proof mismatch'))
        for op in row['leases']:
            e=row['evidence'][op];growth=sum(e['background_growth_bytes'].values())
            short=e['reserve_bytes']+e['foreground_short_growth_bytes']+growth
            parked=e['reserve_bytes']+e['foreground_remaining_growth_bytes']+growth
            if short!=e['short_required_bytes'] or parked!=e['parking_required_bytes'] or row['available_bytes']<max(short,parked):
                errors.append(dict(tick=row['tick'],operation=op,reason='lease budget arithmetic/capacity invalid'))
            if row['leases'][op]<=now:errors.append(dict(tick=row['tick'],operation=op,reason='already expired lease'))
    return dict(rows=count,errors=errors,role='deterministic observation replay and budget arithmetic; not a prediction-accuracy guarantee')
