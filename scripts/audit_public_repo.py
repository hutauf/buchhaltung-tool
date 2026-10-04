"""No private strings are printed; examine the complete history before pushing."""
import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOL/'src'))
from autobookkeeping.public_privacy import audit,git


def configured(key):
    try:return git(TOOL,'config','--local','--get',key).decode().strip()
    except subprocess.CalledProcessError:return None


def main():
    parser=argparse.ArgumentParser(description='Öffentlichen Code, alle Commit-Versionen und Git-Identität prüfen')
    parser.add_argument('--staged',action='store_true');parser.add_argument('--refs-from-stdin',action='store_true')
    parser.add_argument('--name');parser.add_argument('--email');args=parser.parse_args()
    extra=[]
    if args.refs_from_stdin:
        for line in sys.stdin:
            fields=line.split()
            if len(fields)!=4:raise ValueError('Ungültige Push-Referenz')
            if set(fields[1])!={'0'}:extra.append(fields[1])
    policy=TOOL/'.github/public-identities.toml'
    identities=tomllib.loads(policy.read_text(encoding='utf8')).get('commits',{}) if policy.exists() else {}
    identities={commit:(identity['name'],identity['email']) for commit,identity in identities.items()}
    result=audit(TOOL,args.name or configured('bookkeeping.publicName'),args.email or configured('bookkeeping.publicEmail'),args.staged,extra,historical_identities=identities)
    print(json.dumps(result,ensure_ascii=False,indent=2));return int(not result['ok'])


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__}));sys.exit(1)
