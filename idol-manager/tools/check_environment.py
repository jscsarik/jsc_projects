"""Bootstrap checks without shell-dependent inline Python quoting."""
import importlib.metadata
import importlib.util
import sys


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode == "python-version":
        return 0 if sys.version_info >= (3, 12) else 1
    if mode == "executable":
        print(sys.executable)
        return 0
    if mode == "dependencies":
        try:
            if importlib.util.find_spec("PySide6") is None:
                return 1
            version = tuple(int(part) for part in importlib.metadata.version("PySide6").split(".")[:2])
            return 0 if (6, 8) <= version < (7, 0) else 1
        except (ImportError, ValueError):
            return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
