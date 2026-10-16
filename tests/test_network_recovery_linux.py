"""Root-only Linux integration test; all network changes stay in a disposable namespace."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0, 'requires Linux root and network namespaces')
class NetworkRecoveryIntegration(unittest.TestCase):
    def test_broken_network_and_policy_routing_are_repaired_idempotently(self):
        path = Path(os.environ.get('NETWORK_RECOVERY_SCRIPT', Path(__file__).resolve().parents[1] /
                                   'ansible/playbooks/files/host-network-recovery.py'))
        spec = importlib.util.spec_from_file_location('recovery', path)
        recovery = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(recovery)
        namespace = 'k3s-repair-test-' + uuid.uuid4().hex[:10]
        def host(*args):
            return subprocess.run(args, text=True, capture_output=True, check=True, timeout=15)
        def isolated(*args, check=True, data=None):
            return subprocess.run(['ip', 'netns', 'exec', namespace, *args], input=data,
                                  text=True, capture_output=True, check=check, timeout=15)
        host('ip', 'netns', 'add', namespace)
        try:
            isolated('ip', 'link', 'set', 'lo', 'up')
            isolated('ip', 'link', 'add', 'dummy0', 'type', 'dummy')
            isolated('ip', 'link', 'set', 'dummy0', 'up')
            isolated('ip', 'address', 'add', '192.168.1.17/24', 'dev', 'dummy0')
            isolated('iptables', '-N', 'TEST_BASELINE')
            firewall = isolated('iptables-save').stdout
            isolated('ip', 'rule', 'del', 'pref', '32766')
            isolated('ip', 'rule', 'add', 'pref', '5', 'to', '192.168.1.0/24', 'prohibit')
            isolated('ip', 'address', 'flush', 'dev', 'dummy0')
            isolated('ip', 'link', 'set', 'dummy0', 'down')
            isolated('iptables', '-A', 'OUTPUT', '-j', 'DROP')
            self.assertNotEqual(isolated('ping', '-c', '1', '-W', '1', '192.168.1.17', check=False).returncode, 0)
            recovery.run = isolated
            state = {'interface': 'dummy0', 'address': '192.168.1.17/24', 'gateway': '192.168.1.1'}
            for _ in range(2):
                self.assertEqual(recovery.repair_ipv4(state, firewall), [])
                isolated('ping', '-c', '1', '-W', '1', '192.168.1.17')
                peer = json.loads(isolated('ip', '-j', 'route', 'get', '192.168.1.1').stdout)[0]
                self.assertEqual(peer['dev'], 'dummy0')
                routes = json.loads(isolated('ip', '-j', '-4', 'route').stdout)
                self.assertTrue(any(r.get('dst') == 'default' and r.get('gateway') == '192.168.1.1' for r in routes))
                self.assertNotIn('-j DROP', isolated('iptables-save').stdout)
        finally:
            host('ip', 'netns', 'delete', namespace)


if __name__ == '__main__':
    unittest.main()
