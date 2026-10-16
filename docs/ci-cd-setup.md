# CityFlow CI/CD setup

This setup targets Forgejo 17.0 and Runner 13.2, a dedicated CI Runner VM 111,
and a separate CityFlow VM 110.

## Prerequisites

- Forgejo repository `mentorship/cityflow`, Actions enabled.
- Dedicated CI VM 111: Ubuntu 24.04, 2 vCPU, 2 GB RAM, 30 GB SSD, Tailscale + Docker.
- Forgejo Runner installed on VM 111 and registered **only for this repository**.
- Runner label: `cityflow-ci:docker://docker.io/library/node:22-bookworm`.
- Runner capacity: `1`; job containers must **not** receive `/var/run/docker.sock`.
- Runner VM can reach `https://forgejo.tailfe5b25.ts.net/`.

## Runner registration on Forgejo 17

Open repository Settings > Actions > Runners > Create new runner.
Record the UUID and TOKEN **privately**. Generate a runner configuration with
`forgejo-runner generate-config` and edit the generated file **on VM 111**, not in Git:

```yaml
runner:
  capacity: 1
  labels:
    - cityflow-ci:docker://docker.io/library/node:22-bookworm
server:
  connections:
    cityflow:
      url: https://forgejo.tailfe5b25.ts.net/
      uuid: REPLACE_FROM_FORGEJO_UI
      token: REPLACE_FROM_FORGEJO_UI
container:
  docker_host: "-"
  privileged: false
  options: "--memory=1536m --cpus=2"
```

If editing a generated config, update the existing sections rather than duplicating them.
The runner Linux user may need access to the Docker socket on **VM 111** only.
Do not install a runner on the Forgejo server or Proxmox host.

## First run (CI only)

The workflow file is `.forgejo/workflows/ci-cd.yml`.
On a Pull Request to `main` it executes repository sanity checks and Gitleaks.
Python quality gates become mandatory once `pyproject.toml` is present (with
Ruff, mypy, pip-audit, pytest and pytest-cov declared as project development
dependencies).
A missing `uv.lock` fails CI.

