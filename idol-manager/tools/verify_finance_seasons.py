"""10-season accounting-only balance analysis, no original save and no fake matches."""
from contextlib import closing
from pathlib import Path
import json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests import test_finance as fixture
from idol_manager.finance_service import close_season

def main(seasons=10):
    start=time.monotonic();fixture.FinanceTests.setUpClass();t=fixture.FinanceTests();t.setUp()
    try:
        report={'mode':'accounting_only_fixed_rosters_no_match_simulation','seasons':seasons,'agencies':10,
            'assumptions':'16 pro players: annual 30m, 5 first/11 second; no matches so no first activity bonus; no transfer/injury/growth simulation','yearly':[]}
        for season in range(1,seasons+1):
            for w in range(1,25):t.week(w,season)
            with closing(t.db.connect()) as c,c:
                c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json) VALUES (?,'completed','{}','[]')",(season,))
                close_season(c,season,(season-1)*217+183)
            balances=[a.funds_krw for a in t.service.agencies()]
            assert len(set(balances))==1 and balances[0]==1000000000+season*766600000
            for a in t.service.agencies():
                ledger=t.finance.ledger(a.id)
                assert a.funds_krw==1000000000+sum(r['cash_delta'] for r in ledger)
                assert sum(r['debt_delta'] for r in ledger)==t.finance.dashboard(a.id)['debt']==0
            report['yearly'].append({'season':season,'cash_each':balances[0],'debt_each':0,'sponsor_each':240000000,
                'base_salary_each':480000000,'second_reduction_each':33000000,'operating_each':26400000,'bonus_each':1000000000})
            print('Accounting season',season,'cash per agency',balances[0],flush=True)
        with closing(t.db.connect()) as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
            report.update(sponsor_rows=c.execute("SELECT COUNT(*) FROM finance_ledger WHERE kind='weekly_sponsor'").fetchone()[0],
                payroll_rows=c.execute('SELECT COUNT(*) FROM finance_payroll').fetchone()[0],bonus_rows=c.execute("SELECT COUNT(*) FROM finance_ledger WHERE kind='season_bonus'").fetchone()[0],
                integrity='ok',cash_reconciles=True,debt_reconciles=True,actual_save_modified=False,seconds=round(time.monotonic()-start,3))
        (ROOT/'.test-artifacts/finance_10_seasons.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:t.doCleanups();fixture.FinanceTests.doClassCleanups()
if __name__=='__main__':main()
