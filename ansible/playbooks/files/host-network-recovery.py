#!/usr/bin/env python3
"""Stage an IPv4 management-network rescue for this Debian/Cilium cutover.

Capture is safe on a running cluster. Check/arm/restore require stopped k3s,
no container shims/Cilium/Ceph processes and no Ceph/RBD mounts. This does not
restore Kubernetes, application data, or survive a reboot. Never arm before
final backups, and cancel before starting the replacement cluster.
"""
import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path('/var/lib/homelab/network-recovery')
LAN = ipaddress.ip_network('192.168.1.0/24')


def run(*args, check=True, data=None):
    try:
        result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=90)
    except subprocess.TimeoutExpired:
        result = subprocess.CompletedProcess(args, 124, '', 'Command timed out: ' + args[0])
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + args[0] + ': ' + result.stderr.strip())
    return result


def management_network(routes, addresses):
    defaults = [r for r in routes if r.get('dst') == 'default']
    if len(defaults) != 1:
        raise ValueError('Require exactly one IPv4 default route')
    route = defaults[0]
    if route.get('gateway') != '192.168.1.1':
        raise ValueError('Unexpected management gateway')
    links = [a for a in addresses if a['ifname'] == route['dev']]
    if len(links) != 1 or not re.fullmatch(r'[a-zA-Z0-9_.-]+', route['dev']):
        raise ValueError('Ambiguous management interface')
    link = links[0]
    # Keepalived's reserved API VIP must never become the SSH rescue address.
    ips = [a for a in link['addr_info'] if a['family'] == 'inet' and a['local'] != '192.168.1.18'
           and ipaddress.ip_address(a['local']) in LAN and a['prefixlen'] == 24]
    if len(ips) != 1:
        raise ValueError('Require one management /24 address')
    return {'interface': route['dev'], 'mac': link['address'],
            'address': ips[0]['local'] + '/24', 'gateway': route['gateway']}


def require_quiesced(processes, mounts):
    blockers = [p for p in processes if p.startswith(('containerd-shim', 'cilium-agent', 'ceph-', 'radosgw'))]
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) >= 3 and (fields[2] in ('ceph', 'fuse.ceph') or fields[0].startswith('/dev/rbd')):
            blockers.append('Ceph/RBD mount')
    if blockers:
        raise RuntimeError('Not quiesced: ' + ', '.join(sorted(set(blockers))))


def check_cleanup_result(code, stderr):
    # Cilium 1.14.5 logs this normal cleanup step to stderr.
    errors = '\n'.join(line for line in stderr.splitlines() if not re.fullmatch(
        r'time="[^"]+" level=info msg="Trying to unmount /run/cilium/cgroupv2"', line))
    if code or errors.strip():
        raise RuntimeError('Cilium cleanup reported an error: ' + errors.strip())


def cleanup_command(binary):
    version = run(str(binary), 'version').stdout
    match = re.match(r'Client: (1\.14\.5|1\.20\.2)(?:\s|$)', version)
    if not match:
        raise RuntimeError('Unexpected Cilium version; review cleanup compatibility')
    command = {'1.14.5': 'cleanup', '1.20.2': 'post-uninstall-cleanup'}[match[1]]
    # Rescue removes BPF state only; full teardown remains a separate operation.
    return [str(binary), command, '--bpf-state', '--force']


def processes():
    result = []
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            first = p.read_bytes().split(b'\0')[0].decode()
            if first:
                result.append(Path(first).name)
        except FileNotFoundError:
            pass
    return result


