"""The supported Vine entry point must protect writes before touching the backend."""
import importlib.util
from pathlib import Path
import sys


def test_approved_vine_write_uses_publication_and_archive_lock(monkeypatch, tmp_path):
    script = Path(__file__).parents[1] / 'scripts' / 'vine_backend.py'
    monkeypatch.syspath_prepend(str(script.parent))
    spec = importlib.util.spec_from_file_location('vine_script_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    events = []
    class Guard:
        result = {'pushed': True}
        def __init__(self, *args, **kwargs):
            self.enabled = kwargs.get('enabled', True)
        def __enter__(self):
            events.append('enter')
            return self
        def __exit__(self, *args):
            events.append('exit')
    monkeypatch.setattr(module, 'Publication', Guard)
    monkeypatch.setattr(module, 'FileLock', Guard)
    monkeypatch.setattr(module, 'data_root', lambda: tmp_path)
    monkeypatch.setattr(module, 'run', lambda: events.append('write') or 0)
    monkeypatch.setattr(module, 'print_json', lambda value: events.append('report'))
    monkeypatch.setattr(sys, 'argv', ['vine_backend.py', 'update-sale', '--approved'])
    assert module.main() == 0
    assert events == ['enter', 'enter', 'write', 'exit', 'exit', 'report']
