"""External, unbooked invoice preparation; archive adoption needs the same approval."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from autobookkeeping.archive import atomic, encoded, outside, sha, within
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError, order_snapshot, same_order
from autobookkeeping.taxes import calculate


class _ReadOnlyDraftArchive:
    def __init__(self, archive):
        self.source = archive
        self.repo, self.root = archive.repo, archive.root
        self.state = copy.deepcopy(archive.catalog())
        self.documents = {}

    def verify(self):
        # The caller verifies the real archive under its lock before constructing us.
        return None

    def catalog(self):
        return copy.deepcopy(self.state)

    def read(self, name):
        return self.documents[name] if name in self.documents else self.source.read(name)


class _ExternalInvoices(LocalInvoices):
    def commit(self, before, after, documents):
        self.archive.state = copy.deepcopy(after)
        self.archive.documents.update(documents)


def prepare_external(workflow, target: Path, prepare) -> dict:
    """Run the existing preparation and preview rules entirely in memory/local files."""
    target = outside(workflow.archive.repo, target)
    if target.exists():
        raise WorkflowError("Lokaler Vorbereitungsordner muss neu sein")
    memory = _ReadOnlyDraftArchive(workflow.archive)
    staged = _ExternalInvoices(memory)
    result = prepare(staged)
    invoice = memory.catalog()['local_invoice_drafts'][result['id']]['current']
    if invoice['status'] != 'test_draft':
        raise WorkflowError('Nur unverbindliche Entwürfe lokal vorbereiten')
    before = workflow.archive.catalog().get('local_invoice_drafts', {}).get(invoice['id'])
    staged.preview(invoice['id'], target, e_invoice=True)
    names = list(invoice['documents'])
    if invoice.get('receipt_candidate'):
        names.append(invoice['receipt_candidate']['document'])
    files = {}
    for index, name in enumerate(dict.fromkeys(names)):
        content = memory.read(name)
        local_name = f'original-{index}.pdf'
        atomic(target / local_name, content)
        files[name] = dict(file=local_name, sha256=sha(content),
                          metadata=memory.state['documents'][name])
    previews = {name: sha((target / name).read_bytes()) for name in
                ('rechnung.pdf', 'rechnung.xml', 'xml-validierung.json', 'metadaten.json')}
    plan = dict(version=1, invoice=invoice, files=files, previews=previews,
                base_revision=before['current']['revision'] if before else None,
                proposed_number=result['proposed_number'])
    plan['revision'] = sha(encoded(plan))
    atomic(target / 'vorbereitung.json', encoded(plan))
    return dict(result, local_only=True, archived=False, output=str(target),
                preparation_revision=plan['revision'], preparation=str(target / 'vorbereitung.json'))


def read_preparation(archive, path: Path, revision: str) -> tuple[dict, dict]:
    path = outside(archive.repo, path)
    plan = json.loads(path.read_bytes())
    actual = plan.pop('revision', None)
    if actual != revision or sha(encoded(plan)) != revision or plan.get('version') != 1:
        raise WorkflowError('Lokale Vorbereitung entspricht nicht der freigegebenen Revision')
    invoice = plan['invoice']
    body = {k: v for k, v in invoice.items() if k != 'revision'}
    if (invoice.get('status') != 'test_draft' or invoice.get('number') is not None
            or not invoice.get('id', '').startswith('local-draft:')
            or sha(encoded(body)) != invoice.get('revision')):
        raise WorkflowError('Lokaler Entwurf ist ungültig oder wurde verändert')
    names = set(invoice['documents'])
    if invoice.get('receipt_candidate'):
        names.add(invoice['receipt_candidate']['document'])
    if set(plan['files']) != names:
        raise WorkflowError('Originalumfang der lokalen Vorbereitung wurde verändert')
    if set(plan.get('previews', {})) != {'rechnung.pdf', 'rechnung.xml', 'xml-validierung.json', 'metadaten.json'}:
        raise WorkflowError('Lokale Vorschau ist unvollständig')
    for name, digest in plan['previews'].items():
        if sha((path.parent / name).read_bytes()) != digest:
            raise WorkflowError('Lokale Vorschau wurde seit der Prüfung verändert')
    documents = {}
    for name, entry in plan['files'].items():
        within(archive.root, name)
        local = (path.parent / entry['file']).resolve()
        if not local.is_relative_to(path.parent.resolve()):
            raise WorkflowError('Lokales Original liegt außerhalb der Vorbereitung')
        content = local.read_bytes()
        metadata = entry['metadata']
        if (not name.endswith('.pdf.enc') or not content.startswith(b'%PDF-')
                or sha(content) != entry['sha256'] or sha(content) != metadata['sha256_plaintext']
                or len(content) != metadata['bytes_plaintext'] or metadata['record_id'] != invoice['id']
                or metadata['role'] not in ('test_draft', 'unbooked_receipt')):
            raise WorkflowError('Lokales Original entspricht nicht der geprüften Vorbereitung')
        documents[name] = content
    return plan, documents


def adopt_preparation(workflow, path: Path, revision: str, order, approved: bool) -> dict:
    if not approved:
        raise WorkflowError('Übernahme der lokalen Vorbereitung benötigt die Bündelfreigabe')
    plan, documents = read_preparation(workflow.archive, path, revision)
    invoice = plan['invoice']
    before = workflow.archive.catalog()
    if invoice['seller'] != before['local_invoice_settings']['seller']:
        raise WorkflowError('Absenderprofil seit lokaler Vorbereitung geändert')
    if invoice.get('entry_source') != 'manual':
        if order is None:
            raise WorkflowError('Aktuelle eBay-Leseprüfung fehlt')
        source = order_snapshot(order)
        source.update(calculate(source['positions'], invoice['small_business'],
                                [p['vat_rate'] for p in invoice['positions']]))
        if any(invoice.get(k) != value for k, value in source.items()):
            raise WorkflowError('Verkaufsdaten seit lokaler Vorbereitung geändert')
    workflow.check_duplicates(before, invoice, invoice.get('replacement_of'))
    # The preview reserves no number. A batch may advance the sequence before
    # this invoice; issue still checks the actual next number under its lock.
    active = [v['current'] for v in before.get('local_invoice_drafts', {}).values()
              if v['current']['status'] == 'test_draft' and same_order(v['current'], invoice)]
    if active and (len(active) != 1 or active[0]['id'] != invoice['id']
                   or active[0]['revision'] not in (plan['base_revision'], invoice['revision'])):
        raise WorkflowError('Anderer oder geänderter Entwurf für diesen Verkauf vorhanden')
    existing = before.get('local_invoice_drafts', {}).get(invoice['id'])
    if existing and existing['current']['revision'] == invoice['revision']:
        return dict(workflow.summary(existing['current'], before), adopted=False)
    if existing and existing['current']['revision'] != plan['base_revision']:
        raise WorkflowError('Gespeicherter Entwurf seit Vorbereitung geändert')
    after = copy.deepcopy(before)
    for name, entry in plan['files'].items():
        if name in after['documents'] and after['documents'][name] != entry['metadata']:
            raise WorkflowError('Übernahme würde bestehendes Original verändern')
        after['documents'][name] = entry['metadata']
    history = existing['history'] + [existing['current']] if existing else []
    after.setdefault('local_invoice_drafts', {})[invoice['id']] = dict(current=invoice, history=history)
    workflow.commit(before, after, documents)
    return dict(workflow.summary(invoice, after), adopted=True)