Before installing dependencies, CI runs `uv lock --check` to verify that
`uv.lock` matches `pyproject.toml`. Installation uses `uv sync --locked`, and
the audit and quality tools run with `uv run --no-sync` against that environment.
A stale lockfile fails CI instead of being updated. After intentionally changing
dependencies, run `uv lock` locally and commit `pyproject.toml` and `uv.lock`
together. See [uv's lockfile checks](https://docs.astral.sh/uv/concepts/projects/sync/#checking-the-lockfile).

Ruff keeps its default checks and adds the flake8-bandit security rules (`S`);
only `S101` is disabled for pytest assertions under `tests/`. Mypy checks
`src/cityflow`, including the bodies of functions without annotations. It detects
incompatible argument and return types, unhandled `None` and invalid interface
usage where type information is available. Notebooks are outside the initial
type-checking scope. Both tools read their configuration from `pyproject.toml`.

CI installs the `ci` dependency group and selects Polars' CPU compatibility
runtime with `POLARS_FORCE_PKG=compat`. The runner VM may not expose the CPU
instructions required by the standard runtime, which can cause an
`Illegal instruction` crash during test collection. The compatibility runtime
is provided by [`polars[rtcompat]`](https://docs.pola.rs/user-guide/installation/#legacy-cpu).
To run the same checks locally:

```bash
uv lock --check --python 3.13
uv sync --locked --python 3.13 --group ci
bash infra/scripts/audit-dependencies.sh
uv run --no-sync ruff check .
uv run --no-sync mypy
POLARS_FORCE_PKG=compat uv run --no-sync pytest -q
```

Pytest reads its coverage options from `pyproject.toml`: it measures statements
and branches across `cityflow`, prints missing lines, and requires at least 80%
combined coverage. It saves `coverage.xml` and the HTML report in `htmlcov/`.
Tests use synthetic data and temporary files, so no raw dataset is needed.

In CI, pytest also appends a Markdown coverage table to `FORGEJO_STEP_SUMMARY`.
Open the `ci` job in a workflow run to see the **Coverage** summary above its
logs, with a row for each file and totals for statements, branches and missing
coverage. This requires Forgejo 17+ and Runner 13.2+. The table is generated
when tests finish, including ordinary test failures or a failed coverage
threshold; failures before pytest starts do not produce a coverage table.
See [Forgejo job summaries](https://forgejo.org/docs/v17.0/user/actions/advanced-features/#job-summaries).

The final CI step uploads both reports as the `coverage` artifact with 14-day
retention. `always()` preserves reports after test failures too; if an earlier
installation or lint step fails before pytest runs, no reports are available
and the upload step emits a warning. Download the artifact from the workflow
run page and open `htmlcov/index.html` to inspect uncovered lines and branches.
The workflow uses upload-artifact v3 for
[Forgejo compatibility](https://forgejo.org/docs/latest/user/actions/advanced-features/#artifacts).

Until CD prerequisites below are complete, **leave ENABLE_DEPLOY unset**.
The deploy job then skips and no SSH secret is required.

## Python dependency audit with pip-audit

After installing the locked dependencies, CI runs
`bash infra/scripts/audit-dependencies.sh` in its own **Python dependency audit
(pip-audit)** step, before Ruff, mypy and pytest. Vulnerabilities or audit errors
fail the `ci` job, which the deploy job requires. Ruff's `S` rules inspect source
code and do not check dependency versions for known vulnerabilities.

The script uses `uv export --locked --all-groups --no-emit-project`
to create a temporary requirements file from `uv.lock`. It includes direct and
transitive dependencies, development tools, the auditor itself and the `ci`
group. Environment markers select packages for the current Python version and
platform (Python 3.13 on Linux in CI). It does not audit every platform/Python
combination in the universal lockfile. Only the local CityFlow project is
excluded from the export; it is not a published third-party package.

`pip-audit` uses `--require-hashes --disable-pip` because uv has already resolved,
pinned and recorded hashes for the full dependency graph. No second resolution
or package installation is needed for the audit. `--strict` fails if a dependency
cannot be collected or checked, so an incomplete audit is not reported as clean. The temporary
requirements file is removed on exit and is not committed.

Install tools with `uv sync --locked --group ci`, then run the same script
locally. The report appears in the terminal/CI log with affected packages,
vulnerability IDs, CVE/GHSA aliases where available and fixed versions.
The runner needs outbound HTTPS access to PyPI for current advisory data.
See the [pip-audit documentation](https://github.com/pypa/pip-audit#usage).

For a finding, review the advisory and upgrade the affected dependency to a
fixed version, using `uv lock --upgrade-package PACKAGE` where the declared
constraints allow it. For a transitive dependency, its parent may also need
an upgrade. Update `pyproject.toml` constraints if needed, commit the updated
lockfile and rerun the audit and quality checks. The script does not apply
automatic fixes or ignore vulnerabilities.

## Secret scanning with Gitleaks

The main CI job checks all commits introduced by a PR (`base..head`) or a push
to `main` (`before..after`), before installing Python dependencies. It scans
commit patches, so adding a secret and removing it in a later commit still
fails CI. Merge resolutions are included. The deploy job already requires
this CI job, so a finding or scanner/install error blocks deployment.

Both workflows fetch full history (`fetch-depth: 0`). If a push has no base
commit (for example, a new branch or an unavailable commit after a force push),
the scan falls back to all fetched history. Shallow clones fail explicitly
rather than returning an incomplete clean result.

`.forgejo/workflows/gitleaks-history.yml` scans all fetched branches and tags
every Monday at 06:00 in `Europe/Chisinau`, and supports **Run workflow** in
Forgejo Actions. The schedule is registered only after the workflow reaches
the default branch; see the [Forgejo schedule reference](https://forgejo.org/docs/v17.0/user/actions/reference/#onschedule).
Unreachable commits and deleted remote refs are outside the fetched history.

`infra/scripts/install-gitleaks.sh` pins **Gitleaks 8.30.1** and verifies the
archive against a checked-in SHA-256 before extraction. It supports Linux and
macOS on x64/ARM64 and needs no Docker socket, root installation or license
secret. The runner needs HTTPS access to GitHub release downloads. When
upgrading, update the version and all four checksums from the
[official release](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1).

`.gitleaks.toml` extends the [built-in Gitleaks rules](https://github.com/gitleaks/gitleaks/tree/v8.30.1/config)
for private keys and provider/generic API tokens. Extra rules catch literal
password assignments and `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` assignments
without an entropy threshold. Empty values, `${VARIABLE}` / `${{ secrets.NAME }}`
references and `<placeholder>` values do not match these project rules. The
only project allowlist is the exact commented `cityflow-local` username example
in `.env.example` (formerly `env.example`), including its historical commits.
The rest of that file is still scanned. Gitleaks detects patterns, so a clean
scan is not proof that no secret exists.

### Local scans

Install the pinned version from the repository root, keeping it outside Git:

```bash
bash infra/scripts/install-gitleaks.sh "$PWD/.local/bin"
export PATH="$PWD/.local/bin:$PATH"

# Check the index after git add, before committing.
bash infra/scripts/scan-secrets.sh staged

# Check all commits introduced by the current branch.
bash infra/scripts/scan-secrets.sh changes main HEAD

# Fetch current remote refs, then check all available history.
git fetch --all --tags --prune
bash infra/scripts/scan-secrets.sh history
```

For a shallow clone, first run `git fetch --unshallow --tags`. Local staged
scans check only the index and do not require full history. No Git hook is
installed automatically.

`uv run pytest -q` also runs integration checks against temporary Git repos
when Gitleaks is on `PATH` (otherwise those checks are skipped). CI installs
Gitleaks first, so these checks run there. They cover built-in token/SSH rules,
project credentials, redaction, safe templates, deleted secrets, merge
resolutions, other branches, missing base commits and shallow-clone failures.

All scan modes use `--redact=100`; logs show the rule, file, line and commit
without printing the secret value. No secret report is uploaded as an artifact.
If a real secret is found, revoke or rotate it first, remove the literal from
code, and use local environment variables or Forgejo Secrets. Deleting the
current file does not remove the secret from Git history. For a verified false
positive, add a narrowly scoped rule-specific allowlist with a reason; do not
exclude whole configuration files or baseline all existing findings.

## Enable deployment later

1. Protect `main`: only maintainers merge reviewed PRs; require passing CI.
2. Create a dedicated deploy SSH key (no passphrase for automation). Add its
   public key to `/home/alex/.ssh/authorized_keys` on VM 110, *not* Forgejo.
   The private key has powerful access on VM 110. Never give it to students.
3. On VM 110 verify the SSH **host** public key fingerprint locally:
   `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`.
4. Obtain an SSH `known_hosts` entry for VM 110 using `ssh-keyscan` on VM 111;
   verify it against the fingerprint from step 3 before trusting it.
5. In Forgejo repo Settings > Actions > Secrets set:
   - `DEPLOY_SSH_PRIVATE_KEY`: contents of the deploy private key.
   - `DEPLOY_KNOWN_HOSTS`: verified host key entry for the Tailscale IP.
6. In Actions > Variables set:
   - `DEPLOY_HOST`: VM 110 Tailscale IPv4 (100.x.x.x).
   - `ENABLE_DEPLOY`: `true`.
7. Confirm `infra/scripts/deploy.sh` exists on VM 110, and the `alex` account
   can `git fetch` with its own SSH key and run `docker compose`.
8. Test a reviewed PR to `main` and confirm deploy logs in Actions.

The deployment uses `git merge --ff-only` on VM 110 and reconciles RustFS using
`docker compose up -d --no-deps rustfs`. Existing data remains mounted via
`CITYFLOW_DATA_DIR` outside the repository. This is a homelab pattern, not
HA, and it must be combined with backups and tested restore.

Security: workflow authors can execute code. A runner with access to the Docker
socket or privileged containers is effectively root on its host; isolate it.
The CD key to `alex` has broad permissions on VM 110, so protect `main`, do not
make deployment available from PR runs, and plan a least-privilege deploy
account/forced command as a future hardening step.
