"""One atomic intake per offseason; only never-public identities are generated."""
from pathlib import Path
from copy import deepcopy
import hashlib,random,secrets,uuid,unicodedata
from .catalog import SUPPORTED_EXTENSIONS
from .config import SKILLS,load_settings
from .domain import generate_attributes
from .draft_estimates import estimate
from .game_clock import current_game_date
from .conditions import seed_for
from .annual_schema import initialize_annual


def scan_assets(c,root,user_asset_dir=None):
    """Keep old IDs, use UUID4 for new photos, and don't count copied bytes twice."""
    from PySide6.QtGui import QImageReader
    root=Path(root);folder=root/'assets/idols';files=sorted(p for base in (folder,*((Path(user_asset_dir),) if user_asset_dir else ())) for p in base.rglob('*'))
    existing={r[1]:r[0] for r in c.execute('SELECT id,photo_path FROM people')}
    by_hash={r[0]:r[1] for r in c.execute('SELECT digest,person_id FROM annual_assets')}
    available={}
    for path in files:
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:continue
        relative=path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path.resolve())
        try:
            stat=path.stat();cached=c.execute('SELECT * FROM annual_assets WHERE photo_path=?',(relative,)).fetchone()
            if cached and cached['file_size']==stat.st_size and cached['modified_ns']==stat.st_mtime_ns:
                identity,digest=cached['person_id'],cached['digest']
            else:
                if not QImageReader(str(path)).canRead():continue
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                identity=existing.get(relative) or by_hash.get(digest)
                if identity is None:
                    identity=str(uuid.uuid4());name=unicodedata.normalize('NFC',path.stem).strip()
                    if not name:continue
                    # Name keys are not identities; duplicate display names are allowed.
                    c.execute('INSERT INTO people VALUES (?,?,?,?)',(identity,name,'annual-asset:'+identity,relative))
                c.execute('''INSERT INTO annual_assets VALUES (?,?,?,?,?) ON CONFLICT(photo_path) DO UPDATE SET
                    person_id=excluded.person_id,digest=excluded.digest,file_size=excluded.file_size,modified_ns=excluded.modified_ns''',
                    (relative,identity,digest,stat.st_size,stat.st_mtime_ns))
                by_hash.setdefault(digest,identity)
            available[identity]=digest
        except (OSError,ValueError):continue
    return available


