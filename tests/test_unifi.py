from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'kubernetes/apps/network/unifi/app'


def read(name):
    return yaml.safe_load((APP / name).read_text())


def test_unifi_keeps_database_private_and_credentials_encrypted():
    values = read('helmrelease.yaml')['spec']['values']
    mongo = values['controllers']['main']['containers']['mongodb']
    assert mongo['args'][mongo['args'].index('--bind_ip') + 1] == '127.0.0.1'
    assert all(port['port'] != 27017 for service in values['service'].values() for port in service['ports'].values())
    secret = read('secret.sops.yaml')
    assert 'sops' in secret
    for key in ['MONGO_PASS', 'MONGO_INITDB_ROOT_PASSWORD']:
        assert mongo['env'][key]['valueFrom']['secretKeyRef']['name'] == secret['metadata']['name']
        assert secret['stringData'][key].startswith('ENC[')
    assert values['controllers']['main']['containers']['unifi']['env']['MONGO_HOST'] == '127.0.0.1'


def test_unifi_route_uses_verified_tls_and_renewal_reimports_certificate():
    values = read('helmrelease.yaml')['spec']['values']
    route = read('httproute.yaml')['spec']
    tls = read('backendtlspolicy.yaml')['spec']
    assert route['parentRefs'][0]['name'] == 'envoy-internal'
    assert route['hostnames'] == [tls['validation']['hostname']]
    assert tls['validation']['wellKnownCACertificates'] == 'System'
    backend = route['rules'][0]['backendRefs'][0]
    assert backend['name'] == tls['targetRefs'][0]['name'] == 'unifi'
    assert backend['port'] == values['service']['main']['ports'][tls['targetRefs'][0]['sectionName']]['port']
    controller = values['controllers']['main']
    assert controller['annotations']['reloader.stakater.com/auto'] == 'true'
    mounts = values['persistence']['certificate']['advancedMounts']['main']
    assert set(mounts) == {'install-certificate'}
    assert mounts['install-certificate'][0]['readOnly'] is True


def test_unifi_restarts_against_retained_storage_on_one_node():
    values = read('helmrelease.yaml')['spec']['values']
    assert values['controllers']['main']['strategy'] == 'Recreate'
    for key in ['config', 'database']:
        claim = values['persistence'][key]['existingClaim']
        pv, pvc = yaml.safe_load_all((APP / f'{claim}-storage.yaml').read_text())
        assert pvc['metadata']['name'] == pv['spec']['claimRef']['name'] == claim
        assert pvc['spec']['volumeName'] == pv['metadata']['name']
        assert pv['spec']['persistentVolumeReclaimPolicy'] == 'Retain'
        assert pv['metadata']['annotations']['kustomize.toolkit.fluxcd.io/prune'] == 'disabled'
        assert pv['spec']['local']['path'] == f'/var/lib/homelab/app-data/{claim}'
        terms = pv['spec']['nodeAffinity']['required']['nodeSelectorTerms']
        assert terms[0]['matchExpressions'][0]['values'] == ['k8s-phoenix']
