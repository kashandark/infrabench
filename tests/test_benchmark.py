import copy
import json

import pytest
import yaml

from infrabench.cli import main
from infrabench.core import InputError, evaluate, load_scenarios, markdown, read_data


@pytest.fixture
def suite():
    return load_scenarios()


@pytest.fixture
def submission(suite):
    return {'schema_version': 1, 'agent': 'test', 'responses': [
        {'scenario_id': s['id'], **s['reference_response']} for s in suite]}


def test_reference_and_categories(suite, submission):
    report = evaluate(suite, submission)
    assert len(suite) == 10
    assert len({s['category'] for s in suite}) == 7
    assert report['score'] == 100
    assert all(c['passed'] for r in report['results'] for c in r['checks'])


def test_missing_responses_count_as_zero(suite, submission):
    submission['responses'] = submission['responses'][:1]
    report = evaluate(suite, submission)
    assert report['score'] == 10
    assert report['answered_count'] == 1
    assert sum(r['missing'] for r in report['results']) == 9


def test_weighted_partial_credit(suite, submission):
    submission['responses'][0]['diagnosis'] = ''
    result = evaluate(suite, submission)['results'][0]
    assert result['score'] == round(80 / 110 * 100, 2)


def test_critical_failure_zeros_scenario(suite, submission):
    submission['responses'][0]['actions'] += ' ' + suite[0]['checks'][-1]['values'][0]
    result = evaluate(suite, submission)['results'][0]
    assert result['raw_score'] > 0
    assert result['score'] == 0
    assert result['critical_failure']


@pytest.mark.parametrize('change', ['duplicate', 'unknown', 'field', 'version', 'type'])
def test_invalid_submission(suite, submission, change):
    if change == 'duplicate':
        submission['responses'].append(submission['responses'][0])
    elif change == 'unknown':
        submission['responses'][0]['scenario_id'] = 'unknown'
    elif change == 'field':
        submission['responses'][0]['extra'] = 'x'
    elif change == 'version':
        submission['schema_version'] = 2
    else:
        submission['responses'][0]['actions'] = ['not a string']
    with pytest.raises(InputError):
        evaluate(suite, submission)


def test_case_whitespace_and_contains_any(suite, submission):
    suite = copy.deepcopy(suite)
    suite[0]['checks'][0]['operator'] = 'contains_any'
    suite[0]['checks'][0]['values'] = ['UNSEEN PHRASE', 'some phrase']
    submission['responses'][0]['diagnosis'] = 'SOME\n   PHRASE'
    assert evaluate(suite, submission)['results'][0]['score'] == 100


@pytest.mark.parametrize('content', ['id: a\nid: b', '!!python/object/apply:os.system ["echo unsafe"]', '[broken'])
def test_bad_yaml(tmp_path, content):
    path = tmp_path / 'bad.yaml'
    path.write_text(content)
    with pytest.raises(InputError):
        read_data(path)


def test_oversize(tmp_path):
    path = tmp_path / 'large.json'
    path.write_text('x' * 2_000_001)
    with pytest.raises(InputError):
        read_data(path)


@pytest.mark.parametrize('mutation', ['duplicate_scenario', 'duplicate_check', 'weight', 'operator'])
def test_bad_scenarios(suite, tmp_path, mutation):
    scenario = copy.deepcopy(suite[0])
    if mutation == 'duplicate_check':
        scenario['checks'].append(scenario['checks'][0])
    elif mutation == 'weight':
        scenario['checks'][0]['weight'] = 0
    elif mutation == 'operator':
        scenario['checks'][0]['operator'] = 'execute'
    (tmp_path / 'one.yaml').write_text(yaml.safe_dump(scenario))
    if mutation == 'duplicate_scenario':
        (tmp_path / 'two.yaml').write_text(yaml.safe_dump(scenario))
    with pytest.raises(InputError):
        load_scenarios(tmp_path)


def test_empty_suite_directory(tmp_path):
    with pytest.raises(InputError):
        load_scenarios(tmp_path)


def test_reproducibility_and_hash(suite, submission):
    a = evaluate(suite, submission)
    assert a == evaluate(suite, submission)
    submission['agent'] = 'other'
    assert evaluate(suite, submission)['submission_sha256'] != a['submission_sha256']


def test_cli_and_reports(tmp_path, submission):
    source = tmp_path / 'answers.json'
    source.write_text(json.dumps(submission))
    output = tmp_path / 'report'
    assert main(['evaluate', str(source), '--output', str(output), '--min-score', '100']) == 0
    assert json.loads((output / 'report.json').read_text())['score'] == 100
    assert 'PASS' in (output / 'report.md').read_text()
    submission['responses'] = submission['responses'][:1]
    source.write_text(json.dumps(submission))
    assert main(['evaluate', str(source), '--output', str(output), '--min-score', '90']) == 1
    assert main(['evaluate', str(source), '--output', str(output), '--min-score', 'nan']) == 2
    assert main(['evaluate', str(tmp_path / 'missing'), '--output', str(output)]) == 2
    assert main(['validate']) == 0
    assert main(['list']) == 0


def test_export_hides_reference_and_rubric(tmp_path):
    output = tmp_path / 'prompts.json'
    assert main(['export', '--output', str(output)]) == 0
    data = json.loads(output.read_text())
    assert len(data['scenarios']) == 10
    assert all('reference_response' not in s and 'checks' not in s for s in data['scenarios'])


def test_markdown_escapes_html(suite, submission):
    submission['agent'] = '<script>alert(1)</script>'
    assert '<script>' not in markdown(evaluate(suite, submission))


def test_commands_are_never_executed(suite, submission, tmp_path):
    sentinel = tmp_path / 'must-not-exist'
    submission['responses'][0]['actions'] = f'touch {sentinel}'
    evaluate(suite, submission)
    assert not sentinel.exists()
