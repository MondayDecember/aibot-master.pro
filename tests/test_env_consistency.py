"""Guard against drift between config.py, .env.example and the configurator."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Set by docker-compose / wrappers, intentionally not in .env.example
INFRA_KEYS = {"DB_PATH", "HEARTBEAT_FILE", "TTS_VOICE_DIR"}


def _env_example_keys():
    keys = set()
    with open(os.path.join(ROOT, ".env.example"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"#?\s*([A-Z_]+)=", line.strip())
            if m:
                keys.add(m.group(1))
    return keys


def _config_keys():
    with open(os.path.join(ROOT, "config.py"), encoding="utf-8") as f:
        return set(re.findall(r'os\.getenv\(\s*"([A-Z_]+)"', f.read()))


def test_every_config_key_is_documented():
    missing = _config_keys() - _env_example_keys() - INFRA_KEYS
    assert not missing, f"Keys used in config.py but absent from .env.example: {missing}"


def test_configurator_edits_only_real_keys():
    from tools.configure import SETTINGS
    known = _env_example_keys()
    unknown = {key for key, *_ in SETTINGS} - known
    assert not unknown, f"Configurator offers keys missing from .env.example: {unknown}"
