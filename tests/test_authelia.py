from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / 'kubernetes/apps/security/authelia/app'
SONARR = ROOT / 'kubernetes/apps/media/sonarr/app'
APPS = [('sonarr', 'tv', 80), ('radarr', 'movies', 80), ('lidarr', 'grooves', 8686),
        ('prowlarr', 'prowlarr', 80), ('bazarr', 'bazarr', 6767), ('whisparr', 'whisparr', 6969)]


def read(path):
    return yaml.safe_load(path.read_text())


@pytest.mark.parametrize('app,host,port', APPS)
def test_only_lokiraze_can_open_apps_and_failures_deny_access(app, host, port):
    directory = SONARR.parent.parent / app / 'app'
    access = read(AUTH / 'configuration.yaml')['access_control']
    assert access['default_policy'] == 'deny'
    assert access['rules'] == [{
        'domain': [host + '.${SECRET_DOMAIN}' for _, host, _ in APPS],
        'subject': 'user:lokiraze', 'policy': 'one_factor',
    }]
    policy = read(directory / 'securitypolicy.yaml')['spec']
    assert policy['targetRefs'] == [{
        'group': 'gateway.networking.k8s.io', 'kind': 'HTTPRoute', 'name': app,
    }]
    assert policy['extAuth']['failOpen'] is False
    assert policy['extAuth']['http']['path'] == '/api/authz/ext-authz/'
    assert read(AUTH / 'httproute.yaml')['spec']['parentRefs'][0]['name'] == 'envoy-internal'


@pytest.mark.parametrize('app,host,port', APPS)
def test_only_api_path_bypasses_sso_and_direct_lan_access_is_not_allowed(app, host, port):
    directory = SONARR.parent.parent / app / 'app'
    api = read(directory / 'api-httproute.yaml')['spec']
    assert api['hostnames'] == [host + '.${SECRET_DOMAIN}']
    matches = [{'path': {'type': 'PathPrefix', 'value': '/api'}}]
    if app == 'prowlarr':
        matches.append({'path': {'type': 'RegularExpression', 'value': '^/[0-9]+/(api|download)/?$'}})
    assert api['rules'][0]['matches'] == matches
    assert api['rules'][0]['backendRefs'] == [{'name': app, 'port': port}]
    network = read(directory / 'networkpolicy.yaml')['spec']
    assert network['podSelector']['matchLabels'] == {'app.kubernetes.io/name': app}
    assert network['policyTypes'] == ['Ingress']
    for rule in network['ingress']:
        assert rule['ports'] == [{'protocol': 'TCP', 'port': port}]
        for peer in rule['from']:
            assert 'namespaceSelector' in peer and 'podSelector' in peer
            assert 'ipBlock' not in peer
    env = read(directory / 'helmrelease.yaml')['spec']['values']['controllers']['main']['containers'][app]['env']
    if app == 'bazarr':
        assert env['DYNACONF_AUTH__TYPE'] == '@none'
    else:
        assert env[f'{app.upper()}__AUTH__METHOD'] == 'External'
        assert env[f'{app.upper()}__AUTH__REQUIRED'] == 'Enabled'
    ks = read(directory.parent / 'ks.yaml')['spec']
    assert {'name': 'cluster-apps-authelia'} in ks['dependsOn']
    resources = read(directory / 'kustomization.yaml')['resources']
    for filename in ('securitypolicy.yaml', 'api-httproute.yaml', 'networkpolicy.yaml'):
        assert './' + filename in resources


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
