import importlib.util
from pathlib import Path
import pytest

PATH = Path(__file__).resolve().parents[1] / 'ansible/playbooks/files/host-network-recovery.py'


def module():
    spec = importlib.util.spec_from_file_location('recovery', PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_capture_rejects_ambiguous_or_non_lan_defaults():
    m = module()
    addresses = [{'ifname': 'eno1', 'address': 'aa:bb:cc:dd:ee:ff', 'addr_info': [
        {'family': 'inet', 'local': '192.168.1.17', 'prefixlen': 24}]}]
    route = {'dst': 'default', 'dev': 'eno1', 'gateway': '192.168.1.1'}
    assert m.management_network([route], addresses)['address'] == '192.168.1.17/24'
    with pytest.raises(ValueError):
        m.management_network([route, route], addresses)
    with pytest.raises(ValueError):
        m.management_network([{**route, 'gateway': '10.0.0.1'}], addresses)


def test_recovery_refuses_live_containers_and_ceph():
    m = module()
    for processes, mounts in [(['containerd-shim-runc-v2'], ''), (['cilium-agent'], ''),
                              ([], 'x /mnt ceph rw 0 0'), ([], '/dev/rbd0 /mnt ext4 rw 0 0')]:
        with pytest.raises(RuntimeError):
            m.require_quiesced(processes, mounts)
    m.require_quiesced(['sshd', 'python3'], '/dev/sda2 / ext4 rw 0 0')


def test_cleanup_stderr_is_not_treated_as_success():
    m = module()
    with pytest.raises(RuntimeError):
        m.check_cleanup_result(0, 'Error: cannot detach BPF program\n')
    with pytest.raises(RuntimeError):
        m.check_cleanup_result(1, '')
    m.check_cleanup_result(0, '')


def test_restore_cannot_touch_network_before_quiescence_check(tmp_path, monkeypatch):
    m = module()
    (tmp_path / 'armed').touch()
    def blocked():
        raise RuntimeError('live containers')
    monkeypatch.setattr(m, 'preflight', blocked)
    monkeypatch.setattr(m, 'run', lambda *a, **k: pytest.fail('network command before gate'))
    with pytest.raises(RuntimeError, match='live containers'):
        m.restore(tmp_path, {})


def test_stale_pidfile_can_be_preserved_across_filesystems(tmp_path, monkeypatch):
    import errno
    m = module()
    source = tmp_path / 'runtime' / 'cilium.pid'
    source.parent.mkdir()
    source.write_text('999999999\n')
    recovery = tmp_path / 'persistent'
    recovery.mkdir()
    def cross_device(*args, **kwargs):
        raise OSError(errno.EXDEV, 'cross-device rename')
    monkeypatch.setattr(Path, 'rename', cross_device)
    m.retire_pidfile(source, recovery)
    assert not source.exists()
    assert (recovery / 'stale-cilium.pid').read_text() == '999999999\n'


def test_second_capture_cannot_arm_another_timer(tmp_path, monkeypatch):
    m = module()
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    monkeypatch.setattr(m, 'preflight', lambda: None)
    monkeypatch.setattr(m, 'run', lambda *a, **k: None)
    a, b = tmp_path / 'capture-a', tmp_path / 'capture-b'
    a.mkdir(); b.mkdir()
    import time
    m.arm(a, {'created_at': time.time(), 'unit': 'one'})
    with pytest.raises(RuntimeError, match='active rescue'):
        m.arm(b, {'created_at': time.time(), 'unit': 'two'})


def test_cancel_only_removes_its_active_capture(tmp_path, monkeypatch):
    m = module()
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    monkeypatch.setattr(m, 'run', lambda *a, **k: None)
    old = tmp_path / 'capture-old'; old.mkdir()
    (old / 'armed').touch()
    (tmp_path / 'active').write_text('capture-new')
    m.cancel(old, {'unit': 'old-unit'})
    assert (tmp_path / 'active').read_text() == 'capture-new'
    assert not (old / 'armed').exists()


def test_cancel_clears_its_active_record(tmp_path, monkeypatch):
    m = module(); monkeypatch.setattr(m, 'ROOT', tmp_path)
    monkeypatch.setattr(m, 'run', lambda *a, **k: None)
    folder = tmp_path / 'capture-own'; folder.mkdir()
    (folder / 'armed').touch(); (tmp_path / 'active').write_text(folder.name)
    m.cancel(folder, {'unit': 'own-unit'})
    assert not (tmp_path / 'active').exists()


def test_cancellation_load_does_not_need_network_or_snapshot(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    m = module(); monkeypatch.setattr(m, 'ROOT', tmp_path)
    folder = tmp_path / 'capture-test'; folder.mkdir()
    (folder / 'state.json').write_text(json.dumps({'unit': 'k3s-net-rescue-123456abcdef'}))
    original = Path.stat
    monkeypatch.setattr(Path, 'stat', lambda self, **kw: SimpleNamespace(st_uid=0, st_mode=0o40700) if self == folder else original(self, **kw))
    monkeypatch.setattr(m, 'run', lambda *a, **k: pytest.fail('cancel must not inspect network'))
    assert m.load(folder, validate_network=False)[1]['unit'] == 'k3s-net-rescue-123456abcdef'


@pytest.mark.parametrize('version, command', [
    ('1.14.5', 'cleanup'), ('1.20.2', 'post-uninstall-cleanup'),
])
def test_restore_uses_saved_client_version_without_expanding_cleanup_scope(tmp_path, monkeypatch, version, command):
    from subprocess import CompletedProcess
    m = module()
    root = tmp_path / 'recovery'; root.mkdir()
    folder = root / 'capture-test'; folder.mkdir()
    (folder / 'armed').touch()
    (root / 'active').write_text(folder.name)
    (folder / 'iptables.save').write_text('saved firewall')
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'preflight', lambda: None)
    monkeypatch.setattr(m, 'retire_pidfile', lambda *a: None)
    monkeypatch.setattr(m, 'repair_ipv4', lambda *a: [])
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        output = f'Client: {version} test-build\nDaemon: Not responding\n' if args[-1] == 'version' else ''
        return CompletedProcess(args, 0, output, '')
    monkeypatch.setattr(m, 'run', run)
    m.restore(folder, {'interface': 'eno1'})
    assert (str(folder / 'cilium'), command, '--bpf-state', '--force') in calls
    assert not any('--all-state' in args for args in calls)


@pytest.mark.parametrize('version', ['1.20.20', '1.21.0', '1.14.5-dev', 'unknown'])
def test_restore_refuses_unreviewed_client_before_touching_pidfile_or_network(tmp_path, monkeypatch, version):
    from subprocess import CompletedProcess
    m = module(); monkeypatch.setattr(m, 'ROOT', tmp_path)
    folder = tmp_path / 'capture-test'; folder.mkdir()
    (folder / 'armed').touch(); (tmp_path / 'active').write_text(folder.name)
    monkeypatch.setattr(m, 'preflight', lambda: None)
    monkeypatch.setattr(m, 'retire_pidfile', lambda *a: pytest.fail('unsupported CLI touched pidfile'))
    def run(*args, **kwargs):
        assert args == (str(folder / 'cilium'), 'version')
        return CompletedProcess(args, 0, f'Client: {version} test-build\nDaemon: 1.20.2\n', '')
    monkeypatch.setattr(m, 'run', run)
    with pytest.raises(RuntimeError, match='Unexpected Cilium version'):
        m.restore(folder, {'interface': 'eno1'})
