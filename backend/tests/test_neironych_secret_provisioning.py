import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('provision', ROOT / 'ops/provision_neironych_key.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_atomic_secret_update_preserves_other_settings_and_permissions(tmp_path):
    path = tmp_path / '.env'
    path.write_text('OTHER=value\nNEIRONYCH_API_KEY=old-test-only\n')
    path.chmod(0o600)
    module.provision(path, 'new-test-only-key')
    assert path.read_text() == "OTHER=value\nNEIRONYCH_API_KEY='new-test-only-key'\n"
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('key', ['', 'bad\nkey', '${EXPAND_ME}', "bad'quoted"])
def test_empty_or_unsafe_key_does_not_change_existing_file(tmp_path, key):
    path = tmp_path / '.env'
    path.write_text('NEIRONYCH_API_KEY=old-test-only\n')
    path.chmod(0o600)
    with pytest.raises(ValueError):
        module.provision(path, key)
    assert path.read_text() == 'NEIRONYCH_API_KEY=old-test-only\n'


def test_workflow_provisioning_is_owner_opt_in_only():
    source = (ROOT / '.github/workflows/deploy-dev.yml').read_text()
    assert "if: github.event_name == 'workflow_dispatch' && inputs.provision_neironych_key" in source
    assert 'default: false' in source
    assert 'NEIRONYCH_API_KEY: ${{ secrets.NEIRONYCH_API_KEY }}' in source
