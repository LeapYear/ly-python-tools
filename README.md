# ly_python_tools

This repo is intended to codify a number of opinionated best-practice approaches
to writing python code.

It consists of a few executables:

- autoupgrade: A tool that automatically upgrades developer dependencies for a poetry project.
- version: Helps enforce pep440 specification for python projects.

and a number of lint and pre-commit configurations that we believe should be
taken as solid recommendations for any python project. Making your project
depend on this package will also install a number of linters out-of-the-box:

- autoflake
- black
- reorder-python-imports
- pyupgrade
- pyright
- flake8 (optional)
- prospector (optional)

however you are expected to configure and run these yourself.

This is pre-alpha quality software. Use at your own risk.

## Quickstart

Install the project with all of the extras.

```bash
poetry install -E prospector -E flake8
```

Install pre-commit and hooks

```bash
poetry run pre-commit install --install-hooks
```

Run the linters

```
poetry run pre-commit run -a
```

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
poetry add --dev ly_python_tools -E prospector -E flake8
# Install the lint hooks
poetry run pre-commit install --install-hooks
# Run all of the linters
poetry run pre-commit run -a
```

Upgrade all dev-dependencies

```
poetry run autoupgrade
```
