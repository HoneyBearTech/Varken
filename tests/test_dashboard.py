"""The Grafana dashboard in dashboard/: generated, and built only from metrics and labels Varken serves."""
import importlib.util
import re
from pathlib import Path

import pytest

from tests.sample_metrics import sample

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('make_dashboard', ROOT / 'dashboard' / 'make_dashboard.py')
make_dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_dashboard)

SERIES = re.compile(r'^(\w+)\{(.*)\} ', re.MULTILINE)


@pytest.fixture(scope='module')
def served():
    """Every metric name in the sample scrape, with the labels it carries."""
    labels = {}
    for name, label_text in SERIES.findall(sample()):
        labels.setdefault(name, set()).update(re.findall(r'(\w+)="', label_text))
    return labels


def test_the_committed_dashboard_is_up_to_date():
    assert make_dashboard.main(['--check']) == 0


def test_it_has_the_original_dashboards_35_panels():
    panels = make_dashboard.dashboard()['panels']
    assert len(panels) == 35
    assert len({panel['id'] for panel in panels}) == 35


@pytest.mark.parametrize('build', ['dashboard', 'argus_dashboard'])
def test_every_query_uses_metrics_and_labels_varken_serves(served, build):
    for panel in getattr(make_dashboard, build)()['panels']:
        for target in panel['targets']:
            names = set(re.findall(r'\bvarken_\w+', target['expr']))
            assert names, panel['title']
            for name in names:
                assert name in served, (panel['title'], name)
            used = set(re.findall(r'(\w+)\s*(?:=~|!=|=)\s*"', target['expr']))
            used |= set(re.findall(r'by \(([\w, ]+)\)', target['expr'])[0].replace(' ', '').split(',')
                        if 'by (' in target['expr'] else [])
            for label in used:
                assert any(label in served[name] for name in names), (panel['title'], label)


@pytest.mark.parametrize('build', ['dashboard', 'argus_dashboard'])
def test_every_table_column_is_a_label_of_its_metric(served, build):
    for panel in getattr(make_dashboard, build)()['panels']:
        if panel['type'] != 'table':
            continue
        name = re.match(r'(\w+)', panel['targets'][0]['expr']).group(1)
        columns = panel['transformations'][0]['options']['include']['names']
        assert set(columns) <= served[name], (panel['title'], set(columns) - served[name])


def test_the_argus_copy_pins_argus_data_source():
    dash = make_dashboard.argus_dashboard()
    text = make_dashboard.formatted(dash)
    assert '${datasource}' not in text
    assert dash['uid'] == 'argus-varken' and 'argus' in dash['tags']
    assert [v['name'] for v in dash['templating']['list']] == list(make_dashboard.LIBRARIES)


def test_the_argus_copy_leaves_ombi_and_sickchill_out():
    full, argus = make_dashboard.dashboard()['panels'], make_dashboard.argus_dashboard()['panels']
    assert not [p['title'] for p in argus if make_dashboard.uses(p, 'varken_ombi_')]
    assert not [p['title'] for p in argus if make_dashboard.uses(p, 'varken_sickchill_')]
    assert len(argus) == len(full) - 8 + 7  # Seerr's 6 tiles and table in Ombi's places
    assert len({p['id'] for p in argus}) == len(argus)
    # The original panels keep their ids, so links to a panel work in both; Seerr's are numbered after them.
    original = {p['id']: p['title'] for p in full}
    assert all(original[p['id']] == p['title'] for p in argus if p['id'] in original)
    assert sorted(p['id'] for p in argus if p['id'] not in original) == list(range(len(full) + 1, len(full) + 8))


def test_the_argus_copy_names_the_instance_of_each_sonarr_and_radarr_row(served):
    def arr_table(p):
        return p['type'] == 'table' and any(make_dashboard.uses(p, m) for m in ('varken_sonarr_', 'varken_radarr_'))
    tables = [p for p in make_dashboard.argus_dashboard()['panels'] if arr_table(p)]
    assert len(tables) == 5
    for panel in tables:
        columns = panel['transformations'][0]['options']['include']['names']
        assert columns[0] == 'server'
        assert panel['transformations'][-1]['options']['renameByName']['server'] == 'Instance'
        mapping = next(o for o in panel['fieldConfig']['overrides'] if o['matcher']['options'] == 'Instance')
        assert mapping['properties'][0]['value'][0]['options'] == {'1': {'text': 'HD', 'index': 0},
                                                                  '2': {'text': '4K', 'index': 1}}
    # Varken's own copy is unchanged: no instance column.
    for panel in make_dashboard.dashboard()['panels']:
        if panel['type'] == 'table':
            assert 'server' not in panel['transformations'][0]['options']['include']['names']
