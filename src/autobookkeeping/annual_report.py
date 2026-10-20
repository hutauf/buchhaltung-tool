"""Readable annual source report alongside the complete lossless inspection export."""
from __future__ import annotations

import csv
import io
import re
import subprocess
from collections import Counter
from html import escape
from pathlib import Path
from decimal import Decimal

from autobookkeeping.archive import atomic, encoded, sha
from autobookkeeping.cashflow import document_flows
from autobookkeeping.homeoffice import eur_summary
from autobookkeeping.reconciliation import findings


def report(catalog, year):
    year = str(year)
    if not re.fullmatch(r'[12]\d{3}', year): raise ValueError('Jahr vierstellig angeben')
    selected = {}
    for rid, versions in catalog['records'].items():
        row = versions['current']
        flows, warnings = document_flows(catalog, row)
        if row.get('coverage') != 'complete': warnings.append('Originalbeleg fehlt')
        flows = [flow for flow in flows if flow['date'].startswith(year + '-')]
        if not str(row.get('date') or '').startswith(year + '-') and not flows: continue
        selected[rid] = {'record_id': rid, 'kind': row['kind'], 'number': row.get('document_number') or row.get('number'),
            'date': row.get('date'), 'status': row['status'], 'original_id': row.get('original_id'),
            'replacement_of': row.get('replacement_of'), 'gross': row.get('gross'), 'net': row.get('net'),
            'vat': row.get('vat'), 'category': row.get('category'), 'documents': row['documents'],
            'coverage': row.get('coverage'), 'tax_treatment': row.get('tax_treatment'),
            'flows': flows, 'warnings': warnings, 'history_versions': len(versions['history']),
            'tax_assignment_open': bool(row.get('tax_review_required') or row.get('business_use') in ('mixed', 'unclear'))}
    cases = [case for case in findings(catalog) if str(case['row'].get('created_at') or '').startswith(year + '-')
             or str(case['row'].get('paid_at') or '').startswith(year + '-')
             or any(rid in selected for rid in case['row']['record_ids'])]
    return {'version': 1, 'year': int(year), 'scope': 'recorded_entries_only', 'tax_return_ready': False,
            'summary': eur_summary(catalog, year), 'counts': dict(Counter(r['kind'] for r in selected.values())),
            'records': list(selected.values()), 'ebay_findings': cases,
            'limitations': ['Einzelne erfasste EÜR-Einträge; keine vollständige Steuererklärung oder Betriebsprüfung.',
                'Zahlungsdaten laut erfasster Quelle; keine Bankabstimmung oder Verknüpfung mit Original-Zahlungsnachweisen.',
                'Keine automatische steuerliche Zuordnung zu amtlichen Formularfeldern, Reverse Charge, Vorsteuer, AfA oder Zehn-Tage-Regel.',
                'Verknüpfte Originale, sämtliche Metadatenhistorien und auch andere Jahre bleiben im vollständigen Export enthalten.']}


