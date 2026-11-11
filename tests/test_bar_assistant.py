from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[1] / 'kubernetes/apps/home/bar-assistant/app'


def test_bar_assistant_cannot_consume_unbounded_resources_or_run_on_radio_and_camera_nodes():
    values = yaml.safe_load((BASE / 'helmrelease.yaml').read_text())['spec']['values']
    for controller in values['controllers'].values():
        pod = controller['pod']
        assert pod['nodeSelector'] == {'kubernetes.io/hostname': 'k8s-phoenix'}
        assert pod['automountServiceAccountToken'] is False
        for container in controller['containers'].values():
            limits = container['resources']['limits']
            assert int(limits['cpu'].removesuffix('m')) <= 750
            assert int(limits['memory'].removesuffix('Mi')) <= 768
            assert limits['ephemeral-storage'] == '256Mi'
    search = values['controllers']['search']['containers']['app']['env']
    assert search['MEILI_MAX_INDEXING_THREADS'] == '1'
    assert search['MEILI_MAX_INDEXING_MEMORY'] == '128MiB'
    volumes = list(yaml.safe_load_all((BASE / 'storage.yaml').read_text()))
    for volume in volumes:
        if volume['kind'] == 'PersistentVolume':
            assert volume['spec']['persistentVolumeReclaimPolicy'] == 'Retain'
            assert volume['spec']['local']['path'].startswith('/var/lib/homelab/ssd-data/bar-assistant-')
            assert volume['spec']['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions'][0]['values'] == ['k8s-phoenix']


def test_bar_assistant_routes_require_home_login_and_direct_access_is_restricted():
    policy = yaml.safe_load((BASE / 'securitypolicy.yaml').read_text())['spec']
    assert policy['targetRefs'][0]['name'] == 'bar-assistant'
    assert policy['extAuth']['failOpen'] is False
    # Salt Rim always sends its own Authorization header, including before login.
    auth = yaml.safe_load((BASE.parents[2] / 'security/authelia/app/configuration.yaml').read_text())
    endpoints = auth['server']['endpoints']['authz']
    endpoint_name = policy['extAuth']['http']['path'].strip('/').split('/')[-1]
    assert endpoints[endpoint_name]['implementation'] == 'ExtAuthz'
    assert endpoints[endpoint_name]['authn_strategies'] == [{'name': 'CookieSession'}]
    assert 'cookie' in policy['extAuth']['headersToExtAuth']
    assert {'ext-authz', 'auth-request', 'forward-auth', 'legacy'} <= endpoints.keys()
    network = yaml.safe_load((BASE / 'networkpolicy.yaml').read_text())['spec']
    assert network['policyTypes'] == ['Ingress']
    for rule in network['ingress']:
        for peer in rule['from']:
            assert 'podSelector' in peer and 'ipBlock' not in peer
    assert not (BASE / 'api-httproute.yaml').exists()
