#!/usr/bin/env python3
"""Rehearse containerd reconnect and graceful CRI shutdown in a separate runtime.

No production container, socket, data directory or service is stopped. The test
container uses host networking only to avoid invoking production CNI; it runs
only a local signal trap and writes to its private test directory.
"""
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import uuid


def run(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True, timeout=40)
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args[:3]) + ': ' + result.stderr)
    return result


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run as root')
    # Resolve the actual embedded binaries without reading configuration secrets.
    pids = run('pgrep', '-x', 'containerd').stdout.split()
    if len(pids) != 1:
        raise RuntimeError('Expected one production containerd; inspect additional runtimes first')
    binary_dir = Path('/proc', pids[0], 'exe').resolve().parent
    binary = binary_dir / 'containerd'
    if not binary.exists():
        raise RuntimeError('Installed containerd entry point missing')
    arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}[platform.machine()]
    ident = uuid.uuid4().hex[:8]
    base = Path('/var/lib/homelab/runtime-validation') / ('check-' + ident)
    base.mkdir(mode=0o700, parents=True)
    socket = str(base / 'containerd.sock')
    unit = 'k3s-runtime-check-' + ident
    config = base / 'config.toml'
    config.write_text('''version = 2
[plugins."io.containerd.grpc.v1.cri"]
  sandbox_image = "registry.k8s.io/pause:3.10.2@sha256:f548e0e8e3dc1896ca956272154dde3314e8cc4fde0a57577ee9fa1c63f5baf4"
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
  runtime_type = "io.containerd.runc.v2"
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
  BinaryName = '''+json.dumps(str(binary_dir/'runc'))+'\n')
    pod = {'metadata': {'name': unit, 'namespace': 'isolated-runtime-test', 'uid': ident, 'attempt': 0},
           'log_directory': str(base/'logs'), 'linux': {'security_context': {'namespace_options': {'network': 2}}}}
    container = {'metadata': {'name': 'signal-check', 'attempt': 0},
                 'image': {'image': 'docker.io/library/busybox:1.38.0@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e'},
                 'command': ['/bin/sh', '-c', 'trap "echo graceful > /proof/stopped; exit 0" TERM; echo ready > /proof/ready; while :; do sleep 1 & wait $!; done'],
                 'log_path': 'signal-check.log', 'mounts': [{'container_path': '/proof', 'host_path': str(base/'proof'), 'readonly': False}]}
    (base/'proof').mkdir(); (base/'logs').mkdir()
    (base/'pod.json').write_text(json.dumps(pod)); (base/'container.json').write_text(json.dumps(container))
    def cri(*args, check=True):
        return run('/usr/local/bin/k3s', 'crictl', '--runtime-endpoint', 'unix://'+socket,
                   '--image-endpoint', 'unix://'+socket, *args, check=check)
    created = False
    def start():
        nonlocal created
        if created:
            run('systemctl', 'start', unit+'.service')
        else:
            run('systemd-run', '--quiet', '--unit='+unit, '--property=KillMode=process',
            '--setenv=PATH='+str(binary_dir)+':/usr/sbin:/usr/bin:/sbin:/bin',
                '--', str(binary), '-c', str(config), '-a', socket,
                '--state', str(base/'state'), '--root', str(base/'root'))
            created = True
        for _ in range(30):
            if Path(socket).exists() and cri('info', check=False).returncode == 0:
                return
            time.sleep(0.5)
        raise RuntimeError('Isolated runtime did not become ready')
    pod_id = container_id = None
    try:
        start()
        for image in ('docker.io/library/busybox:1.38.0@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e', 'registry.k8s.io/pause:3.10.2@sha256:f548e0e8e3dc1896ca956272154dde3314e8cc4fde0a57577ee9fa1c63f5baf4'):
            run('/usr/local/bin/k3s', 'ctr', '--address', socket, '--namespace', 'k8s.io',
                'images', 'pull', '--platform', 'linux/'+arch, image)
        pod_id = cri('runp', str(base/'pod.json')).stdout.strip()
        container_id = cri('create', '--no-pull', pod_id, str(base/'container.json'), str(base/'pod.json')).stdout.strip()
        cri('start', container_id)
        for _ in range(20):
            if (base/'proof/ready').exists():
                break
            time.sleep(0.2)
        assert (base/'proof/ready').exists(), 'Test process did not start'
        before = json.loads(cri('inspect', container_id).stdout)['info']['pid']
        # k3s configures Pdeathsig=SIGKILL for its containerd child.
        run('systemctl', 'kill', '--kill-who=main', '--signal=SIGKILL', unit+'.service')
        run('systemctl', 'stop', unit+'.service')
        assert Path('/proc', str(before)).exists(), 'Container did not survive runtime stop'
        # Reconnect to the same isolated state, with no kubelet supervising it.
        start()
        after = json.loads(cri('inspect', container_id).stdout)['info']['pid']
        assert before == after, 'Runtime did not reconnect to the existing container'
        run('/usr/local/bin/k3s', 'ctr', '--address', socket, '--namespace', 'k8s.io',
            'tasks', 'kill', '--signal', 'SIGTERM', container_id)
        for _ in range(30):
            status = json.loads(cri('inspect', container_id).stdout)['status']
            if status['state'] == 'CONTAINER_EXITED':
                break
            time.sleep(0.2)
        assert status['state'] == 'CONTAINER_EXITED', 'Graceful stop timed out; no forced kill'

        assert status['exitCode'] == 0, status
        assert (base/'proof/stopped').read_text().strip() == 'graceful'
        cri('stopp', pod_id)
        tasks = run('/usr/local/bin/k3s', 'ctr', '--address', socket, '--namespace', 'k8s.io', 'tasks', 'list', '-q').stdout.strip()
        assert not tasks, 'Stopped sandboxes still own runtime tasks'
        assert json.loads(cri('inspect', container_id).stdout)['status']['exitCode'] == 0
        cri('rm', container_id); container_id = None
        cri('rmp', pod_id); pod_id = None
        tasks = run('/usr/local/bin/k3s', 'ctr', '--address', socket, '--namespace', 'k8s.io', 'tasks', 'list', '-q').stdout.strip()
        assert not tasks, 'Isolated runtime tasks remain'
        report = {'result': 'passed', 'arch': arch, 'container_survived_runtime_stop': True, 'runtime_stop_signal': 'SIGKILL',
                  'same_pid_after_reconnect': True, 'graceful_exit_code': status['exitCode'],
                  'no_tasks_before_metadata_removal': True, 'sandbox_removed': True, 'production_runtime_pid': pids[0]}
        (base/'result.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({'directory': str(base), **report}), flush=True)
    finally:
        # Stop/delete only IDs created by this private runtime; never use --all.
        if container_id or pod_id:
            start()
        if container_id:
            cri('stop', '--timeout', '15', container_id, check=False)
            cri('rm', container_id, check=False)
        if pod_id:
            cri('stopp', pod_id, check=False)
            cri('rmp', pod_id, check=False)
        run('systemctl', 'stop', unit+'.service', check=False)
        run('systemctl', 'reset-failed', unit+'.service', check=False)


if __name__ == '__main__':
    main()
