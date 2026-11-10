"""Read-only save projection and disposable QImage thumbnails; never reads PA."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3
from .game_clock import GameDate


def readonly(path):
    c=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c


def inspect_save(path,*,check=True):
    from .migrations import SCHEMA_VERSION
    with closing(readonly(path)) as c:
        c.execute('BEGIN')
        version=c.execute('PRAGMA user_version').fetchone()[0]
        if not 1<=version<=SCHEMA_VERSION:raise ValueError('지원하지 않는 저장 버전입니다. 원본과 백업을 보존하고 해당 버전의 프로그램을 사용하세요.')
        if check and (c.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchone()):
            raise ValueError('세이브 무결성 오류입니다. 초기화하지 않았습니다.')
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'game','people','idols','abilities'}<=tables or not c.execute('SELECT 1 FROM game WHERE id=1').fetchone():
            raise ValueError('정상적으로 생성된 IDOL Manager 게임이 아닙니다.')
        required={3:{'agencies','roster_memberships','draft_state','draft_turns','draft_picks'},
            4:{'squad_formations','squad_leaders'},5:{'game_clock'},
            6:{'scheduled_matches','match_results'},7:{'player_conditions'},
            10:{'season_finals'},11:{'development_results'},12:{'finance_contracts'},
            13:{'market_terms'},16:{'annual_intakes'},17:{'award_outcomes'}}
        for introduced,names in required.items():
            if version>=introduced and not names<=tables:raise ValueError('저장 버전에 필요한 테이블이 누락되었습니다. 초기화하지 않았습니다.')
        if version==SCHEMA_VERSION:
            from .initial_setup import KNOWN_TABLES
            if not KNOWN_TABLES<=tables:raise ValueError('현재 저장 스키마가 불완전합니다. 원본과 백업을 보존했습니다.')
        day=None
        if version>=5:
            from .game_clock import current_game_date
            day=current_game_date(c)
        agency=None
        if 'player_settings' in tables:
            agency=c.execute('SELECT a.id,a.name,a.logo_path FROM player_settings p JOIN agencies a ON a.id=p.agency_id WHERE p.game_id=1').fetchone()
        people=[]
        if agency:
            # CA is the public current eight-skill average, not health or PA.
            owned=[dict(r) for r in c.execute("""SELECT p.id,p.name,p.photo_path,r.career_status,
                AVG(b.value) AS ca FROM roster_memberships r JOIN people p ON p.id=r.person_id
                JOIN abilities b ON b.person_id=p.id WHERE r.agency_id=?
                AND r.career_status IN ('pro_pending','first_team','second_team','trainee')
                GROUP BY p.id ORDER BY ca DESC,p.id""",(agency['id'],))]
            leader=c.execute("SELECT person_id FROM squad_leaders WHERE agency_id=? AND squad='first_team'",(agency['id'],)).fetchone() if 'squad_leaders' in tables else None
            first=[p for p in owned if p['career_status']=='first_team']
            pros=[p for p in owned if p['career_status'] in ('pro_pending','first_team','second_team')]
            primary=next((p for p in first if leader and p['id']==leader[0]),None)
            if primary is None:primary=next(iter(first or pros or owned),None)
            if primary:
                people.append(primary)
                secondary=next((p for group in (first,pros,[p for p in owned if p['career_status']=='trainee']) for p in group if p['id']!=primary['id']),None)
                if secondary:people.append(secondary)
        rank=None
        if agency and day and not day.is_founding:
            # Do not invent a rank before any scored fixture exists.
            played=('match_results' in tables and c.execute('SELECT 1 FROM match_results r JOIN scheduled_matches m ON m.id=r.match_id WHERE m.season=? LIMIT 1',(day.season,)).fetchone())
            if played and version>=12:
                final=c.execute('SELECT final_order_json FROM season_finals WHERE season=?',(day.season,)).fetchone()
                order=json.loads(final[0]) if final and final[0] else None
                if order and agency['id'] in order:rank=order.index(agency['id'])+1
                else:
                    from .league import standings
                    rows=standings(c,day.season);own=next((r for r in rows if r['agency_id']==agency['id']),None)
                    if own:rank=1+sum(r['points']>own['points'] for r in rows)
        phase=('founding' if day.is_founding else 'preparation' if day.is_preparation else 'maintenance' if day.is_maintenance else 'regular' if day.is_regular else 'postseason' if day.is_postseason else 'offseason') if day else 'legacy'
        return dict(db_version=version,agency_id=agency['id'] if agency else None,
            agency_name=agency['name'] if agency else '기획사 선택 전',logo_path=agency['logo_path'] if agency else '',
            season=day.season if day else None,phase=phase,week=day.week if day else None,
            weekday=day.weekday() if day else None,absolute_day=day.absolute_day if day else None,
            date_label=str(day) if day else '이전 버전 날짜 · 불러올 때 변환',league_rank=rank,
            representatives=people)


def image_path(root,value):
    return Path(value) if value and Path(value).is_absolute() else Path(root)/(value or '__missing_image__')


def preview_signature(info,root):
    paths=[info.get('logo_path')]+[p['photo_path'] for p in info['representatives']]
    stamps=[]
    for value in paths:
        p=image_path(root,value)
        try:stamps.append((value,p.stat().st_mtime_ns,p.stat().st_size))
        except OSError:stamps.append((value,None))
    data={k:info[k] for k in ('agency_name','season','phase','week','league_rank')}
    data['people']=[p['id'] for p in info['representatives']];data['images']=stamps
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def render_thumbnail(info,root,target):
    """QImage/QPainter are usable in a worker. Never instantiate a QPixmap here."""
    from PySide6.QtCore import Qt,QRect,QSaveFile,QIODevice
    from PySide6.QtGui import QImage,QPainter,QColor,QFont,QGuiApplication
    if QGuiApplication.instance() is None:raise RuntimeError('썸네일 생성에는 Qt 애플리케이션이 필요합니다.')
    image=QImage(400,225,QImage.Format.Format_ARGB32);image.fill(QColor('#101b32'))
    painter=QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        def crop(value,rect,caption):
            photo=QImage(str(image_path(root,value)))
            painter.fillRect(rect,QColor('#263752'))
            if not photo.isNull():
                scaled=photo.scaled(rect.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
                x=(scaled.width()-rect.width())//2;y=(scaled.height()-rect.height())//2
                painter.drawImage(rect,scaled,QRect(x,y,rect.width(),rect.height()))
            else:
                painter.setPen(QColor('#b8cbea'));painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,caption)
        painter.setFont(QFont('Malgun Gothic',9))
        for index in range(2):
            person=info['representatives'][index] if len(info['representatives'])>index else None
            rect=QRect(202+index*98,12,90,147)
            crop(person['photo_path'] if person else '',rect,'사진 없음')
            painter.setPen(QColor('#ecf3ff'))
            if person:painter.drawText(QRect(rect.x(),162,rect.width(),19),Qt.AlignmentFlag.AlignCenter,person['name'])
        logo=QImage(str(image_path(root,info.get('logo_path'))))
        if not logo.isNull():
            painter.fillRect(QRect(16,16,170,78),QColor('#e7eefb'))
            logo=logo.scaled(165,72,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            painter.drawImage(18+(165-logo.width())//2,18,logo)
        else:
            painter.setPen(QColor('#a9ccff'));painter.setFont(QFont('Malgun Gothic',13,QFont.Weight.Bold))
            painter.drawText(QRect(16,18,170,70),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,info['agency_name'])
        painter.setPen(QColor('#f0f5ff'));painter.setFont(QFont('Malgun Gothic',10,QFont.Weight.Bold))
        painter.drawText(QRect(16,94,170,58),Qt.TextFlag.TextWordWrap,info['agency_name'])
        labels={'founding':'창단 준비','regular':'정규','postseason':'포스트시즌','offseason':'비시즌','legacy':'이전 저장'}
        caption=('시즌 '+str(info['season'])+' · ' if info['season'] else '')+labels[info['phase']]
        if info['week']:caption+=' '+str(info['week'])+'주차'
        painter.fillRect(QRect(0,190,400,35),QColor('#243955'));painter.setFont(QFont('Malgun Gothic',10))
        painter.drawText(QRect(14,194,375,25),Qt.AlignmentFlag.AlignVCenter,caption+(' · '+str(info['league_rank'])+'위' if info['league_rank'] else ''))
    finally:painter.end()
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    output=QSaveFile(str(target))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):raise OSError(output.errorString())
    if not image.save(output,'PNG') or not output.commit():raise OSError('썸네일 파일을 저장하지 못했습니다.')
