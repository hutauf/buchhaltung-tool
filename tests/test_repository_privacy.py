import subprocess
from pathlib import Path

import httpx
import pytest

from autobookkeeping.local_invoices import WorkflowError
from autobookkeeping import repository_privacy as module


@pytest.mark.parametrize('url', ['git@github.com:synthetic/private.git',
                                'https://github.com/synthetic/private.git',
                                'ssh://git@github.com/synthetic/private.git'])
def test_supported_canonical_remotes(url):
    assert module.github_repository(url) == 'synthetic/private'


@pytest.mark.parametrize('url', ['https://github.com.evil.invalid/user/repo',
                                'https://secret:password@github.com/user/repo',
                                'https://github.com/user/repo?token=secret',
                                'git@unverified.invalid:user/repo',
                                'https://github.com/user/../repo'])
def test_untrusted_or_credential_bearing_addresses_rejected(url):
    with pytest.raises(WorkflowError): module.github_repository(url)


def test_only_explicit_existing_local_bare_repository_is_accepted(tmp_path):
    with pytest.raises(WorkflowError): module.github_repository(str(tmp_path / 'absent'))
    subprocess.run(['git', 'init', '--bare', str(tmp_path / 'local.git')], check=True, capture_output=True)
    assert module.assert_private_remote(str(tmp_path / 'local.git'), tmp_path)['verification'] == 'local_bare_repository'


@pytest.mark.parametrize('status,metadata,allowed', [
    (200, {'full_name':'synthetic/private','private':True,'visibility':'private'}, True),
    (200, {'full_name':'synthetic/private','private':False,'visibility':'public'}, False),
    (200, {'full_name':'synthetic/private','private':True,'visibility':'internal'}, False),
    (200, {'full_name':'other/repository','private':True,'visibility':'private'}, False),
    (200, {'full_name':'synthetic/private'}, False),
    (404, {}, False), (403, {}, False), (302, {}, False),
])
def test_visibility_requires_exact_authenticated_metadata(monkeypatch,tmp_path,status,metadata,allowed):
    monkeypatch.setattr(module, 'github_token', lambda repo:'synthetic-secret')
    def get(url,**options):
        assert url == 'https://api.github.com/repos/synthetic/private'
        assert options['headers']['Authorization'] == 'Bearer synthetic-secret'
        assert options['follow_redirects'] is False
        return httpx.Response(status,json=metadata)
    monkeypatch.setattr(module.httpx,'get',get)
    if allowed:
        assert module.assert_private_remote('git@github.com:synthetic/private.git', tmp_path)['private'] is True
    else:
        with pytest.raises(WorkflowError) as caught:
            module.assert_private_remote('git@github.com:synthetic/private.git', tmp_path)
        assert 'synthetic-secret' not in str(caught.value)


def test_network_error_does_not_leak_credentials(monkeypatch,tmp_path):
    monkeypatch.setattr(module,'github_token',lambda repo:'synthetic-secret')
    def failed(*args,**kwargs): raise httpx.ConnectError('synthetic-secret')
    monkeypatch.setattr(module.httpx,'get',failed)
    with pytest.raises(WorkflowError) as caught:
        module.assert_private_remote('git@github.com:synthetic/private.git',tmp_path)
    assert 'synthetic-secret' not in str(caught.value)


def test_authentication_prefers_local_secret_and_credential_lookup_never_prompts(monkeypatch,tmp_path):
    monkeypatch.delenv('GH_TOKEN',raising=False);monkeypatch.delenv('GITHUB_TOKEN',raising=False)
    (tmp_path/'.env').write_text('GITHUB_TOKEN=synthetic-env-token\n')
    assert module.github_token(tmp_path) == 'synthetic-env-token'
    (tmp_path/'.env').unlink()
    def fill(command,**kwargs):
        assert kwargs['env']['GIT_TERMINAL_PROMPT']=='0' and kwargs['env']['GCM_INTERACTIVE']=='never'
        return subprocess.CompletedProcess(command,0,b'username=synthetic\npassword=synthetic-credential\n')
    monkeypatch.setattr(module.subprocess,'run',fill)
    assert module.github_token(tmp_path)=='synthetic-credential'
