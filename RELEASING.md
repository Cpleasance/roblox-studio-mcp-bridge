# Releasing

Releases are cut by pushing a `v*` tag. `.github/workflows/release.yml` then builds the sdist +
wheel, creates a GitHub Release with checksums, and publishes to PyPI.

## One-time PyPI setup (before the first release)

PyPI publishing uses [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) — no API token
is stored anywhere.

1. Create the project on PyPI (or, for the very first upload, use the *pending publisher* flow so no
   manual upload is needed):
   - Go to <https://pypi.org/manage/account/publishing/>
   - Add a **pending publisher**:
     - PyPI project name: `roblox-studio-mcp-bridge`
     - Owner: `Cpleasance`
     - Repository: `roblox-studio-mcp-bridge`
     - Workflow: `release.yml`
     - Environment: `pypi`
2. In the GitHub repo, create an **Environment** named `pypi`
   (Settings → Environments → New environment). Optionally add a required reviewer so each publish
   is gated by a manual approval.

Until step 1 is done the `pypi-publish` job fails harmlessly on each tag; the GitHub Release still
completes.

## Cutting a release

1. Update `version` in `pyproject.toml` and `__version__` in `roblox_studio_mcp/__init__.py`
   (keep them in sync).
2. Move the `## [Unreleased]` section of `CHANGELOG.md` under a new `## [x.y.z] - YYYY-MM-DD`
   heading; leave a fresh empty `## [Unreleased]`.
3. Commit, then tag and push:
   ```bash
   git commit -am "release: vX.Y.Z"
   git tag vX.Y.Z
   git push && git push --tags
   ```
4. Watch the **Release** workflow. On success: GitHub Release published,
   `roblox-studio-mcp-bridge X.Y.Z` live on PyPI.

## Local build check

```bash
python -m build
python -m twine check dist/*
```
