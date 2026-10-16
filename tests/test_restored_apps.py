from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'home': ['home-assistant', 'mosquitto', 'zwave-js-ui', 'frigate'],
    'media': ['calibre-web','jellyseer','lidarr','podfetch','podgrab','prowlarr','radarr','readarr','recyclarr','sonarr','whisparr'],
    'security': ['vaultwarden'],
    'monitoring': ['grafana','kube-prometheus-stack','kubernetes-dashboard'],
    'default': ['hajimari'],
}

def apps():
    for ns, names in EXPECTED.items():
        for name in names:
            yield ns, name, ROOT / 'kubernetes/apps' / ns / name

def test_every_restored_app_is_reachable_but_suspended():
    for ns, name, path in apps():
        parent = yaml.safe_load((path.parent / 'kustomization.yaml').read_text())
        assert f'./{name}/ks.yaml' in parent['resources']
        ks = yaml.safe_load((path / 'ks.yaml').read_text())
        assert ks['spec']['suspend'] is True
        assert ks['spec']['sourceRef']['name'] == 'flux-system'
        assert ks['spec']['sourceRef']['namespace'] == 'flux-system'
        assert (ROOT / ks['spec']['path']).is_dir()
        hr = yaml.safe_load((path / 'app/helmrelease.yaml').read_text())
        assert hr['apiVersion'] == 'helm.toolkit.fluxcd.io/v2'
        assert hr['spec']['suspend'] is True

def test_chart_sources_and_storage_are_explicit():
    sources = {d['metadata']['name'] for d in yaml.safe_load_all((ROOT / 'kubernetes/apps/flux-system/app-recovery/sources.yaml').read_text())}
    for ns, name, path in apps():
        hr = yaml.safe_load((path / 'app/helmrelease.yaml').read_text())
        assert hr['spec']['chart']['spec']['sourceRef']['name'] in sources
        for file in (path / 'app').glob('*.yaml'):
            if '.sops.' in file.name: continue
            assert 'ceph-block' not in file.read_text()
            assert 'ingress-nginx' not in file.read_text()
        for pvc in (path / 'app').glob('*pvc.yaml'):
            assert yaml.safe_load(pvc.read_text())['spec']['storageClassName'] == 'local-app-data'

def test_vaultwarden_persists_actual_data_and_frigate_uses_secret_env():
    hr = yaml.safe_load((ROOT / 'kubernetes/apps/security/vaultwarden/app/helmrelease.yaml').read_text())
    assert hr['spec']['values']['persistence']['config']['mountPath'] == '/data'
    hr = yaml.safe_load((ROOT / 'kubernetes/apps/home/frigate/app/helmrelease.yaml').read_text())
    values = hr['spec']['values']
    config = values['configmap']['config']['data']['config.yml']
    assert '${PORCH_CAMERA}' not in config
    assert '{FRIGATE_PORCH_CAMERA}' in config
    assert values['env']['FRIGATE_PORCH_CAMERA']['valueFrom']['secretKeyRef']['key'] == 'PORCH_CAMERA'
    assert values['persistence']['usb']['hostPath'] == '/dev/bus/usb'


def test_namespace_local_substitution_and_external_routes():
    for rel in ['default/hajimari', 'network/external']:
        ks = yaml.safe_load((ROOT / 'kubernetes/apps' / rel / 'ks.yaml').read_text())
        assert ks['spec']['postBuild']['substituteFrom'] == [{'kind': 'Secret', 'name': 'cluster-secrets'}]
        assert ks['spec']['postBuild']['substitute']['NFS_SERVER'] == '192.168.1.50'
    for app in ['jellyfin', 'robo', 'stash', 'torrent']:
        path = ROOT / 'kubernetes/apps/network/external/app' / app
        route = yaml.safe_load((path / 'httproute.yaml').read_text())
        assert route['spec']['parentRefs'][0]['name'] == ('envoy-external' if app == 'jellyfin' else 'envoy-internal')
        endpoints = yaml.safe_load((path / 'endpointslice.yaml').read_text())
        service = yaml.safe_load((path / 'service.yaml').read_text())
        assert endpoints['metadata']['labels']['kubernetes.io/service-name'] == service['metadata']['name']
        assert route['spec']['rules'][0]['backendRefs'][0]['name'] == service['metadata']['name']
