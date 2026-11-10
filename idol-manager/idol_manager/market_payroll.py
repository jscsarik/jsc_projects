from .game_clock import regular_day
"""Confirmed v19 daily allocation, using the v18 payroll writer and journals."""
from .finance_service import salary_parts,round_10000

def allocated_base(c,contract,season,cycle,start,end):
    stop=end+1
    days=max(0,min(stop,contract['end_day'] if contract['end_day'] is not None else stop)-max(start,contract['start_day']))
    base=salary_parts(contract['annual_krw'],cycle,0,0)[0]
    amount=round_10000(base*days,28)
    term=c.execute('SELECT root_id FROM market_terms WHERE contract_id=?',(contract['id'],)).fetchone()
    root=term[0] if term else contract['id']
    segments=c.execute('''SELECT x.* FROM finance_contracts x JOIN market_terms t ON t.contract_id=x.id
        WHERE t.root_id=? AND x.start_day<? AND (x.end_day IS NULL OR x.end_day>?)
        AND (x.end_day IS NULL OR x.end_day>x.start_day) ORDER BY x.start_day,x.id''',(root,stop,start)).fetchall()
    coverage=[max(0,min(stop,r['end_day'] if r['end_day'] is not None else stop)-max(start,r['start_day'])) for r in segments]
    # Correct a transfer's rounding only in the final segment, without ever
    # editing a previously settled invoice. Salary changes use distinct roots.
    if segments and sum(coverage)==28 and all(r['annual_krw']==contract['annual_krw'] for r in segments) and segments[-1]['id']==contract['id']:
        amount=base-sum(round_10000(base*n,28) for n in coverage[:-1])
    return amount,days

def projected_salary(c,agency,season,week,*,include_max_bonus=False):
    start=regular_day(season,week-3);end=start+27
    runtime=c.execute('SELECT rollout_day FROM finance_runtime WHERE game_id=1').fetchone()
    if not runtime:return 0
    contracts=c.execute("""SELECT * FROM finance_contracts WHERE agency_id=? AND (kind='pro' OR id IN (SELECT contract_id FROM paid_draft_contracts)) AND start_day<?
        AND (end_day IS NULL OR end_day>?) AND (end_day IS NULL OR end_day>start_day)""",(agency,end+1,start)).fetchall()
    if start<runtime[0]:contracts=[r for r in contracts if r['source']=='market19' and r['start_day']>=runtime[0]]
    bases=[allocated_base(c,r,season,week//4,start,end)[0] for r in contracts]
    return sum(base+(round_10000(base,10) if include_max_bonus else 0) for base in bases)
