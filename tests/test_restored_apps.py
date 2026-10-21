from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'home': ['home-assistant', 'mosquitto', 'zwave-js-ui', 'frigate'],
    'media': ['calibre-web','jellyseer','lidarr','podfetch','prowlarr','radarr','recyclarr','sonarr','whisparr'],
    'security': ['vaultwarden'],
    'monitoring': ['grafana','kube-prometheus-stack'],
    'default': ['homepage', 'theme-park'],
}

def apps():
    for ns, names in EXPECTED.items():
        for name in names:
            yield ns, name, ROOT / 'kubernetes/apps' / ns / name

DISABLED = set()


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
    assert hr['spec']['values']['persistence']['config']['advancedMounts']['main']['vaultwarden'] == [{'path': '/data'}]
    hr = yaml.safe_load((ROOT / 'kubernetes/apps/home/frigate/app/helmrelease.yaml').read_text())
    values = hr['spec']['values']
    config = values['configMaps']['config']['data']['config.yml']
    assert '${PORCH_CAMERA}' not in config
    assert '{FRIGATE_PORCH_CAMERA}' in config
    assert values['controllers']['main']['containers']['app']['env']['FRIGATE_PORCH_CAMERA']['valueFrom']['secretKeyRef']['key'] == 'PORCH_CAMERA'
    assert values['persistence']['usb']['hostPath'] == '/dev/bus/usb'


def test_namespace_local_substitution_and_external_routes():
    for rel in ['default/homepage', 'default/theme-park', 'network/external']:
        ks = yaml.safe_load((ROOT / 'kubernetes/apps' / rel / 'ks.yaml').read_text())
        assert ks['spec']['postBuild']['substituteFrom'] == [{'kind': 'Secret', 'name': 'cluster-secrets'}]
        if rel == 'network/external':
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
    assert podfetch['controllers']['main']['containers']['podfetch']['env']['DATABASE_URL'] == 'sqlite:///app/db/podcast.db'
    assert '@sha256:' in podfetch['controllers']['main']['containers']['podfetch']['image']['tag']
    whisparr = yaml.safe_load((ROOT / 'kubernetes/apps/media/whisparr/app/helmrelease.yaml').read_text())['spec']['values']
    assert whisparr['controllers']['main']['containers']['whisparr']['env']['PUID'] == whisparr['controllers']['main']['containers']['whisparr']['env']['PGID'] == 568


def test_prometheus_route_uses_verified_internal_http_service():
    base = ROOT / 'kubernetes/apps/monitoring/kube-prometheus-stack/app'
    assert './httproute.yaml' not in yaml.safe_load((base / 'kustomization.yaml').read_text())['resources']
    route = yaml.safe_load((base / 'httproute.yaml').read_text())['spec']
    assert route['hostnames'] == ['prometheus.${SECRET_DOMAIN}']
    assert route['parentRefs'] == [{'name': 'envoy-internal', 'namespace': 'network', 'sectionName': 'https'}]
    assert route['rules'][0]['backendRefs'] == [{'name': 'kube-prometheus-stack-prometheus', 'port': 9090}]


def test_recyclarr_preserves_state_between_nonoverlapping_jobs():
    base = ROOT / 'kubernetes/apps/media/recyclarr/app'
    values = yaml.safe_load((base / 'helmrelease.yaml').read_text())['spec']['values']
    assert values['controllers']['main']['cronjob']['concurrencyPolicy'] == 'Forbid'
    assert values['persistence']['config']['existingClaim'] == 'recyclarr-state'
    assert values['persistence']['config']['type'] == 'persistentVolumeClaim'
    assert values['persistence']['config']['advancedMounts']['main']['recyclarr'] == [
        {'path': '/config', 'readOnly': False, 'subPath': ''}
    ]
    assert values['persistence']['config-file']['advancedMounts']['main']['recyclarr'] == [
        {'path': '/config/recyclarr.yml', 'subPath': 'recyclarr.yml', 'readOnly': True}
    ]
    pv = yaml.safe_load((base / 'state-pv.yaml').read_text())['spec']
    pvc = yaml.safe_load((base / 'state-pvc.yaml').read_text())['spec']
    assert pv['persistentVolumeReclaimPolicy'] == 'Retain'
    assert pv['claimRef'] == {'namespace': 'media', 'name': 'recyclarr-state'}
    assert pvc['volumeName'] == 'local-recyclarr-state'


def test_workload_manifests_are_referenced_by_kustomize():
    workload_kinds = {'HelmRelease', 'Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'CronJob', 'Pod'}
    for path in (ROOT / 'kubernetes/apps').rglob('*.yaml'):
        if '.sops.' in path.name:
            continue
        documents = list(yaml.safe_load_all(path.read_text()))
        if not any(isinstance(doc, dict) and doc.get('kind') in workload_kinds for doc in documents):
            continue
        parent = yaml.safe_load((path.parent / 'kustomization.yaml').read_text())
        resources = {(path.parent / resource).resolve() for resource in parent.get('resources', [])}
        assert path.resolve() in resources, f"Unused workload manifest: {path.relative_to(ROOT)}"


def test_frigate_uses_local_database_and_authenticated_route():
    base = ROOT / 'kubernetes/apps/home/frigate/app'
    values = yaml.safe_load((base / 'helmrelease.yaml').read_text())['spec']['values']
    config = yaml.safe_load(values['configMaps']['config']['data']['config.yml'])
    assert config['database']['path'] == '/config/frigate.db'
    assert config['auth']['enabled'] is False
    assert config['proxy']['header_map']['user'] == 'remote-user'
    policy = yaml.safe_load((base / 'securitypolicy.yaml').read_text())['spec']
    assert policy['extAuth']['failOpen'] is False
    assert config['tls']['enabled'] is False
    assert config['ffmpeg']['hwaccel_args'] == 'preset-vaapi'
    assert all(c['ffmpeg']['inputs'][0]['roles'] == ['detect'] for c in config['cameras'].values())
    assert values['service']['main']['ports'] == {'http': {'port': 8971}, 'rtsp': {'port': 8554}}
    assert config['go2rtc']['streams'] == {
        name: [camera['ffmpeg']['inputs'][0]['path']] for name, camera in config['cameras'].items()
    }
    route = yaml.safe_load((base / 'httproute.yaml').read_text())
    assert route['spec']['rules'][0]['backendRefs'] == [{'name': 'frigate', 'port': 8971}]
    assert route['spec']['parentRefs'][0]['name'] == 'envoy-internal'
    pv = yaml.safe_load((base / 'config-pv.yaml').read_text())['spec']
    pvc = yaml.safe_load((base / 'config-pvc.yaml').read_text())['spec']
    assert pvc['volumeName'] == 'local-frigate-config'
    assert pv['persistentVolumeReclaimPolicy'] == 'Retain'
    assert pv['local']['path'] == '/var/lib/homelab/app-data/frigate-config'
    assert values['persistence']['config']['globalMounts'] == [{'path': '/config'}]
    assert values['persistence']['media']['advancedMounts']['main']['app'] == [{'path': '/media'}]
