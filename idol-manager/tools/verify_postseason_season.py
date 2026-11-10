"""Real 585+6 regular season followed by actual finals and 217-day rollover."""
from pathlib import Path
import sys,json,tempfile,time,sqlite3
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.verify_special_season import main as regular
from idol_manager.database import Database
from idol_manager.finals_service import FinalsService
from idol_manager.calendar_service import CalendarService


def finish(db):
    # The old v15 fixture had no photos and stopped before annual recruitment
    # existed. Supply distinct test-only photos and process the real draft.
    temp=tempfile.TemporaryDirectory(prefix='idol_finals_annual_')
    root=Path(temp.name)
    from tests.test_annual_draft import png
    for n in range(70):png(root/'assets/idols'/f'후속 신인 {n}.png',5000+n)
    finals=FinalsService(db);calendar=CalendarService(db,root=root)
    while calendar.state().date.absolute_day<217:
        day=calendar.state().date
        if day.day_in_season==189:
            # New founding contracts have real expiry dates. Renew the player's
            # roster through the same public negotiation API before the market.
            from idol_manager.market_service import MarketService
            market=MarketService(db)
            player=db.connect()
            try:agency=player.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()[0]
            finally:player.close()
            for person in market.public_people(agency=agency):
                if person['career_status'] in ('first_team','second_team') and person['end_season']==day.season:
                    identity=market.start_negotiation(agency,person['id'],'renew')
                    market.offer(identity,person['market']*11//10,1,request_id='verify-renew:'+str(day.season)+':'+person['id'])
        if day.day_in_season==196:
            from idol_manager.annual_draft import AnnualDraftService
            from idol_manager.market_service import MarketService
            api=AnnualDraftService(db,root,MarketService(db));api.start()
            while api.state()['turn']:
                state=api.state();turn=state['turn']
                if turn['agency_id']!=state['player']:api.ai_step();continue
                person=next(p for p in state['candidates'] if p['age']<17)
                api.pick(turn['agency_id'],person['id'],expected_pick=turn['pick_number'])
        for row in finals.rows():
            if row['status']!='completed':finals.play(row['id'])
        if day.weekday()==0:
            from idol_manager.squads import SquadService
            squads=SquadService(db)
            for squad in ('first_team','second_team'):
                snapshot=squads.snapshot()
                if not dict(snapshot.leaders).get(squad):
                    person=next(p.id for p in snapshot.members if p.squad==squad)
                    squads.set_leader(squad,person,expected_revision=snapshot.revision)
        calendar.advance_day(expected_absolute_day=day.absolute_day)
    with closing(db.connect()) as c:
        report={'regular':c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],
            'specials':c.execute("SELECT COUNT(*) FROM special_events WHERE season=1 AND status='completed'").fetchone()[0],
            'finals':[dict(r) for r in c.execute('SELECT kind,round_number,COUNT(*) games FROM final_contests WHERE season=1 GROUP BY kind,round_number')],
            'honors':[dict(r) for r in c.execute('SELECT * FROM season_honors')],
            'finance_sponsor_rows':c.execute("SELECT COUNT(*) FROM finance_ledger WHERE season=1 AND kind='weekly_sponsor'").fetchone()[0],
            'finance_payroll_rows':c.execute('SELECT COUNT(*) FROM finance_payroll WHERE season=1').fetchone()[0],
            'finance_bonus_rows':c.execute("SELECT COUNT(*) FROM finance_ledger WHERE season=1 AND kind='season_bonus'").fetchone()[0],
            'date':str(calendar.state().date),'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],
            'foreign_keys':[tuple(r) for r in c.execute('PRAGMA foreign_key_check')],'actual_save_modified':False}
        assert report['regular']==585 and report['specials']==6
        assert (report['finance_sponsor_rows'],report['finance_payroll_rows'],report['finance_bonus_rows'])==(240,960,10)
        for agency,balance in c.execute('SELECT id,funds_krw FROM agencies'):
            assert balance==1000000000+c.execute('SELECT COALESCE(SUM(cash_delta),0) FROM finance_ledger WHERE agency_id=?',(agency,)).fetchone()[0]
        assert c.execute("SELECT COUNT(*) FROM season_honors WHERE kind='champion'").fetchone()[0]==1
        assert report['integrity']=='ok' and not report['foreign_keys']
    temp.cleanup()
    return report


if __name__=='__main__':
    start=time.monotonic()
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'season.sqlite3';regular(path)
        report=finish(Database(path));report['seconds']=round(time.monotonic()-start,3)
        (ROOT/'.test-artifacts/postseason_full_season.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
