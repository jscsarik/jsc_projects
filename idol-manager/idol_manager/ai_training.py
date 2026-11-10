"""Once-per-Tuesday AI focus plans, inside the calendar transaction."""
import json
from collections import Counter
from .config import SKILLS
from .game_clock import current_game_date,GameDate
from .finance_service import cash,debt,load_rules
from .finance_policy import RESERVE_WEEKS
from .market_payroll import projected_salary
from .annual_policy import style_for
from .training_service import week_start,save_sheet,FOCUS_COST
from .training_policy import choose


def available_budget(c,agency,day,style):
    # The existing optional-spend rule excludes all debt, including future
    # release installments. Nothing is paid from hoped-for sponsorship.
    if debt(c,agency):return 0
    runtime=c.execute('SELECT * FROM finance_runtime WHERE game_id=1').fetchone()
    rules=json.loads(runtime['rules_json']) if runtime else load_rules()
    counts=Counter(r[0] for r in c.execute('SELECT career_status FROM roster_memberships WHERE agency_id=?',(agency,)))
    weekly=counts['second_team']*rules['second_weekly_krw']+counts['trainee']*rules['trainee_weekly_krw']
    # This week's already-incurred costs remain owed after exceptional moves.
    incurred=0
    for role,key in (('second_team','second_weekly_krw'),('trainee','trainee_weekly_krw')):
        ids={r[0] for r in c.execute('SELECT person_id FROM development_days WHERE agency_id=? AND role=? AND absolute_day BETWEEN ? AND ?',(agency,role,week_start(day),day.absolute_day))}
        ids.update(r[0] for r in c.execute('SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status=?',(agency,role)))
        incurred+=len(ids)*rules[key]
    season=day.season
    week=next((w for w in rules['pay_weeks'] if day.is_regular and w>=day.week),None)
    if week is None:season+=1;week=rules['pay_weeks'][0]
    # Reuse exact contract allocation and per-contract bonus rounding.
    payroll=projected_salary(c,agency,season,week,include_max_bonus=True)
    weeks=max(RESERVE_WEEKS.get(style,2),week-day.week+1 if season==day.season else week)
    operating=max(weekly,incurred)+(weeks-1)*weekly
    promises=c.execute("""SELECT COALESCE(SUM(value),0) FROM
        (SELECT MAX(b.annual) AS value FROM market_bids b JOIN market_auctions a ON a.id=b.auction_id
        WHERE b.agency_id=? AND a.status='open' GROUP BY a.id)""",(agency,)).fetchone()[0]
    promised_pay=(promises*110+599)//600
    reserved_cash=0
    for t in c.execute("""SELECT t.agency_a,t.agency_b,v.terms_json FROM market_trades t JOIN market_trade_versions v
        ON v.trade_id=t.id AND v.version=t.version WHERE t.status='accepted_pending' AND (t.agency_a=? OR t.agency_b=?)""",(agency,agency)):
        amount=json.loads(t['terms_json']).get('cash',0)
        reserved_cash+=max(0,amount if t['agency_a']==agency else -amount)
    return max(0,cash(c,agency)-payroll-operating-promised_pay-reserved_cash)


def plan(c,root):
    day=current_game_date(c)
    if not day or day.is_founding or day.weekday()!=1 or not(day.is_regular or day.is_postseason):return
    player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
    if not player:return
    for agency, in c.execute('SELECT id FROM agencies WHERE id!=? ORDER BY id',(player[0],)).fetchall():
        sheet=c.execute('SELECT confirmed,revision FROM training_sheets WHERE week_start=? AND agency_id=?',(week_start(day),agency)).fetchone()
        if sheet and sheet['confirmed']:continue
        players=[]
        for r in c.execute("SELECT person_id,career_status FROM roster_memberships WHERE agency_id=? AND career_status IN ('first_team','second_team') ORDER BY person_id",(agency,)).fetchall():
            # Explicit public columns: PA and secret prospect data never enter policy.
            skills=dict(c.execute('SELECT skill,value FROM abilities WHERE person_id=?',(r['person_id'],)))
            players.append(dict(id=r['person_id'],career_status=r['career_status'],skills=[skills[s] for s in SKILLS]))
        style=style_for(root,agency)
        choices=choose(players,available_budget(c,agency,day,style),style,cost=FOCUS_COST)
        save_sheet(c,agency,choices,confirm=True,expected_revision=sheet['revision'] if sheet else 0)
