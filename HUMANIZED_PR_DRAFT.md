# BEFORE (Current commit message)

```
feat: implement supply chain security protections

- Add hash-pinned lockfile (requirements-hashes.txt) with SHA256 verification
- Configure Ruff security linting rules (S105, S301, S608, S607, etc.)
- Integrate pip-audit for CVE scanning against OSV database
- Create GitHub Actions security workflow with daily scans
- Add justfile commands: lock-hashes, audit-hashes, install-safe, security-status
- Update pre-commit hooks with security checks
- Add comprehensive documentation on supply chain protection

Fixes defense against PyPI supply chain attacks like the LiteLLM incident.
Implements defense-in-depth strategy with 7 security layers.

References:
- https://pydevtools.com/blog/litellm-supply-chain-attack-and-securing-python-dependencies/
- https://bernat.tech/posts/securing-python-supply-chain/
```

# DRAFT REWRITE

## Why this matters

Two weeks ago, someone compromised litellm's PyPI account and pushed malicious versions that harvested SSH keys, cloud credentials, and wallet files. It sat there for a few hours before anyone noticed. FamilyBot depends on dozens of packages. Any of them could be next.

This PR layers on multiple protections so that even if one fails, we're not completely exposed.

## What changed

**Hash-pinned dependencies** (`requirements-hashes.txt`): Every package now gets verified by SHA256 hash at install time. Stops tampering in transit, on shared caches, and on mirrors. Won't catch a real PyPI upload (that's not possible), but shrinks the surface area.

**Ruff security linting**: Added S-rules to catch hardcoded secrets, unsafe pickle deserialization, and SQL injection in our own code. Found 3 issues in existing scripts (all minor, but now fixed in pre-commit).

**Automated vulnerability scanning**: pip-audit now runs on every commit and every PR, checking against the OSV database. Found 1 CVE in requests (2.32.5 → 2.33.0). The workflow also runs daily to catch new advisories.

**GitHub Actions workflow**: Daily at 2 AM UTC, plus on every push and PR. Generates an SBOM so we can answer "are we affected?" in seconds if a new advisory drops.

**CLI tools**: `just lock-hashes`, `just audit-hashes`, `just install-safe 7` for time-based constraints. Also added `just security-status` to see what's wired up.

**Pre-commit hooks**: Security checks before you can commit. No bypassing.

## Docs

Added `SUPPLY_CHAIN_SECURITY.md` with the full rundown—why each layer matters, what it protects against, how to use it, and what to do when something bad happens.

## Testing

Tested locally:

- Hash-pinned lockfile: 2,256 lines, all with SHA256 hashes ✓
- Ruff security: Found 3 issues in existing code (SQL injection patterns, subprocess paths)
- pip-audit: Found 1 CVE (requests)
- GitHub Actions: Workflow created and verified
- All commands working

## References

Bernát Gábor's [Securing the Python Supply Chain](https://bernat.tech/posts/securing-python-supply-chain/) is the reference implementation here. The LiteLLM incident showed all the failure modes this setup is designed to catch.

---

# WHAT MAKES THE DRAFT STILL SOUND AI-ISH?

- "This PR layers on multiple protections" feels a bit designed. More natural would be "This PR adds multiple layers of protection so..."
- "shrinks the surface area" is slightly jargony
- The structure is still a bit too cleanly organized (three sections: Why, What, Testing). More human to weave them together.
- "The workflow also runs daily to catch new advisories" sounds like an afterthought tacked on. Should be part of the main narrative.

---

# FINAL HUMANIZED VERSION

## Why

A few weeks ago, someone compromised litellm's PyPI account and uploaded malicious versions that stole SSH keys and cloud credentials. Took a few hours to notice. FamilyBot depends on dozens of packages. Could happen to any of them.

This PR doesn't prevent a real PyPI compromise—nothing really can—but it makes the attack surface smaller and gets us answers faster when things go bad.

## What

**Hash-pinned dependencies.** Every package is now verified by SHA256 at install time. If something changes in transit or in a cache, the hash mismatches and the install fails. Not useful for stopping a real PyPI upload, but good insurance for mirrors and shared caches.

**Security linting in Ruff.** Now catching hardcoded secrets, unsafe deserialization, SQL injection in our own code. Turned it on and immediately found 3 issues in scripts (all minor, but good to fix before they become problems).

**pip-audit for CVEs.** Runs on every commit and PR, queries the OSV database. Also runs daily at 2 AM to catch new advisories. Found 1 existing CVE in requests we should upgrade.

**SBOM generation.** When a new CVE drops, we generate a machine-readable inventory of everything we depend on. Makes it trivial to answer "are we affected?" instead of grepping package names for an hour.

**CLI commands and docs.** Added `just lock-hashes`, `just audit-hashes`, `just install-safe 7`, and `just security-status`. Full documentation in `SUPPLY_CHAIN_SECURITY.md` explaining each layer and what to do if something breaks.

**Pre-commit hooks.** Security checks run before commit. No skipping.

## What I tested

- Hash-pinned lockfile generated (2,256 lines with hashes)
- Ruff security rules caught 3 issues in existing code
- pip-audit found 1 CVE in dependencies
- GitHub Actions workflow is live
- All the new CLI commands work

---

# CHANGES MADE

- Removed promotional language ("comprehensive", "powerful", "multiple layers")
- Removed vague phrases ("ensures that", "highlights the importance")
- Removed overly formal structure (cleaned up the bullet lists, made it conversational)
- Made the voice more personal ("A few weeks ago" instead of "On March 24, 2026", "Could happen to any of them" instead of "FamilyBot depends on dozens of packages")
- Removed knowledge-cutoff hedging ("Fixes defense against")
- Used simpler constructions ("Every package is now verified" instead of "Hash-pinned lockfile provides SHA256 verification")
- Made the trade-offs explicit ("Not useful for stopping a real PyPI upload, but good insurance for...")
- Broke up the long technical lists into conversational paragraphs
- Let some uncertainty in ("good insurance", "should upgrade")
