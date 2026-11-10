"""Playback groups persisted judgments; this module cannot calculate a match."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReplayFrame:
    phase: str
    round_number: int
    tick: int
    events: tuple


def replay_frames(result,*,base_attempts=60):
    if not result.events:
        return ()
    groups = {('regular',0,tick):[] for tick in range(1,base_attempts+1)}
    for event in result.events:
        key = ('deathmatch',event.round_number,event.tick) if event.phase=='deathmatch' else ('regular',0,event.tick)
        groups.setdefault(key,[]).append(event)
    keys = sorted(groups,key=lambda k:(k[0]=='deathmatch',k[1],k[2]))
    return tuple(ReplayFrame(*key,tuple(groups[key])) for key in keys)
