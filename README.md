# ly_python_tools

This package consists of a few executables:

- autoupgrade: A tool that automatically upgrades developer dependencies for a poetry project.
- pyproper: A simple wrapper around pyright that allows for bootstrapping pyright in an easy-to-find location.
- version: Uses configuration to adds CI metadata to python package versions and enforces pep440.

This is pre-alpha quality software. Use at your own risk.

## Tools

### Autoupgrade

The `autoupgrade` tool will update dev-dependencies automatically. This replaces
the process of merging dependabot PRs one at a time. Instead, we would create a
PR where we had run `autoupgrade` and that single PR replaces the individual
dependabot PRs.

By default, it will upgrade everything to the latest available at the time of
running the tool, however additional constraints can be added. Extras for
packages can also be defined. We do not support autoupgrading package
dependencies to latest because that can lead to breakages in APIs.

For example, we can configure the dev-dependencies to ensure pytest is lower
than `7.1.0` and ensure that prospector is installed with all extra tools.

```toml
[tool.autoupgrade.constraints]
pytest = "<7.1.0"

[tool.autoupgrade.extras]
prospector = ["with_everything"]
```

### Pyproper

`pyproper` is a simple wrapper around `pyright`. It's only purpose is to allow
for consistent bootstrapping of `pyright` by ensuring an isolated version of
node is used (via `PYRIGHT_PYTHON_GLOBAL_NODE`) and the project is installed in
a known location (by setting `PYRIGHT_PYTHON_ENV_DIR=$XDG_DATA_HOME/pyright`)

### Version

`version` allows for advanced configuration of the python package version in
CI. This enables including metadata to the python version depending on CI
tags or branches. This also enforces consistent and strict adherence to the
pep440 spec.

Some example use-cases:

- Tag to release rules:

  - Branches matching `^main` and tag matching `^v(.*)$` must also match the project file's version. They are pushed to repo A.
  - Branches matching `^main$` are alpha releases with a number matching the env var `BUILD_NUM`. They are pushed to repo B.
  - Branches not matching `^main$` are development releases with a number matching the env var `BUILD_NUM`. They are pushed to repo B.

## Quickstart

Install the project.

```
poetry install -E prospector -E flake8
```

Bootstrap pyright using pyproper. This will ensure pyright is downloaded

```
poetry run pyproper --bootstrap
```

## Contributing

Contact the author(s) if you want to contribute.

### Circle CI

The pre-commit hooks use the CircleCI config validator. If you edit the CircleCI
config, [install CircleCI cli locally](https://circleci.com/docs/2.0/local-cli/)
so you can validate the config. If you don't have the cli installed, use

```bash
SKIP=circleci-validate git commit ...
```

## Using in a poetry project

Install and use the linters

```
# Install all linters
poetry add --dev ly_python_tools@latest -E prospector -E flake8
# Ensure pyright is downloaded
poetry run pyproper --bootstrap
# Run the linters
poetry run pyproper
```

Upgrade all dev-dependencies

```
poetry run autoupgrade
```

## CI config

```yaml
run: |  # Install step can fail due to network failures.
  poetry install
  poetry run lint --bootstrap
run: |  # Step should only fail due to linting failures.
  poetry run lint src/
```
