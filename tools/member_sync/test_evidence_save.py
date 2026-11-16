"""Atomic evidence writes tolerate temporary Windows readers, never partial writes."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import runner


@pytest.mark.skipif(os.name!='nt',reason='Windows file sharing semantics')
def test_reader_release_allows_atomic_evidence_update(tmp_path):
    path=tmp_path/'evidence.json';runner.save(path,{'old':True})
    reader=path.open('rb')
    def release():time.sleep(.15);reader.close()
    thread=threading.Thread(target=release);thread.start()
    try:runner.save(path,{'new':True})
    finally:thread.join();reader.close()
    assert json.loads(path.read_bytes())=={'new':True}
    assert not list(tmp_path.glob('.pending-*'))


@pytest.mark.skipif(os.name!='nt',reason='Windows file sharing semantics')
def test_persistent_reader_stops_and_preserves_old_evidence(tmp_path):
    path=tmp_path/'evidence.json';runner.save(path,{'old':True})
    with path.open('rb'):
        with pytest.raises(PermissionError):runner.save(path,{'new':True})
    assert json.loads(path.read_bytes())=={'old':True}
    assert not list(tmp_path.glob('.pending-*'))


def test_other_io_error_is_not_retried(tmp_path,monkeypatch):
    calls=[]
    def fail(*args):calls.append(True);raise OSError('synthetic disk failure')
    monkeypatch.setattr(runner.os,'replace',fail)
    with pytest.raises(OSError):runner.save(tmp_path/'evidence.json',{'value':1})
    assert len(calls)==1 and not list(tmp_path.glob('.pending-*'))
