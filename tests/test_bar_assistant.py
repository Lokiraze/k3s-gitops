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


def test_bar_assistant_uses_one_home_login_and_blocks_password_registration():
    values = yaml.safe_load((BASE / 'helmrelease.yaml').read_text())['spec']['values']
    api = values['controllers']['api']['containers']['app']['env']
    web = values['controllers']['web']['containers']['app']['env']
    assert api['ENABLE_PASSWORD_LOGIN'] == 'false'
    assert web['ALLOW_REGISTRATION'] == 'false'
    assert web['REDIRECT_TO_SSO'] == 'true'
    assert not (BASE / 'securitypolicy.yaml').exists()
    assert './securitypolicy.yaml' not in yaml.safe_load((BASE / 'kustomization.yaml').read_text())['resources']
    # The API's registration service is also used internally by SSO provisioning.
    assert api['ALLOW_REGISTRATION'] == 'true'
    nginx = values['configMaps']['api-nginx']['data']['sso-only.conf']
    assert 'api/auth/register' in nginx and 'return 404;' in nginx
    auth = yaml.safe_load((BASE.parents[2] / 'security/authelia/app/configuration.yaml').read_text())
    oidc = auth['identity_providers']['oidc']
    client = next(c for c in oidc['clients'] if c['client_id'] == api['AUTHELIA_CLIENT_ID'])
    assert client['redirect_uris'] == [api['AUTHELIA_REDIRECT_URI']]
    assert client['redirect_uris'] == ['https://bar.${SECRET_DOMAIN}/oauth/callback']
    assert client['token_endpoint_auth_method'] == 'client_secret_post'
    assert {'openid', 'profile', 'email', 'groups'} <= set(client['scopes'])
    assert client['public'] is False
    assert client['client_secret'].startswith('$$pbkdf2-sha512$$')
    assert oidc['authorization_policies'][client['authorization_policy']] == {
        'default_policy': 'deny', 'rules': [{'policy': 'one_factor', 'subject': 'user:lokiraze'}],
    }


def test_bar_assistant_direct_access_is_restricted():
    network = yaml.safe_load((BASE / 'networkpolicy.yaml').read_text())['spec']
    assert network['policyTypes'] == ['Ingress']
    for rule in network['ingress']:
        for peer in rule['from']:
            assert 'podSelector' in peer and 'ipBlock' not in peer
    assert not (BASE / 'api-httproute.yaml').exists()
