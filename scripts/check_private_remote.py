"""Read-only GitHub visibility guard, also used by the private pre-push hook."""
import json
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / 'src'))
from autobookkeeping.workspace import assert_data_repo, git
from autobookkeeping.local_invoices import WorkflowError


if __name__ == '__main__':
    try:
        repo = assert_data_repo(TOOL / 'daten', remote=True, require_upstream=False)
        if len(sys.argv) > 1 and (len(sys.argv) != 3 or sys.argv[1] != 'origin'
                                or sys.argv[2] != git(repo, 'remote', 'get-url', '--push', 'origin').decode().strip()):
            raise WorkflowError('Push darf ausschließlich zum geprüften origin-Ziel erfolgen')
        print(json.dumps({'ok': True, 'remote_guard_passed': True}))
    except WorkflowError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
    except Exception as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__}))
        sys.exit(1)
