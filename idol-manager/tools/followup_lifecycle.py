"""Additional QA branch: legal finite contracts, release debt, FA and debut.

Copies the completed reproducibility run. No SQL changes to dates, contracts,
cash or match results: all subsequent changes use ordinary game services.
"""
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
import json,sqlite3,shutil,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.followup_long_run import LongSimulation,Monitor,save,protect_connections

class Lifecycle(LongSimulation):
    def negotiate(self,person,purpose):
        market=self.service.market;n=market.start_negotiation('ador',person['id'],purpose)
        amount=30000000 if purpose=='debut' else ((person['market']*110+999999)//1000000)*10000
        for attempt in range(3):
            offered=market.offer(n,amount,1,request_id=f'qa-life:{n}:{attempt}')
            self.lifecycle.append(dict(day=self.service.calendar.state().date.absolute_day,purpose=purpose,person=person['id'],accepted=bool(offered['accepted'])))
            if offered['accepted']:return True
            if purpose!='debut':amount=((amount*105+999999)//1000000)*10000
        return False

    def player_policy(self):
        super().player_policy();d=self.service.calendar.state().date;m=self.service.market
        if d.is_regular or d.is_postseason:return
        if d.season==4 and d.week==1:
            people=sorted((p for p in m.public_people(agency='ador') if p['career_status']=='second_team'),key=lambda p:(p['average'],p['id']))[:3]
            renewed=[p for p in people if self.negotiate(p,'renew')]
            for person in renewed[:2]:m.release('ador',person['id'],'installments',request_id='qa-life-release:'+person['id'])
        if d.season==4 and d.week==3:
            own=m.public_people(agency='ador')
            if sum(p['career_status'] in ('first_team','second_team','pro_pending') for p in own)<16:
                available=sorted((p for p in m.public_people(available=True) if p['age']>=17),key=lambda p:(-p['average'],p['id']))
                if available:
                    p=available[0];amount=((p['market']*110+999999)//1000000)*10000
                    m.bid('ador',p['id'],amount,1,request_id='qa-life-bid:'+p['id'])
        if d.season==4 and d.week==4:
            for p in sorted(m.public_people(agency='ador'),key=lambda p:(-p['average'],p['id'])):
                own=m.public_people(agency='ador')
                if sum(x['career_status'] in ('first_team','second_team','pro_pending') for x in own)>=16:break
                if p['career_status']=='trainee' and p['age']>=17:self.negotiate(p,'debut')

    def annual(self):
        # This QA player deliberately develops juniors; nine AI policies stay
        # unchanged. Keeping free pro slots permits the FA/debut scenarios.
        for plan in self.service.market.release_balances('ador'):
            if plan['remaining']>0:self.service.market.prepay_release('ador',plan['id'],expected_remaining=plan['remaining'])
        # Preserve the original QA failure and record the authorized resolution.
        for issue in self.issues:
            if 'FinanceError' in issue.get('error','') and '채무' in issue['error']:
                issue.update(fixed=True,resolution='User-authorized full release payoff through official API; original failure preserved')
        api=self.service.annual_draft;api.start()
        while True:
            state=api.state();turn=state['turn']
            if turn is None:return
            self.budget()
            if turn['agency_id']!='ador':api.ai_step();continue
            juniors=[p for p in state['candidates'] if p['age']<17]
            if not juniors:raise ValueError('QA junior policy has no eligible candidate')
            chosen=max(juniors,key=lambda p:(p['average'],p['id']))
            api.pick('ador',chosen['id'],expected_pick=turn['pick_number'])

def main():
    protect_connections();source=ROOT/'diagnostics/followup_b';folder=ROOT/'diagnostics/followup_lifecycle'
    if folder.exists() and not (folder/'run_manifest.json').exists():raise ValueError('Not a marked QA branch')
    folder.mkdir(exist_ok=True)
    if not (folder/'simulation.sqlite3').exists():
        with closing(sqlite3.connect((source/'simulation.sqlite3').as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(folder/'simulation.sqlite3')) as b:a.backup(b)
        for name in ('run_manifest.json','checkpoint.json','season_resources.json'):shutil.copyfile(source/name,folder/name)
    args=SimpleNamespace(output=folder,resource_root=ROOT/'diagnostics/followup_world',seed=261029,seasons=6,budget_seconds=86400,resume=True,allow_long_run=True)
    with Monitor() as monitor:status=Lifecycle(args).run()
    save('lifecycle_branch_resources.json',monitor.result())
    with closing(sqlite3.connect(folder/'simulation.sqlite3')) as c:
        history=dict(c.execute('SELECT kind,COUNT(*) FROM market_history WHERE absolute_day>=651 GROUP BY kind'))
        debts=c.execute("SELECT COUNT(*),SUM(original_krw),SUM(outstanding_krw) FROM finance_debts WHERE kind='release_scheduled'").fetchone()
    save('lifecycle_branch.json',dict(status=status,history=history,release_debts=debts,source='3-season reproducibility copy; official services only',summary=str(folder/'simulation_summary.json')))
    return 0 if status=='completed' else 2
if __name__=='__main__':raise SystemExit(main())
