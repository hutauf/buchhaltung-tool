"""Private operating description: interview proposals and versioned encrypted answers."""
from __future__ import annotations

import copy
from datetime import date
from autobookkeeping.archive import atomic, encoded, outside, sha
from autobookkeeping.local_invoices import WorkflowError, now

QUESTIONS = {
    'responsibility': 'Wer führt die Aufzeichnungen und darf Rechnungen oder Ausgaben freigeben? Gibt es eine Vertretung?',
    'scope': 'Welche Geschäftsvorfälle, Quellen und weiteren Systeme nutzt du tatsächlich? Was bleibt außerhalb dieses Tools?',
    'start': 'Seit wann gilt das Verfahren? Wie wurde die Rechnungsnummernübergabe dokumentiert?',
    'intake': 'Wo kommen Originalbelege an, wie häufig werden sie erfasst und wie werden fehlende Originale behandelt?',
    'locations': 'Wo liegen Tool, privates Datenrepo und vorübergehende Klartextexporte? Wie werden letztere entfernt?',
    'reconciliation': 'Wer führt den eBay-Verkaufsabgleich wann aus und dokumentiert Abweichungen oder Ausfälle?',
    'classification': 'Wie werden Belegangaben, betriebliche Verwendung und steuerliche Sonderfälle vor der Übernahme geklärt?',
    'access': 'Wer hat Zugriff? Wie schützt du Geräte und das private Git-Repository?',
    'password_custody': 'Wie und getrennt wo verwahrst du Archivpasswort und Notfallkopie? Nur Verfahren nennen, niemals das Passwort.',
    'retention': 'Wie stellst du elfjährige Aufbewahrung, mögliche Verlängerungen und dauerhafte Lesbarkeit sicher?',
    'backup': 'Welche unabhängigen Sicherungen und Wiederherstellungstests führst du tatsächlich durch? Fehlende Maßnahmen offen benennen.',
    'export': 'Wer darf vollständige Daten und Originale für Steuerberatung oder Finanzamt exportieren und sicher übergeben?',
}
STATES = {'documented', 'open', 'not_applicable'}


def interview_prompt():
    return ('Hilf mir, meine tatsächlichen Buchhaltungsabläufe zu dokumentieren. Führe ein Interview, '
        'höchstens zwei Fragen gleichzeitig. Erfinde keine Antworten oder durchgeführten Kontrollen. '
        'Unbekanntes bleibt offen; Nichtanwendbarkeit begründen. Frage niemals nach Passwörtern, Tokens, '
        'Steuernummern oder Käuferdaten. Beschreibe organisatorische Verfahren, keine Betriebsprüfung durch das Finanzamt. '
        'CD-Sicherung ist optional; Zahlung-zu-Originalnachweis-Verknüpfung und automatischer Gebührenimport sind außerhalb des Tools. '
        'Frage am Ende nach Bestätigung des zusammengefassten Entwurfs. Gib danach ein JSON-Objekt mit den folgenden '
        'Schlüsseln aus; je Schlüssel {"status":"documented|open|not_applicable","text":"tatsächlicher Ablauf oder offene Frage"}. '
        'Bestehende Antworten eines lokalen Agenten zunächst lesen und erhalten; keine Zugangswerte aus .env lesen. '
        'Lokale Agenten nutzen verfahrensdoku vorbereiten und speichern erst nach konkreter Freigabe. '
        'In einem Chat ohne Repositoryzugriff nur den Entwurf ausgeben, keine Speicherung behaupten.\n\n' +
        '\n'.join(key + ': ' + question for key, question in QUESTIONS.items()))


def checked_answers(answers):
    if not isinstance(answers, dict) or set(answers) - QUESTIONS.keys():
        raise WorkflowError('Unbekannte oder fehlformatierte Betriebsangaben')
    result = {}
    for key in QUESTIONS:
        value = answers.get(key, {'status': 'open', 'text': ''})
        if (not isinstance(value, dict) or set(value) != {'status', 'text'}
            or value['status'] not in STATES or not isinstance(value['text'], str)
            or value['status'] != 'open' and not value['text'].strip()):
            raise WorkflowError('Betriebsangabe benötigt Status und Text; Nichtanwendbarkeit begründen')
        result[key] = {'status': value['status'], 'text': value['text'].strip()}
    return result


