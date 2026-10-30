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
