"""Reuse the saved-event match scene for finals; no second replay engine."""
from contextlib import closing
from dataclasses import replace
import json
from PySide6.QtWidgets import QLabel,QPushButton
from PySide6.QtCore import Qt
from .competition_progress import CompetitionProgress,show_table_region
from ..game_clock import current_game_date,GameDate
from ..match_types import MatchFixture,MatchSelection,LineupOption,MatchResult
from ..match_service import ABILITY_NAMES
from .match_page import MatchPage,make_table,fill_table


class FinalsMatchAdapter:
    def __init__(self,finals):self.finals=finals;self.database=finals.database

    def fixtures(self,*,today_only=True):
        with closing(self.database.connect()) as c:
            names=dict(c.execute('SELECT id,name FROM agencies'));day=current_game_date(c)
            player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone();player=player[0] if player else None
            rows=self.finals.rows(today_only=False,season=day.season if today_only and day else None);result=[]
            for r in rows:
                if today_only and (not day.is_postseason or (r['kind']=='post' and r['round_number']!=day.week) or (r['kind']=='tie' and r['absolute_day']!=day.absolute_day)):continue
                if not today_only and r['status']!='completed':continue
                date=GameDate(r['absolute_day']);content=json.loads(r['content_json'])
                reason='' if r['status']=='completed' or (day and day.absolute_day==r['absolute_day']) else '현재 날짜의 경기만 진행할 수 있습니다.'
                if not reason and r['status']!='completed' and any(p['absolute_day']<r['absolute_day'] and p['status']!='completed' for p in rows):reason='이전 결정전·경기를 먼저 완료해 주세요.'
                label=('동률 결정전' if r['kind']=='tie' else f'{r["round_number"]}라운드 {r["game_number"]}차전')+' · '+content['name']
                result.append(MatchFixture(r['id'],r['season'],date.week,date.weekday(),r['game_number'],label,tuple(content['main_abilities']),r['required'],
                    'in_progress' if r['status']=='prepared' else r['status'],tuple((a,names[a]) for a in json.loads(r['agencies_json'])),player,
                    r['status'] if r['input_json'] else None,reason))
            return tuple(result)

    def selection(self,identity):
        fixture=next((r for r in self.fixtures() if r.id==identity),None)
        if fixture is None:fixture=next(r for r in self.fixtures(today_only=False) if r.id==identity)
        options,count,fixed=self.finals.selection(identity)
        return MatchSelection(fixture,tuple(LineupOption(o['player'],o['photo_path'],o['leader'],o['available'],o['condition']) for o in options),count,fixed)

    def play(self,identity,*,lineups=None):return self._present(self.finals.play(identity,lineups=lineups),identity)
    def result(self,identity):
        r=self.finals.result(identity);return self._present(r,identity) if r else None

    @staticmethod
    def _present(record,identity):
        s=record['summary']
        if 'resolution' in s:return MatchResult.restore(s,record['events'])
        teams=tuple(dict(agency_id=t['agency_id'],total_score=t['base_score']+t['tiebreak_score'],base_score=t['base_score'],deathmatch_score=t['tiebreak_score'],teamwork_score=t.get('teamwork_score',0)) for t in s['teams'])
        players=tuple(dict(p,winning_idol=False,losing_idol=False) for p in s['players'])
        return MatchResult(identity,'deathmatch' if any(e.phase=='deathmatch' for e in record['events']) else 'normal',s['order'][0],s['order'][-1],teams,players,record['events'],tuple(s.get('teamwork',())))

    def result_names(self,identity):
        with closing(self.database.connect()) as c:
            row=c.execute('SELECT input_json FROM final_contests WHERE id=?',(identity,)).fetchone()
            return {p['id']:p['name'] for t in json.loads(row[0])['teams'] for p in t['players']} if row and row[0] else {}

    def presentation(self,identity):
        with closing(self.database.connect()) as c:
            row=c.execute('SELECT input_json FROM final_contests WHERE id=?',(identity,)).fetchone()
            data=json.loads(row[0]);return {t['agency_id']:t['leader_id'] for t in data['teams']},dict(c.execute('SELECT id,photo_path FROM people'))

    def standings(self,season):
        from ..league import standings
        with closing(self.database.connect()) as c:return standings(c,season)


