# Contributing

Use a branch and a pull request describing the problem, changed behavior and validation. Preserve the BSD license and original authorship.

## Setup and checks

From the repository root, with Python 3.9+:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
ruff check .
python examples/synthetic/run_demo.py --output demo-output
python -m build
python tests/smoke_wheel.py dist/*.whl
```

The initial Ruff policy checks syntax errors, invalid control flow and undefined names across the repository. Broader style rules can be enabled incrementally without mixing wholesale legacy formatting into behavior changes.

## Tests and scientific changes

Add regression tests for changed behavior, using temporary directories and synthetic data. Mock external process boundaries rather than requiring CellProfiler, Conda or GPU models for unit tests. Check failure status as well as successful outputs. Keep tests independent of execution order and the author's home directory.

Changes to segmentation, normalization or aggregation require documented validation with representative data, tool versions and expected results. The synthetic example does not establish biological accuracy. Do not commit private microscopy data or large model weights; document access and checksums for approved datasets instead.

## Releases

Change `imagemorphflow.__version__`, update CHANGELOG and CITATION, pass CI, then tag the reviewed commit. Inspect both wheel and source distribution. The wheel must work outside an editable checkout. Preserve immutable revisions for external forks and archive platform locks for verified scientific environments.
