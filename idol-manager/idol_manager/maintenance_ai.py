"""Roster upkeep windows reuse market contracts, public evaluation and squad AI."""
import sqlite3
from contextlib import contextmanager
from .game_clock import current_game_date

def run(c):
    from .market_service import MarketService,public_people,PRO,_budget
    from .market_rules import player_value
    from .squads import SquadService
    d=current_game_date(c)
    if not d or d.weekday()!=0:return
    class Bound(MarketService):
        @contextmanager
        def write(self):yield c
    api=Bound(None)
    player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
    if not player:return
    for agency, in c.execute('SELECT id FROM agencies WHERE id!=? ORDER BY id',(player[0],)).fetchall():
        c.execute('SAVEPOINT upkeep')
        try:
            members=list(public_people(c,agency=agency));pros=[p for p in members if p['career_status'] in PRO]
            trainees=[p for p in members if p['career_status']=='trainee' and p['age']>=17]
            team=[sum(p['skills'][i] for p in pros)/max(1,len(pros)) for i in range(8)]
            if trainees:
                target=max(trainees,key=lambda p:(player_value(p,team),p['id']))
                spare=[p for p in pros if p['career_status']=='second_team']
                if len(pros)>=16 and spare:
                    outgoing=min(spare,key=lambda p:(player_value(p,team),p['id']))
                    # A clear public-value improvement is required before paying a penalty.
                    if player_value(target,team)<=player_value(outgoing,team)+8:target=None
                    else:
                        _budget(c,agency,0 if target['inherited_debut'] else 30000000)
                        api.release(agency,outgoing['id'],'immediate',request_id=f'upkeep-release:{d.absolute_day}:{agency}')
                if target:
                    if target['inherited_debut']:api.promote_contracted_trainee(agency,target['id'])
                    else:
                        n=api.start_negotiation(agency,target['id'],'debut')
                        api.offer(n,30000000,1,request_id=f'upkeep-debut:{d.absolute_day}:{agency}')
                        status=c.execute('SELECT status FROM market_negotiations WHERE id=?',(n,)).fetchone()[0]
                        if status!='accepted':raise ValueError('No roster gain; keep the original professional.')
            # Existing squad composition/leader policy, without hidden PA.
            members=tuple(p for p in SquadService._members(c,agency) if p.squad in PRO)
            if len(members)>=5:
                plan=SquadService(None).policy.plan(members)
                changed=[p for p in members if p.squad!=('first_team' if p.id in plan.first_team_ids else 'second_team')]
                for p in changed:c.execute("UPDATE roster_memberships SET career_status='pro_pending' WHERE person_id=?",(p.id,))
                for p in changed:c.execute("UPDATE roster_memberships SET career_status=? WHERE person_id=?",('first_team' if p.id in plan.first_team_ids else 'second_team',p.id))
                SquadService._set_leader(c,agency,'first_team',plan.first_leader_id)
                SquadService._set_leader(c,agency,'second_team',plan.second_leader_id)
                c.execute('UPDATE squad_formations SET revision=revision+1 WHERE agency_id=?',(agency,))
                from .conditions import sync_rosters
                sync_rosters(c,d.absolute_day,'ai-maintenance')
            c.execute('RELEASE upkeep')
        except (ValueError,sqlite3.IntegrityError) as error:
            __import__('logging').getLogger(__name__).debug('%s upkeep rolled back: %s',agency,error)
            c.execute('ROLLBACK TO upkeep');c.execute('RELEASE upkeep')
