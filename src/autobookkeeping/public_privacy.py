"""Check public Git snapshots, identity and locally available private fingerprints."""
from __future__ import annotations
import io
import json
import os
import re
import subprocess
from pathlib import Path

ROOT_FILES={'.bookkeeping-tool.json','.gitattributes','.gitignore','AGENTS.md','README.md','LICENSE','pyproject.toml','requirements.txt'}
DIRECTORIES={'src','scripts','tests','docs','skills','.github','.githooks'}
SUFFIXES={'.py','.md','.html','.toml','.txt','.yaml','.yml'}


def git(repo,*args,input=None):
    env=dict(os.environ)
    for key in ('GIT_DIR','GIT_WORK_TREE','GIT_COMMON_DIR'):env.pop(key,None)
    return subprocess.check_output(['git','-C',str(repo),*args],input=input,env=env,stderr=subprocess.PIPE,timeout=60)


def private_fingerprints(repo):
    """Never persist or display private strings in an audit report."""
    data=repo/'daten';values=set()
    if not (data/'.env').exists():return values
    from dotenv import dotenv_values
    environment=dotenv_values(data/'.env')
    for key,value in environment.items():
        if value and len(value)>=4 and any(part in key.upper() for part in ('PASSWORD','TOKEN','SECRET','API_KEY','EMAIL')):
            values.add(value.casefold())
    from autobookkeeping.archive import Archive,unseal,sha
    archive=Archive(data)
    if not archive.key_path.exists():return values
    from autobookkeeping.workspace import assert_data_repo
    assert_data_repo(data)
    values.update(git(data,'rev-list','--all').decode().splitlines())
    values.add(sha((archive.root/'database.json.enc').read_bytes()))
    identifiers={'order_id','orderid','order_id_aliases','tracking_number','trackingnumber','transaction_id','transactionid','item_id','itemid','invoice_id','expense_id','receipt_id'}
    personal={'name','firstname','lastname','fullname','email','street','street1','street2','address1','address2','iban','tax_number'}
    def walk(value,path=(),field=''):
        if isinstance(value,dict):
            for key,child in value.items():walk(child,path+(str(key).casefold(),),str(key).casefold())
        elif isinstance(value,list):
            for child in value:walk(child,path,field)
        elif isinstance(value,(str,int)):
            text=str(value).strip()
            if not text:return
            if field in identifiers and len(text)>=6:values.add(text.casefold())
            if field in ('sha256','sha256_plaintext','sha256_ciphertext') and len(text)>=32:values.add(text.casefold())
            if field in personal and len(text)>=4 and text.casefold() not in ('berlin','deutschland') and any(any(part in name for part in ('buyer','customer','issuer','shipping_address')) for name in path[:-1]):
                values.add(text.casefold())
    walk(archive.catalog())
    checklist=data/'bookkeeping_checklist.json.enc'
    if checklist.exists():walk(json.loads(unseal(archive.unlock(),checklist.read_bytes(),'bookkeeping_checklist.json')))
    return values


def blobs(repo,oids):
    unique=sorted(set(oids))
    if not unique:return {}
    response=git(repo,'cat-file','--batch',input=('\n'.join(unique)+'\n').encode())
    stream=io.BytesIO(response);result={}
    for oid in unique:
        header=stream.readline().split()
        if len(header)!=3 or header[0].decode()!=oid or header[1]!=b'blob':raise ValueError('Ungültiges öffentliches Git-Objekt')
        result[oid]=stream.read(int(header[2]))
        if stream.read(1)!=b'\n':raise ValueError('Ungültige Git-Objektgrenze')
    return result


def content_issues(data,fingerprints,secrets=()):
    try:text=data.decode('utf8')
    except UnicodeDecodeError:return ['binary_content']
    issues=[];folded=text.casefold()
    pattern=fingerprints if hasattr(fingerprints,'search') else re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(v) for v in fingerprints)+r')(?!\w)') if fingerprints else None
    if pattern and pattern.search(folded) or any(value in folded for value in secrets):issues.append('private_fingerprint')
    if re.search(r'(?i)(?:[A-Z]:[\\/]Users[\\/]|/home/)[A-Za-z0-9_.-]+',text):issues.append('personal_path')
    if any(not match.startswith('00-') for match in re.findall(r'\b\d{2}-\d{5}-\d{5}\b',text)):issues.append('non_synthetic_order_id')
    if re.search(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',text):issues.append('private_key')
    return issues


def audit(repo,name,email,staged=False,extra=(),fingerprints=None):
    repo=Path(repo).resolve();issues=[];entries=[];commits=[]
    fingerprints=private_fingerprints(repo) if fingerprints is None else fingerprints
    loaded=bool(fingerprints)
    pattern=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(v) for v in sorted(fingerprints,key=len,reverse=True))+r')(?!\w)') if fingerprints else None
    secrets=[]
    if (repo/'daten/.env').exists():
        from dotenv import dotenv_values
        secrets=[value.casefold() for key,value in dotenv_values(repo/'daten/.env').items() if value and len(value)>=4 and any(part in key.upper() for part in ('PASSWORD','TOKEN','SECRET','API_KEY'))]
    if not name or not email or not email.endswith('@users.noreply.github.com'):
        raise ValueError('Öffentlichen Anzeigenamen und GitHub-Noreply-Adresse konfigurieren')
    if staged:
        for variable in ('GIT_AUTHOR_IDENT','GIT_COMMITTER_IDENT'):
            identity=git(repo,'var',variable).decode()
            if not identity.startswith(name+' <'+email+'> '):issues.append({'scope':'identity','reason':'unexpected_identity'})
        for entry in git(repo,'ls-files','--stage','-z').split(b'\0'):
            if entry:
                details,path=entry.split(b'\t',1);mode,oid,stage=details.split()
                if stage!=b'0':issues.append({'scope':'index','reason':'unmerged_index'})
                entries.append((path.decode(),mode.decode(),oid.decode()))
    else:
        commits=git(repo,'rev-list','--all',*extra).decode().splitlines()
        for commit in commits:
            raw=git(repo,'cat-file','commit',commit);headers=raw.split(b'\n\n',1)[0].decode()
            for field in ('author','committer'):
                match=re.search(r'^'+field+r' (.*?) <(.*?)> \d+ [+-]\d{4}$',headers,re.M)
                if not match or match.groups()!=(name,email):issues.append({'scope':'commit','reason':'unexpected_identity'})
            for reason in content_issues(raw,pattern,secrets):issues.append({'scope':'commit','reason':reason})
            for entry in git(repo,'ls-tree','-r','-z',commit).split(b'\0'):
                if entry:
                    details,path=entry.split(b'\t',1);mode,kind,oid=details.split()
                    entries.append((path.decode(),mode.decode(),oid.decode()))
    contents=blobs(repo,[oid for path,mode,oid in entries if mode in ('100644','100755')])
    for path,mode,oid in set(entries):
        p=Path(path)
        allowed=path in ROOT_FILES or p.parts[0] in DIRECTORIES and (p.suffix in SUFFIXES or p.parts[0]=='.githooks' and p.name in ('pre-commit','pre-push'))
        if not allowed or mode not in ('100644','100755'):
            issues.append({'scope':'file','path':path,'reason':'not_public_code'});continue
        for reason in content_issues(contents[oid],pattern,secrets):issues.append({'scope':'file','path':path,'reason':reason})
    return {'ok':not issues,'commits_checked':len(commits),'file_versions_checked':len(set(entries)),
            'private_fingerprints_loaded':loaded,'issues':issues}
