# ass-spec

The reference Assayer plugin that reviews Markdown product and software
specifications against the canonical 18-point quality policy.

This is a standalone plugin project. It depends on the Assayer platform
distribution (`assayer`) and does not live inside the Assayer source tree.

## Development

```bash
pip install https://github.com/elioyu-07/Assayer/releases/download/v0.1.1/assayer-0.1.1-py3-none-any.whl
                             # official platform SDK + conformance CLIs
pip install -e .             # this plugin, editable

# validate the plugin against the platform contracts
assayer-plugin-surface-check src
assayer-plugin-check ass_spec:registration
assayer-plugin-package-check .
python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
assayer-plugin-release-check --source . dist/*.whl  # exact-wheel release gate

# run the plugin's own tests
python -m unittest discover -s tests -p 'test_*.py'
```

## Layout

```
src/ass_spec/            # plugin source (imports only the public SDK surface)
tests/                   # plugin behavior + layer-migration equivalence proofs
fixtures/                # deterministic conformance fixtures
assayer-plugin-release.json   # release descriptor
src/ass_spec/semantic-review.md   # packaged Agent decision boundary
```

## Public SDK surface

`ass-spec` imports only names from the Assayer public surface defined in
`assayer_platform.public_surface`. `assayer-plugin-surface-check` fails the
build if the plugin reaches beyond that whitelist, which is what keeps the
platform boundary enforceable for any third-party plugin.

## Versioning

`ass-spec` releases independently of Assayer. Its `pyproject.toml` declares the
supported platform range:

```toml
dependencies = ["assayer>=0.1.1,<0.2.0"]
```

The release check combines source and public-surface validation with exact-wheel
installation, real entry-point loading, deterministic fixtures, and the
installed `assayer.release_acceptance` journey. For strict interactive Checks,
that journey must prove every declared checkpoint collection, finalization,
resume, replay, terminal publication, and the durable ledger. Domain payloads
remain plugin-owned; the platform validates the lifecycle evidence.
