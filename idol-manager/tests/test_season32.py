"""Bounded calendar/contract checks, never reads or writes user saves."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import tempfile,unittest,random,sqlite3,json
from idol_manager.service import GameService
from idol_manager.database import Database
from idol_manager.game_clock import GameDate,regular_day,DAYS_PER_SEASON
from idol_manager.development_service import capture_day
from tests.test_annual_draft import png

class Season32Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='idol_32_');cls.addClassCleanup(cls.folder.cleanup)
        cls.root=Path(cls.folder.name)
        for i in range(500):png(cls.root/'assets/idols'/f'person{i:03}.png',i+1)
        svc=GameService(cls.root);svc.new_game();svc.draft_session.select_agency('ador');svc.draft.start(rng=random.Random(2))
        for number in range(1,161):
            svc.draft.pick(svc.draft.state().next_turn.agency_id,svc.draft.available_candidates()[0].id,expected_pick_number=number)
        with closing(svc.database.connect()) as c,c:
            c.execute("UPDATE founding_setup SET prep_day=1,status='active'");c.execute('UPDATE game_clock SET absolute_day=1')
            from idol_manager.founding import start_contracts
            start_contracts(c)
        for n in svc.market.negotiations():
            if n['purpose']=='founding' and n['status']=='open':svc.market.offer(n['id'],70000000,1,request_id='fixture:'+n['id'])
        with closing(svc.database.connect()) as c,c:c.execute('UPDATE founding_setup SET prep_day=6');c.execute('UPDATE game_clock SET absolute_day=6')
        members=svc.squads.snapshot().members;svc.squads.confirm_initial(tuple(m.id for m in members[:5]))
        for squad in ('first_team','second_team'):
            state=svc.squads.snapshot();svc.squads.set_leader(squad,next(m.id for m in state.members if m.squad==squad),expected_revision=state.revision)
        svc.calendar.advance_day(expected_absolute_day=6)
        cls.template=svc.database.path

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='idol_32_copy_');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.sqlite3'
        with closing(sqlite3.connect(self.template.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(self.path)) as dst:src.backup(dst)
        self.service=GameService(self.root,database_path=self.path);self.db=self.service.database
    def rows(self,q,args=()):
        with closing(self.db.connect()) as c:return [tuple(r) for r in c.execute(q,args)]
    def day(self,d):
        with closing(self.db.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=?',(d,))
    def prepare_annual(self):
        self.day(203)
        self.service.annual_draft.rescan()
        ranks=[a.id for a in self.service.agencies()]
        with closing(self.db.connect()) as c,c:
            c.execute("INSERT OR REPLACE INTO season_finals(season,status,frozen_json,standings_json,final_order_json) VALUES (1,'completed','{}','[]',?)",(json.dumps(ranks),))
        self.day(210);self.service.annual_draft.start()
        return self.service.annual_draft.state()

    def test_32_week_boundaries_and_first_draft_preserved(self):
        self.assertEqual(DAYS_PER_SEASON,224)
        cases={0:('prep',1),7:('regular',1),84:('regular',12),91:('maintenance',1),98:('regular',13),175:('regular',24),182:('post',1),196:('post',3),203:('off',1),217:('off',3),224:('prep',1),231:('regular',1)}
        for day,(phase,week) in cases.items():
            d=GameDate(day);actual='prep' if d.is_preparation else 'maintenance' if d.is_maintenance else 'regular' if d.is_regular else 'post' if d.is_postseason else 'off'
            self.assertEqual((actual,d.week),(phase,week));self.assertEqual(d.weekday(),0)
            self.assertEqual(GameDate(day-1).after(),d) if day else None
        self.assertEqual(GameDate(224).season,2)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM draft_picks'),[(160,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches'),[(585,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM special_events'),[(6,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM roster_memberships WHERE career_status='first_team'"),[(50,)])
        self.assertEqual(regular_day(1,13),98)

    def test_intake_30_youth_40_adults_and_minor_paid_trainee(self):
        state=self.prepare_annual()
        self.assertEqual(self.rows('SELECT SUM(initial_age<17),SUM(initial_age>=17),COUNT(*) FROM annual_entries'),[(30,40,70)])
        minor=next(p for p in state['candidates'] if p['new'] and p['age']<17)
        turn=state['turn'];self.service.annual_draft.pick(turn['agency_id'],minor['id'],expected_pick=turn['pick_number'])
        self.assertEqual(self.rows('SELECT annual_krw,kind FROM finance_contracts WHERE person_id=? AND end_day IS NULL',(minor['id'],)),[(20000000,'draft_trainee')])
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(minor['id'],)),[('trainee',)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM market_negotiations WHERE person_id=?',(minor['id'],)),[(0,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM annual_turns'),[(30,)])

    def test_adult_trainee_salary_and_contract_inheritance(self):
        state=self.prepare_annual();turn=state['turn'];agency=turn['agency_id']
        person=next(p for p in state['candidates'] if p['new'] and p['age']>=17)
        self.service.annual_draft.pick(agency,person['id'],expected_pick=turn['pick_number'],registration='trainee')
        with self.assertRaises(ValueError):self.service.annual_draft.offer(agency,29000000,2,expected_pick=turn['pick_number'],request_id='too-low')
        self.service.annual_draft.offer(agency,70000000,2,expected_pick=turn['pick_number'],request_id='adult')
        before=self.rows("SELECT id,annual_krw,start_day,end_day FROM finance_contracts WHERE person_id=? AND kind='draft_trainee'",(person['id'],))[0]
        self.assertEqual(before[1],70000000)
        self.day(224)
        outgoing=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team' LIMIT 1",(agency,))[0][0]
        self.day(203)
        renewal=self.service.market.start_negotiation(agency,outgoing,'renew')
        self.service.market.offer(renewal,70000000,1,request_id='room-renew')
        self.day(224)
        self.service.market.release(agency,outgoing,'immediate',request_id='room')
        self.service.market.promote_contracted_trainee(agency,person['id'],expected_contract=before[0])
        self.service.market.promote_contracted_trainee(agency,person['id'],expected_contract=before[0])
        self.assertEqual(before,self.rows('SELECT id,annual_krw,start_day,end_day FROM finance_contracts WHERE id=?',(before[0],))[0])
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(person['id'],)),[('second_team',)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM roster_memberships WHERE agency_id=? AND career_status IN ('first_team','second_team')",(agency,)),[(16,)])

    def test_halves_age_growth_and_no_maintenance_settlement(self):
        from idol_manager.development_service import apply_monday
        ages=dict(self.rows('SELECT person_id,age FROM idols'))
        with closing(self.db.connect()) as c,c:
            for day in (*range(84,91),*range(175,182)):capture_day(c,day)
            apply_monday(c,91);apply_monday(c,91)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM development_settlements WHERE absolute_day=91 AND kind='growth'").fetchone()[0],1)
            apply_monday(c,98)
            self.assertFalse(c.execute("SELECT 1 FROM development_settlements WHERE absolute_day=98 AND kind='growth'").fetchone())
            apply_monday(c,182);apply_monday(c,203)
        self.assertEqual(dict(self.rows('SELECT person_id,age FROM idols')),{p:a+2 for p,a in ages.items()})
        self.assertEqual(self.rows('SELECT regular_week FROM age_milestones ORDER BY regular_week'),[(12,),(24,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM development_settlements WHERE absolute_day=182 AND kind='growth'"),[(1,)])
        from idol_manager.finance_service import settle_week
        before=self.rows('SELECT funds_krw FROM agencies ORDER BY id')
        with closing(self.db.connect()) as c,c:settle_week(c,97)
        self.assertEqual(before,self.rows('SELECT funds_krw FROM agencies ORDER BY id'))

    def test_three_failed_adult_offers_and_ai_shared_philosophy(self):
        state=self.prepare_annual();turn=state['turn'];person=next(p for p in state['candidates'] if p['new'] and p['age']>=17)
        self.service.annual_draft.pick(turn['agency_id'],person['id'],expected_pick=1,registration='trainee')
        with patch('idol_manager.market_service.acceptance',return_value=0):
            for i,amount in enumerate((30000000,31500000,33100000)):
                self.service.annual_draft.offer(turn['agency_id'],amount,1,expected_pick=1,request_id=f'fail:{i}')
        self.assertEqual(self.rows('SELECT status FROM annual_turns WHERE pick_number=1'),[('failed',)])
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(person['id'],)),[(None,)])
        self.assertEqual(self.rows('SELECT consumed FROM market_draft_rights WHERE person_id=?',(person['id'],)),[(1,)])
        next_turn=self.service.annual_draft.state()['turn']
        if next_turn['agency_id']!='ador':
            original=self.db.connect
            def connect():
                c=original();c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and (col in ('potential','archetype') or t=='annual_secrets') else sqlite3.SQLITE_OK);return c
            with patch.object(self.db,'connect',side_effect=connect):self.assertTrue(self.service.annual_draft.ai_step())
        self.assertEqual(self.rows('SELECT philosophy,COUNT(*) FROM recruitment_philosophies GROUP BY philosophy ORDER BY philosophy'),[('balanced',4),('development',2),('specialist',3)])

    def test_paid_trainee_payroll_uses_negotiated_salary_once(self):
        state=self.prepare_annual();turn=state['turn'];person=next(p for p in state['candidates'] if p['new'] and p['age']>=17)
        self.service.annual_draft.pick(turn['agency_id'],person['id'],expected_pick=1,registration='trainee')
        self.service.annual_draft.offer(turn['agency_id'],70000000,2,expected_pick=1,request_id='pay')
        from idol_manager.finance_service import settle_week
        end=regular_day(2,4,6)
        with closing(self.db.connect()) as c,c:
            for day in range(regular_day(2,1),end+1):capture_day(c,day)
            settle_week(c,end);settle_week(c,end)
        self.assertEqual(self.rows('SELECT annual_krw,kind FROM finance_contracts WHERE person_id=?',(person['id'],)),[(70000000,'draft_trainee')])
        paid=self.rows('SELECT base_krw,due_krw FROM finance_payroll WHERE person_id=?',(person['id'],))
        self.assertEqual(len(paid),1);self.assertEqual(paid[0][0],11670000);self.assertEqual(paid[0][0],paid[0][1])

    def legacy_copy(self):
        # Convert only this disposable test DB back to a well-defined 31-week
        # representation; then exercise the real v24->v25 backup/migration.
        from idol_manager.season32_schema import DATE_COLUMNS,json_dates
        def inverse(day):
            if day is None:return None
            if day<0:return day
            season,offset=divmod(day,224)
            if offset<7:return -7+offset if season==0 else (season-1)*217+210+offset
            if 91<=offset<98:raise ValueError('No legacy midpoint equivalent')
            return season*217+offset-(7 if offset<91 else 14)
        with closing(self.db.connect()) as c,c:
            # A genuine v24 fixture cannot retain schemas added in v26/v28.
            for name in ('franchise_join','franchise_move'):c.execute('DROP TRIGGER IF EXISTS '+name)
            for name in ('franchise_seasons','franchise_stints','maintenance_condition_resets'):c.execute('DROP TABLE IF EXISTS '+name)
            c.execute('PRAGMA defer_foreign_keys=ON');triggers=c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
            for name,sql in triggers:c.execute('DROP TRIGGER '+name)
            c.create_function('legacy_day',1,inverse)
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            columns={t:[r[1] for r in c.execute('PRAGMA table_info('+t+')')] for t in tables}
            for table in tables:
                if table in ('legacy_game_clock','season32_adoption','age_milestones'):continue
                names=[n for n in columns[table] if n in DATE_COLUMNS]
                if names:c.execute('UPDATE '+table+' SET '+','.join(n+'='+('MAX(0,legacy_day('+n+'))' if n=='rollout_day' else 'legacy_day('+n+')')+'+7000000000' for n in names))
            for table in tables:
                if table in ('legacy_game_clock','season32_adoption','age_milestones'):continue
                names=[n for n in columns[table] if n in DATE_COLUMNS]
                if names:c.execute('UPDATE '+table+' SET '+','.join(n+'='+n+'-7000000000' for n in names))
                for column in columns[table]:
                    if column.endswith('_json'):
                        for rowid,raw in c.execute('SELECT rowid,'+column+' FROM '+table+' WHERE '+column+' IS NOT NULL').fetchall():
                            try:
                                with patch('idol_manager.season32_schema.map_day',side_effect=inverse):value=json_dates(json.loads(raw))
                                if value!=json.loads(raw):c.execute('UPDATE '+table+' SET '+column+'=? WHERE rowid=?',(json.dumps(value),rowid))
                            except (TypeError,ValueError):pass
            for name,sql in triggers:c.execute(sql)
            c.execute('PRAGMA user_version=24')

    def test_legacy_migration_preserves_results_money_and_attributes(self):
        self.day(9);self.service.calendar.ensure_current_schedule()
        match=self.rows('SELECT id FROM scheduled_matches WHERE week=1 AND weekday=2 ORDER BY match_order LIMIT 1')[0][0]
        result=self.service.matches.play(match)
        protected={t:self.rows('SELECT * FROM '+t+' ORDER BY 1') for t in ('abilities','idols','agencies','roster_memberships','draft_picks','match_results','match_team_stats','match_events')}
        contracts=self.rows('SELECT id,annual_krw FROM finance_contracts ORDER BY id')
        self.legacy_copy()
        db=Database(self.path);self.assertTrue(db.last_backup_path.exists())
        self.assertEqual(self.rows('SELECT absolute_day FROM game_clock'),[(9,)])
        for t,rows in protected.items():
            actual=self.rows('SELECT * FROM '+t+' ORDER BY 1')
            if t=='match_results':
                rows=[r[:4]+(json.loads(r[4]),)+r[5:] for r in rows];actual=[r[:4]+(json.loads(r[4]),)+r[5:] for r in actual]
            self.assertEqual(rows,actual,t)
        self.assertEqual(contracts,self.rows('SELECT id,annual_krw FROM finance_contracts ORDER BY id'))
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches'),[(585,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM special_events'),[(6,)])
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])
        self.assertIsNone(Database(self.path).last_backup_path)

    def test_legacy_weekly_repayment_does_not_skip_inserted_monday(self):
        self.legacy_copy()
        with closing(self.db.connect()) as c,c:
            person=c.execute("SELECT person_id FROM roster_memberships WHERE agency_id='ador' LIMIT 1").fetchone()[0]
            c.execute("INSERT INTO market_release_plans(id,person_id,agency_id,absolute_day,total,method,next_day) VALUES ('weekly-fixture',?,'ador',77,0,'installments',84)",(person,))
        Database(self.path)
        self.assertEqual(self.rows("SELECT next_day FROM market_release_plans WHERE id='weekly-fixture'"),[(91,)])

    def test_prepared_legacy_save_is_rejected_without_changes(self):
        self.day(9);self.service.calendar.ensure_current_schedule()
        match=self.rows('SELECT id FROM scheduled_matches WHERE week=1 AND weekday=2 ORDER BY match_order LIMIT 1')[0][0]
        self.service.matches._prepare(match,None,None)
        self.legacy_copy()
        with closing(self.db.connect()) as c:before=list(c.iterdump())
        with self.assertRaises(RuntimeError):Database(self.path)
        with closing(self.db.connect()) as c:self.assertEqual(before,list(c.iterdump()))

    def test_existing_half_birthday_is_not_reissued_after_conversion(self):
        self.legacy_copy()
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=80')
            c.execute("INSERT INTO development_settlements VALUES ('old-birthday',1,77,'birthday',77,77,'1','old')")
            c.execute('UPDATE idols SET age=age+1,health=MAX(0,health-1)')
        before=self.rows('SELECT person_id,age,health FROM idols ORDER BY person_id')
        Database(self.path)
        from idol_manager.development_service import settle_birthday
        with closing(self.db.connect()) as c,c:
            runtime=c.execute('SELECT * FROM development_runtime').fetchone();settle_birthday(c,91,runtime,json.loads(runtime['rules_json']))
        self.assertEqual(before,self.rows('SELECT person_id,age,health FROM idols ORDER BY person_id'))
        self.assertEqual(self.rows('SELECT regular_week FROM age_milestones'),[(12,)])

    def test_ai_midpoint_upkeep_paid_contract_and_repeat(self):
        self.day(91)
        from idol_manager.market_service import _new_contract,_move,process_market
        person=self.rows("SELECT person_id FROM initial_draft_undrafted ORDER BY person_id LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE abilities SET value=100,potential=100 WHERE person_id=?',(person,));c.execute('UPDATE idols SET average=100,age=18 WHERE person_id=?',(person,))
            contract=_new_contract(c,person,'jyp',35000000,2,'draft_trainee',finite_trainee=True)
            c.execute('INSERT INTO paid_draft_contracts VALUES (?,1,1)',(contract['id'],));_move(c,person,'jyp','trainee','trainee',contract,'fixture-older-contract')
            original=tuple(c.execute('SELECT id,annual_krw,start_day,end_day FROM finance_contracts WHERE id=?',(contract['id'],)).fetchone())
            c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and col in ('potential','archetype') else sqlite3.SQLITE_OK)
            process_market(c,91)
        self.assertIn(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(person,))[0][0],('first_team','second_team'))
        self.assertEqual(original,self.rows('SELECT id,annual_krw,start_day,end_day FROM finance_contracts WHERE id=?',(contract['id'],))[0])
        funds=self.rows('SELECT funds_krw FROM agencies ORDER BY id')
        with closing(self.db.connect()) as c,c:process_market(c,91)
        self.assertEqual(funds,self.rows('SELECT funds_krw FROM agencies ORDER BY id'))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM roster_memberships WHERE agency_id='jyp' AND career_status IN ('first_team','second_team')"),[(16,)])

    def test_full_annual_thirty_turns_without_professional_overflow(self):
        self.prepare_annual()
        for _ in range(100):
            state=self.service.annual_draft.state();turn=state['turn']
            if not turn:break
            if turn['agency_id']!='ador':self.service.annual_draft.ai_step();continue
            if turn['status']=='scheduled':
                self.service.annual_draft.pick('ador',state['candidates'][0]['id'],expected_pick=turn['pick_number'],registration='trainee')
            else:self.service.annual_draft.offer('ador',70000000,1,expected_pick=turn['pick_number'],request_id='player:'+str(turn['pick_number']))
        self.assertIsNone(self.service.annual_draft.state()['turn'])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM annual_turns WHERE status IN ('signed','failed')"),[(30,)])
        self.assertTrue(all(n<=16 for _,n in self.rows("SELECT agency_id,COUNT(*) FROM roster_memberships WHERE career_status IN ('first_team','second_team','pro_pending') GROUP BY agency_id")))
        self.assertTrue(all(n<=3 for _,n in self.rows('SELECT negotiation_id,COUNT(*) FROM market_offers GROUP BY negotiation_id')))

    def test_ui_phase_labels_registration_and_no_midweek_matches(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from idol_manager.ui.main_window import MainWindow
        app=QApplication.instance() or QApplication([])
        self.day(91);w=MainWindow(self.service);w.resize(1300,900);w.show();self.addCleanup(w.close)
        w.show_schedule();QTest.qWait(80)
        self.assertIn('중간 정비',w.game_date_label.text());self.assertIn('14/32',w.game_date_label.text())
        self.assertFalse(self.service.matches.fixtures())
        w.show_market();w.market_page.tabs.setCurrentIndex(5);QTest.qWait(30)
        w.show_annual();self.assertEqual(w.annual_page.registration.count(),2)
        self.assertEqual(w.annual_page.annual.minimum(),3000)
        folder=Path('reports/season32');folder.mkdir(exist_ok=True);w.grab().save(str(folder/'maintenance.png'))
