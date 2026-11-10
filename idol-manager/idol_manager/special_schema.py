"""Version 8: special-event records are separate from all regular-match records."""
SPECIAL_TABLES=('special_points','special_judgments','special_ability_stats','special_player_stats',
                'special_team_results','special_rounds','special_sessions')
V8_STATEMENTS=(
    '''CREATE TABLE special_sessions (
        event_id TEXT PRIMARY KEY REFERENCES special_events(id) ON DELETE CASCADE,
        engine_version TEXT NOT NULL,seed TEXT NOT NULL,standings_json TEXT NOT NULL,groups_json TEXT NOT NULL)''',
    '''CREATE TABLE special_rounds (
        id TEXT PRIMARY KEY,event_id TEXT NOT NULL REFERENCES special_sessions(event_id) ON DELETE CASCADE,
        stage TEXT NOT NULL CHECK(stage IN('upper','lower','final')),
        content_id TEXT NOT NULL,content_name TEXT NOT NULL,main_json TEXT NOT NULL,
        required INTEGER NOT NULL CHECK(required BETWEEN 1 AND 10),base_attempts INTEGER NOT NULL CHECK(base_attempts IN(30,60)),
        agencies_json TEXT NOT NULL,seed TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK(status IN('scheduled','prepared','completed','blocked')),
        input_json TEXT,result_json TEXT,error TEXT NOT NULL DEFAULT '',UNIQUE(event_id,stage))''',
    '''CREATE TABLE special_team_results (
        round_id TEXT NOT NULL REFERENCES special_rounds(id) ON DELETE CASCADE,agency_id TEXT NOT NULL REFERENCES agencies(id),
        rank INTEGER NOT NULL CHECK(rank BETWEEN 1 AND 5),base_score INTEGER NOT NULL CHECK(base_score>=0),
        tiebreak_score INTEGER NOT NULL CHECK(tiebreak_score>=0),forfeit INTEGER NOT NULL CHECK(forfeit IN(0,1)),
        PRIMARY KEY(round_id,agency_id),UNIQUE(round_id,rank))''',
    '''CREATE TABLE special_player_stats (
        round_id TEXT NOT NULL,person_id TEXT NOT NULL REFERENCES people(id),agency_id TEXT NOT NULL,
        content_id TEXT NOT NULL,base_attempts INTEGER NOT NULL CHECK(base_attempts IN(30,60)),
        base_successes INTEGER NOT NULL,base_failures INTEGER NOT NULL,main_attempts INTEGER NOT NULL,
        support_attempts INTEGER NOT NULL,leader_attempts INTEGER NOT NULL CHECK(leader_attempts BETWEEN 0 AND 2),
        leader_successes INTEGER NOT NULL,deathmatch_attempts INTEGER NOT NULL,deathmatch_successes INTEGER NOT NULL,
        success_rate REAL NOT NULL CHECK(success_rate BETWEEN 0 AND 1),
        PRIMARY KEY(round_id,person_id),FOREIGN KEY(round_id,agency_id) REFERENCES special_team_results(round_id,agency_id) ON DELETE CASCADE,
        CHECK(base_successes BETWEEN 0 AND base_attempts),CHECK(base_failures=base_attempts-base_successes),
        CHECK(main_attempts+support_attempts=base_attempts),CHECK(leader_successes BETWEEN 0 AND leader_attempts),
        CHECK(deathmatch_successes BETWEEN 0 AND deathmatch_attempts))''',
    '''CREATE TABLE special_ability_stats (
        round_id TEXT NOT NULL,person_id TEXT NOT NULL,phase TEXT NOT NULL CHECK(phase IN('main','support','leader','deathmatch')),
        skill TEXT NOT NULL,attempts INTEGER NOT NULL,successes INTEGER NOT NULL,failures INTEGER NOT NULL,
        PRIMARY KEY(round_id,person_id,phase,skill),
        FOREIGN KEY(round_id,person_id) REFERENCES special_player_stats(round_id,person_id) ON DELETE CASCADE,
        CHECK(successes BETWEEN 0 AND attempts),CHECK(failures=attempts-successes))''',
    '''CREATE TABLE special_judgments (
        round_id TEXT NOT NULL REFERENCES special_rounds(id) ON DELETE CASCADE,sequence INTEGER NOT NULL,
        agency_id TEXT NOT NULL,person_id TEXT NOT NULL,phase TEXT NOT NULL CHECK(phase IN('main','support','leader','deathmatch')),
        skill TEXT NOT NULL,tick INTEGER NOT NULL CHECK(tick BETWEEN 1 AND 60),round_number INTEGER NOT NULL,
        attempt INTEGER NOT NULL,probability REAL NOT NULL CHECK(probability BETWEEN 0 AND 1),
        roll REAL NOT NULL CHECK(roll>=0 AND roll<1),success INTEGER NOT NULL CHECK(success IN(0,1)),
        PRIMARY KEY(round_id,sequence),
        FOREIGN KEY(round_id,person_id) REFERENCES special_player_stats(round_id,person_id) ON DELETE CASCADE,
        FOREIGN KEY(round_id,agency_id) REFERENCES special_team_results(round_id,agency_id) ON DELETE CASCADE)''',
    '''CREATE TABLE special_points (
        event_id TEXT NOT NULL REFERENCES special_sessions(event_id) ON DELETE CASCADE,
        agency_id TEXT NOT NULL REFERENCES agencies(id),stage TEXT NOT NULL CHECK(stage IN('upper','lower','final')),
        round_id TEXT NOT NULL,delta INTEGER NOT NULL CHECK(delta IN(-2,0,1,2)),
        PRIMARY KEY(event_id,agency_id,stage),
        FOREIGN KEY(round_id,agency_id) REFERENCES special_team_results(round_id,agency_id) ON DELETE CASCADE)''',
    'CREATE INDEX idx_special_players_person ON special_player_stats(person_id,content_id)',
    '''CREATE VIEW special_standings AS SELECT e.season,p.agency_id,SUM(p.delta) AS points
        FROM special_points p JOIN special_events e ON e.id=p.event_id GROUP BY e.season,p.agency_id''',
    '''CREATE VIEW idol_special_career_stats AS SELECT person_id,COUNT(*) AS appearances,
        SUM(base_attempts) AS base_attempts,SUM(base_successes) AS base_successes,
        SUM(leader_attempts) AS leader_attempts,SUM(leader_successes) AS leader_successes,
        SUM(deathmatch_attempts) AS deathmatch_attempts,SUM(deathmatch_successes) AS deathmatch_successes
        FROM special_player_stats GROUP BY person_id''',
)
