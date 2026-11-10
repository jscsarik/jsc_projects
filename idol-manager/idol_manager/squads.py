"""Transactional initial formation, Monday roster moves, and squad leaders."""
from contextlib import closing
import sqlite3
import json

from .agencies import Agency
from .config import SKILLS
from .game_clock import current_game_date, is_monday
from .squad_policy import CoverageSquadPolicy, SquadPolicy
from .squad_types import SquadMember, SquadSnapshot
from .conditions import sync_rosters,promotion_allowed

PRO_SQUADS = ("pro_pending","first_team","second_team")
PLAYING_SQUADS = ("first_team","second_team")


class SquadError(ValueError):
    pass


class SquadService:
    def __init__(self, database, policy: SquadPolicy | None = None):
        self.database = database
        self.policy = policy or CoverageSquadPolicy()

    def condition_summaries(self,identities):
        """UI-only projection of the existing registration/rest rules."""
        from .conditions import public_condition
        from .condition_rules import required_rest_weeks
        result={}
        with closing(self.database.connect()) as c:
            c.execute('PRAGMA query_only=ON');c.execute('BEGIN');day=current_game_date(c)
            if day is None:return result
            for person in identities:
                row=c.execute('SELECT squad,complete_rest_weeks FROM player_conditions WHERE person_id=?',(person,)).fetchone()
                if row is None:continue
                state=public_condition(c,person,day.absolute_day)
                required=required_rest_weeks(state.registration_weeks) if state.registration_weeks else 0
                completed=row['complete_rest_weeks'] if row['squad']=='second_team' else 0
                result[person]=(state.registration_weeks,max(0,required-completed))
        return result

    @staticmethod
    def _normal_changes_today(c):
        day=current_game_date(c)
        if day is None or not is_monday(day):return set()
        return {r[0] for r in c.execute('''SELECT DISTINCT person_id FROM condition_events
            WHERE absolute_day=? AND kind='roster' AND occurred=1
            AND json_extract(details_json,'$.reason')='manual'
            AND json_extract(details_json,'$.from') IN('first_team','second_team')
            AND json_extract(details_json,'$.to') IN('first_team','second_team')
            AND json_extract(details_json,'$.from')!=json_extract(details_json,'$.to')''',(day.absolute_day,))}

    def normal_changes_today(self):
        with closing(self.database.connect()) as c:
            c.execute('PRAGMA query_only=ON');return self._normal_changes_today(c)

    @staticmethod
    def _guard_normal_change(c,identities):
        blocked=SquadService._normal_changes_today(c)&set(identities)
        if blocked:
            names=[c.execute('SELECT name FROM people WHERE id=?',(p,)).fetchone()[0] for p in sorted(blocked)]
            raise SquadError(' / '.join(names)+' 선수는 오늘 이미 1군·2군을 변경했습니다. 일반 선수단 변경은 선수당 같은 월요일에 한 번만 가능합니다.')

    @staticmethod
    def _ensure_manual_log(c,moves):
        # Normally sync_rosters writes this fact. Also cover a legacy missing
        # condition row so a successful move can never evade the daily limit.
        day=current_game_date(c)
        if not is_monday(day):return
        recorded=SquadService._normal_changes_today(c)
        for person,source,target in moves:
            if person not in recorded:
                c.execute('''INSERT INTO condition_events(event_key,person_id,absolute_day,kind,occurred,details_json)
                    VALUES (?,?,?,'roster',1,?)''',(f'manual-squad:{day.absolute_day}:{person}',person,day.absolute_day,json.dumps(dict(reason='manual',**{'from':source,'to':target}))))

    @staticmethod
    def _completed(connection):
        row = connection.execute("SELECT status FROM draft_state WHERE id=1").fetchone()
        if not row or row[0] != "completed":
            raise SquadError("최초 드래프트를 완료한 뒤 선수단을 편성할 수 있습니다.")
        counts = connection.execute("""SELECT a.id,COUNT(k.person_id) FROM agencies a
            LEFT JOIN draft_turns t ON t.agency_id=a.id LEFT JOIN draft_picks k ON k.pick_number=t.pick_number
            GROUP BY a.id""").fetchall()
        if len(counts)!=10 or any(row[1]!=16 for row in counts):
            raise SquadError("드래프트 지명 기록이 기획사별 16명 조건에 맞지 않습니다.")

    @staticmethod
    def _player(connection, expected_agency_id=None):
        row = connection.execute("SELECT agency_id FROM player_settings WHERE game_id=1").fetchone()
        if not row:
            raise SquadError("플레이어 기획사가 선택되지 않았습니다.")
        if expected_agency_id is not None and expected_agency_id != row[0]:
            raise SquadError("운영 기획사가 변경되었습니다. 명단을 다시 불러와 주세요.")
        return row[0]

    @staticmethod
    def _monday(connection):
        day = current_game_date(connection)
        if not is_monday(day):
            raise SquadError("선수 교체와 리더 지정·변경은 저장된 게임 날짜가 월요일일 때만 확정할 수 있습니다.")

    @staticmethod
    def _members(connection, agency_id):
        columns = ",".join(f"MAX(CASE WHEN a.skill='{skill}' THEN a.value END) AS {skill}" for skill in SKILLS)
        rows = connection.execute(f"""SELECT p.id,p.name,p.photo_path,i.age,r.career_status AS squad,
            i.average,i.health,{columns} FROM roster_memberships r
            JOIN people p ON p.id=r.person_id JOIN idols i ON i.person_id=r.person_id
            JOIN abilities a ON a.person_id=r.person_id WHERE r.agency_id=?
            AND r.career_status IN ('pro_pending','first_team','second_team','trainee')
            GROUP BY p.id ORDER BY p.name,p.id""", (agency_id,)).fetchall()
        if any(row[skill] is None for row in rows for skill in SKILLS):
            raise SquadError("선수의 현재 능력치 데이터가 불완전합니다. 저장 파일을 확인해 주세요.")
        return tuple(SquadMember(**dict(row)) for row in rows)

    def roster(self, agency_id):
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN")
            self._completed(connection)
            return self._members(connection,agency_id)

    def snapshot(self) -> SquadSnapshot:
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN")
            day = current_game_date(connection)
            try:
                agency_id = self._player(connection)
            except SquadError as error:
                return SquadSnapshot(None,day,False,str(error),False,0,(),())
            row = connection.execute("SELECT id,name,logo_path,funds_krw FROM agencies WHERE id=?", (agency_id,)).fetchone()
            agency = Agency(**dict(row)) if row else None
            try:
                self._completed(connection)
            except SquadError as error:
                return SquadSnapshot(agency,day,False,str(error),False,0,(),())
            formation = connection.execute("SELECT revision FROM squad_formations WHERE agency_id=?", (agency_id,)).fetchone()
            leaders = tuple((row[0],row[1]) for row in connection.execute(
                "SELECT squad,person_id FROM squad_leaders WHERE agency_id=? ORDER BY squad", (agency_id,)))
            return SquadSnapshot(agency,day,True,"",formation is not None,formation[0] if formation else 0,
                                 self._members(connection,agency_id),leaders)

    @staticmethod
    def _validate_counts(connection, agency_id, *, initial=False):
        counts = dict(connection.execute("""SELECT career_status,COUNT(*) FROM roster_memberships
            WHERE agency_id=? GROUP BY career_status""", (agency_id,)).fetchall())
        first = counts.get("first_team",0)
        second = counts.get("second_team",0)
        pending = counts.get("pro_pending",0)
        if first>5 or second>11 or first+second+pending>16 or pending:
            raise SquadError("프로 최대 16명·1군 최대 5명·2군 최대 11명 조건을 위반했습니다.")
        if initial and first!=5:
            raise SquadError("최초 편성은 1군 정확히 5명과 실제 보유한 나머지 프로를 2군에 배치해야 합니다.")

    def initial_contract_reason(self):
        from .founding import contract_reason,staged,waiting
        with closing(self.database.connect()) as c:
            from .squad_calendar import initial_sunday
            if staged(c) and waiting(c) and not initial_sunday(c):return '창단 준비 일요일에 최초 선수단을 편성합니다.'
            return contract_reason(c,self._player(c))

    def _initialize_agency(self, connection, agency_id, first_ids):
        if connection.execute("SELECT 1 FROM squad_formations WHERE agency_id=?", (agency_id,)).fetchone():
            raise SquadError("이미 최초 편성을 확정했습니다. 선수 교체 기능을 사용해 주세요.")
        members = self._members(connection,agency_id)
        professionals = [member for member in members if member.squad in PRO_SQUADS]
        from .founding import waiting,contract_reason,staged
        founding=waiting(connection)
        modern=staged(connection)
        from .squad_calendar import initial_sunday
        if founding and modern and not initial_sunday(connection):raise SquadError('최초 선수단 편성은 창단 준비 일요일에 진행합니다.')
        reason=contract_reason(connection,agency_id)
        if reason:raise SquadError(reason)
        if not (5<=len(professionals)<=16 if modern else len(professionals)==16) or (not founding and not modern and any(member.squad!="pro_pending" for member in professionals)):
            raise SquadError("최초 편성에는 계약된 프로가 최소 5명 필요합니다. 월요일 FA 시장에서 결원을 보충해 주세요.")
        if len(first_ids)!=5 or len(set(first_ids))!=5 or not set(first_ids)<={member.id for member in professionals}:
            raise SquadError("소속 프로 선수 16명 중 중복 없이 정확히 5명을 1군으로 선택해 주세요.")
        for member in professionals:
            connection.execute("UPDATE roster_memberships SET career_status=? WHERE person_id=? AND agency_id=?",
                               ("first_team" if member.id in first_ids else "second_team",member.id,agency_id))
        self._validate_counts(connection,agency_id,initial=True)
        connection.execute("INSERT INTO squad_formations(agency_id) VALUES (?)", (agency_id,))
        sync_rosters(connection,current_game_date(connection).absolute_day,'initial')

    @staticmethod
    def _set_leader(connection, agency_id, squad, person_id):
        if squad not in PLAYING_SQUADS:
            raise SquadError("리더는 1군 또는 2군에만 지정할 수 있습니다.")
        if person_id is None:
            connection.execute("DELETE FROM squad_leaders WHERE agency_id=? AND squad=?", (agency_id,squad))
            return
        if not connection.execute("""SELECT 1 FROM roster_memberships
            WHERE person_id=? AND agency_id=? AND career_status=?""", (person_id,agency_id,squad)).fetchone():
            label = "1군" if squad == "first_team" else "2군"
            raise SquadError(f"해당 선수는 운영 기획사의 {label} 소속이 아닙니다. 선수단을 다시 확인해 주세요.")
        connection.execute("""INSERT INTO squad_leaders(agency_id,squad,person_id) VALUES (?,?,?)
            ON CONFLICT(agency_id,squad) DO UPDATE SET person_id=excluded.person_id""", (agency_id,squad,person_id))

    def _initialize_ai(self, connection, player_id):
        for row in connection.execute("SELECT id FROM agencies WHERE id!=? ORDER BY id", (player_id,)).fetchall():
            agency_id = row[0]
            if connection.execute("SELECT 1 FROM squad_formations WHERE agency_id=?", (agency_id,)).fetchone():
                continue
            members = tuple(m for m in self._members(connection,agency_id) if m.squad in PRO_SQUADS)
            plan = self.policy.plan(members)
            self._initialize_agency(connection,agency_id,plan.first_team_ids)
            self._set_leader(connection,agency_id,"first_team",plan.first_leader_id)
            self._set_leader(connection,agency_id,"second_team",plan.second_leader_id)

    def confirm_initial(self, first_team_ids, *, expected_agency_id=None):
        if isinstance(first_team_ids,str) or len(first_team_ids)!=5 or len(set(first_team_ids))!=5:
            raise SquadError("중복 없이 정확히 5명을 1군으로 선택해 주세요.")
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN IMMEDIATE")
            self._completed(connection)
            player = self._player(connection,expected_agency_id)
            from .squad_calendar import initial_sunday
            if not initial_sunday(connection):self._monday(connection)
            self._initialize_agency(connection,player,tuple(first_team_ids))
            self._initialize_ai(connection,player)

    def initialize_ai_agencies(self):
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN IMMEDIATE")
            self._completed(connection)
            self._monday(connection)
            self._initialize_ai(connection,self._player(connection))

    def _begin_change(self, connection, expected_revision, *, expected_agency_id=None,initial_leader=False,fill_vacancy=False):
        self._completed(connection)
        agency_id = self._player(connection,expected_agency_id)
        from .finals_service import roster_change_reason
        reason=roster_change_reason(connection,agency_id,fill_vacancy=fill_vacancy)
        if reason and not initial_leader:raise SquadError(reason)
        row = connection.execute("SELECT revision FROM squad_formations WHERE agency_id=?", (agency_id,)).fetchone()
        if row is None:
            raise SquadError("최초 선수단 편성을 먼저 확정해 주세요.")
        if type(expected_revision) is not int or row[0]!=expected_revision:
            raise SquadError("선수단이 다른 창에서 변경되었습니다. 최신 명단을 불러온 뒤 다시 시도해 주세요.")
        return agency_id

    @staticmethod
    def _bump(connection, agency_id):
        connection.execute("UPDATE squad_formations SET revision=revision+1 WHERE agency_id=?", (agency_id,))

    @staticmethod
    def _owns(connection, agency_id, person_id, required_squad):
        if not connection.execute("""SELECT 1 FROM roster_memberships
            WHERE person_id=? AND agency_id=? AND career_status=?""", (person_id,agency_id,required_squad)).fetchone():
            raise SquadError("선택한 선수의 소속 또는 선수단이 변경되었습니다. 명단을 다시 확인해 주세요.")

    def swap(self, first_id, second_id, *, expected_revision):
        if first_id==second_id:
            raise SquadError("맞교환할 두 선수를 각각 선택해 주세요.")
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN IMMEDIATE")
            agency = self._begin_change(connection,expected_revision)
            self._owns(connection,agency,first_id,"first_team")
            self._owns(connection,agency,second_id,"second_team")
            self._guard_normal_change(connection,(first_id,second_id))
            if not promotion_allowed(connection,second_id,current_game_date(connection).absolute_day):
                raise SquadError("부상 강등 후 복귀 제한 기간입니다. 강등 2주 뒤 월요일부터 1군 등록이 가능합니다.")
            # Stage within one transaction to respect both capacities at every step.
            connection.execute("UPDATE roster_memberships SET career_status='pro_pending' WHERE person_id=?", (first_id,))
            connection.execute("UPDATE roster_memberships SET career_status='first_team' WHERE person_id=?", (second_id,))
            connection.execute("UPDATE roster_memberships SET career_status='second_team' WHERE person_id=?", (first_id,))
            self._validate_counts(connection,agency)
            self._bump(connection,agency)
            sync_rosters(connection,current_game_date(connection).absolute_day)
            self._ensure_manual_log(connection,((first_id,'first_team','second_team'),(second_id,'second_team','first_team')))
            if current_game_date(connection).weekday()==4 and len([p for p in self._members(connection,agency) if p.squad=='first_team'])!=5:
                raise SquadError('금요일 특별 교체는 1군 정확히 5명을 유지해야 합니다. 맞교환을 사용해 주세요.')

    def move(self, person_id, target_squad, *, expected_revision):
        if target_squad not in PLAYING_SQUADS:
            raise SquadError("프로 선수는 1군과 2군 사이에서만 이동할 수 있습니다.")
        source = "second_team" if target_squad=="first_team" else "first_team"
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN IMMEDIATE")
            agency = self._begin_change(connection,expected_revision,fill_vacancy=target_squad=='first_team')
            self._owns(connection,agency,person_id,source)
            self._guard_normal_change(connection,(person_id,))
            if target_squad=='first_team' and not promotion_allowed(connection,person_id,current_game_date(connection).absolute_day):
                raise SquadError("부상 강등 후 복귀 제한 기간입니다. 강등 2주 뒤 월요일부터 1군 등록이 가능합니다.")
            limit = 5 if target_squad=="first_team" else 11
            count = connection.execute("SELECT COUNT(*) FROM roster_memberships WHERE agency_id=? AND career_status=?", (agency,target_squad)).fetchone()[0]
            if count>=limit:
                raise SquadError("이동할 선수단이 정원에 도달했습니다. 1군·2군 맞교환을 사용해 주세요.")
            connection.execute("UPDATE roster_memberships SET career_status=? WHERE person_id=?", (target_squad,person_id))
            self._validate_counts(connection,agency)
            self._bump(connection,agency)
            sync_rosters(connection,current_game_date(connection).absolute_day)
            self._ensure_manual_log(connection,((person_id,source,target_squad),))
            if current_game_date(connection).weekday()==4 and len([p for p in self._members(connection,agency) if p.squad=='first_team'])!=5:
                raise SquadError('금요일 특별 교체는 1군 정확히 5명을 유지해야 합니다. 맞교환을 사용해 주세요.')

    def promotion_reason(self):
        from .finals_service import roster_change_reason
        with closing(self.database.connect()) as c:
            row=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            return roster_change_reason(c,row[0],fill_vacancy=True) if row else '플레이어 기획사가 선택되지 않았습니다.'

    def change_reason(self):
        from .finals_service import roster_change_reason
        with closing(self.database.connect()) as c:
            row=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            return roster_change_reason(c,row[0]) if row else '플레이어 기획사가 선택되지 않았습니다.'

    def set_leader(self, squad, person_id, *, expected_revision, expected_agency_id=None):
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN IMMEDIATE")
            from .squad_calendar import vacant_leader_allowed
            player=self._player(connection,expected_agency_id)
            first=vacant_leader_allowed(connection,player,squad)
            if first and person_id is None:raise SquadError('해당 선수단에서 리더로 지정할 선수를 선택해 주세요.')
            agency = self._begin_change(connection,expected_revision,expected_agency_id=expected_agency_id,initial_leader=first)
            self._set_leader(connection,agency,squad,person_id)
            self._bump(connection,agency)

    def leader_change_reason(self,squad):
        from .squad_calendar import vacant_leader_allowed
        from .finals_service import roster_change_reason
        with closing(self.database.connect()) as c:
            agency=self._player(c)
            return '' if vacant_leader_allowed(c,agency,squad) else roster_change_reason(c,agency)
