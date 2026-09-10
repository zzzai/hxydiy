"""Run dependency-free contract checks in an isolated production-image container.

Uses only in-memory SQLite fixtures, never production configuration or storage.
"""
from test_technician_project_records import TestProjectRecords


if __name__ == '__main__':
    names = sorted(name for name in dir(TestProjectRecords) if name.startswith('test_'))
    for name in names:
        case = TestProjectRecords()
        case.setup_method()
        try:
            getattr(case, name)()
        finally:
            case.teardown_method()
    print(f'Server image contract checks passed: {len(names)}; isolated SQLite; network disabled')
