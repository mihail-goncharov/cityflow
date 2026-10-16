"""Exercise the real scanner on disposable Git repositories and synthetic values."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GIT = shutil.which("git")
BASH = shutil.which("bash")
GITLEAKS = shutil.which("gitleaks")
pytestmark = pytest.mark.skipif(
    not all((GIT, BASH, GITLEAKS)), reason="Requires git, bash and gitleaks on PATH"
)


def run(command, *args, cwd):
    # Commands are resolved above; arguments are fixed test data and temp paths.
    return subprocess.run(  # noqa: S603
        [command, *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def git(repo, *args):
    result = run(
        GIT, "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
        *args, cwd=repo,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def commit(repo):
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Synthetic scanner fixture")
    return git(repo, "rev-parse", "HEAD")


def scan(repo, *args):
    return run(BASH, str(ROOT / "infra/scripts/scan-secrets.sh"), *args, cwd=repo)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Scanner test")
    git(tmp_path, "config", "user.email", "scanner@example.invalid")
    shutil.copyfile(ROOT / ".gitleaks.toml", tmp_path / ".gitleaks.toml")
    (tmp_path / "README.md").write_text("Clean initial commit\n", encoding="utf-8")
    commit(tmp_path)
    return tmp_path


@pytest.mark.parametrize("key,value,rule", [
    ("RUSTFS_ACCESS_KEY", "rustfsadmin", "cityflow-rustfs-credentials"),
    ("RUSTFS_SECRET_KEY", "weak123", "cityflow-rustfs-credentials"),
    ("DB_PASSWORD", "admin123", "cityflow-password"),
    ("password", "several words with spaces", "cityflow-password"),
])
@pytest.mark.parametrize("style", ["env", "yaml", "json"])
def test_literal_credentials_fail_and_are_redacted(repo, key, value, rule, style):
    if style == "env":
        content = f'{key}="{value}"\n'
    elif style == "yaml":
        content = f"  {key}: '{value}'\n"
    else:
        content = f'{{"{key}": "{value}"}}\n'
    # Even example files must reject real literal values.
    (repo / ".env.example").write_text(content, encoding="utf-8")
    git(repo, "add", ".")

    result = scan(repo, "staged")

    assert result.returncode == 1
    assert rule in result.stdout
    assert "REDACTED" in result.stdout
    assert value not in result.stdout + result.stderr


@pytest.mark.parametrize("kind,rule", [
    ("ssh", "private-key"), ("token", "github-pat"),
])
def test_default_rules_are_still_enabled(repo, kind, rule):
    if kind == "ssh":
        label = "OPENSSH PRIVATE KEY"
        content = f"-----BEGIN {label}-----\n{'YXNkZmdoamts' * 12}\n-----END {label}-----\n"
    else:
        prefix = "ghp_"
        content = f"{prefix}Z8qL7fR3nW6cT2yU9iO4pD5sA1gH0jKxVbNmCeQr\n"
    (repo / "accidental.txt").write_text(content, encoding="utf-8")
    git(repo, "add", ".")

    result = scan(repo, "staged")

    assert result.returncode == 1
    assert rule in result.stdout
    assert content.strip() not in result.stdout + result.stderr


def test_templates_and_existing_commented_examples_are_clean(repo):
    shutil.copyfile(ROOT / ".env.example", repo / ".env.example")
    # This example also existed under the old name in the repository history.
    shutil.copyfile(ROOT / ".env.example", repo / "env.example")
    shutil.copyfile(ROOT / "compose.yaml", repo / "compose.yaml")
    references = ["", "${DB_PASSWORD}", '"${{ secrets.DB_PASSWORD }}"', "<set locally>"]
    (repo / "settings.env").write_text(
        "".join(f"DB_PASSWORD={value}\n" for value in references), encoding="utf-8"
    )
    git(repo, "add", ".")

    assert scan(repo, "staged").returncode == 0


@pytest.mark.parametrize("base_kind", ["valid", "empty", "zero", "unavailable"])
def test_committed_then_deleted_secret_is_detected(repo, base_kind):
    base = git(repo, "rev-parse", "HEAD")
    key = "RUSTFS_SECRET_KEY"
    (repo / "accidental.env").write_text(
        f"{key}=fixture-weak123\n", encoding="utf-8"
    )
    leaked_commit = commit(repo)
    (repo / "accidental.env").unlink()
    head = commit(repo)
    base = {"valid": base, "empty": "", "zero": "0" * 40, "unavailable": "f" * 40}[base_kind]

    result = scan(repo, "changes", base, head)

    assert result.returncode == 1
    assert "cityflow-rustfs-credentials" in result.stdout
    # A later clean range excludes the old introduction; history still finds it.
    assert scan(repo, "changes", leaked_commit, head).returncode == 0
    assert scan(repo, "history").returncode == 1


def test_history_includes_other_branches(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "-qc", "old-branch")
    key = "RUSTFS_ACCESS_KEY"
    (repo / "settings.env").write_text(
        f"{key}=fixture-local\n", encoding="utf-8"
    )
    commit(repo)
    git(repo, "switch", "-q", "main")

    assert scan(repo, "changes", base, "HEAD").returncode == 0
    assert scan(repo, "history").returncode == 1


def test_merge_resolution_is_scanned(repo):
    git(repo, "switch", "-qc", "feature")
    (repo / "feature.txt").write_text("Clean feature\n", encoding="utf-8")
    commit(repo)
    git(repo, "switch", "-q", "main")
    git(repo, "merge", "--no-ff", "--no-commit", "feature")
    key = "DB_PASSWORD"
    (repo / "settings.env").write_text(
        f"{key}=fixture-merge123\n", encoding="utf-8"
    )
    head = commit(repo)

    assert scan(repo, "changes", "HEAD^1", head).returncode == 1


def test_shallow_history_and_invalid_head_fail(repo, tmp_path):
    clone = tmp_path / "shallow"
    git(repo, "clone", "-q", "--depth=1", repo.as_uri(), str(clone))

    result = scan(clone, "history")

    assert result.returncode == 2
    assert "requires full Git history" in result.stderr
    assert scan(repo, "changes", "HEAD", "missing-head").returncode != 0
