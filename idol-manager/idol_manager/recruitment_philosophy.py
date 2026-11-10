"""Persisted recruitment identity, separate from financial management style."""
import random,secrets
from .game_clock import current_game_date

FIELDS={'music':(0,1,2),'visual':(4,5),'performance':(1,5),'broadcast':(3,6)}
V23_STATEMENTS=(
"""CREATE TABLE IF NOT EXISTS recruitment_identity(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,seed TEXT NOT NULL)""",
"""CREATE TABLE IF NOT EXISTS recruitment_philosophies(game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,
 agency_id TEXT NOT NULL REFERENCES agencies(id),philosophy TEXT NOT NULL CHECK(philosophy IN ('balanced','specialist','development')),
 PRIMARY KEY(game_id,agency_id))""",
"""CREATE TABLE IF NOT EXISTS recruitment_specialties(game_id INTEGER NOT NULL,season INTEGER NOT NULL,agency_id TEXT NOT NULL,field TEXT NOT NULL,
 PRIMARY KEY(game_id,season,agency_id),UNIQUE(game_id,season,field),
 FOREIGN KEY(game_id,agency_id) REFERENCES recruitment_philosophies(game_id,agency_id) ON DELETE CASCADE ON UPDATE CASCADE)""",
)

def ensure(c,season=None):
    player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
    if not player:return {}
    day=current_game_date(c);season=season or (day.season if day else 1)
    agencies=[r[0] for r in c.execute('SELECT id FROM agencies WHERE id!=? ORDER BY id',(player[0],))]
    if len(agencies)!=9:raise ValueError('영입 철학 배정에는 AI 기획사 9곳이 필요합니다.')
    seed=c.execute('SELECT seed FROM recruitment_identity WHERE game_id=1').fetchone()
    if not seed:
        c.execute('INSERT INTO recruitment_identity VALUES (1,?)',(str(secrets.randbits(128)),))
        seed=c.execute('SELECT seed FROM recruitment_identity WHERE game_id=1').fetchone()
    profiles=dict(c.execute('SELECT agency_id,philosophy FROM recruitment_philosophies WHERE game_id=1'))
    if not profiles:
        kinds=['balanced']*4+['specialist']*3+['development']*2
        random.Random(seed[0]+':identity').shuffle(kinds)
        c.executemany('INSERT INTO recruitment_philosophies VALUES (1,?,?)',zip(agencies,kinds))
    elif player[0] in profiles:
        # Player selection may change before the first pick. Transfer the new
        # player's former AI identity to the former player; preserve 4:3:2.
        missing=[a for a in agencies if a not in profiles]
        if len(missing)!=1:raise ValueError('AI 영입 철학 기록이 불완전합니다.')
        c.execute('UPDATE recruitment_philosophies SET agency_id=? WHERE game_id=1 AND agency_id=?',(missing[0],player[0]))
    profiles=dict(c.execute('SELECT agency_id,philosophy FROM recruitment_philosophies WHERE game_id=1'))
    if set(profiles)!=set(agencies):raise ValueError('AI 영입 철학 기록이 불완전합니다.')
    specialists=sorted(a for a,k in profiles.items() if k=='specialist')
    fields=dict(c.execute('SELECT agency_id,field FROM recruitment_specialties WHERE game_id=1 AND season=?',(season,)))
    if not fields:
        selected=random.Random(seed[0]+f':season:{season}').sample(list(FIELDS),3)
        c.executemany('INSERT INTO recruitment_specialties VALUES (1,?,?,?)',[(season,a,f) for a,f in zip(specialists,selected)])
        fields=dict(zip(specialists,selected))
    if set(fields)!=set(specialists):raise ValueError('AI 전문 분야 기록이 불완전합니다.')
    return {a:dict(philosophy=k,field=fields.get(a)) for a,k in profiles.items()}
