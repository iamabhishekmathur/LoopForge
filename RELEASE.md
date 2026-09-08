# Release Checklist

1. Run `pytest`.
2. Run `python -m loopforge schemas validate`.
3. Run `python -m loopforge demo --path /tmp/loopforge-demo --force`.
4. Run `python -m loopforge readiness` inside `/tmp/loopforge-demo`.
5. Run `python -m loopforge refinements preview REFINE-0001-0001` inside `/tmp/loopforge-demo`.
6. Run `python -m loopforge redact preview` inside `/tmp/loopforge-demo`.
7. Run `python -m build --no-isolation`.
8. Tag the release, for example `v0.1.0`.
9. Use the release workflow to build distribution artifacts.
10. Publish to PyPI when project ownership and package credentials are ready.
