"""Read a finalized backup and decrypt its Git bundle outside both repositories."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from dotenv import dotenv_values

TOOL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOL/'src'))
from autobookkeeping.archive import Archive, atomic, cd_verify, outside, unseal
from autobookkeeping.workspace import git_environment


def restore(source, password_file, output):
    source=Path(source).resolve()
    cd_verify(source)
    destination=outside(source,Path(output))/'repository.bundle'
    if destination.exists(): raise ValueError('Bundle-Ziel existiert bereits')
    password=dotenv_values(password_file).get('ENCRYPTION_PASSWORD','')
    archive=Archive(source,password)
    data=unseal(archive.unlock(),(source/'repository.bundle.enc').read_bytes(),'repository.bundle')
    with tempfile.TemporaryDirectory(prefix='bookkeeping-restore-') as temporary:
        bundle=Path(temporary)/'repository.bundle'; atomic(bundle,data)
        subprocess.run(['git','init','--quiet',temporary],env=git_environment(),check=True,capture_output=True)
        subprocess.run(['git','-C',temporary,'bundle','verify',str(bundle)],env=git_environment(),check=True,capture_output=True)
    atomic(destination,data)
    return {'ok':True,'bundle':str(destination)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Verschlüsselte CD-Sicherung ohne bestehenden Datenworkspace wiederherstellen')
    parser.add_argument('source',type=Path);parser.add_argument('--password-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try: print(json.dumps(restore(args.source,args.password_file,args.output),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__}));sys.exit(1)
