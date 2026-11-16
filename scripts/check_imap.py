"""Read-only GMX health check with verified TLS and credential-free diagnostics."""
import json
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / 'src'))
from autobookkeeping.config import load_settings
from autobookkeeping.imap_client import gmx_imap
from autobookkeeping.diagnostics import failure


if __name__ == '__main__':
    try:
        with gmx_imap(load_settings()):
            print(json.dumps({'ok': True, 'imap_login': True, 'mailbox_read_only': True,
                              'tls_certificate_verified': True}))
    except Exception as exc:
        print(json.dumps(failure(exc), ensure_ascii=False))
        raise SystemExit(1)
