import importlib.util
from pathlib import Path


def test_cleanup_gate_ignores_systemd_bpf_but_finds_cilium():
    path = Path(__file__).resolve().parents[1] / 'ansible/playbooks/files/cilium-cleanup-check.py'
    spec = importlib.util.spec_from_file_location('cleanup_check', path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    records = [{'id': 1, 'name': 'sd_fw_ingress'}, {'id': 2, 'name': 'sd_devices'},
               {'id': 3, 'name': 'cil_sock4_conne'}, {'id': 4, 'name': 'cilium_lxc'}]
    assert [r['id'] for r in m.cilium_objects(records)] == [3, 4]
    assert m.cilium_objects(records[:2]) == []
