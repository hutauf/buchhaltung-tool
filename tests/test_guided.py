import json
import runpy
from pathlib import Path
import pytest
from cryptography.exceptions import InvalidTag
from autobookkeeping.archive import Archive, encoded
from autobookkeeping import guided
from autobookkeeping.local_invoices import WorkflowError
from autobookkeeping.diagnostics import failure

ROOT=Path(__file__).resolve().parents[1]


def test_payment_requires_concrete_confirmation_and_keeps_signed_amount(monkeypatch):
    inputs=iter(['-4,50','2011-01-02','SYNTHETIC-BANK-ROW','Synthetic statement','ja','BUCHEN'])
    monkeypatch.setattr('builtins.input',lambda _:next(inputs))
    p=guided.payment('SYNTHETIC-RECORD')
    assert p['amount']=='-4.50' and p['source_complete'] is True and p['record_id']=='SYNTHETIC-RECORD'
    monkeypatch.setattr('builtins.input',lambda _:'nein')
    with pytest.raises(WorkflowError,match='Abgebrochen'): guided.confirm(p,True)


def test_receipt_dialog_builds_valid_metadata_without_json_authoring(monkeypatch):
    inputs=iter(['Synthetic vendor','SYNTHETIC-1','Synthetic subscription','2011-01-02','11','11','0',
                 'no_vat_shown','software_subscriptions','DE','business','nein','nein','Synthetic original reviewed','','ENTWURF'])
    monkeypatch.setattr('builtins.input',lambda _:next(inputs))
    p=guided.receipt({})
    assert p['gross']=='11.00' and p['net']=='11.00' and p['vat']=='0.00'
    assert p['vat_rate'] is None and p['pay_date'] is None and p['category']=='software_subscriptions'


def test_safe_errors_have_next_steps_without_secret_exception_text(tmp_path):
    import httpx
    secret='SYNTHETIC-SECRET-NOT-PUBLIC'
    error=httpx.HTTPStatusError(secret,request=httpx.Request('GET','https://example.invalid/'+secret),response=httpx.Response(401))
    result=failure(error)
    assert '401' in result['error'] and secret not in json.dumps(result)
    (tmp_path/'output').mkdir();(tmp_path/'output/publication.json').write_text('{}')
    result=failure(InvalidTag(secret),tmp_path)
    assert 'passwort pruefen' in result['hint'] and result['publication_pending']
    assert 'resume' in result['next'] and secret not in json.dumps(result)


def test_password_memory_check_uses_real_wrapper_not_env_equality(tmp_path,monkeypatch,capsys):
    archive=Archive(tmp_path,'synthetic-password-for-tests');archive.init()
    (tmp_path/'.env').write_text('ENCRYPTION_PASSWORD=wrong-local-value\n')
    module=runpy.run_path(str(ROOT/'scripts/password.py'))
    module['run'].__globals__['data_root']=lambda:tmp_path
    monkeypatch.setattr(module['getpass'],'getpass',lambda _:'synthetic-password-for-tests')
    assert module['run']('pruefen')['ok']
    monkeypatch.setattr(module['getpass'],'getpass',lambda _:'wrong-local-value')
    with pytest.raises(InvalidTag): module['run']('pruefen')
    assert 'synthetic-password-for-tests' not in capsys.readouterr().out


def test_password_setup_never_overwrites_existing_archive(tmp_path,monkeypatch):
    module=runpy.run_path(str(ROOT/'scripts/password.py'))
    module['run'].__globals__['data_root']=lambda:tmp_path
    module['run'].__globals__['assert_data_repo']=lambda *a,**k:tmp_path
    (tmp_path/'.env').write_text('GMX_EMAIL=synthetic@example.invalid\n')
    inputs=iter(['synthetic-passphrase-long','synthetic-passphrase-long'])
    monkeypatch.setattr(module['getpass'],'getpass',lambda _:next(inputs))
    monkeypatch.setattr('builtins.input',lambda _:'GESICHERT')
    assert module['run']('einrichten')['ok']
    from dotenv import dotenv_values
    assert dotenv_values(tmp_path/'.env')['GMX_EMAIL']=='synthetic@example.invalid'
    before=(tmp_path/'.env').read_bytes()
    with pytest.raises(WorkflowError):module['run']('einrichten')
    assert (tmp_path/'.env').read_bytes()==before


def test_password_never_falls_back_to_echoed_terminal_input(monkeypatch):
    module=runpy.run_path(str(ROOT/'scripts/password.py'))
    def no_echo(_):
        import warnings
        warnings.warn('synthetic no terminal',module['getpass'].GetPassWarning)
        raise AssertionError('Must abort before asking with visible input')
    monkeypatch.setattr(module['getpass'],'getpass',no_echo)
    with pytest.raises(WorkflowError,match='verdeckt'):module['secret']('Synthetic prompt')
