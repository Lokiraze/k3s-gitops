from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'kubernetes/apps/media/bazarr/app'


def test_bazarr_uses_distinct_writable_media_mounts_and_preserves_settings():
    values = yaml.safe_load((APP / 'helmrelease.yaml').read_text())['spec']['values']
    for key, source in [('tv', 'tvshows'), ('movies', 'movies')]:
        volume = values['persistence'][key]
        assert volume['path'] == f'/mnt/user/media/{source}'
        assert volume['advancedMounts']['main']['bazarr'] == [{'path': f'/{key}'}]
    controller = values['controllers']['main']
    assert controller['strategy'] == 'Recreate'
    assert controller['containers']['bazarr']['env']['PUID'] == 568
    seed = controller['initContainers']['seed-config']['command'][-1]
    assert 'if [ ! -s /config/config/config.yaml ]; then' in seed
    assert set(values['persistence']['bootstrap']['advancedMounts']['main']) == {'seed-config'}
    secret = yaml.safe_load((APP / 'secret.sops.yaml').read_text())
    assert 'sops' in secret
    assert secret['stringData']['config.yaml'].startswith('ENC[')
    assert secret['stringData']['initial-password'].startswith('ENC[')


def test_bazarr_internal_route_matches_service_and_retained_storage():
    values = yaml.safe_load((APP / 'helmrelease.yaml').read_text())['spec']['values']
    route = yaml.safe_load((APP / 'httproute.yaml').read_text())['spec']
    assert route['parentRefs'][0]['name'] == 'envoy-internal'
    assert route['rules'][0]['backendRefs'][0]['port'] == values['service']['main']['ports']['http']['port']
    pv = yaml.safe_load((APP / 'config-pv.yaml').read_text())['spec']
    pvc = yaml.safe_load((APP / 'config-pvc.yaml').read_text())
    assert pv['persistentVolumeReclaimPolicy'] == 'Retain'
    assert pv['claimRef']['name'] == pvc['metadata']['name'] == values['persistence']['config']['existingClaim']
    assert pv['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions'][0]['values'] == ['k8s-phoenix']
