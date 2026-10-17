from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'home': ['home-assistant', 'mosquitto', 'zwave-js-ui', 'frigate'],
    'media': ['calibre-web','jellyseer','lidarr','podfetch','podgrab','prowlarr','radarr','readarr','recyclarr','sonarr','whisparr'],
    'security': ['vaultwarden'],
    'monitoring': ['grafana','kube-prometheus-stack'],
    'default': ['hajimari'],
}

def apps():
    for ns, names in EXPECTED.items():
        for name in names:
            yield ns, name, ROOT / 'kubernetes/apps' / ns / name

DISABLED = {('home', 'frigate'), ('media', 'readarr'), ('security', 'vaultwarden')}


def test_every_restored_app_has_explicit_activation_state():
    for ns, name, path in apps():
        parent = yaml.safe_load((path.parent / 'kustomization.yaml').read_text())
        assert f'./{name}/ks.yaml' in parent['resources']
        ks = yaml.safe_load((path / 'ks.yaml').read_text())
        assert ks['spec']['suspend'] is ((ns, name) in DISABLED)
        assert ks['spec']['sourceRef']['name'] == 'flux-system'
        assert ks['spec']['sourceRef']['namespace'] == 'flux-system'
        assert (ROOT / ks['spec']['path']).is_dir()
        hr = yaml.safe_load((path / 'app/helmrelease.yaml').read_text())
        assert hr['apiVersion'] == 'helm.toolkit.fluxcd.io/v2'
        assert hr['spec']['suspend'] is ((ns, name) in DISABLED)

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


def test_http_routes_do_not_contain_helm_templates():
    for route in (ROOT / 'kubernetes/apps').glob('**/httproute.yaml'):
        doc = yaml.safe_load(route.read_text())
        for hostname in doc.get('spec', {}).get('hostnames', []):
            assert '{{' not in hostname, str(route)


def test_podfetch_uses_restored_sqlite_and_whisparr_matches_restored_owner():
    podfetch = yaml.safe_load((ROOT / 'kubernetes/apps/media/podfetch/app/helmrelease.yaml').read_text())['spec']['values']
    assert podfetch['env']['DATABASE_URL'] == 'sqlite:///app/db/podcast.db'
    assert '@sha256:' in podfetch['image']['tag']
    whisparr = yaml.safe_load((ROOT / 'kubernetes/apps/media/whisparr/app/helmrelease.yaml').read_text())['spec']['values']
    assert whisparr['env']['PUID'] == whisparr['env']['PGID'] == 568


def test_prometheus_route_uses_verified_internal_http_service():
    base = ROOT / 'kubernetes/apps/monitoring/kube-prometheus-stack/app'
    assert './httproute.yaml' in yaml.safe_load((base / 'kustomization.yaml').read_text())['resources']
    route = yaml.safe_load((base / 'httproute.yaml').read_text())['spec']
    assert route['hostnames'] == ['prometheus.${SECRET_DOMAIN}']
    assert route['parentRefs'] == [{'name': 'envoy-internal', 'namespace': 'network', 'sectionName': 'https'}]
    assert route['rules'][0]['backendRefs'] == [{'name': 'kube-prometheus-stack-prometheus', 'port': 9090}]


def test_recyclarr_preserves_state_between_nonoverlapping_jobs():
    base = ROOT / 'kubernetes/apps/media/recyclarr/app'
    values = yaml.safe_load((base / 'helmrelease.yaml').read_text())['spec']['values']
    assert values['controller']['cronjob']['concurrencyPolicy'] == 'Forbid'
    assert values['persistence']['config']['existingClaim'] == 'recyclarr-state'
    assert values['persistence']['config']['mountPath'] == '/config'
    assert values['persistence']['config']['type'] == 'pvc'
    assert values['persistence']['config']['readOnly'] is False
    assert values['persistence']['config']['subPath'] == ''
    assert values['persistence']['config-file']['mountPath'] == '/config/recyclarr.yml'
    assert values['persistence']['config-file']['readOnly'] is True
    pv = yaml.safe_load((base / 'state-pv.yaml').read_text())['spec']
    pvc = yaml.safe_load((base / 'state-pvc.yaml').read_text())['spec']
    assert pv['persistentVolumeReclaimPolicy'] == 'Retain'
    assert pv['claimRef'] == {'namespace': 'media', 'name': 'recyclarr-state'}
    assert pvc['volumeName'] == 'local-recyclarr-state'
