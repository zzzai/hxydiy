"""Entry point for the shared, guarded release-input maintenance tool."""
import importlib.util
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / 'deploy/diy/disk_maintenance.py'
SPEC = importlib.util.spec_from_file_location('disk_maintenance', SOURCE)
OPS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPS)


if __name__ == '__main__':
    OPS.main()
