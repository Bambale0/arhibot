from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_housekeeping_cleans_dangling_images_and_builder_cache() -> None:
    script = (REPO_ROOT / 'ops/runtime_housekeeping.sh').read_text()

    assert 'docker image prune -f' in script
    assert 'docker builder prune -f' in script
    assert 'mode=${2:-REPORT}' in script


def test_successful_deploy_runs_housekeeping_in_apply_mode() -> None:
    script = (REPO_ROOT / 'ops/deploy_docker.sh').read_text()

    assert '"${app_dir}/ops/runtime_housekeeping.sh" "${app_dir}" APPLY' in script
    assert 'rollout_succeeded=1' in script
