"""Three-season contract/accounting stress test, not a match simulation."""
from pathlib import Path
from contextlib import closing
import json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests import test_market as fixture
from tests.test_finance import FinanceTests
from idol_manager.market_service import _settle_auctions
from idol_manager.finance_service import close_season
from idol_manager.conditions import repair_ai_leaders

def main():
    start=time.monotonic();fixture.MarketTests.setUpClass();t=fixture.MarketTests();t.setUp()
    try:
        agencies=[a.id for a in t.service.agencies()]
        with closing(t.db.connect()) as c:
            protected={table:[tuple(r) for r in c.execute('SELECT * FROM '+table+' ORDER BY 1')] for table in ('people','abilities','draft_picks','scheduled_matches','special_events')}
        for season in range(1,4):
            for w in range(1,25):FinanceTests.week(t,w,season)
            with t.market.write() as c:
                c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json) VALUES (?,'completed','{}','[]')",(season,));close_season(c,season,(season-1)*217+183)
            t.day((season-1)*217+189)
            for agency in agencies:
                for p in t.market.public_people(agency=agency):
                    if p['career_status'] not in ('first_team','second_team'):continue
                    n=t.market.start_negotiation(agency,p['id'],'renew')
                    r=t.market.offer(n,66000000,1,request_id=f'stress:renew:{season}:{agency}:{p["id"]}')
                    assert r['accepted']
            t.day((season-1)*217+203)
            terms=t.trade_terms();trade=t.market.propose_trade('ador','jyp',dict(terms,cash=1000000),request_id=f'stress:trade:{season}')
            assert t.market.trade_reply(trade,'jyp','accept',expected_version=1)=='completed'
            p=t.member('ador');q=t.member('jyp')
            t.market.release('ador',p,'immediate',request_id=f'stress:release:a:{season}')
            t.market.release('jyp',q,'immediate',request_id=f'stress:release:b:{season}')
            t.market.bid('jyp',p,66000000,1,request_id=f'stress:fa:a:{season}')
            t.market.bid('ador',q,66000000,1,request_id=f'stress:fa:b:{season}')
            t.day((season-1)*217+205)
            with t.market.write() as c:_settle_auctions(c,(season-1)*217+205,lambda:season)
            t.day((season-1)*217+210)
            with t.market.write() as c:repair_ai_leaders(c,(season-1)*217+210)
            snapshot=t.service.squads.snapshot()
            for squad in ('first_team','second_team'):
                if not dict(snapshot.leaders).get(squad):
                    member=next(p.id for p in snapshot.members if p.squad==squad);t.service.squads.set_leader(squad,member,expected_revision=snapshot.revision);snapshot=t.service.squads.snapshot()
            with closing(t.db.connect()) as c:
                assert not c.execute('''SELECT person_id FROM finance_contracts WHERE start_day<=? AND (end_day IS NULL OR end_day>?) GROUP BY person_id HAVING COUNT(*)>1''',((season-1)*217+210,(season-1)*217+210)).fetchone()
                assert all(tuple(r)==(16,5,11) for r in c.execute("SELECT COUNT(*),SUM(career_status='first_team'),SUM(career_status='second_team') FROM roster_memberships WHERE career_status IN ('first_team','second_team') GROUP BY agency_id"))
                for agency,balance in c.execute('SELECT id,funds_krw FROM agencies'):
                    assert balance==1000000000+c.execute('SELECT COALESCE(SUM(cash_delta),0) FROM finance_ledger WHERE agency_id=?',(agency,)).fetchone()[0]
                assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
            print('Market accounting season',season,'completed',flush=True)
        with closing(t.db.connect()) as c:
            for table,rows in protected.items():assert rows==[tuple(r) for r in c.execute('SELECT * FROM '+table+' ORDER BY 1')],table
            report=dict(mode='market_and_accounting_only_no_matches_or_new_annual_draft',seasons=3,
                accepted_offers=c.execute('SELECT COUNT(*) FROM market_offers WHERE accepted=1').fetchone()[0],
                completed_trades=c.execute("SELECT COUNT(*) FROM market_trades WHERE status='completed'").fetchone()[0],
                releases=c.execute('SELECT COUNT(*) FROM market_release_plans').fetchone()[0],
                completed_auctions=c.execute("SELECT COUNT(*) FROM market_auctions WHERE status='completed'").fetchone()[0],
                payroll_rows=c.execute('SELECT COUNT(*) FROM finance_payroll').fetchone()[0],
                contracts=c.execute('SELECT COUNT(*) FROM finance_contracts').fetchone()[0],
                protected_data_preserved=True,cash_reconciles=True,one_active_contract=True,integrity='ok',actual_save_modified=False,seconds=round(time.monotonic()-start,3))
        (ROOT/'.test-artifacts/market_three_cycles.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    finally:t.doCleanups();fixture.MarketTests.doClassCleanups()
if __name__=='__main__':main()
