# External scientific integrations

Core installation and tests do not require these tools. They are deliberately separate from the base package.

## pycytominer

The upstream README used branch `issues/440`. The immutable revision inspected on 2026-10-15 is `06fd80a98c7273e7f5be5db31bfac707bb40b6bb`:

```bash
python -m pip install -r requirements/profiles-fork.txt
```

The standard `profiles` extra installs the published package; use the requirements file to reproduce the original fork-specific behavior. Do not mix this fork with an unverified version in the same experiment.

## micro-sam

The upstream README used branch `loaddata_updated`. The immutable revision inspected on 2026-10-15 is `d5e1aaeaa57ec70f289e0972301157bac033c1ce`:

```bash
conda activate sam
python -m pip install -r requirements/microsam-fork.txt
```

Prepare a compatible micro-sam environment with its required PyTorch/GPU dependencies first, following that repository's installation guide. Model weights must be obtained and validated separately.

These files pin source revisions, not transitive dependencies, CUDA drivers, plugins or model checkpoints. Neither fork was executed against laboratory images as part of the maintenance changes. Archive a verified platform lock and model/pipeline checksums with each experiment.