def public_status(catalog):
    current = catalog.get('operating_procedure', {}).get('current')
    answers = current['answers'] if current else {}
    return {'available': bool(current), 'documented': sum(a['status'] == 'documented' for a in answers.values()),
            'not_applicable': sum(a['status'] == 'not_applicable' for a in answers.values()),
            'open': sum(answers.get(key, {}).get('status', 'open') == 'open' for key in QUESTIONS),
            'total': len(QUESTIONS), 'effective_from': current['effective_from'] if current else None}


def proposal(catalog, answers, effective_from):
    date.fromisoformat(effective_from)
    if len(effective_from) != 10: raise WorkflowError('Gültigkeitsbeginn als ISO-Datum angeben')
    current = catalog.get('operating_procedure', {}).get('current')
    merged = dict(current['answers']) if current else {}
    merged.update(answers)
    return {'version': 1, 'base_revision': sha(encoded(current)), 'effective_from': effective_from,
            'answers': checked_answers(merged)}


def markdown(body):
    labels = {'documented': 'Beschrieben', 'open': 'Offen', 'not_applicable': 'Nicht anwendbar'}
    parts = ['# Private betriebliche Verfahrensdokumentation',
             'Gültig ab: ' + body['effective_from'],
             'Beschreibung des tatsächlichen Betriebs. Kein Prüfbericht des Finanzamts und kein Nachweis einer durchgeführten Betriebsprüfung.']
    for key, question in QUESTIONS.items():
        answer = body['answers'][key]
        parts += ['## ' + question, '**' + labels[answer['status']] + '**', answer['text'] or 'Noch nicht beschrieben.']
    return '\n\n'.join(parts) + '\n'


def prepare(archive, answers, effective_from, target):
    archive.verify(); target = outside(archive.repo, target)
    if target.exists(): raise WorkflowError('Entwurfsordner muss neu sein')
    body = proposal(archive.catalog(), answers, effective_from)
    atomic(target / 'betriebsangaben.json', encoded(body))
    atomic(target / 'verfahrensdokumentation.md', markdown(body).encode('utf8'))
    return {'ok': True, 'revision': sha(encoded(body)), 'output': str(target),
            'saved': False, 'open': sum(v['status'] == 'open' for v in body['answers'].values())}


def save(workflow, body, revision, approved):
    if not approved or revision != sha(encoded(body)):
        raise WorkflowError('Betriebsdokumentation benötigt Bestätigung des konkreten Entwurfs und seiner Revision')
    workflow.archive.verify(); before = workflow.archive.catalog()
    current = before.get('operating_procedure', {}).get('current')
    expected = proposal(before, body['answers'], body['effective_from'])
    if body != expected: raise WorkflowError('Betriebsdokumentation wurde inzwischen geändert; Entwurf neu vorbereiten')
    if current and (current['answers'], current['effective_from']) == (body['answers'], body['effective_from']):
        return {'ok': True, 'changed': False}
    after = copy.deepcopy(before)
    versions = after.setdefault('operating_procedure', {'current': None, 'history': []})
    if current: versions['history'].append(copy.deepcopy(current))
    versions['current'] = {'answers': body['answers'], 'effective_from': body['effective_from'], 'recorded_at': now()}
    workflow.commit(before, after, {})
    return {'ok': True, 'changed': True, **public_status(after)}


def validate(catalog):
    value = catalog.get('operating_procedure')
    if value is None: return
    from datetime import datetime
    for row in [value['current'], *value['history']]:
        if checked_answers(row['answers']) != row['answers'] or datetime.fromisoformat(row['recorded_at']).tzinfo is None:
            raise ValueError('Ungültige private Betriebsdokumentation')
        if len(row['effective_from']) != 10: raise ValueError('Ungültiger Gültigkeitsbeginn')
        date.fromisoformat(row['effective_from'])
