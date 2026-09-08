# Release Checklist

1. Run `pytest`.
2. Run `python -m loopforge schemas validate`.
3. Run `python -m build`.
4. Tag the release, for example `v0.1.0`.
5. Use the release workflow to build distribution artifacts.
6. Publish to PyPI when project ownership and package credentials are ready.