class FinalsPage(MatchPage):
    def __init__(self,service,thumbnails,parent=None):
        # A small facade redirects only match operations, preserving calendar
        # and database services used by the existing scene.
        class Facade:
            def __getattr__(self,name):return getattr(service,name)
        facade=Facade();facade.matches=FinalsMatchAdapter(service.finals)
        self.finals=service.finals
        self._anchor_day=None;self._showing_result=False
        super().__init__(facade,thumbnails,parent)
        self.findChild(QLabel,'title').setText('동률 결정전 · 포스트시즌')
        self.view_combo.setItemText(0,'현재 라운드 일정');self.view_combo.setItemText(1,'지난 경기 결과 조회')
        self.reload_button.setText('결과 새로고침');self.ai_button.setText('오늘 AI 경기 진행')
        self.current_button=QPushButton('현재 일정으로 이동');self.current_button.clicked.connect(self.go_current)
        self.view_combo.parentWidget().layout().itemAt(2).layout().insertWidget(1,self.current_button)
        self.stage_progress=CompetitionProgress();self.layout().insertWidget(2,self.stage_progress)
        self.series_card=QLabel();self.series_card.setObjectName('summary');self.series_card.setWordWrap(True);self.layout().insertWidget(3,self.series_card)
        self.fixture_table.setMaximumHeight(180)
        self.honors_table=make_table();self.tabs.addTab(self.honors_table,'기획사 통산 기록');self.reload()

    def _configure_battle(self,result):
        super()._configure_battle(result)
        f=self.selection.fixture
        with closing(self.finals.database.connect()) as c:
            row=c.execute('SELECT * FROM final_contests WHERE id=?',(result.match_id,)).fetchone()
            if row['kind']=='post':
                wins={a:0 for a,_ in f.agencies}
                for r in c.execute("SELECT result_json FROM final_contests WHERE season=? AND kind='post' AND round_number=? AND status='completed' AND game_number<?",(row['season'],row['round_number'],row['game_number'])):
                    wins[json.loads(r[0])['order'][0]]+=1
                suffix=' · 시리즈 '+ ' : '.join(f'{name} {wins[a]}승' for a,name in f.agencies)
            else:suffix=' · 같은 승점 그룹 단판 순위 결정전 · 피로 페널티 0'
        self.battle.content.setText(f'시즌 {f.season} · {f.content_name}'+suffix)

    def select_fixture(self):
        super().select_fixture()
        if not self.selection or self.is_busy():return
        f=self.selection.fixture
        show_table_region(self.lineup_table,f.player_participates and f.status!='completed' and not f.block_reason)
        self.tabs.setTabVisible(0,f.status!='completed')
        if f.status=='completed' and not self._showing_result:
            self._show_result(self.matches.result(f.id));return
        current=next((r for r in self.finals.rows(today_only=False) if r['id']==self.selection.fixture.id),None)
        if current:
            self.detail.setText(f'{GameDate(current["absolute_day"])} · {f.content_name}\n'+' VS '.join(name for _,name in f.agencies)
                +f'\n주요: {" / ".join(f.main_abilities)} · 필요 {f.required}명'+('\n'+f.block_reason if f.block_reason else ''))
        if current and current['kind']=='post':
            upcoming=[r for r in self.finals.rows(today_only=False,season=current['season']) if r['kind']=='post' and r['round_number']==current['round_number'] and r['absolute_day']>current['absolute_day']]
            if upcoming:self.detail.setText(self.detail.text()+'\n공개된 다음 경기: '+' / '.join(f'{GameDate(r["absolute_day"])} · {json.loads(r["content_json"])["name"]} · {r["required"]}명' for r in upcoming))
            self.detail.setText(self.detail.text()+'\n금요일 3차전은 1승 1패일 때만 열리며 시작 전 참가 팀의 1·2군 교체를 허용합니다.')

    def _show_result(self,result):
        if self._showing_result or result is None:return
        self._showing_result=True
        try:self._render_saved_result(result)
        finally:self._showing_result=False

    def _render_saved_result(self,result):
        super()._show_result(result)
        record=self.finals.result(result.match_id);names=dict(self.selection.fixture.agencies)
        if record['kind']=='tie':self.result_summary.setText('동률 그룹 최종 순위: '+' → '.join(names[a] for a in record['summary']['order'])+'\n정규 승점·117경기 전적에는 포함하지 않습니다.')
        else:
            self.result_summary.setText(self.result_summary.text().replace('(+1점)','(시리즈 +1승 · 정규 승점 변동 없음)'))
            with closing(self.finals.database.connect()) as c:
                row=c.execute('SELECT s.* FROM final_series s JOIN final_contests m ON m.season=s.season AND m.round_number=s.round_number WHERE m.id=?',(result.match_id,)).fetchone()
                if row and row['winner_id']:self.result_summary.setText(self.result_summary.text()+f'\n라운드 진출/우승: {names[row["winner_id"]]}')
        if record['summary'].get('forfeits'):
            self.result_summary.setText(self.result_summary.text()+'\n몰수: '+', '.join(names[a]+': '+reason for a,reason in record['summary']['forfeits'].items())
                +(' · 양측 몰수: 저장된 정규 상위 시드 몰수승' if record['summary'].get('forfeit_policy')=='higher_frozen_regular_seed' else ' · 복수 몰수 순서는 저장된 공정 추첨' if record['summary'].get('lottery_order') else ''))

    def reload(self,*args):
        if self.is_busy() or self._closing:return
        day=self.service.calendar.state().date
        if day and self._anchor_day!=day.absolute_day:
            self._anchor_day=day.absolute_day;self.selection=None
            self.view_combo.blockSignals(True);self.view_combo.setCurrentIndex(0);self.view_combo.blockSignals(False)
        error=''
        if day and day.is_postseason:
            try:self.finals.prepare_current()
            except ValueError as exc:error=str(exc)
        super().reload(*args)
        if self.is_busy():return
        state=self.finals.season_state()
        if state:
            with closing(self.finals.database.connect()) as c:names=dict(c.execute('SELECT id,name FROM agencies'))
            ranks=json.loads(state['final_order_json']) if state['final_order_json'] else []
            self.notice.setText(('정규 최종 순위: '+' / '.join(f'{i+1}위 {names[a]}' for i,a in enumerate(ranks)) if ranks else '정규 종료 후 동률 결정전을 완료하면 시드를 확정합니다.')
                +(f'\n최종 챔피언: {names[state["champion_id"]]}' if state['champion_id'] else '')+'\n일정: 1주 3·4위, 2주 2위·승자, 3주 1위·승자 · 수·목 및 1승1패 금요일')
        else:self.notice.setText('정규 24주와 특별전 6회를 모두 마친 뒤 다음 월요일에 최종 순위와 포스트시즌 대진을 준비합니다.')
        if state and state['final_order_json']:
            with closing(self.finals.database.connect()) as c:
                series=[]
                for s in c.execute('SELECT * FROM final_series WHERE season=? ORDER BY round_number',(state['season'],)):
                    wins={s['agency_a']:0,s['agency_b']:0}
                    for r in c.execute("SELECT result_json FROM final_contests WHERE season=? AND kind='post' AND round_number=? AND status='completed'",(state['season'],s['round_number'])):wins[json.loads(r[0])['order'][0]]+=1
                    series.append(f'{s["round_number"]}R {names[s["agency_a"]]} {wins[s["agency_a"]]} : {wins[s["agency_b"]]} {names[s["agency_b"]]}'+(f' → {names[s["winner_id"]]}' if s['winner_id'] else ''))
                self.notice.setText(self.notice.text()+'\n'+' / '.join(series))
        if hasattr(self,'honors_table'):
            fill_table(self.honors_table,('기획사','정규 1위','포스트시즌 진출','최종 챔피언 트로피'),
                [(r['name'],r['regular_titles'] or 0,r['qualifications'] or 0,r['trophies'] or 0) for r in self.finals.honors()])
        if hasattr(self,'stage_progress'):
            self.render_progress()
            self.notice.setText('저장된 결과는 다시 계산하지 않습니다. 오늘 경기는 출전자 선택 또는 AI 경기 진행으로 처리하세요.')
        if error:self.notice.setText(error)

    def go_current(self):
        if self.is_busy():return
        self._anchor_day=None;self.reload()

    def controls(self):
        super().controls()
        if hasattr(self,'current_button'):self.current_button.setEnabled(not self.is_busy())
        if self.selection and self.selection.fixture.status!='completed' and not self.selection.fixture.player_participates:
            self.start_button.setText('AI 경기 진행')
            self.selection_hint.setText(self.selection.fixture.block_reason or '이번 대결에는 내 기획사가 참가하지 않습니다. AI 경기 진행을 눌러 주세요.')
        if not self.selection:
            self.detail.setText('아래 단계 현황에서 현재 대진과 다음 경기일을 확인하세요.')
            show_table_region(self.lineup_table,False)

    def render_progress(self):
        day=self.service.calendar.state().date
        selected=self.selection.fixture if self.selection else None
        season=selected.season if selected and not self.view_combo.currentData() else day.season if day else 1
        state=self.finals.season_state(season)
        with closing(self.finals.database.connect()) as c:
            names=dict(c.execute('SELECT id,name FROM agencies'))
            series=[dict(r) for r in c.execute('SELECT * FROM final_series WHERE season=? ORDER BY round_number',(season,))]
        rows=self.finals.rows(today_only=False,season=season);cards=[]
        ranks=json.loads(state['final_order_json']) if state and state['final_order_json'] else []
        ties=[r for r in rows if r['kind']=='tie']
        if ties:cards.append(dict(title='✓ 순위 결정전 완료' if all(r['status']=='completed' for r in ties) else '순위 결정전',body=f'{len(ties)}개 동률 그룹',active=any(r['status']!='completed' for r in ties)))
        for number,title in ((1,'1라운드 · 3위 vs 4위'),(2,'2라운드 · 2위 vs 1R 승자'),(3,'결승 · 1위 vs 2R 승자')):
            item=next((s for s in series if s['round_number']==number),None)
            games=[r for r in rows if r['kind']=='post' and r['round_number']==number]
            wins={a:sum(r['status']=='completed' and json.loads(r['result_json'])['order'][0]==a for r in games) for a in (item['agency_a'],item['agency_b'])} if item else {}
            body='\n'.join(f'{names[a]} · {wins[a]}승' for a in wins) if item else '진출 기획사 미확정'
            if item and item['winner_id']:body+='\n진출: '+names[item['winner_id']]
            cards.append(dict(title=('✓ ' if item and item['winner_id'] else '')+title,body=body,active=bool(day and day.is_postseason and day.week==number and not (item and item['winner_id']))))
        cards.append(dict(title='최종 챔피언',body=names.get(state['champion_id'],'미확정') if state else '미확정'))
        self.stage_progress.update_cards(cards)
        current=next((s for s in series if day and day.is_postseason and s['round_number']==day.week),series[-1] if series else None)
        context='지난 경기 결과 조회' if not self.view_combo.currentData() else '현재 라운드'
        today=[r for r in rows if day and r['absolute_day']==day.absolute_day]
        next_game=next((r for r in rows if day and r['absolute_day']>=day.absolute_day and r['status']!='completed'),None)
        player=self.service.draft_session.player_agency()
        self.series_card.setText(f'현재 게임: {day} · {context} (시즌 {season})'
            +(f'\n{names[current["agency_a"]]} VS {names[current["agency_b"]]}' if current else '\n정규 시즌 종료 후 대진이 확정됩니다.')
            +(' · 플레이어 참가 시리즈' if current and player in (current['agency_a'],current['agency_b']) else ' · AI 기획사 대결' if current else '')
            +(f'\n오늘 {len(today)}경기 · 미완료 {sum(r["status"]!="completed" for r in today)}경기' if today else '\n오늘 포스트시즌 경기가 없습니다.')
            +(f'\n다음 경기: {GameDate(next_game["absolute_day"])} · {next_game["game_number"]}차전' if next_game else '\n현재 확정된 미처리 경기가 없습니다.'))
        by_id={r['id']:r for r in rows}
        blocked=self.fixture_table.blockSignals(True);sorting=self.fixture_table.isSortingEnabled();self.fixture_table.setSortingEnabled(False)
        for i in range(self.fixture_table.rowCount()):
            item=self.fixture_table.item(i,0);r=by_id.get(item.data(Qt.ItemDataRole.UserRole))
            if r:item.setText(str(GameDate(r['absolute_day'])))
        self.fixture_table.setSortingEnabled(sorting);self.fixture_table.blockSignals(blocked)

    def refresh_standings(self):
        super().refresh_standings()
        state=self.finals.season_state(self.selection.fixture.season if self.selection else None)
        if state and state['final_order_json']:
            with closing(self.finals.database.connect()) as c:names=dict(c.execute('SELECT id,name FROM agencies'))
            ranks={names[a]:i+1 for i,a in enumerate(json.loads(state['final_order_json']))}
            sorting=self.standings_table.isSortingEnabled();self.standings_table.setSortingEnabled(False)
            for row in range(self.standings_table.rowCount()):
                self.standings_table.item(row,0).setText(str(ranks[self.standings_table.item(row,1).text()]))
            self.standings_table.setSortingEnabled(sorting)
