"""Read an explicitly reviewed, offline numbering handover; never contact services."""
import json
import re
from pathlib import Path
from autobookkeeping.archive import outside, sha
from autobookkeeping.local_invoices import WorkflowError


def read_handover(repo: Path, path: Path):
    data = outside(repo, path).read_bytes()
    report = json.loads(data)
    if (not isinstance(report, dict) or report.get('version') != 1
        or not isinstance(report.get('last_number'), str)
        or not re.fullmatch(r'\d{4,}', report['last_number'])
        or report.get('inventory_complete') is not True
        or type(report.get('unfinalized')) is not int or report['unfinalized'] != 0
        or report.get('external_numbering_stopped') is not True
        or not isinstance(report.get('verification_basis'), str)
        or not report['verification_basis'].strip()):
        raise WorkflowError('Nummernübergabe benötigt vollständigen Bestand, keine offenen externen Entwürfe und bestätigtes Ende der externen Nummernvergabe')
    reference = {'source': 'reviewed_offline_handover', 'source_sha256': sha(data),
                 'verification_basis': report['verification_basis'], 'report': report}
    return report, reference
