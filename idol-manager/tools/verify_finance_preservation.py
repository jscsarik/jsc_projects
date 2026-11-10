"""Migrate a fresh read-only backup copy; compare every pre-existing row."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.database import Database
source=ROOT/'data/idol_manager.sqlite3';target=ROOT/'.test-artifacts/finance_migration_verified.sqlite3'
with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as src:
    source_schema=src.execute('PRAGMA user_version').fetchone()[0]
    with closing(sqlite3.connect(target)) as dst:src.backup(dst)
def snapshot(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        return {t:sorted(tuple(r) for r in c.execute('SELECT * FROM "'+t+'"')) for t, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
before=snapshot(target);db=Database(target);after=snapshot(target)
original=json.loads((ROOT/'.test-artifacts/finance_before.json').read_text(encoding='utf-8'))
assets={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'assets').rglob('*') if p.is_file()}
with closing(db.connect()) as c:
    report={'source_schema':source_schema,'copy_schema':c.execute('PRAGMA user_version').fetchone()[0],
        'existing_tables_preserved':{t:rows==after[t] for t,rows in before.items()},
        'copy_clock':[tuple(r) for r in c.execute('SELECT * FROM game_clock')],
        'copy_finance_journal_rows':c.execute('SELECT COUNT(*) FROM finance_ledger').fetchone()[0],
        'copy_payroll_rows':c.execute('SELECT COUNT(*) FROM finance_payroll').fetchone()[0],
        'copy_debts':c.execute('SELECT COUNT(*) FROM finance_debts').fetchone()[0],
        'copy_contracts':c.execute('SELECT COUNT(*) FROM finance_contracts').fetchone()[0],
        'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],'foreign_keys':[tuple(r) for r in c.execute('PRAGMA foreign_key_check')],
        'original_asset_count':len(original['assets']),'all_assets_unchanged':assets==original['assets'],
        'bgm_preferences_unchanged':hashlib.sha256((ROOT/'data/bgm_settings.json').read_bytes()).hexdigest()==original['bgm_settings'],
        'original_db_equals_start_snapshot':snapshot(source)=={t:sorted(tuple(r) for r in rows) for t,rows in original['tables'].items()},
        'actual_save_modified_by_verifier':False,'development_backup':original['backup'],
        'copy_migration_backup':str(db.last_backup_path)}
assert all(report['existing_tables_preserved'].values()) and report['all_assets_unchanged'] and report['bgm_preferences_unchanged']
assert report['integrity']=='ok' and not report['foreign_keys']
(ROOT/'.test-artifacts/finance_preservation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
