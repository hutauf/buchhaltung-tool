"""Fresh clone/venv acceptance test with isolated synthetic data, never real bookings."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]


def run_test(output: Path):
    output = output.resolve()
    if output.exists() or output.is_relative_to(TOOL):
        raise ValueError('Neuen Testordner außerhalb des Toolrepos angeben')
    if os.name == 'nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\FileSystem') as key:
            try: long_paths = winreg.QueryValueEx(key, 'LongPathsEnabled')[0]
            except FileNotFoundError: long_paths = 0
        if not long_paths and len(str(output / 'restored-tool' / '.venv')) > 40:
            raise ValueError('Windows-Pfadlängen begrenzt: kurzen Testpfad wie C:/bk1 verwenden (Factur-X enthält umfangreiche Dateinamen)')
    output.mkdir(parents=True)
    clone = output / 'tool'
    environment = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')
                   and k not in ('PYTHONPATH','GH_TOKEN','GITHUB_TOKEN','BOOKKEEPING_EXPECTED_SNAPSHOT')}
    environment.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    def run(command, cwd=output):
        result = subprocess.run(list(map(str,command)),cwd=cwd,env=environment,
                                capture_output=True,timeout=600)
        with (output/'test.log').open('ab') as stream:
            stream.write(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('Release-Test fehlgeschlagen; lokales test.log prüfen')
        return result.stdout
    run(['git','clone','--quiet','--no-hardlinks','-c','core.autocrlf=false',TOOL,clone])
    run(['git','-C',clone,'config','user.name','Synthetic Release Test'])
    run(['git','-C',clone,'config','user.email','synthetic@example.invalid'])
    run(['git','-C',clone,'config','core.autocrlf','false'])
    venv.EnvBuilder(with_pip=True).create(clone/'.venv')
    python = clone/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    run([python,'-m','pip','install','-e',str(clone)+'[test]'])
    remote = output/'synthetic-private.git'
    run(['git','init','--bare',remote])
    run([python,'-X','utf8',clone/'scripts/setup_workspace.py','--data-url',remote],clone)
    data=clone/'daten'
    (data/'.env').write_text('ENCRYPTION_PASSWORD=synthetic-release-test-password\n',encoding='utf8')
    for key,value in [('user.name','Synthetic Release Test'),('user.email','synthetic@example.invalid'),('core.autocrlf','false')]:
        run(['git','-C',data,'config',key,value])
    run(['git','-C',data,'add','.bookkeeping-data.json','.gitignore','.gitattributes','workspace.json',
         'AGENTS.md','verfahrensdokumentation.md','buchhaltung'])
    run(['git','-C',data,'commit','-m','Synthetic initial workspace'])
    run(['git','-C',data,'push','-u','origin','HEAD:main'])
    run([python,'-X','utf8',clone/'tests/release_smoke_scenario.py',output],clone)
    return json.loads((output/'report.json').read_bytes())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Frische Pythonumgebung und synthetischen Ablauf testen')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try: print(json.dumps(run_test(args.output),ensure_ascii=False,indent=2))
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));sys.exit(1)
