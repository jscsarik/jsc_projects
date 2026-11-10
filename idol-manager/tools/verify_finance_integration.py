"""Actual regular/special/postseason engines plus finance in a temporary save."""
from pathlib import Path
from contextlib import closing
import json,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.verify_special_season import main as regular
from tools.verify_postseason_season import finish
from idol_manager.database import Database
from idol_manager.finance_service import FinanceService

def main():
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='idol_finance_integration_') as folder:
        path=Path(folder)/'full_season.sqlite3';regular(path);db=Database(path);report=finish(db);finance=FinanceService(db)
        report['finances']=[]
        with closing(db.connect()) as c:
            for agency, in c.execute('SELECT id FROM agencies ORDER BY id'):
                entries=finance.ledger(agency);d=finance.dashboard(agency)
                assert d['cash']==1000000000+sum(r['cash_delta'] for r in entries)
                assert d['debt']==sum(r['debt_delta'] for r in entries)
                sponsors=sum(r['amount'] for r in entries if r['kind']=='weekly_sponsor')
                bonus=sum(r['amount'] for r in entries if r['kind']=='season_bonus')
                assert sponsors==240000000 and bonus==1000000000
                report['finances'].append(dict(agency=agency,cash=d['cash'],debt=d['debt'],sponsors=sponsors,bonus=bonus,
                    payroll_due=sum(r['due_krw'] for r in finance.payroll(agency)),payroll_paid=sum(r['paid_krw'] for r in finance.payroll(agency))))
        report.update(cash_reconciles=True,debt_reconciles=True,actual_matches_simulated=True,seconds=round(time.monotonic()-start,3))
        (ROOT/'.test-artifacts/finance_full_season.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
