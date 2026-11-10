"""Independent, replayable team-only bonuses; never individual ability trials."""
import random

def bonus_rng(rng):return random.Random('franchise-v1:'+repr(rng.getstate()))

def trial(team,successes,tick,after_sequence,rng):
    count=sum(p.franchise for p in team.players)
    if len(team.players)<3 or not count or len(successes)!=len(team.players) or not all(successes):return None
    probability=min(45,count*15)/100;roll=rng.random()
    return dict(agency_id=team.agency_id,tick=tick,after_sequence=after_sequence,
                franchise_count=count,probability=probability,roll=roll,success=roll<probability)
