from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / 'kubernetes/apps'


def test_local_storage_never_dynamically_provisions_empty_data():
    path = APPS / 'kube-system/local-app-data/app/storageclass.yaml'
    sc = yaml.safe_load(path.read_text())
    assert sc['provisioner'] == 'kubernetes.io/no-provisioner'
    assert sc['reclaimPolicy'] == 'Retain'
    assert sc['volumeBindingMode'] == 'WaitForFirstConsumer'
    ks = yaml.safe_load((path.parent.parent / 'ks.yaml').read_text())
    assert ks['spec']['prune'] is False


def test_home_restores_are_bound_to_the_right_claim_and_node():
    for app, claim, node, required_file in [
        ('home-assistant', 'home-assistant-config', 'k8s-bahamut', '.storage/core.config_entries'),
        ('zwave-js-ui', 'zwavejs-config', 'k8s-ifrit', 'settings.json'),
    ]:
        base = APPS / 'home' / app / 'app'
        pv = yaml.safe_load((base / 'config-pv.yaml').read_text())
        pvc = yaml.safe_load((base / 'config-pvc.yaml').read_text())
        spec = pv['spec']
        assert spec['persistentVolumeReclaimPolicy'] == 'Retain'
        assert spec['claimRef'] == {'namespace': 'home', 'name': claim}
        assert pvc['spec']['volumeName'] == pv['metadata']['name']
        assert spec['storageClassName'] == pvc['spec']['storageClassName'] == 'local-app-data'
        assert spec['local']['path'] == f'/var/lib/homelab/app-data/{claim}'
        expr = spec['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions'][0]
        assert expr == {'key': 'kubernetes.io/hostname', 'operator': 'In', 'values': [node]}
        hr = yaml.safe_load((base / 'helmrelease.yaml').read_text())
        guard = hr['spec']['values']['controllers']['main']['initContainers']['verify-restored-data']
        assert '.restore-verified' in guard['command'][-1]
        assert required_file in guard['command'][-1]
        assert hr['spec']['values']['persistence']['config']['advancedMounts']['main']['verify-restored-data'] == [{'path': '/restore', 'readOnly': True}]
        assert './config-pv.yaml' in yaml.safe_load((base / 'kustomization.yaml').read_text())['resources']


def test_restore_guard_rejects_empty_and_unverified_data(tmp_path):
    import subprocess
    for app, claim, required in [
        ('home-assistant', 'home-assistant-config', '.storage/core.config_entries'),
        ('zwave-js-ui', 'zwavejs-config', 'settings.json'),
    ]:
        hr = yaml.safe_load((APPS / 'home' / app / 'app/helmrelease.yaml').read_text())
        command = hr['spec']['values']['controllers']['main']['initContainers']['verify-restored-data']['command'][-1]
        target = tmp_path / app
        target.mkdir()
        command = command.replace('/restore/', str(target) + '/')
        def passes():
            return subprocess.run(['sh', '-ec', command], capture_output=True).returncode == 0
        assert not passes()
        marker = target / '.restore-verified'
        marker.write_text(claim)
        assert not passes()
        data = target / required
        data.parent.mkdir(parents=True, exist_ok=True)
        data.write_text('{}')
        assert passes()
        marker.write_text('wrong-claim')
        assert not passes()
        marker.unlink()
        assert not passes()


def test_media_claims_have_retained_node_bound_volumes_and_restore_guards():
    for pvc_path in (APPS / 'media').glob('*/app/config-pvc.yaml'):
        base = pvc_path.parent
        pvc = yaml.safe_load(pvc_path.read_text())
        pv = yaml.safe_load((base / 'config-pv.yaml').read_text())
        spec = pv['spec']
        assert spec['persistentVolumeReclaimPolicy'] == 'Retain'
        assert spec['claimRef'] == {'namespace': 'media', 'name': pvc['metadata']['name']}
        assert pvc['spec']['volumeName'] == pv['metadata']['name']
        assert spec['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions'][0]['values'] == ['k8s-phoenix']
        hr = yaml.safe_load((base / 'helmrelease.yaml').read_text())
        guard = hr['spec']['values']['controllers']['main']['initContainers']['verify-restored-data']
        assert pvc['metadata']['name'] in guard['command'][-1]
        assert hr['spec']['values']['persistence']['config']['advancedMounts']['main']['verify-restored-data'][0]['readOnly'] is True


def test_monitoring_storage_is_bound_and_cannot_start_without_a_restore():
    for app, claim in [('grafana','grafana'),('kube-prometheus-stack','prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0')]:
        base = APPS / 'monitoring' / app / 'app'
        pv = yaml.safe_load((base / 'config-pv.yaml').read_text())
        assert pv['spec']['claimRef'] == {'namespace': 'monitoring', 'name': claim}
        assert pv['spec']['persistentVolumeReclaimPolicy'] == 'Retain'
        assert pv['spec']['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions'][0]['values'] == ['k8s-odin']
        values = yaml.safe_load((base / 'helmrelease.yaml').read_text())['spec']['values']
        if app == 'grafana':
            assert values['persistence']['existingClaim'] == claim
            pvc = yaml.safe_load((base / 'config-pvc.yaml').read_text())['spec']
            guards = values['extraInitContainers']
        else:
            ps = values['prometheus']['prometheusSpec']
            assert ps['replicas'] == 1
            pvc = ps['storageSpec']['volumeClaimTemplate']['spec']
            guards = ps['initContainers']
        assert pvc['volumeName'] == pv['metadata']['name']
        assert any(g['name']=='verify-restored-data' and '.restore-verified' in g['command'][-1] for g in guards)
