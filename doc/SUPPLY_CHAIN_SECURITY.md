# FamilyBot Supply Chain Security

This document explains the supply chain security protections implemented in FamilyBot, based on the [LiteLLM supply chain attack](https://pydevtools.com/blog/litellm-supply-chain-attack-and-securing-python-dependencies/) incident and [Bernát Gábor's guide to securing the Python supply chain](https://bernat.tech/posts/securing-python-supply-chain/).

## Why This Matters

On March 24, 2026, malicious versions of the popular `litellm` package (versions 1.82.7 and 1.82.8) were uploaded directly to PyPI by a compromised maintainer account. The malware:

- Harvested SSH keys, cloud credentials, database passwords, and crypto wallets
- Exfiltrated sensitive data to external servers
- Attempted to create persistent backdoors in Kubernetes clusters

This could happen to **any** Python package, including FamilyBot's dependencies. Defense-in-depth is essential.

## Security Layers Implemented

### 1. Hash-Pinned Lockfile (✅ Implemented)

**File:** `requirements-hashes.txt`

Every dependency is pinned to an exact version with its SHA256 hash. This protects against:

- **Tampering in transit** (MITM attacks)
- **Cache poisoning** on shared systems
- **Mirror compromises**

**Does NOT protect against:** Legitimate PyPI uploads of malicious code (but narrows attack surface significantly)

#### Generate or update the hash-pinned lockfile

```bash
just lock-hashes
```

Or manually:

```bash
uv pip compile pyproject.toml --extra dev --generate-hashes -o requirements-hashes.txt
```

#### Install with hash verification

```bash
uv pip install -r requirements-hashes.txt
```

The installer will verify every package matches its hash at install time.

### 2. Ruff Security Linting (✅ Implemented)

**File:** `pyproject.toml` (Ruff configuration)

Ruff's security rules (S-rules) catch vulnerabilities in **your code**:

- **S105**: Hardcoded passwords/secrets
- **S301**: Unsafe pickle deserialization
- **S608**: SQL injection vulnerabilities
- And 20+ more

#### Run security linting

```bash
just lint          # Runs all linting, including S-rules
ruff check --select S src/ scripts/  # Security rules only
```

#### Pre-commit integration

Security linting runs automatically on every commit via `.pre-commit-config.yaml`.

### 3. Pip-audit for Vulnerability Scanning (✅ Implemented)

**Database:** OSV (Open Source Vulnerabilities)

Checks your entire dependency tree against the OSV database for known CVEs.

#### Run pip-audit

```bash
just audit             # Against requirements.txt
just audit-hashes      # Against requirements-hashes.txt (recommended)
```

#### In CI/CD

GitHub Actions runs pip-audit automatically on every push and pull request. When a new CVE is disclosed, pip-audit will catch it within hours.

### 4. GitHub Actions Security Workflow (✅ Implemented)

**File:** `.github/workflows/security.yml`

Automated security scanning runs:

- **On every push** to main/develop
- **On every pull request**
- **Daily at 2 AM UTC** (to catch new CVEs)

The workflow:

1. Verifies lockfile contains hashes
2. Installs dependencies from `requirements-hashes.txt` with hash verification
3. Runs Ruff security linting
4. Runs pip-audit against OSV database
5. Generates CycloneDX SBOM (Software Bill of Materials)
6. Posts results to pull requests

#### View results

Go to the "Actions" tab in your GitHub repository to see runs and results.

### 5. Supply Bill of Materials (SBOM) (✅ Implemented)

**Format:** CycloneDX (machine-readable)

After a supply chain incident is disclosed, you need to answer "are we affected?" within minutes, not hours.

The SBOM generated in CI lists every dependency, making this trivial.

#### Generate locally

```bash
uv run pip-audit -r requirements-hashes.txt --format cyclonedx --output sbom.xml
```

#### Download from CI

1. Go to a GitHub Actions run
2. Download the "sbom" artifact
3. Search for the affected package

Example: After a hypothetical "requests" vulnerability:

```bash
grep -i "requests" sbom.xml
```

### 6. Time-Based Installation Constraints (✅ Implemented)

**PEP:** [PEP 751](https://peps.python.org/pep-0751/) (uv implementation)

Limit installations to packages published before a specific date. Most malware is caught by the community within 24-72 hours, so a 7-day buffer acts as a temporary quarantine window that delays adoption of very recent publishes while allowing legitimate updates.

#### Install with 7-day buffer

```bash
just install-safe 7
```

This installs packages published at least 7 days ago, providing a temporary safety window against fresh compromises. Note: Once a release ages past the cutoff date, it becomes eligible for installation again (unless the lockfile is rotated or dependencies are updated). If a release is suspected of being malicious, follow up with lockfile rotation or package pinning to prevent future adoption.

#### Manual approach

```bash
uv pip install --exclude-newer 2026-03-28 -r requirements-hashes.txt
```

The date is automatically calculated from "7 days ago."

#### Why this works

1. **March 24, 2026**: LiteLLM malicious versions uploaded
2. **March 24 (hours later)**: Discovered via automated scanning
3. **March 25**: Security advisory published
4. **March 26**: pip-audit and GitHub advisories updated
5. **With 7-day buffer on March 31**: Cutoff is March 24; packages from March 24 and earlier are eligible for installation

## Defense-in-Depth Strategy

| Layer | Protects Against | Implementation |
| ----- | --------------- | --------------- |
| **Hash pinning** | Transit tampering, cache poisoning | `requirements-hashes.txt` |
| **Ruff security** | Vulnerabilities in our code | `pyproject.toml` [tool.ruff.lint] |
| **Pip-audit** | Known CVEs in dependencies | Pre-commit + CI/CD |
| **SBOM** | Slow incident response | CycloneDX in CI artifacts |
| **Time-based constraints** | Fresh compromises | `--exclude-newer` flag |
| **Pre-commit hooks** | Local developer errors (can be bypassed) | `.pre-commit-config.yaml` - Enforced via CI/branch-protection |
| **GitHub Actions** | Manual review gaps | `.github/workflows/security.yml` |

## Release Process Best Practices

When releasing FamilyBot:

### 1. Update lockfile before release

```bash
just lock-hashes
```

### 2. Verify security checks pass

```bash
just check              # Runs lint, format, type-check, audit-hashes, check-toml
just audit-hashes       # Explicitly check hash-pinned lockfile
```

### 3. Commit the hash-pinned lockfile

```bash
git add requirements-hashes.txt
git commit -m "chore: update hash-pinned dependencies for release"
```

### 4. Tag the release

```bash
git tag -a v2.11.2 -m "Release 2.11.2 with supply chain security hardening"
```

GitHub Actions will automatically run security checks and publish artifacts.

## What to Do When a Vulnerability is Announced

### Immediate (minutes)

1. **Check the SBOM:**
   - Is FamilyBot affected? Search the latest SBOM artifact from CI
   - If NO → No action needed

2. **If affected, check the version:**
   - Is the vulnerable version in `requirements-hashes.txt`?
   - If NO → You're protected by pinning to an older version

### Short-term (hours)

1. **Update the vulnerable package:**

   ```bash
   # Update pyproject.toml dependency version
   # Then regenerate lockfile:
   just lock-hashes
   ```

2. **Run security checks:**

   ```bash
   just check
   just audit-hashes
   ```

3. **Commit and push:**

   ```bash
   git commit -am "fix: update vulnerable dependency"
   git push
   ```

4. **Review GitHub Actions results** to confirm fix

## Ongoing Maintenance

### Weekly

- Review any GitHub security alerts in your repository settings
- Check pip-audit results from the daily scheduled CI run

### Monthly

- Run `just check-updates` to see if newer versions are available
- Review new Ruff rule releases (included in `pyproject.toml`)

### Quarterly

- Regenerate hash-pinned lockfile with current ecosystem state:

  ```bash
  just lock-hashes
  ```

- Audit any dependencies for deprecation notices

## Tools Reference

### Commands for Daily Use

```bash
# Check current security status
just security-status

# Run security linting only
ruff check --select S src/ scripts/

# Audit dependencies for CVEs
just audit-hashes

# Regenerate hash-pinned lockfile
just lock-hashes

# Install with time-based constraints
just install-safe 7

# Run all quality checks (including security)
just check
```

### Files to Monitor

- `pyproject.toml` - Dependency versions and Ruff config
- `requirements-hashes.txt` - Hash-pinned lockfile (commit to git)
- `requirements.txt` - Standard lockfile (optional, for CI caching)
- `.pre-commit-config.yaml` - Pre-commit hooks including security
- `.github/workflows/security.yml` - Automated GitHub Actions
- `.pylintrc` - Additional linting rules (legacy, being phased out)
- `.ruff.toml` - Ruff configuration (if separated from pyproject.toml)

## Further Reading

- [Securing the Python Supply Chain](https://bernat.tech/posts/securing-python-supply-chain/) - Bernát Gábor (the definitive guide)
- [LiteLLM Supply Chain Attack](https://futuresearch.ai/blog/litellm-pypi-supply-chain-attack/) - Technical breakdown
- [PEP 751: Lockfile Specification](https://peps.python.org/pep-0751/) - Future of Python lockfiles
- [OSV Database](https://osv.dev/) - The vulnerability database pip-audit queries
- [uv Documentation](https://docs.astral.sh/uv/) - Modern Python packaging

## Questions?

If you have questions about FamilyBot's security posture, file an issue on GitHub with the `security` label.

---

**Last updated:** April 5, 2026
**Based on:** LiteLLM attack incident (March 24, 2026)
**Maintained by:** FamilyBot maintainers
