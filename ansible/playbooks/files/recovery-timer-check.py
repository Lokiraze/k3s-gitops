#!/usr/bin/env python3
"""Test detached systemd recovery without changing host networking.

Run arm over SSH, disconnect, then run verify PATH in a new SSH session
at least 25 seconds later. This is a prerequisite probe, not host rollback.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


def run(*args, check=True, data=None):
    return subprocess.run(args, input=data, text=True, capture_output=True, check=check)


def net(state, *args, **kwargs):
    return run('ip', 'netns', 'exec', state['namespace'], *args, **kwargs)


def read_state(folder):
    folder = Path(folder)
    if not re.fullmatch(r'/run/k3s-recovery-check-[a-z0-9_]+', str(folder)):
        raise ValueError('Not a recovery-check directory')
    info = folder.stat()
    if info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('State directory must be private and owned by root')
    state = json.loads((folder / 'state.json').read_text())
    if not re.fullmatch(r'k3s-check-[a-f0-9]{12}', state['namespace']):
        raise ValueError('Not a recovery-check namespace')
    return folder, state


def ping(state):
    return net(state, 'ping', '-c', '1', '-W', '1', '192.0.2.1', check=False).returncode == 0


def cleanup(folder, state):
    for suffix in ('recover', 'cancel'):
        unit = state['namespace'] + '-' + suffix
        run('systemctl', 'stop', unit + '.timer', unit + '.service', check=False)
        run('systemctl', 'reset-failed', unit + '.service', check=False)
    net(state, 'true', check=False)
    run('ip', 'netns', 'delete', state['namespace'], check=False)
    shutil.rmtree(folder)


def arm():
    for tool in ('ip', 'iptables', 'iptables-save', 'iptables-restore', 'ping', 'systemd-run'):
        if not shutil.which(tool):
            raise RuntimeError('Missing prerequisite: ' + tool)
    folder = Path(tempfile.mkdtemp(prefix='k3s-recovery-check-', dir='/run'))
    state = {'namespace': 'k3s-check-' + os.urandom(6).hex(), 'armed_at': time.time()}
    (folder / 'state.json').write_text(json.dumps(state))
    script = folder / 'check.py'
    shutil.copyfile(__file__, script)
    try:
        run('ip', 'netns', 'add', state['namespace'])
        net(state, 'ip', 'link', 'set', 'lo', 'up')
        net(state, 'ip', 'link', 'add', 'dummy0', 'type', 'dummy')
        net(state, 'ip', 'link', 'set', 'dummy0', 'up')
        net(state, 'ip', 'address', 'add', '192.0.2.1/32', 'dev', 'dummy0')
        if not ping(state):
            raise RuntimeError('Baseline namespace ping failed')
        # An empty nftables ruleset saves nothing; restoring it would not clear
        # a subsequently created filter table. Materialize that table first.
        net(state, 'iptables', '-N', 'RECOVERY_PROBE')
        snapshot = net(state, 'iptables-save').stdout
        if '*filter\n' not in snapshot:
            raise RuntimeError('Firewall snapshot omitted the filter table')
        (folder / 'iptables.save').write_text(snapshot)
        net(state, 'ip', 'route', 'replace', 'blackhole', '192.0.2.1/32', 'table', 'local')
        if ping(state):
            raise RuntimeError('Broken route did not fail the probe')
        net(state, 'ip', 'route', 'replace', 'local', '192.0.2.1/32', 'dev', 'dummy0', 'table', 'local')
        if not ping(state):
            raise RuntimeError('Route repair did not restore ping')
        net(state, 'iptables', '-A', 'OUTPUT', '-j', 'DROP')
        if ping(state):
            raise RuntimeError('Broken firewall did not fail the probe')
        net(state, 'ip', 'route', 'replace', 'blackhole', '192.0.2.1/32', 'table', 'local')
        for suffix, command in (
            ('recover', [sys.executable, str(script), 'recover', str(folder)]),
            ('cancel', ['/usr/bin/touch', str(folder / 'cancel-fired')]),
        ):
            run('systemd-run', '--quiet', '--unit=' + state['namespace'] + '-' + suffix,
                '--on-active=20s', '--timer-property=AccuracySec=1s', '--', *command)
        run('systemctl', 'stop', state['namespace'] + '-cancel.timer')
        state['armed_at'] = time.time()
        (folder / 'state.json').write_text(json.dumps(state))
        print(str(folder), flush=True)
    except BaseException:
        cleanup(folder, state)
        raise


def recover(folder, state):
    net(state, 'ip', 'route', 'replace', 'local', '192.0.2.1/32', 'dev', 'dummy0', 'table', 'local')
    net(state, 'iptables-restore', data=(folder / 'iptables.save').read_text())
    if not ping(state):
        raise RuntimeError('Timer could not restore namespace connectivity')
    (folder / 'recovered').write_text('route and firewall repaired\n')


def verify(folder, state):
    if time.time() - state['armed_at'] < 25:
        raise RuntimeError('Wait at least 25 seconds before verification')
    try:
        unit = state['namespace'] + '-recover.service'
        result = run('systemctl', 'show', unit, '-p', 'Result', '--value').stdout.strip()
        if result != 'success' or not (folder / 'recovered').exists() or not ping(state):
            raise RuntimeError('Detached recovery did not pass')
        if (folder / 'cancel-fired').exists():
            raise RuntimeError('Canceled timer unexpectedly fired')
        print('PASS: detached timer repaired isolated routing/firewall; cancellation passed')
    finally:
        cleanup(folder, state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['arm', 'recover', 'verify', 'cleanup'])
    parser.add_argument('folder', nargs='?')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root')
    if args.action == 'arm':
        if args.folder:
            parser.error('arm does not accept a state directory')
        arm()
    else:
        if not args.folder:
            parser.error('State directory required')
        folder, state = read_state(args.folder)
        {'recover': recover, 'verify': verify, 'cleanup': cleanup}[args.action](folder, state)