def preflight():
    for unit in ('k3s', 'k3s-agent'):
        state = run('systemctl', 'show', unit, '-p', 'ActiveState', '--value').stdout.strip()
        if state not in ('inactive', 'failed'):
            raise RuntimeError(unit + ' is not stopped: ' + state)
    require_quiesced(processes(), Path('/proc/mounts').read_text())


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load(folder, validate_network=True):
    folder = Path(folder)
    if folder.parent != ROOT or not re.fullmatch(r'capture-[a-z0-9_]+', folder.name):
        raise ValueError('Unexpected recovery directory')
    if folder.is_symlink() or folder.stat().st_uid != 0 or folder.stat().st_mode & 0o077:
        raise ValueError('Recovery directory must be private and root-owned')
    state = json.loads((folder / 'state.json').read_text())
    if not re.fullmatch(r'k3s-net-rescue-[a-f0-9]{12}', state['unit']):
        raise ValueError('Unexpected recovery unit')
    if not validate_network:
        return folder, state
    if state['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        raise RuntimeError('Capture is from another boot; recapture before cutover')
    link = json.loads(run('ip', '-j', 'link', 'show', 'dev', state['interface']).stdout)[0]
    if link['address'] != state['mac']:
        raise RuntimeError('Management interface identity changed')
    if digest(folder / 'cilium') != state['cilium_sha256']:
        raise RuntimeError('Saved Cilium binary changed')
    for name, expected in state['snapshots'].items():
        if digest(folder / name) != expected:
            raise RuntimeError('Saved network state changed: ' + name)
    return folder, state


def ensure_root():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0 or ROOT.stat().st_mode & 0o077:
        raise RuntimeError('Recovery root must be private and root-owned')


def capture():
    network = management_network(json.loads(run('ip', '-j', '-4', 'route').stdout),
                                 json.loads(run('ip', '-j', 'address').stdout))
    agents = []
    for p in Path('/proc').glob('[0-9]*/exe'):
        try:
            if p.resolve().name == 'cilium-agent':
                agents.append(p.parent)
        except FileNotFoundError:
            pass
    if len(agents) != 1:
        raise RuntimeError('Require exactly one running Cilium agent to capture its CLI')
    source = agents[0] / 'root/usr/bin/cilium-dbg'
    if not source.is_file():
        source = agents[0] / 'root/usr/bin/cilium'
    ensure_root()
    folder = Path(tempfile.mkdtemp(prefix='capture-', dir=ROOT))
    try:
        shutil.copyfile(source, folder / 'cilium')
        (folder / 'cilium').chmod(0o700)
        cleanup_command(folder / 'cilium')
        snapshots = {}
        for name, command in [('iptables.save', ['iptables-save']),
                              ('ip6tables.save', ['ip6tables-save']),
                              ('routes.json', ['ip', '-j', '-4', 'route', 'show', 'table', 'all']),
                              ('rules.json', ['ip', '-j', '-4', 'rule'])]:
            content = run(*command).stdout
            if name == 'iptables.save' and '*filter\n' not in content:
                raise RuntimeError('IPv4 snapshot must include the filter table')
            (folder / name).write_text(content)
            snapshots[name] = digest(folder / name)
        shutil.copyfile(__file__, folder / 'recovery.py')
        state = {**network, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                 'created_at': time.time(), 'cilium_sha256': digest(folder / 'cilium'),
                 'snapshots': snapshots, 'unit': 'k3s-net-rescue-' + os.urandom(6).hex()}
        (folder / 'state.json').write_text(json.dumps(state, indent=2))
        print(folder)
    except BaseException:
        shutil.rmtree(folder)
        raise


def arm(folder, state):
    preflight()
    if time.time() - state['created_at'] > 3600:
        raise RuntimeError('Recapture network state within an hour of cutover')
    if (ROOT / 'active').exists():
        raise RuntimeError('Another active rescue must be canceled first')
    if (folder / 'armed').exists():
        raise RuntimeError('Already armed')
    (folder / 'armed').touch()
    (ROOT / 'active').write_text(folder.name)
    try:
        run('systemd-run', '--quiet', '--unit=' + state['unit'], '--on-active=10m',
            '--timer-property=AccuracySec=1s', '--property=TimeoutStartSec=5min', '--',
            sys.executable, str(folder / 'recovery.py'), 'restore', str(folder))
    except BaseException:
        (folder / 'armed').unlink()
        (ROOT / 'active').unlink()
        raise
    print('Armed for ten minutes. Cancel after verifying a NEW SSH connection, before starting k3s.')


def repair_ipv4(state, firewall):
    errors = []
    interface = state['interface']
    commands = [
        ['ip', 'link', 'set', interface, 'up'],
        ['ip', 'address', 'replace', state['address'], 'dev', interface],
        ['ip', 'route', 'replace', '192.168.1.0/24', 'dev', interface, 'src', state['address'].split('/')[0]],
    ]
    rules = json.loads(run('ip', '-j', '-4', 'rule').stdout)
    # Reserve the first lookups for local delivery and replies on the home LAN.
    # This also works if cleanup removed lookup-main or left a blocking rule.
    for rule in rules:
        if rule.get('priority') in (0, 1):
            commands.append(['ip', '-4', 'rule', 'del', 'pref', str(rule['priority'])])
    commands.extend([
        ['ip', '-4', 'rule', 'add', 'pref', '0', 'lookup', 'local'],
        ['ip', '-4', 'rule', 'add', 'pref', '1', 'to', str(LAN), 'lookup', 'main'],
        ['ip', 'route', 'replace', 'default', 'via', state['gateway'], 'dev', interface],
    ])
    for command in commands:
        result = run(*command, check=False)
        if result.returncode:
            errors.append(result.stderr)
    result = run('iptables-restore', '--wait', '10', data=firewall, check=False)
    if result.returncode:
        errors.append(result.stderr)
    selected = run('ip', '-j', '-4', 'route', 'get', state['gateway'], check=False)
    if selected.returncode:
        errors.append('Management peer route lookup failed: ' + selected.stderr)
    else:
        routes = json.loads(selected.stdout)
        if len(routes) != 1 or routes[0].get('dev') != interface:
            errors.append('Management peer selected the wrong interface')
    return errors


def retire_pidfile(pidfile, folder):
    # A stopped agent can leave a stale pidfile. Do not remove a live PID.
    if pidfile.exists():
        pid = pidfile.read_text().strip()
        if not pid.isdigit() or Path('/proc', pid).exists():
            raise RuntimeError('Cilium pidfile may identify a live process')
        shutil.copyfile(pidfile, folder / 'stale-cilium.pid')
        pidfile.unlink()


def restore(folder, state):
    if not (folder / 'armed').exists():
        raise RuntimeError('Not armed')
    preflight()
    if not (ROOT / 'active').exists() or (ROOT / 'active').read_text() != folder.name:
        raise RuntimeError('This capture does not own the active rescue')
    command = cleanup_command(folder / 'cilium')
    errors = []
    retire_pidfile(Path('/var/run/cilium/cilium.pid'), folder)
    result = run(*command, check=False)
    (folder / 'cleanup.log').write_text(result.stdout + result.stderr)
    try:
        check_cleanup_result(result.returncode, result.stderr)
    except RuntimeError as e:
        errors.append(str(e))
    errors.extend(repair_ipv4(state, (folder / 'iptables.save').read_text()))
    interface = state['interface']
    for direction in ('ingress', 'egress'):
        result = run('tc', 'filter', 'show', 'dev', interface, direction, check=False)
        if result.returncode or re.search(r'\bcil_|cilium', result.stdout):
            errors.append('Cilium management-interface filters remain: ' + direction)
    report = {'completed_at': time.time(), 'errors': errors,
              'scope': 'IPv4 management network only; verify SSH and remaining BPF state manually'}
    (folder / 'result.json').write_text(json.dumps(report, indent=2))
    if errors:
        raise RuntimeError('Recovery incomplete; inspect result.json and cleanup.log')
    print('IPv4 recovery commands completed. Verify a new SSH connection; cluster remains stopped.')


def cancel(folder, state):
    # The caller holds the same lock as restore, so cancellation cannot interrupt
    # half a network repair or race with a timer beginning to run.
    (folder / 'armed').unlink(missing_ok=True)
    if (ROOT / 'active').exists() and (ROOT / 'active').read_text() == folder.name:
        (ROOT / 'active').unlink()
    run('systemctl', 'stop', state['unit'] + '.timer', check=False)
    print('Disarmed. Saved state and logs retained.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['capture', 'check', 'arm', 'restore', 'cancel'])
    parser.add_argument('folder', nargs='?')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root')
    ensure_root()
    # One lock covers every capture on this host, including cancellation.
    with (ROOT / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'capture':
            if args.folder:
                parser.error('capture does not accept a directory')
            capture()
        else:
            if not args.folder:
                parser.error('Recovery directory required')
            folder, state = load(args.folder, validate_network=args.action != 'cancel')
            if args.action == 'check':
                preflight()
                print('Quiescence checks passed; nothing armed or changed')
            else:
                {'arm': arm, 'restore': restore, 'cancel': cancel}[args.action](folder, state)
