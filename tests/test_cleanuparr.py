from pathlib import Path
import yaml

APP = Path(__file__).resolve().parents[1] / 'kubernetes/apps/media/cleanuparr/app'


def test_cleanuparr_has_persistent_config_and_protected_internal_route():
    values = yaml.safe_load((APP / 'helmrelease.yaml').read_text())['spec']['values']
    assert values['controllers']['main']['strategy'] == 'Recreate'
    assert list(values['persistence']) == ['config']
    assert values['persistence']['config']['existingClaim'] == 'cleanuparr-config'
    route = yaml.safe_load((APP / 'httproute.yaml').read_text())
    assert route['spec']['parentRefs'][0]['name'] == 'envoy-internal'
    assert route['spec']['rules'][0]['backendRefs'] == [{'name': 'cleanuparr', 'port': 11011}]
    policy = yaml.safe_load((APP / 'securitypolicy.yaml').read_text())
    assert policy['spec']['targetRefs'][0]['name'] == route['metadata']['name']
    assert policy['spec']['extAuth']['failOpen'] is False


def test_cleanuparr_direct_access_is_limited_to_the_authenticated_gateway():
    policy = yaml.safe_load((APP / 'networkpolicy.yaml').read_text())['spec']
    assert policy['podSelector']['matchLabels'] == {'app.kubernetes.io/name': 'cleanuparr'}
    assert policy['policyTypes'] == ['Ingress']
    assert policy['ingress'] == [{'from': [{
        'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'network'}},
        'podSelector': {'matchLabels': {'gateway.envoyproxy.io/owning-gateway-name': 'envoy-internal'}},
    }], 'ports': [{'protocol': 'TCP', 'port': 11011}]}]
    assert './networkpolicy.yaml' in yaml.safe_load((APP / 'kustomization.yaml').read_text())['resources']
    assert {'name': 'cluster-apps-authelia'} in yaml.safe_load((APP.parent / 'ks.yaml').read_text())['spec']['dependsOn']
