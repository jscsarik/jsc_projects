"""Preview only by default; the explicit flag approves only age 16 -> 17."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from idol_manager.config import ROOT
from idol_manager.database import Database
from idol_manager.draft import DraftEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="최초 후보 나이 검사 및 명시적으로 승인한 16→17세 보정")
    parser.add_argument("--approve-age-16-to-17", action="store_true", help="표시된 16세 최초 후보의 나이만 17세로 변경하는 데 명시적으로 동의")
    arguments = parser.parse_args()
    engine = DraftEngine(Database(ROOT / "data" / "idol_manager.sqlite3"))
    issues = engine.age_issues()
    for person in issues:
        print(f"{person.name} | {person.age}세 | {person.id}")
    print(f"규칙(17~26세)을 벗어난 최초 후보: {len(issues)}명")
    if not arguments.approve_age_16_to_17:
        print("나이를 변경하지 않았습니다. --approve-age-16-to-17 옵션은 16세 후보를 17세로 변경하는 명시적 승인입니다.")
        return 0
    approved_ids = tuple(person.id for person in issues if person.age == 16)
    if not approved_ids:
        print("보정할 16세 후보가 없습니다.")
        return 0
    result = engine.correct_legacy_ages(approved=True, person_ids=approved_ids)
    print(f"{len(result.corrected_ids)}명의 나이만 17세로 변경했습니다. 백업: {result.backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
