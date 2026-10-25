from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'kubernetes/apps/home/music-assistant/app'


def read(name):
    return yaml.safe_load((APP / name).read_text())


def test_music_assistant_lan_access_without_mount_privileges():
    values = read('helmrelease.yaml')['spec']['values']
    main = values['controllers']['main']
    assert main['strategy'] == 'Recreate'
    assert main['pod']['hostNetwork'] is True
    assert main['pod']['dnsPolicy'] == 'ClusterFirstWithHostNet'
    assert main['pod']['automountServiceAccountToken'] is False
    security = main['containers']['app']['securityContext']
    assert security['allowPrivilegeEscalation'] is False
    assert security['capabilities'] == {'drop': ['ALL'], 'add': ['NET_BIND_SERVICE']}
    route = read('httproute.yaml')['spec']
    assert route['parentRefs'][0]['name'] == 'envoy-internal'
    assert route['rules'][0]['backendRefs'][0]['port'] == values['service']['main']['ports']['http']['port'] == 8095


def test_music_assistant_retains_data_on_bahamut():
    pv = read('config-pv.yaml')
    pvc = read('config-pvc.yaml')
    data = read('helmrelease.yaml')['spec']['values']['persistence']['data']
    assert pv['spec']['persistentVolumeReclaimPolicy'] == 'Retain'
    assert pv['metadata']['annotations']['kustomize.toolkit.fluxcd.io/prune'] == 'disabled'
    assert pvc['spec']['volumeName'] == pv['metadata']['name']
    assert data['existingClaim'] == pvc['metadata']['name'] == pv['spec']['claimRef']['name']
    assert pv['spec']['local']['path'] == '/var/lib/homelab/app-data/music-assistant-data'
    assert pv['spec']['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions'][0]['values'] == ['k8s-summoner']
    assert data['globalMounts'] == [{'path': '/data'}]
