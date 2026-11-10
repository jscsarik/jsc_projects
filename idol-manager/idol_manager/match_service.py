from .game_clock import regular_day
"""Transactional regular-match orchestration. No Qt, no hidden attributes."""
from collections import Counter
from contextlib import closing
import json
import random
import secrets
import sqlite3

from .config import SKILLS
from .game_clock import current_game_date
from .match_engine import ENGINE_VERSION, LEGACY_ENGINE_VERSION, SUPPORTED_ENGINE_VERSIONS, calculate_match, validate_input
from .match_policy import (NoInjuryAvailability, NoMatchEffects,
                           choose_representative)
from .match_types import (Judgment, MatchError, MatchInput, MatchPlayer, MatchResult,
                          MatchTeam, UnresolvedMatch, MatchFixture, LineupOption, MatchSelection)
from .initial_setup import initial_setup_reason
from .conditions import public_condition,commit_match_conditions
from .condition_rules import injury_probability,PublicCondition
from .lineup_planning import ScheduleAwareLineup,PublicFixture
from .game_clock import DAYS_PER_SEASON
from dataclasses import asdict,replace
from .league import standings

ABILITY_NAMES = dict(zip(('보컬','댄스','랩','예능','외모','신체','지성','리더십'), SKILLS))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class MatchService:
    def __init__(self, database, *, availability=None, effects=None, lineup_policy=None, seed_factory=None):
        self.database = database
        self.availability = availability or NoInjuryAvailability()
        self.effects = effects or NoMatchEffects()
        self.lineup_policy = lineup_policy or ScheduleAwareLineup()
        self.seed_factory = seed_factory or (lambda: secrets.randbits(128))

    @staticmethod
    def _fixture(connection, row, day, player, setup_reason):
        agencies = tuple(tuple(r) for r in connection.execute('''SELECT p.agency_id,a.name FROM match_participants p
            JOIN agencies a ON a.id=p.agency_id WHERE p.match_id=? ORDER BY p.agency_id''',(row['id'],)))
        reason = ''
        if row['status'] == 'completed':
            if not connection.execute('SELECT 1 FROM match_results WHERE match_id=?',(row['id'],)).fetchone():
                reason = '완료 상태에 해당하는 저장 결과가 없습니다. 저장 파일을 확인해 주세요.'
        elif day is None or not day.is_regular or (day.season,day.week,day.weekday()) != (row['season'],row['week'],row['weekday']):
            reason = '현재 게임 날짜의 정규 경기만 시작할 수 있습니다.'
        elif setup_reason:
            reason = setup_reason
        elif row['required_participants'] is None:
            reason = '당일 필요 출전 인원이 확정되지 않았습니다. 날짜 일정을 다시 불러와 주세요.'
        elif connection.execute('''SELECT 1 FROM scheduled_matches WHERE season=? AND week=? AND weekday=?
                AND day_order<? AND status!='completed' LIMIT 1''',
                (row['season'],row['week'],row['weekday'],row['day_order'])).fetchone():
            reason = '더블헤더 1차 경기를 모두 완료한 뒤 2차 경기를 시작할 수 있습니다.'
        run = connection.execute('SELECT status,error FROM match_runs WHERE match_id=?',(row['id'],)).fetchone()
        if run and run['status'] == 'blocked':
            reason = run['error'] or '승자를 결정할 수 없어 차단된 경기입니다. 저장 상태를 점검해 주세요.'
        return MatchFixture(row['id'],row['season'],row['week'],row['weekday'],row['day_order'],row['content_name'],
                            tuple(json.loads(row['main_abilities_json'])),row['required_participants'],row['status'],agencies,
                            player,run['status'] if run else None,reason)

    def fixtures(self, *, today_only=True):
        """Read current fixtures or permanent completed history; never play here."""
        with closing(self.database.connect()) as connection,connection:
            connection.execute('BEGIN')
            day = current_game_date(connection)
            player = connection.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            setup = initial_setup_reason(connection)
            if today_only:
                if day is None or not day.is_regular:
                    return ()
                rows = connection.execute('''SELECT * FROM scheduled_matches WHERE season=? AND week=? AND weekday=?
                    ORDER BY day_order,match_order''',(day.season,day.week,day.weekday())).fetchall()
            else:
                rows = connection.execute("SELECT * FROM scheduled_matches WHERE status='completed' ORDER BY season DESC,match_order DESC").fetchall()
            return tuple(self._fixture(connection,r,day,player[0] if player else None,setup) for r in rows)

    def selection(self, match_id):
        """Public eligible first-team values for the player's side only."""
        with closing(self.database.connect()) as connection,connection:
            connection.execute('BEGIN')
            row = connection.execute('SELECT * FROM scheduled_matches WHERE id=?',(match_id,)).fetchone()
            if row is None:
                raise MatchError('정규 경기 정보를 찾을 수 없습니다.')
            player = connection.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            fixture = self._fixture(connection,row,current_game_date(connection),player[0] if player else None,initial_setup_reason(connection))
            if fixture.status == 'completed' or fixture.block_reason or not fixture.player_participates:
                return MatchSelection(fixture,(),0,None)
            leader = connection.execute("SELECT person_id FROM squad_leaders WHERE agency_id=? AND squad='first_team'",(fixture.player_agency_id,)).fetchone()
            day=regular_day(fixture.season,fixture.week,fixture.weekday)
            players = tuple(p for p in self._public_first_team(connection,fixture.player_agency_id)
                            if self.availability.available(p) or public_condition(connection,p.id,day).injured)
            fixed = None
            run = connection.execute('SELECT input_json,condition_json FROM match_runs WHERE match_id=?',(match_id,)).fetchone()
            frozen_conditions={}
            if run:
                frozen = MatchInput.from_dict(json.loads(run[0]))
                team = next(t for t in frozen.teams if t.agency_id == fixture.player_agency_id)
                players = team.players
                fixed = tuple(p.id for p in players)
                leader = (team.leader_id,)
                if run[1]:frozen_conditions=json.loads(run[1])['public']
            paths = dict(connection.execute('''SELECT p.id,p.photo_path FROM people p
                JOIN roster_memberships r ON r.person_id=p.id WHERE r.agency_id=?''',(fixture.player_agency_id,)))
            options=[]
            for p in players:
                condition=(PublicCondition(**frozen_conditions[p.id]) if p.id in frozen_conditions else public_condition(connection,p.id,day))
                if run and not run[1]:
                    # Pre-v7 prepared games retain their original probabilities.
                    condition=replace(condition,penalty=0,injured=False)
                options.append(LineupOption(p,paths.get(p.id,''),bool(leader and p.id==leader[0]),
                                           fixed is not None or (not condition.injured and self.availability.available(p)),condition))
            return MatchSelection(fixture,tuple(options),min(fixture.required,sum(o.available for o in options)),fixed)

    @staticmethod
    def _public_future(connection,agency,match_row,day):
        rows=connection.execute('''SELECT m.weekday,m.day_order,m.main_abilities_json,m.participants_min,m.participants_max,
            CASE WHEN m.weekday=? THEN m.required_participants ELSE NULL END AS known_count
            FROM scheduled_matches m JOIN match_participants p ON p.match_id=m.id
            WHERE p.agency_id=? AND m.season=? AND m.week=? AND m.status!='completed'
            AND (m.weekday>? OR (m.weekday=? AND m.day_order>?)) ORDER BY m.weekday,m.day_order''',
            (day.weekday(),agency,day.season,day.week,day.weekday(),day.weekday(),match_row['day_order'])).fetchall()
        return tuple(PublicFixture(regular_day(day.season,day.week,r[0]),
                     tuple(ABILITY_NAMES[s] for s in json.loads(r[2])),r[5] if r[5] is not None else (r[3]+r[4]+1)//2) for r in rows)

    def result_names(self, match_id):
        with closing(self.database.connect()) as connection:
            run = connection.execute('SELECT input_json FROM match_runs WHERE match_id=?',(match_id,)).fetchone()
            if not run:
                return {}
            snapshot = MatchInput.from_dict(json.loads(run[0]))
            return {p.id:p.name for t in snapshot.teams for p in t.players}

    @staticmethod
    def _load_result(connection, match_id):
        row = connection.execute('SELECT summary_json FROM match_results WHERE match_id=?', (match_id,)).fetchone()
        if row is None:
            return None
        events = tuple(Judgment(r['sequence'], r['agency_id'], r['person_id'], r['phase'], r['skill'],
                                r['tick'], r['round_number'], r['attempt'], r['probability'], r['roll'], bool(r['success']))
                       for r in connection.execute('SELECT * FROM match_events WHERE match_id=? ORDER BY sequence', (match_id,)))
        return MatchResult.restore(json.loads(row[0]), events)

    def result(self, match_id):
        with closing(self.database.connect()) as connection, connection:
            connection.execute('BEGIN')
            return self._load_result(connection, match_id)

    @staticmethod
    def _public_first_team(connection, agency_id):
        # Deliberately explicit projection: potential, archetype and any future
        # promising-player flag cannot enter policies or prepared snapshots.
        rows = connection.execute('''SELECT p.id,p.name,i.health,a.skill,a.value
            FROM roster_memberships r JOIN people p ON p.id=r.person_id
            JOIN idols i ON i.person_id=p.id JOIN abilities a ON a.person_id=p.id
            WHERE r.agency_id=? AND r.career_status='first_team' ORDER BY p.id,a.skill''', (agency_id,))
        people = {}
        for row in rows:
            item = people.setdefault(row['id'], dict(name=row['name'], health=row['health'], skills={}))
            item['skills'][row['skill']] = row['value']
        if any(set(p['skills']) != set(SKILLS) for p in people.values()):
            raise MatchError('1군 선수의 현재 능력치 데이터가 불완전합니다.')
        from .franchise import eligible
        franchises=eligible(connection,agency_id)
        return tuple(MatchPlayer(identity, agency_id, p['name'], p['health'], tuple(p['skills'][s] for s in SKILLS),identity in franchises)
                     for identity, p in people.items())

    @staticmethod
    def _check_overrides(match, lineups, representatives):
        agencies = {t.agency_id for t in match.teams}
        if set(lineups or {}) - agencies or set(representatives or {}) - agencies:
            raise MatchError('이번 경기 참가 기획사의 출전자만 지정할 수 있습니다.')
        for team in match.teams:
            if lineups and team.agency_id in lineups:
                supplied = tuple(lineups[team.agency_id])
                if len(supplied) != len(set(supplied)) or set(supplied) != {p.id for p in team.players}:
                    raise MatchError('이미 준비된 경기의 출전자를 변경할 수 없습니다.')
            if representatives and team.agency_id in representatives and representatives[team.agency_id] != team.representative_id:
                raise MatchError('이미 준비된 경기의 데스매치 대표를 변경할 수 없습니다.')

    def _prepare(self, match_id, lineups, representatives):
        with closing(self.database.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            cached = self._load_result(connection, match_id)
            if cached is not None:
                return cached
            row = connection.execute('SELECT * FROM scheduled_matches WHERE id=?', (match_id,)).fetchone()
            if row is None:
                raise MatchError('존재하지 않는 정규 경기입니다. 특별전은 특별전 메뉴에서 진행해 주세요.')
            day = current_game_date(connection)
            if not day or not day.is_regular or (day.season, day.week, day.weekday()) != (row['season'], row['week'], row['weekday']):
                raise MatchError('현재 게임 날짜의 정규 경기만 진행할 수 있습니다.')
            if connection.execute('''SELECT 1 FROM scheduled_matches WHERE season=? AND week=? AND weekday=?
                AND day_order<? AND status!='completed' LIMIT 1''',
                (row['season'], row['week'], row['weekday'], row['day_order'])).fetchone():
                raise MatchError('더블헤더 1차 경기를 모두 완료한 후 2차 경기를 진행해 주세요.')
            run = connection.execute('SELECT * FROM match_runs WHERE match_id=?', (match_id,)).fetchone()
            if run:
                if run['engine_version'] not in SUPPORTED_ENGINE_VERSIONS:
                    raise MatchError('준비된 경기의 엔진 버전이 다릅니다. 기존 판정 규칙으로 재개해야 합니다.')
                match = MatchInput.from_dict(json.loads(run['input_json']))
                self._check_overrides(match, lineups, representatives)
                if run['status'] == 'blocked':
                    raise UnresolvedMatch(run['error'])
                if run['status'] == 'completed':
                    raise MatchError('완료 경기 결과가 누락되었습니다. 저장 파일을 확인해 주세요.')
                return match, int(run['seed'])
            if row['status'] != 'scheduled':
                raise MatchError('경기 상태와 준비 데이터가 일치하지 않습니다.')
            required = row['required_participants']
            if required is None:
                raise MatchError('당일 필요 출전 인원이 확정되지 않았습니다. 날짜 일정을 확인해 주세요.')
            try:
                main = tuple(ABILITY_NAMES[s] for s in json.loads(row['main_abilities_json']))
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise MatchError('콘텐츠 주요 능력치를 읽을 수 없습니다.') from error
            if len(main) not in (2, 3) or len(set(main)) != len(main) or not 1 <= required <= 5:
                raise MatchError('콘텐츠 주요 능력치 또는 필요 출전 인원이 올바르지 않습니다.')
            agencies = tuple(r[0] for r in connection.execute(
                'SELECT agency_id FROM match_participants WHERE match_id=? ORDER BY agency_id', (match_id,)))
            if len(agencies) != 2:
                raise MatchError('정규 경기에는 서로 다른 두 기획사가 필요합니다.')
            if set(lineups or {}) - set(agencies) or set(representatives or {}) - set(agencies):
                raise MatchError('이번 경기 참가 기획사의 출전자만 지정할 수 있습니다.')
            teams = []
            probabilities = {}
            condition_context={'public':{},'injury_probabilities':{}}
            for agency in agencies:
                if not connection.execute('SELECT 1 FROM squad_formations WHERE agency_id=?', (agency,)).fetchone():
                    raise MatchError('경기 전에 참가 기획사의 최초 선수단 편성을 완료해 주세요.')
                leader = connection.execute("SELECT person_id FROM squad_leaders WHERE agency_id=? AND squad='first_team'", (agency,)).fetchone()
                leader_id = leader[0] if leader else None
                all_players=self._public_first_team(connection,agency)
                conditions={p.id:public_condition(connection,p.id,day.absolute_day) for p in all_players}
                eligible = tuple(p for p in all_players if self.availability.available(p) and not conditions[p.id].injured)
                count = min(required, len(eligible))
                if lineups and agency in lineups:
                    identities = tuple(lineups[agency])
                    if len(set(identities)) != len(identities) or len(identities) != count:
                        raise MatchError(f'출전 가능한 1군 중 정확히 {count}명을 중복 없이 선택해 주세요.')
                    by_id = {p.id: p for p in eligible}
                    if set(identities) - set(by_id):
                        raise MatchError('소속 기획사의 출전 가능한 1군만 선택할 수 있습니다. 2군 대체 출전은 금지됩니다.')
                    selected = tuple(by_id[i] for i in sorted(identities))
                else:
                    if hasattr(self.lineup_policy,'select_for_match'):
                        selected=tuple(self.lineup_policy.select_for_match(eligible,required,main,leader_id,conditions,
                            day.absolute_day,self._public_future(connection,agency,row,day)))
                    else:selected = tuple(self.lineup_policy.select(eligible, required, main, leader_id))
                    if len(selected) != count or len({p.id for p in selected}) != count or any(p not in eligible for p in selected):
                        raise MatchError('출전자 선택 정책이 올바른 1군 명단을 반환하지 않았습니다.')
                selected = tuple(sorted(selected, key=lambda p: p.id))
                representative = (representatives[agency] if representatives and agency in representatives
                                  else choose_representative(selected, main, required, leader_id,
                                      penalties={p.id:conditions[p.id].penalty for p in selected}))
                teams.append(MatchTeam(agency, selected, leader_id, representative))
                for player in selected:
                    condition=conditions[player.id]
                    probabilities[player.id] = {s: max(0,min(1,self.effects.probability(player, s)*(1-condition.penalty))) for s in SKILLS}
                    condition_context['public'][player.id]=asdict(condition)
                    condition_context['injury_probabilities'][player.id]=injury_probability(player.health,condition.registration_weeks,'match')
            match = MatchInput(match_id, row['content_id'], required, main, tuple(teams), probabilities)
            validate_input(match)
            seed = self.seed_factory()
            if type(seed) is not int or seed < 0:
                raise MatchError('경기 난수 시드가 올바르지 않습니다.')
            connection.execute('INSERT INTO match_runs(match_id,engine_version,seed,input_json,status,condition_json) VALUES (?,?,?,?,?,?)',
                               (match_id, ENGINE_VERSION, str(seed), _json(match.to_dict()), 'prepared',_json(condition_context)))
            connection.execute("UPDATE scheduled_matches SET status='in_progress' WHERE id=?", (match_id,))
            return match, seed

    @staticmethod
    def _store_result(connection, result):
        connection.execute('INSERT INTO match_results(match_id,resolution,winner_id,loser_id,summary_json) VALUES (?,?,?,?,?)',
                           (result.match_id, result.resolution, result.winner_id, result.loser_id, _json(result.summary())))
        for team in result.teams:
            connection.execute('INSERT INTO match_team_stats VALUES (?,?,?,?,?,?,?,?)',
                               (result.match_id, team['agency_id'], team['base_score'], team['deathmatch_score'],
                                team['total_score'], team['outcome'], team['points'], team['forfeit']))
        fields = ('person_id','agency_id','content_id','base_attempts','base_successes','base_failures','main_attempts',
                  'support_attempts','leader_attempts','leader_successes','deathmatch_attempts','deathmatch_successes',
                  'success_rate','base_success_rate','outcome','winning_idol','losing_idol')
        for player in result.players:
            values = (result.match_id,) + tuple(player[k] for k in fields)
            connection.execute(f"INSERT INTO match_player_stats VALUES ({','.join('?' for _ in values)})", values)
        counts = Counter((e.person_id, e.phase, e.skill) for e in result.events if e.phase in ('main', 'support'))
        successes = Counter((e.person_id, e.phase, e.skill) for e in result.events if e.phase in ('main', 'support') and e.success)
        connection.executemany('INSERT INTO match_ability_stats VALUES (?,?,?,?,?,?,?)',
                               [(result.match_id, p, phase, skill, n, successes[(p, phase, skill)], n-successes[(p, phase, skill)])
                                for (p, phase, skill), n in counts.items()])
        connection.executemany('INSERT INTO match_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                               [(result.match_id, e.sequence, e.agency_id, e.person_id, e.phase, e.skill, e.tick,
                                 e.round_number, e.attempt, e.probability, e.roll, e.success) for e in result.events])

    def play(self, match_id, *, lineups=None, representatives=None):
        """Select AI for omitted sides; explicit IDs support future player UI.

        Completed calls are idempotent reads. Preparation is committed first so
        process termination cannot reroll. Final records and status commit once.
        """
        try:
            prepared = self._prepare(match_id, lineups, representatives)
            if isinstance(prepared, MatchResult):
                return prepared
            match, seed = prepared
            unresolved = None
            with closing(self.database.connect()) as connection, connection:
                # SQLite serializes calculation as well as finalization across
                # threads/processes. A concurrent caller waits, then reads the
                # saved result without performing a second calculation.
                connection.execute('BEGIN IMMEDIATE')
                cached = self._load_result(connection, match_id)
                if cached is not None:
                    return cached
                run = connection.execute('SELECT status,input_json,seed,engine_version,condition_json FROM match_runs WHERE match_id=?', (match_id,)).fetchone()
                if not run or run['status'] != 'prepared' or run['input_json'] != _json(match.to_dict()) or run['seed'] != str(seed) or run['engine_version'] not in SUPPORTED_ENGINE_VERSIONS:
                    raise MatchError('경기 준비 정보가 변경되었습니다. 저장 파일을 다시 확인해 주세요.')
                try:
                    result = (calculate_match(match,random.Random(seed),include_main_in_random=False)
                              if run['engine_version']==LEGACY_ENGINE_VERSION else calculate_match(match,random.Random(seed)))
                except UnresolvedMatch as error:
                    unresolved = error
                    connection.execute("UPDATE match_runs SET status='blocked',error=? WHERE match_id=?", (str(error),match_id))
                else:
                    self._store_result(connection, result)
                    commit_match_conditions(connection,result,json.loads(run['condition_json']) if run['condition_json'] else None,seed)
                    connection.execute("UPDATE match_runs SET status='completed',error='' WHERE match_id=?", (match_id,))
                    connection.execute("UPDATE scheduled_matches SET status='completed' WHERE id=?", (match_id,))
            if unresolved is not None:
                raise unresolved
            return result
        except sqlite3.Error as error:
            raise MatchError('경기 저장에 실패했습니다. 다른 요청이 진행 중인지 확인한 뒤 다시 시도해 주세요. '
                             '완료되지 않은 경기 결과와 개인 기록은 반영되지 않았습니다.') from error

    def standings(self, season):
        with closing(self.database.connect()) as connection:
            return standings(connection,season)

    def player_records(self, person_id, *, season=None, content_id=None):
        """Per-game history retains team at appearance time, including after transfers."""
        where, args = 'p.person_id=?', [person_id]
        if season is not None:
            where += ' AND m.season=?'; args.append(season)
        if content_id is not None:
            where += ' AND p.content_id=?'; args.append(content_id)
        with closing(self.database.connect()) as connection:
            return tuple(dict(r) for r in connection.execute(f'''SELECT p.*,m.season,m.week,m.weekday,m.day_order
                FROM match_player_stats p JOIN scheduled_matches m ON m.id=p.match_id
                WHERE {where} ORDER BY m.season,m.match_order''', args))
