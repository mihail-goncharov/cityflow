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
On a Pull Request to `main` it executes repository sanity checks. Python quality
gates become mandatory once `pyproject.toml` and `uv.lock` are present (and
Ruff, mypy, pytest and pytest-cov are declared as project development dependencies).

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
uv sync --locked --python 3.13 --group ci
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
