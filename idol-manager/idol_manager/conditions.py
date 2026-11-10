from .game_clock import regular_day
"""Transactional condition state. Callers supply an existing SQLite transaction."""
import hashlib
import json
import random
import secrets

from .condition_rules import (PublicCondition,projected_streak,fatigue_penalty,injury_probability,
                              recovery_day,return_day,required_rest_weeks)
from .game_clock import GameDate,current_game_date,DAYS_PER_SEASON


def seed_for(seed,label):
    return int(hashlib.sha256(f'{seed}|{label}'.encode()).hexdigest(),16)


def initialize_conditions(connection,*,days_per_season=DAYS_PER_SEASON):
    """Backfill proven appearance dates; never invent historical injuries/roster moves."""
    day=current_game_date(connection)
    if day is None:return
    if connection.execute('SELECT 1 FROM condition_runtime WHERE game_id=1').fetchone():return
    absolute=day.absolute_day
    old=connection.execute('SELECT 1 FROM match_results LIMIT 1').fetchone()
    connection.execute('INSERT INTO condition_runtime VALUES (1,?,?)',(absolute if old else 0,str(secrets.randbits(128))))
    connection.execute('''INSERT OR IGNORE INTO appearance_days
        SELECT p.person_id,regular_day(m.season,m.week,m.weekday) FROM match_player_stats p
        JOIN scheduled_matches m ON m.id=p.match_id''',())
    for person,squad in connection.execute('SELECT person_id,career_status FROM roster_memberships').fetchall():
        dates=[r[0] for r in connection.execute('SELECT absolute_day FROM appearance_days WHERE person_id=? AND absolute_day<=? ORDER BY absolute_day',(person,absolute))]
        last=dates[-1] if dates else None;streak=0
        if last is not None:
            previous=last+1
            for value in reversed(dates):
                if value!=previous-1:break
                streak+=1;previous=value
            if last<absolute-1:streak=0
        proven={d//7 for d in dates};week=absolute//7
        if squad=='first_team' and absolute%7!=0:proven.add(week)
        if squad=='first_team':anchor=week if week in proven else week-1
        else:anchor=max(proven,default=-1)
        if squad!='first_team' and anchor<week-1:anchor=-1
        weeks=0;cursor=anchor
        while cursor in proven:weeks+=1;cursor-=1
        connection.execute('''INSERT INTO player_conditions
            (person_id,last_appearance_day,consecutive_days,registration_weeks,registration_week,squad,squad_since,history_known_since)
            VALUES (?,?,?,?,?,?,?,?)''',(person,last,streak,weeks,anchor,squad,absolute,absolute))


def reset_registration(connection,day,*,event_prefix,reason):
    """Reset only registration/rest counters, with an idempotent per-player audit."""
    changed=0
    for row in connection.execute('SELECT person_id,squad,registration_weeks,complete_rest_weeks FROM player_conditions').fetchall():
        person,squad,weeks,rest=tuple(row)
        key=f'{event_prefix}:{person}'
        if connection.execute('SELECT 1 FROM condition_events WHERE event_key=?',(key,)).fetchone():continue
        connection.execute('UPDATE player_conditions SET registration_weeks=0,complete_rest_weeks=0,registration_week=? WHERE person_id=?',(day//7,person))
        connection.execute("INSERT INTO condition_events(event_key,person_id,absolute_day,kind,occurred,details_json) VALUES (?,?,?,'roster',1,?)",
            (key,person,day,json.dumps(dict(reason=reason,**{'from':squad,'to':squad},registration_before=weeks,rest_before=rest),ensure_ascii=False)))
        changed+=1
    return changed


def public_condition(connection,person,day):
    row=connection.execute('SELECT * FROM player_conditions WHERE person_id=?',(person,)).fetchone()
    if row is None:
        return PublicCondition(None,0,1,0,0,False,None,None,day)
    # The current Monday's registration is a preview until that day is closed.
    weeks=row['registration_weeks']+int(row['squad']=='first_team' and row['registration_week']<day//7 and (GameDate(day).is_regular or GameDate(day).is_postseason))
    if row['squad']=='first_team' and (GameDate(day).is_regular or GameDate(day).is_postseason):
        # The first active week counts even after a reset in that same week.
        weeks=max(1,weeks)
        # v0.37.6 could reset an active first week to zero. Only reconstruct a
        # minimum when the saved audit proves uninterrupted first-team service.
        reset=connection.execute("""SELECT absolute_day FROM condition_events
            WHERE event_key GLOB 'manual-registration-reset:*' AND person_id=? AND absolute_day<=?
            AND json_extract(details_json,'$.reason')='user_requested_slot1_registration_reset'
            AND json_extract(details_json,'$.from')='first_team'
            ORDER BY absolute_day DESC LIMIT 1""",(person,day)).fetchone()
        if reset:
            start=GameDate(reset[0]);current=GameDate(day)
            crosses_maintenance=start.day_in_season<91<=current.day_in_season
            if start.season==current.season and (start.is_regular or start.is_postseason) and not crosses_maintenance and row['squad_since']<=reset[0]:
                weeks=max(weeks,day//7-reset[0]//7+1)
    last=row['last_appearance_day']
    legacy=connection.execute('SELECT archive_json FROM calendar_v9_archive WHERE game_id=1').fetchone()
    if legacy:
        adjustment=json.loads(legacy[0]).get('last_adjustments',{}).get(person)
        if adjustment and last==adjustment[0]:last=adjustment[1]
    projected=projected_streak(last,row['consecutive_days'],day)
    current=row['consecutive_days'] if last is not None and last>=day-1 else 0
    return PublicCondition(last,current,projected,fatigue_penalty(projected),weeks,
                           bool(row['injured']),row['recovery_day'],row['return_not_before'],row['history_known_since'])


def sync_rosters(connection,day,reason='manual'):
    if day<0:return  # Preparation does not accumulate registration/rest weeks.
    for row in connection.execute('''SELECT r.person_id,r.career_status,c.squad FROM roster_memberships r
        JOIN player_conditions c ON c.person_id=r.person_id WHERE r.career_status!=c.squad''').fetchall():
        person,target,source=tuple(row)
        connection.execute('''UPDATE player_conditions SET squad=?,squad_since=?,complete_rest_weeks=0,
            history_known_since=MIN(history_known_since,?) WHERE person_id=?''',(target,day,day,person))
        connection.execute('''INSERT INTO condition_events(event_key,person_id,absolute_day,kind,occurred,details_json)
            VALUES (?,?,?,'roster',1,?)''',(f'roster:{person}:{day}:{secrets.token_hex(8)}',person,day,
                                          json.dumps({'from':source,'to':target,'reason':reason})))


def promotion_allowed(connection,person,day):
    row=connection.execute('SELECT return_not_before FROM player_conditions WHERE person_id=?',(person,)).fetchone()
    return not row or row[0] is None or day>=row[0]


def record_appearance(connection,person,day):
    state=public_condition(connection,person,day)
    connection.execute('INSERT OR IGNORE INTO appearance_days VALUES (?,?)',(person,day))
    connection.execute('UPDATE player_conditions SET last_appearance_day=?,consecutive_days=? WHERE person_id=?',
                       (day,state.projected_days,person))


def risk_event(connection,*,key,person,day,kind,probability,rng,details=None):
    if connection.execute('SELECT 1 FROM condition_events WHERE event_key=?',(key,)).fetchone():return False
    row=connection.execute('SELECT injured FROM player_conditions WHERE person_id=?',(person,)).fetchone()
    if row is None or row[0]:return False
    roll=rng.random();occurred=roll<probability
    connection.execute('''INSERT INTO condition_events(event_key,person_id,absolute_day,kind,probability,roll,occurred,details_json)
        VALUES (?,?,?,?,?,?,?,?)''',(key,person,day,kind,probability,roll,occurred,json.dumps(details or {},sort_keys=True)))
    if occurred:
        connection.execute('UPDATE player_conditions SET injured=1,injury_day=?,recovery_day=? WHERE person_id=?',
                           (day,recovery_day(day),person))
    return occurred


def commit_match_conditions(connection,result,context,seed):
    row=connection.execute('SELECT season,week,weekday FROM scheduled_matches WHERE id=?',(result.match_id,)).fetchone()
    day=regular_day(row[0],row[1],row[2])
    commit_appearance_conditions(connection,result.players,context,seed,day,f'match:{result.match_id}')


def commit_appearance_conditions(connection,players,context,seed,day,key,*,seed_label='match-injury-v1'):
    """Shared actual-appearance/injury commit for regular and special contests."""
    rng=random.Random(seed_for(seed,seed_label))
    for player in sorted(players,key=lambda p:p['person_id']):
        person=player['person_id'];record_appearance(connection,person,day)
        if context is not None:
            risk_event(connection,key=f'{key}:{person}',person=person,day=day,kind='match',
                       probability=context['injury_probabilities'][person],rng=rng,
                       details={'match_id':key.removeprefix('match:'),'fatigue':context['public'][person]})


def finish_day(connection,day):
    if connection.execute('SELECT 1 FROM condition_day_runs WHERE absolute_day=?',(day,)).fetchone():return
    runtime=connection.execute('SELECT seed FROM condition_runtime WHERE game_id=1').fetchone()
    if runtime is None:return
    sync_rosters(connection,day,'observed')
    seed=seed_for(runtime[0],f'day:{day}');rng=random.Random(seed);injuries=0
    for row in connection.execute('''SELECT r.person_id,r.career_status,i.health FROM roster_memberships r
        JOIN idols i ON i.person_id=r.person_id WHERE r.career_status IN('first_team','second_team') ORDER BY r.person_id''').fetchall():
        person,squad,health=tuple(row)
        condition=public_condition(connection,person,day)
        if squad=='first_team':
            connection.execute('''UPDATE player_conditions SET registration_weeks=?,registration_week=? WHERE person_id=?''',
                               (condition.registration_weeks,day//7,person))
        played=connection.execute('SELECT 1 FROM appearance_days WHERE person_id=? AND absolute_day=?',(person,day)).fetchone()
        if not played:
            kind='first_rest' if squad=='first_team' else 'second'
            injuries+=risk_event(connection,key=f'day:{day}:{person}',person=person,day=day,kind=kind,
                probability=injury_probability(health,condition.registration_weeks,kind),rng=rng)
    connection.execute('UPDATE player_conditions SET consecutive_days=0 WHERE last_appearance_day IS NULL OR last_appearance_day<?',(day,))
    connection.execute('INSERT INTO condition_day_runs VALUES (?,1,?,?)',(day,str(seed),json.dumps({'new_injuries':injuries})))


def enter_day(connection,day):
    from .maintenance_conditions import apply_reset
    apply_reset(connection,day)
    date=GameDate(day)
    if date.is_offseason and date.week==1 and date.weekday()==0:
        reset_registration(connection,day,event_prefix=f'season-end-registration:{date.season}',reason='season_end_registration_reset')
    # Standard recovery dates; maintenance may explicitly shorten them above.
    for row in connection.execute('SELECT person_id,injury_day FROM player_conditions WHERE injured=1 AND recovery_day<=?',(day,)).fetchall():
        person,injured_day=tuple(row)
        connection.execute('UPDATE player_conditions SET injured=0 WHERE person_id=?',(person,))
        connection.execute('''INSERT OR IGNORE INTO condition_events(event_key,person_id,absolute_day,kind,occurred,details_json)
            VALUES (?,?,?,'recovery',1,'{}')''',(f'recovery:{person}:{injured_day}',person,day))
    if day%7:return
    for row in connection.execute('SELECT * FROM player_conditions').fetchall():
        if GameDate(day).is_maintenance or GameDate(day).is_offseason or GameDate(day).is_preparation or (day>0 and GameDate(day-1).is_maintenance):continue
        rest=row['complete_rest_weeks']+1 if row['squad']=='second_team' and row['squad_since']<=day-7 else 0
        weeks=row['registration_weeks']
        if row['squad']=='second_team' and rest>=required_rest_weeks(weeks):weeks=0
        connection.execute('UPDATE player_conditions SET registration_weeks=?,complete_rest_weeks=? WHERE person_id=?',
                           (weeks,rest,row['person_id']))
    if not connection.execute("SELECT 1 FROM final_contests WHERE kind='tie' AND absolute_day=? AND status!='completed'",(day,)).fetchone():
        forced_demotions(connection,day)


def forced_demotions(connection,day):
    """Monday capacity-safe swaps; replacements stay injured if no healthy option exists."""
    for agency, in connection.execute('SELECT id FROM agencies ORDER BY id').fetchall():
        injured=[r[0] for r in connection.execute('''SELECT r.person_id FROM roster_memberships r
            JOIN player_conditions c ON c.person_id=r.person_id WHERE r.agency_id=? AND r.career_status='first_team' AND c.injured=1 ORDER BY r.person_id''',(agency,))]
        for person in injured:
            candidates=connection.execute('''SELECT r.person_id FROM roster_memberships r JOIN player_conditions c ON c.person_id=r.person_id
                JOIN idols i ON i.person_id=r.person_id WHERE r.agency_id=? AND r.career_status='second_team'
                AND (c.return_not_before IS NULL OR c.return_not_before<=?)
                ORDER BY c.injured,i.health DESC,i.average DESC,r.person_id''',(agency,day)).fetchall()
            if not candidates:raise ValueError('부상자 월요일 교체 후보가 없습니다. 저장 상태를 확인해 주세요.')
            replacement=candidates[0][0]
            connection.execute("UPDATE roster_memberships SET career_status='pro_pending' WHERE person_id=?",(person,))
            connection.execute("UPDATE roster_memberships SET career_status='first_team' WHERE person_id=?",(replacement,))
            connection.execute("UPDATE roster_memberships SET career_status='second_team' WHERE person_id=?",(person,))
            connection.execute('UPDATE player_conditions SET forced_down_day=?,return_not_before=? WHERE person_id=?',(day,return_day(day),person))
            connection.execute('UPDATE squad_formations SET revision=revision+1 WHERE agency_id=?',(agency,))
        sync_rosters(connection,day,'injury_monday')


def repair_ai_leaders(connection,day):
    """Fill vacancies after forced swaps, without optimizing the weekly roster.

    Called after the clock update so existing Monday SQL guards still apply.
    The player's vacancies remain explicit player choices.
    """
    if day%7:return
    for agency, in connection.execute('''SELECT a.id FROM agencies a JOIN squad_formations f ON f.agency_id=a.id
        WHERE a.id NOT IN (SELECT agency_id FROM player_settings) ORDER BY a.id''').fetchall():
        for squad in ('first_team','second_team'):
            if connection.execute('SELECT 1 FROM squad_leaders WHERE agency_id=? AND squad=?',(agency,squad)).fetchone():continue
            candidate=connection.execute('''SELECT r.person_id FROM roster_memberships r
                JOIN abilities a ON a.person_id=r.person_id AND a.skill='leadership'
                JOIN idols i ON i.person_id=r.person_id JOIN player_conditions c ON c.person_id=r.person_id
                WHERE r.agency_id=? AND r.career_status=? ORDER BY c.injured,a.value DESC,i.health DESC,r.person_id LIMIT 1''',(agency,squad)).fetchone()
            if candidate:connection.execute('INSERT INTO squad_leaders VALUES (?,?,?)',(agency,squad,candidate[0]))
