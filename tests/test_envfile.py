from backend.envfile import load_env_file


def test_loads_values_but_real_environment_wins(tmp_path):
    file = tmp_path / '.env'
    file.write_text('# comment\nA=1\nB="two"\nC=\nKEEP=from-file\n1BAD=x\n', encoding='utf-8')
    environ = {'KEEP': 'from-env'}
    loaded = load_env_file(file, environ)
    assert environ == {'KEEP': 'from-env', 'A': '1', 'B': 'two'}
    assert sorted(loaded) == ['A', 'B']


def test_missing_file_and_opt_out(tmp_path):
    assert load_env_file(tmp_path / 'none', {}) == []
    file = tmp_path / '.env'
    file.write_text('A=1\n', encoding='utf-8')
    environ = {'SCHOOL_AGENT_LOAD_DOTENV': '0'}
    assert load_env_file(file, environ) == []
    assert 'A' not in environ
