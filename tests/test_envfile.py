import os
import subprocess
import sys

from backend.envfile import load_env_file


def test_local_settings_preserve_real_environment_and_ignore_empty_values(tmp_path):
    file = tmp_path / '.env'
    file.write_text('\ufeffOPENAI_API_KEY="local-test-key"\nOPENAI_MODEL=local-model\n'
                    'export AZURE_SPEECH_REGION=koreacentral # local region\nEMPTY=\n'
                    '# ignored\nINVALID-NAME=value\n', encoding='utf-8')
    environment = {'OPENAI_API_KEY': 'server-test-key'}
    assert set(load_env_file(file, environment)) == {'OPENAI_MODEL', 'AZURE_SPEECH_REGION'}
    assert environment == {'OPENAI_API_KEY': 'server-test-key', 'OPENAI_MODEL': 'local-model',
                           'AZURE_SPEECH_REGION': 'koreacentral'}


def test_dotenv_can_be_disabled_for_tests(tmp_path):
    file = tmp_path / '.env'
    file.write_text('OPENAI_API_KEY=never-loaded\n', encoding='utf-8')
    environment = {'SCHOOL_AGENT_LOAD_DOTENV': '0'}
    assert load_env_file(file, environment) == []
    assert 'OPENAI_API_KEY' not in environment


def test_config_and_registry_use_server_settings_without_a_provider_call():
    environment = {**os.environ, 'SCHOOL_AGENT_LOAD_DOTENV': '0', 'OPENAI_API_KEY': 'test-only',
                   'OPENAI_MODEL': 'test-model', 'AZURE_SPEECH_KEY': 'test-only',
                   'AZURE_SPEECH_REGION': 'koreacentral'}
    code = ('from backend.runtime import build_registry; import config; '
            'assert config.LLM_API_KEY; '
            'assert set(build_registry().handlers) == '
            '{"REVIEW_SUPPORT", "COMPARE_CASES", "SUMMARIZE_TRANSCRIPT", "TRANSCRIBE_AUDIO", "TONE_REWRITE"}')
    subprocess.run([sys.executable, '-c', code], env=environment, check=True, capture_output=True)
