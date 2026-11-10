"""Read-only source inspection and private-copy pre-growth audit."""
from pathlib import Path
from contextlib import closing
from collections import Counter
import json,sqlite3,sys,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.database import Database


def rows(c,table):return sorted(tuple(r) for r in c.execute(f'SELECT * FROM "{table}"'))


def main():
    source=ROOT/'.test-artifacts/growth_live_copy.sqlite3'
    target=ROOT/'.test-artifacts/growth_part_a_copy.sqlite3'
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as c,closing(sqlite3.connect(target)) as dst:
        old_version=c.execute('PRAGMA user_version').fetchone()[0]
        original={t:rows(c,t) for t, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
        c.backup(dst)
    db=Database(target)
    with closing(db.connect()) as c:
        agencies=[r[0] for r in c.execute('SELECT id FROM agencies')]
        participants=Counter(r[0] for r in c.execute('SELECT agency_id FROM match_participants WHERE season=1'))
        pairs=Counter(tuple(sorted(json.loads(r[0]))) for r in c.execute('''SELECT json_group_array(agency_id) FROM match_participants WHERE season=1 GROUP BY match_id'''))
        contents=Counter(r[0] for r in c.execute('SELECT content_id FROM scheduled_matches WHERE season=1'))
        checks={
            'integrity':c.execute('PRAGMA integrity_check').fetchone()[0]=='ok',
            'foreign_keys':not c.execute('PRAGMA foreign_key_check').fetchall(),
            'regular_585':c.execute('SELECT COUNT(*) FROM scheduled_matches WHERE season=1').fetchone()[0]==585,
            'all_agencies_117':set(participants)==set(agencies) and set(participants.values())=={117},
            'each_pair_13':len(pairs)==45 and set(pairs.values())=={13},
            'contents_19_or_20':len(contents)==30 and Counter(contents.values())==Counter({19:15,20:15}),
            'special_six':c.execute('SELECT COUNT(*) FROM special_events WHERE season=1').fetchone()[0]==6,
            'ca_pa_valid':not c.execute('SELECT 1 FROM abilities WHERE value NOT BETWEEN 0 AND potential OR potential>100 LIMIT 1').fetchone(),
            'eight_skills_per_idol':not c.execute('SELECT person_id FROM abilities GROUP BY person_id HAVING COUNT(*)!=8').fetchone(),
            'no_lineup_duplicates':not c.execute('SELECT person_id FROM roster_memberships GROUP BY person_id HAVING COUNT(*)>1').fetchone(),
            'all_old_rows_preserved':all(v==rows(c,t) for t,v in original.items()),
        }
        report={'checks':{k:'PASS' if v else 'FAIL' for k,v in checks.items()},'source_schema':old_version,'source_tables':len(original),
            'copy_schema':c.execute('PRAGMA user_version').fetchone()[0],
            'clock':[tuple(r) for r in c.execute('SELECT * FROM game_clock')],
            'actual_source_modified':False,'backup':str(db.last_backup_path)}
    (ROOT/'.test-artifacts/growth_part_a_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));assert all(checks.values())


if __name__=='__main__':main()
