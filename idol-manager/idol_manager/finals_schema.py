"""Additive v10 finals and semantic 28 -> 31 week calendar conversion."""
import json

V10_STATEMENTS=(
    '''CREATE TABLE season_finals(season INTEGER PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
        status TEXT NOT NULL CHECK(status IN('ties','seeded','completed','legacy_closed')),
        frozen_json TEXT NOT NULL,standings_json TEXT NOT NULL,final_order_json TEXT,champion_id TEXT REFERENCES agencies(id),playoff_order_json TEXT)''',
    '''CREATE TABLE final_series(season INTEGER REFERENCES season_finals(season) ON DELETE CASCADE,
        round_number INTEGER CHECK(round_number BETWEEN 1 AND 3),agency_a TEXT REFERENCES agencies(id),agency_b TEXT REFERENCES agencies(id),
        winner_id TEXT REFERENCES agencies(id),PRIMARY KEY(season,round_number))''',
    '''CREATE TABLE final_contests(id TEXT PRIMARY KEY,season INTEGER NOT NULL REFERENCES season_finals(season) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN('tie','post')),round_number INTEGER NOT NULL,game_number INTEGER NOT NULL,
        absolute_day INTEGER NOT NULL,agencies_json TEXT NOT NULL,content_json TEXT NOT NULL,required INTEGER NOT NULL CHECK(required BETWEEN 1 AND 5),
        status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN('scheduled','prepared','completed')),
        seed TEXT,input_json TEXT,condition_json TEXT,result_json TEXT,events_json TEXT,
        UNIQUE(season,kind,round_number,game_number))''',
    '''CREATE TABLE season_honors(season INTEGER REFERENCES season_finals(season) ON DELETE CASCADE,
        agency_id TEXT REFERENCES agencies(id),kind TEXT CHECK(kind IN('regular_first','qualification','champion')),
        PRIMARY KEY(season,agency_id,kind))''',
    "CREATE UNIQUE INDEX unique_season_champion ON season_honors(season,kind) WHERE kind IN('champion','regular_first')",
    '''CREATE TABLE calendar_v9_archive(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,archive_json TEXT NOT NULL)''',
)


def leader_guards(c):
    for operation in ('INSERT','UPDATE'):
        c.execute(f'DROP TRIGGER IF EXISTS squad_leader_{operation.lower()}_guard')
        c.execute(f'''CREATE TRIGGER squad_leader_{operation.lower()}_guard BEFORE {operation} ON squad_leaders BEGIN
            SELECT CASE WHEN EXISTS(SELECT 1 FROM final_contests WHERE kind='tie' AND status!='completed')
                THEN RAISE(ABORT,'Finish frozen regular-season tiebreaks first') END;
            SELECT CASE WHEN NOT (
                (SELECT absolute_day%7 FROM game_clock WHERE game_id=1)=0 OR
                EXISTS(SELECT 1 FROM final_contests m JOIN game_clock g ON g.absolute_day=m.absolute_day
                    WHERE m.kind='post' AND m.game_number=3 AND m.status='scheduled' AND g.absolute_day%7=4
                    AND (json_extract(m.agencies_json,'$[0]')=NEW.agency_id OR json_extract(m.agencies_json,'$[1]')=NEW.agency_id)))
                THEN RAISE(ABORT,'Leaders require Monday or eligible Friday final') END;
            SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM roster_memberships WHERE person_id=NEW.person_id
                AND agency_id=NEW.agency_id AND career_status=NEW.squad)
                THEN RAISE(ABORT,'Leader must belong to the matching agency squad') END;
        END''')


def convert_day(day):
    if day is None or day<0:return day
    season,offset=divmod(day,196)
    return season*217+offset+(21 if offset>=168 else 0)


def migrate_calendar(c):
    clock=c.execute('SELECT absolute_day FROM game_clock WHERE game_id=1').fetchone()
    if not clock:return
    columns={'game_clock':('absolute_day',),'condition_runtime':('rollout_day',),
        'player_conditions':('last_appearance_day','squad_since','injury_day','recovery_day','forced_down_day','return_not_before','history_known_since'),
        'appearance_days':('absolute_day',),'condition_events':('absolute_day',),'condition_day_runs':('absolute_day',)}
    archive={'anchor_old':clock[0],'anchor_new':convert_day(clock[0]),'last_adjustments':{}}
    for person,last in c.execute('SELECT person_id,last_appearance_day FROM player_conditions').fetchall():
        if last is not None:archive['last_adjustments'][person]=[convert_day(last),convert_day(clock[0])-(clock[0]-last)]
    for table,names in columns.items():
        rows=c.execute(f'SELECT rowid,{",".join(names)} FROM {table} ORDER BY rowid DESC').fetchall()
        archive[table]=rows
        # Descending date order avoids collisions in primary keys.
        for row in sorted(rows,key=lambda r:max(v if isinstance(v,int) else -1 for v in r[1:]),reverse=True):
            values=[(convert_day(clock[0])+v-clock[0] if table=='player_conditions' and name in ('recovery_day','return_not_before') and v is not None and v>clock[0] else convert_day(v)) for name,v in zip(names,row[1:])]
            c.execute(f'UPDATE {table} SET '+','.join(f'{n}=?' for n in names)+' WHERE rowid=?',(*values,row[0]))
    for person,week in c.execute('SELECT person_id,registration_week FROM player_conditions').fetchall():
        if week>=0:c.execute('UPDATE player_conditions SET registration_week=? WHERE person_id=?',(convert_day(week*7)//7,person))
    c.execute('INSERT INTO calendar_v9_archive VALUES (1,?)',(json.dumps(archive),))
    current,offset=divmod(clock[0],196)
    # Past seasons/offseason are historical; do not invent retroactive results.
    for season in range(1,current+1+(offset>=168)):
        c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json) VALUES (?,'legacy_closed','{}','[]')",(season,))
