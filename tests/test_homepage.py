from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return yaml.safe_load((ROOT / path).read_text())

def test_gateway_discovery_has_read_only_permissions_and_route_owned_links():
    base = 'kubernetes/apps/default/homepage/app/'
    values = read(base + 'helmrelease.yaml')['spec']['values']
    config = values['configMaps']['config']['data']
    assert yaml.safe_load(config['kubernetes.yaml']) == {'mode': 'cluster', 'ingress': False, 'gateway': True}
    assert yaml.safe_load(config['services.yaml']) == []
    docs = list(yaml.safe_load_all((ROOT / base / 'rbac.yaml').read_text()))
    role = next(d for d in docs if d['kind'] == 'ClusterRole')
    assert any('httproutes' in r['resources'] and 'gateways' in r['resources'] for r in role['rules'])
    assert all(set(r['verbs']) <= {'get', 'list', 'watch'} and 'secrets' not in r['resources'] for r in role['rules'])
    routes = [read(str(p.relative_to(ROOT))) for p in (ROOT / 'kubernetes/apps').rglob('httproute.yaml')]
    annotated = [r for r in routes if r['metadata'].get('annotations', {}).get('gethomepage.dev/enabled') == 'true']
    assert len(annotated) >= 19
    for route in annotated:
        a = route['metadata']['annotations']
        assert a['gethomepage.dev/href'] == 'https://' + route['spec']['hostnames'][0]
        assert a['gethomepage.dev/name'] and a['gethomepage.dev/group']
    apex = [r for r in routes if r['spec'].get('hostnames') == ['${SECRET_DOMAIN}']]
    assert len(apex) == 1 and apex[0]['spec']['rules'][0]['backendRefs'] == [{'name': 'homepage', 'port': 3000}]

def test_themes_use_local_server_and_supported_linuxserver_mods():
    for app in ['sonarr', 'lidarr', 'bazarr', 'calibre-web']:
        values = read(f'kubernetes/apps/media/{app}/app/helmrelease.yaml')['spec']['values']
        containers = values['controllers']['main']['containers']
        target = next(c for c in containers.values() if c['image']['repository'].startswith('ghcr.io/linuxserver/'))
        assert target['env']['DOCKER_MODS'] == f'ghcr.io/themepark-dev/theme.park:{app}'
        assert target['env']['TP_DOMAIN'] == 'theme-park.${SECRET_DOMAIN}'
        assert target['env']['TP_THEME'] == 'aquamarine'
