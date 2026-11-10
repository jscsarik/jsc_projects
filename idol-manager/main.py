"""IDOL Manager Windows entry point."""
import sys

if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 이상이 필요합니다. 실행하기.bat를 사용하세요.")

from idol_manager.app import run

if __name__ == "__main__":
    sys.exit(run())
