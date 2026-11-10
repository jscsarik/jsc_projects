"""Explicit opt-in packaged-runtime diagnostics on marked disposable data only."""
from contextlib import closing
from pathlib import Path
import json,sys,time,traceback
from PySide6.QtCore import QTimer,QPoint,QRect
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QApplication

def attach(window,paths):
    marker=paths.root/'release27-qa.json'
    if not marker.is_file() or json.loads(marker.read_text(encoding='utf8')).get('qa_only') is not True:
        raise ValueError('--self-check requires an explicitly marked disposable user-data directory')
    config=json.loads(marker.read_text(encoding='utf8'));result=dict(frozen=bool(getattr(sys,'frozen',False)),executable=sys.executable,resource_root=str(window.service.root),user_root=str(paths.root),steps=[],success=False)
    service=window.service;timer=QTimer(window);timer.setInterval(20);start=time.monotonic()
    def steps():
        yield 'main_window'
        if config.get('expect_empty') and service.database.has_game():raise ValueError('Expected a first-launch empty user profile')
        with closing(service.database.connect()) as c:
            result['before']=dict(day=c.execute('SELECT absolute_day FROM game_clock').fetchone()[0] if service.database.has_game() else None,matches=c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0])
        if config.get('create'):
            if service.database.has_game():raise ValueError('Refuse to reset an existing QA game')
            service.new_game();service.draft_session.select_agency('ador');service.draft.start()
            for number,person in enumerate(service.draft.available_candidates()[:160],1):service.draft.pick(service.draft.state().next_turn.agency_id,person.id,expected_pick_number=number)
            for n in service.market.negotiations('ador'):
                if n['purpose']=='founding' and n['status']=='open':
                    person=next(p for p in service.market.public_people() if p['id']==n['person_id'])
                    service.market.offer(n['id'],person['market']*11//10,1,request_id='runtime:'+n['id'])
            state=service.squads.snapshot();service.squads.confirm_initial(tuple(p.id for p in state.members[:5]))
            for squad in ('first_team','second_team'):
                state=service.squads.snapshot();service.squads.set_leader(squad,next(p.id for p in state.members if p.squad==squad),expected_revision=state.revision)
            for day in range(-7,0):service.calendar.advance_day(expected_absolute_day=day)
            service.calendar.advance_day(expected_absolute_day=0);service.calendar.advance_day(expected_absolute_day=1)
            for match in service.matches.fixtures():service.matches.play(match.id)
            service.calendar.advance_day(expected_absolute_day=2);window.reload();window.refresh_calendar();yield 'new_game_draft_squads_matches_saved'
        for button,page in window.navigation_pages:
            button.click();yield 'page:'+button.text()
        window.show_records();deadline=time.monotonic()+30
        while window.records_page.rendered_generation!=window.records_page.query_generation:
            if time.monotonic()>deadline:raise TimeoutError('Records page query timeout')
            yield None
        yield 'records_ready'
        people=service.profiles.search();person=next((p for p in people if p['exact']),None)
        if person:
            window.profiles.open(person['id']);yield 'profile_open';window.profiles.dialog.close()
        result['image_readable']=sum(QImageReader(str(service.image_root/p.photo_path)).canRead() for p in service.scan.people[:5])
        # Old imports retain their legacy paths; verify them separately.
        with closing(service.database.connect()) as c:
            photo=c.execute('SELECT photo_path FROM people LIMIT 1').fetchone()
            result['legacy_image_readable']=bool(photo and QImageReader(str(service.image_root/photo[0])).canRead())
            clock=c.execute('SELECT absolute_day FROM game_clock').fetchone()
            result['after']=dict(day=clock[0] if clock else None,matches=c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],integrity=c.execute('PRAGMA integrity_check').fetchone()[0],has_game=service.database.has_game())
        result['layouts']=[]
        for width,height in ((800,700),(1280,720),(1920,1080)):
            window.resize(width,height);window.show_squads();yield f'squad_{width}x{height}'
            page=window.squad_page;controls=[page.confirm_button,page.swap_button,page.promote_button,page.demote_button,page.first_leader_button,page.second_leader_button]
            pager=window.portrait_layout.tables.get(page.table)
            if pager and pager.enabled:controls.extend((pager.previous,pager.next,pager.fields,pager.details))
            for control in controls:
                page.page_scroll.ensureWidgetVisible(control);yield None
                rect=QRect(control.mapTo(page.page_scroll.viewport(),QPoint()),control.size())
                result['layouts'].append(dict(width=width,height=height,control=control.text() if hasattr(control,'text') else type(control).__name__,accessible=page.page_scroll.viewport().rect().contains(rect)))
            window.grab().save(str(paths.logs/f'window_{width}x{height}.png'))
        if not all(r['accessible'] for r in result['layouts']):raise ValueError('Layout controls clipped')
        if config.get('scene_preview') and service.database.has_game():
            # Opt-in QA layout only: read public rosters; no match computation,
            # events, scores, dates or game results are created by this preview.
            agencies=service.agencies()[:2];people=[]
            with closing(service.database.connect()) as c:
                leaders={r[0] for r in c.execute("SELECT person_id FROM squad_leaders WHERE squad='first_team'")}
            for agency in agencies:
                for person in service.agency_roster(agency.id):
                    if person.status=='first_team':people.append(dict(id=person.id,name=person.name,photo_path=person.photo_path,agency_id=agency.id,leader=person.id in leaders))
            if len(people)!=10:raise ValueError('Five-player scene fixture needs two formed first teams')
            window.show_matches();page=window.match_page;page.tabs.setCurrentIndex(1)
            page.battle.configure('QA · 5인 출전자 배치 확인 (경기 계산 없음)',[(a.id,a.name) for a in agencies],people)
            result['scene_layouts']=[]
            for width,height in ((800,700),(1280,720),(1920,1080)):
                window.resize(width,height);yield f'scene_{width}x{height}'
                for _ in range(4):yield None
                scene=page.battle
                for card in scene.cards.values():
                    rect=QRect(card.mapTo(scene,QPoint()),card.size())
                    within=scene.rect().contains(rect);parent=card.parentWidget()
                    while parent is not None:
                        within=within and parent.rect().contains(QRect(card.mapTo(parent,QPoint()),card.size()))
                        parent=parent.parentWidget()
                    result['scene_layouts'].append(dict(width=width,height=height,id=card.person['id'],visible=card.isVisible(),contained=within))
                window.grab().save(str(paths.logs/f'five_players_{width}x{height}.png'))
            if not all(r['visible'] and r['contained'] for r in result['scene_layouts']):raise ValueError('Five-player scene cards clipped')
        if config.get('expect_readonly_install'):
            probe=Path(sys.executable).parent/'release27-write-probe.tmp'
            try:
                with probe.open('xb') as f:f.write(b'QA')
            except PermissionError:result['install_write_blocked']=True
            else:
                probe.unlink();raise ValueError('Expected install write protection was not enforced')
        window.grab().save(str(paths.logs/'self-check-window.png'))
        result['qt_platform']=QApplication.platformName();result['success']=True
        result['image_formats']=[bytes(v).decode() for v in QImageReader.supportedImageFormats()]
        if not {'jpg','jpeg','png','webp'}.issubset(result['image_formats']):raise ValueError('Required image codec plugin missing')
        backend=window.bgm.backend
        result['bgm_state']=backend.player.playbackState().name if backend else 'NOT TESTED: no audio backend'
        result['bgm_available']=bool(backend and backend.available)
    iterator=steps()
    def tick():
        try:
            if time.monotonic()-start>120:raise TimeoutError('Self-check timed out')
            label=next(iterator)
            if label:
                result['steps'].append(label)
                (paths.logs/'self-check-progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        except StopIteration:finish()
        except Exception:result['success']=False;result['error']=traceback.format_exc();finish()
    def finish():
        timer.stop();result['elapsed']=time.monotonic()-start
        (paths.logs/'self-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        window.close();QApplication.instance().exit(0 if result['success'] else 2)
    timer.timeout.connect(tick);timer.start()
