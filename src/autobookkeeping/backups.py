"""Encrypted backup register: preparation is never proof of a written medium."""
import copy
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from autobookkeeping.archive import Archive, atomic, cd_export, cd_verify, encoded, outside, sha, unseal, verify_checkpoint
from autobookkeeping.local_invoices import now, WorkflowError
from autobookkeeping.workspace import git, git_environment


def register(workflow, directory):
    source=outside(workflow.archive.repo, Path(directory))
    checked=cd_verify(source)
    descriptor=json.loads((source/'BACKUP.json').read_bytes())
    if descriptor.get('version') != 1: raise WorkflowError('Sicherung benötigt aktuelle BACKUP.json; kein rückwirkender Sicherungsnachweis')
    digest=sha((source/'SHA256SUMS.json').read_bytes()); bid='backup:'+digest
    workflow.archive.verify(); before=workflow.archive.catalog()
    if bid in before.get('backup_register',{}): return {'ok':True,'changed':False,'id':bid}
    after=copy.deepcopy(before)
    row=dict(descriptor, id=bid, export_directory=str(source), manifest_sha256=digest,
             files=checked['files'], registered_at=now(), events=[])
    after.setdefault('backup_register',{})[bid]=row
    workflow.commit(before,after,{})
    return {'ok':True,'changed':True,'id':bid,'written':False,'readback_verified':False}


def export(workflow, directory):
    result=cd_export(workflow.archive, directory)
    return dict(result, register=register(workflow,directory))


def source_for(workflow, bid, directory):
    workflow.archive.verify(); row=workflow.archive.catalog().get('backup_register',{}).get(bid)
    if row is None: raise WorkflowError('Sicherung nicht im Register')
    source=outside(workflow.archive.repo, Path(directory))
    cd_verify(source)
    if sha((source/'SHA256SUMS.json').read_bytes()) != row['manifest_sha256']:
        raise WorkflowError('Gelesenes Medium passt nicht zur registrierten Sicherung')
    if json.loads((source/'BACKUP.json').read_bytes())['data_commit'] != row['data_commit']:
        raise WorkflowError('Abweichender Sicherungsstand')
    return source, row


def event(workflow,bid,payload):
    before=workflow.archive.catalog(); after=copy.deepcopy(before)
    after['backup_register'][bid]['events'].append(dict(payload, at=now()))
    workflow.commit(before,after,{})


def confirm(workflow,bid,directory,label,written,approved):
    if not written or not approved or not isinstance(label,str) or not label.strip():
        raise WorkflowError('Medium, erfolgtes Schreiben/Abschließen und konkrete Freigabe erforderlich')
    source,row=source_for(workflow,bid,directory)
    if source==Path(row['export_directory']).resolve():
        raise WorkflowError('Zurücklesen vom tatsächlichen Sicherungsmedium, nicht vom Exportordner')
    event(workflow,bid,{'type':'medium_readback','written_asserted':True,'checksums_verified':True,
                        'directory':str(source),'medium_label':label})
    return {'ok':True,'id':bid,'written_asserted':True,'readback_verified':True,
            'hardware_detection':False}


def restore_test(workflow,bid,directory,raise_failure=False):
    source,row=source_for(workflow,bid,directory)
    try:
        with tempfile.TemporaryDirectory(prefix='bookkeeping-restore-test-') as temporary:
            target=outside(workflow.archive.repo,Path(temporary))
            bundle=target/'repository.bundle'
            atomic(bundle,unseal(workflow.archive.unlock(),(source/'repository.bundle.enc').read_bytes(),'repository.bundle'))
            def run(*args):
                return subprocess.check_output(['git',*map(str,args)],env=git_environment(),stderr=subprocess.PIPE)
            data=target/'data'; tool=target/'tool'
            run('clone','--quiet','-c','core.autocrlf=false',bundle,data)
            run('clone','--quiet','-c','core.autocrlf=false',source/'tool.bundle',tool)
            run('-C',data,'checkout','--quiet','--detach',row['data_commit'])
            run('-C',tool,'checkout','--quiet','--detach',row['tool_commit'])
            run('-C',data,'fsck','--full');run('-C',tool,'fsck','--full')
            restored=Archive(data,workflow.archive.password); check=restored.verify()
            proofs=list((restored.root/'nachweise').glob('*.json'))
            for statement in proofs: verify_checkpoint(data,statement,workflow.archive.password)
            event(workflow,bid,{'type':'restore_test','result':'passed', 'records':check['records'],
                               'directory':str(source),
                               'documents':check['documents'],'git_proofs':len(proofs),
                               'dependency_install_tested':False,'blockchain_reverified':False})
            return {'ok':True,'id':bid,'restored':True,'records':check['records'],'documents':check['documents'],
                    'dependency_install_tested':False,'blockchain_reverified':False}
    except Exception as exc:
        event(workflow,bid,{'type':'restore_test','result':'failed','directory':str(source),'error_type':type(exc).__name__})
        if raise_failure: raise
        return {'ok':False,'id':bid,'restored':False,'error_type':type(exc).__name__,
                'hint':'Passwort, Pakete, Medium und Git-Historie prüfen; Ergebnis im Register erhalten'}


def public_status(catalog):
    values=sorted(catalog.get('backup_register',{}).values(),key=lambda r:r['registered_at'])
    rows=[]
    for row in values:
        written=[e for e in row['events'] if e['type']=='medium_readback']
        tested=[e for e in row['events'] if e['type']=='restore_test']
        rows.append({'ref':row['id'], 'prepared_at':row['prepared_at'], 'registered_at':row['registered_at'],
                     'files':row['files'], 'data_commit':row['data_commit'],
                     'readback_at':written[-1]['at'] if written else None,
                     'restore_result':tested[-1]['result'] if tested else 'untested',
                     'restore_at':tested[-1]['at'] if tested else None})
    return {'rows':rows, 'interval_days':31}


def validate(catalog):
    import re
    for bid,row in catalog.get('backup_register',{}).items():
        if (bid != 'backup:'+row['manifest_sha256'] or not re.fullmatch(r'[a-f0-9]{64}',row['manifest_sha256'])
            or any(not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}',row[k]) for k in ('data_commit','tool_commit'))
            or type(row['files']) is not int or row['files']<1):
            raise ValueError('Ungültiger Sicherungsnachweis')
        for key in ('prepared_at','registered_at'): datetime.fromisoformat(row[key])
        for entry in row['events']:
            datetime.fromisoformat(entry['at'])
            if entry['type']=='medium_readback':
                if entry.get('written_asserted') is not True or entry.get('checksums_verified') is not True:
                    raise ValueError('Medium ohne Schreibbestätigung und Rückleseprüfung')
            elif entry['type']=='restore_test':
                if entry['result'] not in ('passed','failed'): raise ValueError('Unbekanntes Testergebnis')
            else: raise ValueError('Unbekannter Sicherungseintrag')
