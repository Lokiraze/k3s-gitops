from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / 'kubernetes/apps/security/authelia/app'
SONARR = ROOT / 'kubernetes/apps/media/sonarr/app'


def read(path):
    return yaml.safe_load(path.read_text())


def test_only_lokiraze_can_open_sonarr_and_failures_deny_access():
    access = read(AUTH / 'configuration.yaml')['access_control']
    assert access['default_policy'] == 'deny'
    assert access['rules'] == [{
        'domain': 'tv.${SECRET_DOMAIN}', 'subject': 'user:lokiraze', 'policy': 'one_factor',
    }]
    policy = read(SONARR / 'securitypolicy.yaml')['spec']
    assert policy['targetRefs'] == [{
        'group': 'gateway.networking.k8s.io', 'kind': 'HTTPRoute', 'name': 'sonarr',
    }]
    assert policy['extAuth']['failOpen'] is False
    assert policy['extAuth']['http']['path'] == '/api/authz/ext-authz/'
    assert read(AUTH / 'httproute.yaml')['spec']['parentRefs'][0]['name'] == 'envoy-internal'


def test_only_api_path_bypasses_sso_and_direct_lan_access_is_not_allowed():
    api = read(SONARR / 'api-httproute.yaml')['spec']
    assert api['hostnames'] == ['tv.${SECRET_DOMAIN}']
    assert api['rules'][0]['matches'] == [{'path': {'type': 'PathPrefix', 'value': '/api'}}]
    assert api['rules'][0]['backendRefs'] == [{'name': 'sonarr', 'port': 80}]
    network = read(SONARR / 'networkpolicy.yaml')['spec']
    assert network['podSelector']['matchLabels'] == {'app.kubernetes.io/name': 'sonarr'}
    assert network['policyTypes'] == ['Ingress']
    for rule in network['ingress']:
        assert rule['ports'] == [{'protocol': 'TCP', 'port': 80}]
        for peer in rule['from']:
            assert 'namespaceSelector' in peer and 'podSelector' in peer
            assert 'ipBlock' not in peer
    env = read(SONARR / 'helmrelease.yaml')['spec']['values']['controllers']['main']['containers']['sonarr']['env']
    assert env['SONARR__AUTH__METHOD'] == 'External'
    assert env['SONARR__AUTH__REQUIRED'] == 'Enabled'


def test_ldap_secrets_are_encrypted_and_session_storage_is_retained():
    secret = read(AUTH / 'secret.sops.yaml')
    assert 'sops' in secret
    assert all(value.startswith('ENC[') for value in secret['stringData'].values())
    ldap = read(AUTH / 'configuration.yaml')['authentication_backend']['ldap']
    assert ldap['user'] == 'uid=readonly,ou=people,dc=lokiraze,dc=dev'
    assert 'password' not in ldap
    pv, pvc = list(yaml.safe_load_all((AUTH / 'storage.yaml').read_text()))
    assert pv['spec']['persistentVolumeReclaimPolicy'] == 'Retain'
    assert pv['spec']['claimRef']['name'] == pvc['metadata']['name']
    assert pvc['spec']['volumeName'] == pv['metadata']['name']
    ks = read(SONARR.parent / 'ks.yaml')['spec']
    assert {'name': 'cluster-apps-authelia'} in ks['dependsOn']
