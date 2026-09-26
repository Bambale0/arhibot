from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Request, Response

from app.api.v1 import auth
from app.core.errors import AppError
from app.schemas.auth import LoginRequest
from app.services import rate_limit_service

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_smoke_login_payload_reaches_authentication_validation() -> None:
    workflow = (REPO_ROOT / '.github/workflows/server-smoke.yml').read_text()
    body = re.search(r"--data '([^']+)'", workflow)
    assert body is not None
    payload = LoginRequest.model_validate_json(body.group(1))
    assert payload.email.endswith('@example.com')


@pytest.mark.asyncio
async def test_smoke_observes_the_actual_login_ip_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = (REPO_ROOT / '.github/workflows/server-smoke.yml').read_text()
    digest_assignment = next(
        line.strip() for line in workflow.splitlines() if line.strip().startswith('probe_digest=')
    )
    probe_ip = '198.51.100.77'
    digest = subprocess.check_output(
        ['bash', '-c', f'probe_ip={probe_ip}\n{digest_assignment}\nprintf %s "$probe_digest"'],
        text=True,
        timeout=5,
    )
    now = 1_800_000_000
    monkeypatch.setattr(rate_limit_service, 'time', SimpleNamespace(time=lambda: now))
    monkeypatch.setattr(
        rate_limit_service.OperationalSettingsRepository, 'get', AsyncMock(return_value=None),
    )
    incr = AsyncMock(return_value=1)
    monkeypatch.setattr(rate_limit_service.redis_client, 'incr', incr)
    monkeypatch.setattr(rate_limit_service.redis_client, 'expire', AsyncMock())
    invalid_credentials = AppError(
        type='invalid_credentials', title='Invalid credentials',
        status=401, detail='Synthetic probe',
    )
    monkeypatch.setattr(
        auth, '_service',
        lambda *_args: SimpleNamespace(login=AsyncMock(side_effect=invalid_credentials)),
    )
    request = Request({
        'type': 'http', 'headers': [(b'x-real-ip', probe_ip.encode())],
        'client': ('127.0.0.1', 1234),
    })
    with pytest.raises(AppError) as failure:
        await auth.login_user(
            LoginRequest(email='proxy-probe@example.com', password='not-a-real-password'),
            request, Response(), SimpleNamespace(), SimpleNamespace(),
        )
    assert failure.value.status == 401
    assert incr.await_args_list[0].args == (f'auroom:rate:auth:{digest}:{now // 60}',)


def _run_smoke_transport(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    workflow = (REPO_ROOT / '.github/workflows/server-smoke.yml').read_text()
    step = workflow.split('      - name: Run smoke checks on development host\n', 1)[1]
    script = textwrap.dedent(step.split('        run: |\n', 1)[1])
    transport = script.split("<<'REMOTE'\n", 1)[0]
    # SSH joins its remote command arguments before asking the login shell to run
    # them. Reproduce that transport locally; no network or Docker is involved.
    ssh = tmp_path / 'ssh'
    ssh.write_text('#!/usr/bin/env bash\nshift 3\nexec bash -c "$*"\n')
    ssh.chmod(0o700)
    env = {
        **os.environ,
        'PATH': f'{tmp_path}{os.pathsep}{os.environ["PATH"]}',
        'DEPLOY_SSH_PORT': '22',
        'DEPLOY_SSH_USER': 'smoke',
        'DEPLOY_SSH_HOST': 'example.invalid',
        'DEPLOY_APP_DIR': '/tmp/smoke-app',
    }
    return subprocess.run(
        ['bash'],
        input=f"{transport}<<'REMOTE'\n{body}\nREMOTE\n",
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )


def test_smoke_continues_after_a_child_consumes_stdin(tmp_path: Path) -> None:
    result = _run_smoke_transport(tmp_path, '''set -Eeuo pipefail
printf 'before\n'
# Compose exec attaches stdin even with -T, like this greedy reader.
cat >/dev/null
[[ "$1" == /tmp/smoke-app ]]
printf 'all_checks_completed\n'
''')

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['before', 'all_checks_completed']


def test_smoke_preserves_explicit_input_for_container_python(tmp_path: Path) -> None:
    result = _run_smoke_transport(tmp_path, '''set -Eeuo pipefail
cat >/dev/null
cat <<'PY'
explicit_container_input
PY
printf 'all_checks_completed\n'
''')

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['explicit_container_input', 'all_checks_completed']


@pytest.mark.parametrize('failure_code', [1, 23])
def test_smoke_propagates_failure_after_a_child_consumes_stdin(
    tmp_path: Path, failure_code: int,
) -> None:
    result = _run_smoke_transport(tmp_path, f'''set -Eeuo pipefail
cat >/dev/null
printf 'late_check_failed\n' >&2
exit {failure_code}
''')

    assert result.returncode == failure_code
    assert 'late_check_failed' in result.stderr
