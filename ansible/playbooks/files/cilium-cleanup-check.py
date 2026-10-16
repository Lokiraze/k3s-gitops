#!/usr/bin/env python3
"""Read-only Cilium BPF inventory. --require-clean fails while Cilium objects remain.

Systemd's own BPF firewall/device programs are expected and must be preserved.
This is a BPF postcondition, not proof that SSH, routes, or storage are healthy.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess


def cilium_objects(records):
    return [r for r in records if r.get('name', '').startswith(('cil_', 'cilium_'))]


def query(*args):
    p = subprocess.run(['bpftool', '-j', *args], text=True, capture_output=True, timeout=30)
    if p.returncode:
        raise RuntimeError('BPF inspection failed: ' + p.stderr.strip())
    return json.loads(p.stdout)


def inspect():
    programs = query('prog', 'show')
    maps = query('map', 'show')
    links = query('link', 'show')
    network = query('net', 'show')
    cgroups = query('cgroup', 'tree', '/sys/fs/cgroup')
    cilium_programs = cilium_objects(programs)
    ids = {p['id'] for p in cilium_programs}
    result = {
        'programs': cilium_programs,
        'maps': cilium_objects(maps),
        'links': [link for link in links if link.get('prog_id') in ids],
        'network_attachments': [p for group in network for kind in ('tc', 'xdp')
                                for p in group.get(kind, []) if p.get('id') in ids or cilium_objects([p])],
        'cgroup_attachments': [dict(p, cgroup=group['cgroup']) for group in cgroups
                               for p in group.get('programs', []) if p.get('id') in ids or cilium_objects([p])],
        'pinned_maps': sorted(str(p) for p in Path('/sys/fs/bpf/tc/globals').glob('cilium*')),
    }
    return {'clean': not any(result.values()), 'cilium': result,
            'other_programs_preserved': len(programs) - len(cilium_programs)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-clean', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root')
    report = inspect()
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if args.require_clean and not report['clean'] else 0)