def export(archive, year, target):
    archive.verify(); catalog = archive.catalog(); annual = report(catalog, year)
    # The original complete archive is never reduced by the annual view.
    result = archive.export(target, str(year)); target = Path(result['directory'])
    from autobookkeeping.workspace import git, tool_root
    source = {'catalog_sha256': sha(encoded(catalog)),
              'database_sha256': sha((archive.root / 'database.json.enc').read_bytes()),
              'data_commit': None, 'database_matches_commit': False, 'report_tool_commit': None,
              'timestamp_checks': 'Vorhandene Nachweise kopiert; keine neue Bitcoin-Verifikation ausgeführt.'}
    try:
        source['data_commit'] = git(archive.repo, 'rev-parse', 'HEAD').decode().strip()
        source['database_matches_commit'] = sha(git(archive.repo, 'show', 'HEAD:buchhaltung/database.json.enc')) == source['database_sha256']
    except subprocess.CalledProcessError: pass
    try: source['report_tool_commit'] = git(tool_root(), 'rev-parse', 'HEAD').decode().strip()
    except subprocess.CalledProcessError: pass
    annual['source'] = source
    atomic(target / 'jahresbericht.json', encoded(annual))
    table = io.StringIO(newline=''); writer = csv.writer(table, delimiter=';', quoting=csv.QUOTE_ALL, lineterminator='\r\n')
    writer.writerow(['Datensatz', 'Belegnummer', 'Belegart', 'Belegdatum', 'Zahlungsdatum', 'Zahlungsbetrag_EUR', 'Bereich', 'Herkunft'])
    def text(value):
        value = str(value or '')
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
    for row in annual['records']:
        for flow in row['flows']:
            writer.writerow([text(row['record_id']), text(row['number']), row['kind'], row['date'], flow['date'],
                             f"{Decimal(flow['amount_cents']) / 100:.2f}".replace('.', ','), flow['bucket'], flow['origin']])
    atomic(target / 'jahreszahlungen.csv', ('\ufeff' + table.getvalue()).encode('utf8'))
    def eur(value): return f'{Decimal(value) / 100:.2f}'.replace('.', ',') + ' €'
    summary = annual['summary']
    rows = ''.join('<tr>' + ''.join('<td>' + escape(str(v if v is not None else '—')) + '</td>' for v in (
        row['number'], row['kind'], row['date'], row['gross'],
        eur(sum(f['amount_cents'] for f in row['flows'])), len(row['documents']),
        ' · '.join(row['warnings']) + (' · steuerliche Zuordnung offen' if row['tax_assignment_open'] else ''))) + '</tr>' for row in annual['records'])
    content = ('<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'">'
        '<title>Jahresbericht ' + str(year) + '</title><style>body{font:16px system-ui;margin:3em auto;max-width:1200px;padding:0 1em;color:#203a32}'
        'table{border-collapse:collapse;width:100%}td,th{text-align:left;border-bottom:1px solid #ddd;padding:10px}code{overflow-wrap:anywhere}</style>'
        '<h1>Jahresbericht ' + str(year) + '</h1><p>Erfasste Vorgänge und Zahlungsbewegungen · keine abgabefertige Anlage EÜR.</p>'
        '<p>Einnahmen: <strong>' + eur(summary['income_cents']) + '</strong> · Zahlungsausgaben: <strong>' + eur(summary['cash_expenses_cents']) +
        '</strong> · Homeoffice: <strong>' + eur(summary['homeoffice_cents']) + '</strong> · Arbeitsüberschuss inkl. Pauschale: <strong>' +
        eur(summary['eur_working_surplus_cents']) + '</strong></p><h2>Belege und Zahlungsbezug</h2><table><thead><tr>' +
        ''.join('<th>' + h + '</th>' for h in ('Nummer', 'Art', 'Datum', 'Brutto', 'Zahlungen im Jahr', 'Originaldateien', 'Hinweise')) +
        '</tr></thead><tbody>' + rows + '</tbody></table><h2>eBay-Abweichungen</h2><p>' + str(sum(c['status'] == 'open' for c in annual['ebay_findings'])) +
        ' offen · ' + str(sum(c['status'] == 'explained' for c in annual['ebay_findings'])) + ' erläutert. Gründe und Referenzen stehen in jahresbericht.json.</p>'
        '<h2>Datenstand und Grenzen</h2><p>Datencommit: <code>' + escape(source['data_commit'] or 'nicht verfügbar') + '</code> · ' +
        ('Datenbank entspricht diesem Commit.' if source['database_matches_commit'] else 'Arbeitsstand: Datenbank nicht an diesen Commit gebunden.') +
        '</p><p>Katalog-SHA256: <code>' + source['catalog_sha256'] + '</code></p><ul>' + ''.join('<li>' + escape(x) + '</li>' for x in annual['limitations']) +
        '</ul><p>Vollständiger Bestand: <a href="index.html">Belegansicht</a> · <a href="catalog.json">Katalog mit Historien</a> · '
        '<a href="jahreszahlungen.csv">Zahlungen als CSV</a>. Originalzuordnung: export-manifest.json / documents.csv. '
        'Private Betriebsangaben, sofern vorhanden: dokumentation/betriebsangaben.md und betriebsangaben-historie/. '
        'Vorhandene Zeitnachweise: nachweise/. ' + source['timestamp_checks'] + '</p></html>')
    atomic(target / 'jahresbericht.html', content.encode('utf8'))
    manifest = {name: sha((target / name).read_bytes()) for name in ('jahresbericht.json', 'jahresbericht.html', 'jahreszahlungen.csv', 'export-manifest.json')}
    atomic(target / 'jahresbericht-manifest.json', encoded(manifest))
    return dict(result, year=int(year), report=str(target / 'jahresbericht.html'), tax_return_ready=False)
