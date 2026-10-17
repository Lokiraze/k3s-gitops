from pathlib import Path
import ipaddress
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
def read(path):
    return yaml.safe_load((ROOT / path).read_text())

def test_inventory_bootstrap_and_deferred_nodes():
    inventory = read('ansible/inventory/hosts.yaml')
    active = inventory['kubernetes']['children']
    assert set(active['master']['hosts']) == {'k8s-summoner', 'k8s-phoenix', 'k8s-bahamut'}
    assert set(active['worker']['hosts']) == {'k8s-odin', 'k8s-ifrit'}
    assert set(inventory['deferred']['hosts']) == {'k8s-ramuh', 'k8s-shiva'}

def test_cilium_and_k3s_network_agree():
    network = read('ansible/inventory/group_vars/kubernetes/supplemental.yaml')
    server = read('ansible/inventory/group_vars/master/main.yaml')['k3s_server']
    cilium = read('kubernetes/apps/kube-system/cilium/app/helmrelease.yaml')['spec']['values']
    assert cilium['k8sServiceHost'] == network['kube_vip_addr'] == '192.168.1.18'
    assert cilium['k8sServicePort'] == 6443
    assert cilium['ipv4NativeRoutingCIDR'] == network['cluster_cidr']
    assert server['flannel-backend'] == 'none'
    assert server['disable-kube-proxy'] and server['disable-network-policy']
    assert 'flannel' not in server['disable']
    assert cilium['cni']['binPath'] == '/opt/cni/bin'
    assert cilium['cni']['confPath'] == '/etc/cni/net.d'
    assert 'devices' not in cilium  # infer each Debian NIC, not a nonexistent bond
    assert ipaddress.ip_address(network['kube_vip_addr']) in ipaddress.ip_network(network['node_cidr'])

def test_keepalived_renders_distinct_peers_and_local_healthcheck():
    template = (ROOT / 'ansible/playbooks/templates/keepalived.conf.j2').read_text()
    hosts = ['k8s-summoner', 'k8s-phoenix', 'k8s-bahamut']
    hv = {h: {'ansible_host': ip} for h, ip in zip(hosts, ['192.168.1.15','192.168.1.16','192.168.1.17'])}
    for host in hosts:
        result = Environment(undefined=StrictUndefined).from_string(template).render(
            inventory_hostname=host, ansible_host=hv[host]['ansible_host'], groups={'master': hosts},
            hostvars=hv, ansible_facts={'default_ipv4': {'interface': 'eno1'}}, kube_vip_addr='192.168.1.18')
        assert '192.168.1.18/24 dev eno1' in result
        peers = result.split('unicast_peer {')[1].split('}')[0]
        assert hv[host]['ansible_host'] not in peers
        assert sum(hv[h]['ansible_host'] in peers for h in hosts) == 2
        assert 'track_script' in result

def test_no_talos_runtime_or_duplicate_cni_bootstrap():
    assert not (ROOT / 'talos').exists()
    assert not (ROOT / 'template').exists()
    assert 'spegel' not in (ROOT / 'bootstrap/helmfile/apps.yaml').read_text()
    assert 'talos:' not in (ROOT / 'bootstrap/mod.just').read_text()
    shared = read('ansible/inventory/group_vars/kubernetes/main.yaml')
    assert shared['k3s_server_manifests_templates'] == []
    assert shared['k3s_skip_post_checks'] is True  # Ready requires the later Helm CNI bootstrap

def test_install_and_updates_have_maintenance_gates():
    install = read('ansible/playbooks/cluster-installation.yaml')[0]
    checks = str(install['pre_tasks'])
    assert 'rebuild_managed' in checks and 'existing_k3s' in checks
    update = read('ansible/playbooks/cluster-rollout-update.yaml')[0]
    assert update['serial'] == 1 and update['any_errors_fatal']
    assert 'maintenance_confirmed' in str(update['pre_tasks'])
    assert 'ansible_limit' in str(update['pre_tasks'])
    assert 'sources.list' not in str(update['tasks'])


def test_os_update_rejects_floating_suites_in_deb822_lists():
    import base64
    import re
    play = read('ansible/playbooks/cluster-rollout-update.yaml')[0]
    gate = next(t for t in play['pre_tasks'] if t['name'].startswith('Reject unsupported'))
    expression = gate['ansible.builtin.assert']['that'][0]
    env = Environment(undefined=StrictUndefined)
    env.filters['b64decode'] = lambda value: base64.b64decode(value).decode()
    env.filters['regex_findall'] = lambda value, pattern: re.findall(pattern, value)
    env.filters['split'] = lambda value: value.split()
    env.filters['difference'] = lambda value, allowed: list(set(value) - set(allowed))
    check = env.compile_expression(expression)
    for text, allowed in [
        ('deb https://deb.debian.org/debian bookworm main', True),
        ('Suites: bookworm bookworm-updates', True),
        ('Suites: bookworm stable', False),
        ('Suites: stable-security', False),
        ('Suites: trixie trixie-updates', False),
        ('Suites:\n bookworm\n trixie', False),
        ('Suites:\n bookworm\n bookworm-updates', True),
        ('deb [signed-by=/key.gpg] https://deb.debian.org/debian trixie main', False),
        ('deb [signed-by=/key.gpg] https://deb.debian.org/debian bookworm main', True),
        ('# deb https://deb.debian.org/debian trixie main', True),
        ('deb https://deb.debian.org/debian oldstable main', False),
    ]:
        assert check(item={'content': base64.b64encode(text.encode()).decode()}) is allowed


def test_radio_worker_storage_identity_and_label_are_explicit():
    inv = read('ansible/inventory/hosts.yaml')['kubernetes']['children']
    radio = inv['worker']['hosts']['k8s-ifrit']
    assert radio['internal_sd_cid'] == '035344534d33324780fa263f73014300'
    assert 'internal_disk_serial' not in radio
    assert radio['k3s_node_labels'] == ['usb=zwave']
    worker = read('ansible/inventory/group_vars/worker/main.yaml')['k3s_agent']
    assert 'k3s_node_labels' in worker['node-label']
    prep = read('ansible/playbooks/cluster-prepare.yaml')[0]
    assert 'internal_sd_cid' in str(prep['pre_tasks'])
    assert any('device/cid' in str(t) for t in prep['tasks'])