def intake(c,root,*,rescan=True,user_asset_dir=None):
    initialize_annual(c);day=current_game_date(c)
    if day is None or day.is_founding:return None
    runtime=c.execute('SELECT first_season FROM annual_runtime').fetchone()
    if not day or not runtime or day.season<runtime[0] or not day.is_offseason or day.week>2:return None
    event=c.execute('SELECT * FROM annual_intakes WHERE season=?',(day.season,)).fetchone()
    if event and event['status']=='completed':return dict(event)
    if event is None:
        c.execute("INSERT INTO annual_intakes VALUES (?,1,'shortage',?,0,NULL,'')",(day.season,str(secrets.randbits(128))))
        event=c.execute('SELECT * FROM annual_intakes WHERE season=?',(day.season,)).fetchone()
    assets=scan_assets(c,root,user_asset_dir) if rescan else {r[0]:r[1] for r in c.execute('SELECT person_id,digest FROM annual_assets')}
    # Any sign of previous exposure, employment, retirement or a contract excludes the ID.
    excluded={r[0] for r in c.execute('''SELECT person_id FROM initial_draft_candidates UNION SELECT person_id FROM annual_entries
        UNION SELECT person_id FROM professional_history UNION SELECT person_id FROM finance_contracts
        UNION SELECT person_id FROM market_history UNION SELECT person_id FROM market_draft_rights
        UNION SELECT person_id FROM roster_memberships WHERE agency_id IS NOT NULL OR career_status!='unassigned'
        UNION SELECT person_id FROM market_careers WHERE debut_season IS NOT NULL OR last_agency IS NOT NULL
        UNION SELECT person_id FROM idols WHERE status!='unseen' ''')}
    used_hash={digest for identity,digest in assets.items() if identity in excluded}
    pool=[];unique=set(used_hash)
    for identity,digest in sorted(assets.items()):
        if identity in excluded or digest in unique:continue
        unique.add(digest);pool.append(identity)
    if len(pool)<70:
        c.execute('UPDATE annual_intakes SET available=?,issue=? WHERE season=?',(len(pool),f'미등장 사진 {len(pool)}명 · 70명까지 {70-len(pool)}명 부족합니다. 서로 다른 사진을 추가하고 다시 스캔해 주세요.',day.season))
        return dict(c.execute('SELECT * FROM annual_intakes WHERE season=?',(day.season,)).fetchone())
    seed=event['seed'];picked=random.Random(seed_for(seed,'identities')).sample(pool,70)
    settings=load_settings(Path(root)/'config/generation.json' if (Path(root)/'config/generation.json').is_file() else None)
    settings=deepcopy(settings);adult=settings['age_rules']['initial_draft']
    settings['age_rules'].update(annual_youth=[14,16],annual_adult=[max(17,adult[0]),adult[1]])
    if settings['age_rules']['annual_adult'][1]<17:raise ValueError('기존 생성기의 성인 허용 연령이 17세 미만입니다.')
    ages={}
    for i,identity in enumerate(picked):
        rng=random.Random(seed_for(seed,'person:'+identity))
        attributes=generate_attributes(rng,settings,age_context='annual_youth' if i<30 else 'annual_adult')
        ages[identity]=attributes['age']
        c.execute('''INSERT INTO idols VALUES (?,?,?,?,?,'candidate') ON CONFLICT(person_id) DO UPDATE SET
            age=excluded.age,health=excluded.health,archetype=excluded.archetype,average=excluded.average,status='candidate' ''',
            (identity,attributes['age'],attributes['health'],attributes['archetype'],attributes['average']))
        c.execute("INSERT OR IGNORE INTO roster_memberships VALUES (?,NULL,'unassigned')",(identity,))
        c.execute('INSERT OR IGNORE INTO market_careers VALUES (?,NULL,NULL,?,NULL)',(identity,day.season))
        bounds_rng=random.Random(seed_for(seed,'estimates:'+identity))
        for skill in SKILLS:
            value=attributes['skills'][skill];potential=attributes['potentials'][skill]
            c.execute('''INSERT INTO abilities VALUES (?,?,?,?) ON CONFLICT(person_id,skill) DO UPDATE SET
                value=excluded.value,potential=excluded.potential''',(identity,skill,value,potential))
            bounds=estimate(value,bounds_rng);c.execute('INSERT INTO draft_estimates VALUES (?,?,?,?)',(identity,skill,bounds.low,bounds.high))
        # Unseen historical simulations remain intact, but are not a public career.
        c.execute('''INSERT INTO player_conditions(person_id,squad,squad_since,history_known_since) VALUES (?,'unassigned',?,?)
            ON CONFLICT(person_id) DO UPDATE SET history_known_since=excluded.history_known_since,squad_since=excluded.squad_since''',
            (identity,day.absolute_day,day.absolute_day))
        c.execute('INSERT INTO annual_entries VALUES (?,?,?,?,?)',(identity,day.season,day.season+1,day.absolute_day,attributes['age']))
    eligible=sorted(p for p in picked if ages[p]<=21)
    for identity in random.Random(seed_for(seed,'special')).sample(eligible,2):c.execute('INSERT INTO annual_secrets VALUES (?,1)',(identity,))
    c.execute("UPDATE annual_intakes SET status='completed',available=?,appeared_day=?,issue='' WHERE season=?",(len(pool),day.absolute_day,day.season))
    return dict(c.execute('SELECT * FROM annual_intakes WHERE season=?',(day.season,)).fetchone())


def intake_issue(c,season):
    runtime=c.execute('SELECT first_season FROM annual_runtime').fetchone()
    if not runtime or season<runtime[0]:return ''
    row=c.execute('SELECT status,issue FROM annual_intakes WHERE season=?',(season,)).fetchone()
    return '' if row and row[0]=='completed' else row[1] if row and row[1] else '비시즌 신규 후보 70명 등록을 먼저 완료해 주세요.'
