# macOS, Windows and Linux

Version 1.2 provides one Python package for all three operating systems. You do not need a separate codebase or installer binary for each OS.

## What is covered

| Component | Linux | macOS (Intel / Apple Silicon) | Native Windows |
| --- | --- | --- | --- |
| Package installation, CLI, configuration and diagnostics | Native CI | Native CI on both architectures | Native CI |
| Image metadata, synthetic TIFF example, SQLite ingestion and keyed joins | Native CI | Native CI | Native CI |
| Wheel build and installation outside the source checkout | Native CI | Native CI | Native CI |
| pycytominer profiles and report extras | Install separately; validate your experiment | Install separately; validate your experiment | Install separately; validate your experiment |
| CellProfiler 4.2.8 / plugins / Cellpose | Separate verified environment required | Tool/plugin/architecture compatibility must be checked | WSL2 recommended for the original scientific stack; native installations require validation |
| micro-sam segmentation | CPU or compatible CUDA environment | CPU; MPS depends on the specific model and dependency stack | CPU or compatible CUDA environment; WSL2 is another option |

CI does not install CellProfiler, CUDA, micro-sam models or report extras. Passing core tests does not certify biological accuracy or GPU/model compatibility.

## macOS

Install a supported Python (3.9+; 3.12 is a practical starting point) and Git, then in Terminal:

```bash
git clone https://github.com/cmpela/imagemorphflow.git
cd imagemorphflow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
imf doctor
python examples/synthetic/run_demo.py --output demo-output
```

On Apple Silicon, use a native arm64 Python and compatible dependencies within the same environment. An Intel scientific tool may require a separate x86_64/Rosetta environment; do not mix incompatible architectures. A Mac GPU is not a CUDA device. Start with `segmentation_device: "cpu"`; use `"mps"` only after confirming the model supports it.

## Windows (PowerShell)

Install Python and Git, then:

```powershell
git clone https://github.com/cmpela/imagemorphflow.git
cd imagemorphflow
py -3.12 -m venv .venv
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\imf.exe doctor
.\.venv\Scripts\python.exe examples\synthetic\run_demo.py --output demo-output
```

These commands use the environment executables directly and do not require changing PowerShell's execution policy or running as administrator. If you activate the environment in a normal permitted shell, `imf` also works directly.

Use forward slashes in JSON/YAML Windows paths, for example `C:/Users/Ana/projects/demo`. Backslashes in JSON must be escaped. Spaces and Unicode in native paths are covered by the tests. Configurations point to local OS paths: do not reuse `C:/...` paths inside WSL2 without translating them to `/mnt/c/...`.

For the original Linux scientific stack, install WSL2 with Ubuntu, clone the repository inside WSL2, and follow the Linux commands there. Treat native Windows and WSL2 as different Python/Conda environments. WSL2 GPU access still needs a compatible device and driver.

## Linux

```bash
git clone https://github.com/cmpela/imagemorphflow.git
cd imagemorphflow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
imf doctor
python examples/synthetic/run_demo.py --output demo-output
```

Install your microscope-processing tools separately, then use `imf doctor --config /path/to/config.yaml` to inspect resolved settings. Use your institution's verified CellProfiler/plugin and GPU environment.

## Image access without symlink privileges

`image_link_mode` controls how generated load-data CSVs refer to images:

- `auto` (default): use a directory symlink when allowed; if the OS denies symlink privileges, reference the source directory directly. Existing real directories are preserved.
- `reference`: always reference the original image directory; no symlinks or duplicate dataset storage are needed.
- `symlink`: require symlinks and report permission errors instead of falling back.

Source images must remain accessible while the experiment runs. Load-data CSVs record the actual path, so mask prediction and plate overview use the same image location. `copy_to_scratch` remains a separate, explicitly configured dataset copy.

The small `latest_<step>.yaml` aliases use atomic file copies if symlinks are unavailable. Dated effective configs and manifest snapshots remain available in both modes.

## Conda and segmentation

By default, external tools use Conda from `CONDA_EXE` or PATH. You can set `conda_executable` to an absolute executable path. On Windows use the real `Scripts/conda.exe`, not a `.bat` or `.cmd` wrapper. A Conda/Miniforge prompt normally defines `CONDA_EXE` for you.

```yaml
conda_executable: null
cellprofiler_env: cellprofiler4
sam_env: sam
segmentation_device: cpu
mask_workers: 1
```

`segmentation_device` accepts `auto`, `cpu`, `cuda` or `mps`. `auto` delegates selection to micro-sam; other values are forwarded as `--device`. This selects a backend, not an installation or compatibility guarantee. Explicit CPU mode is useful when no supported GPU is available and can be substantially slower.

The `doctor` command reports platform, Python, installed core package versions, Conda availability, image access mode and requested segmentation backend. It does not install external tools, download weights or claim that a Conda environment/model is valid.

## Example manifests and checks

Start from `examples/manifests/windows.json`, `macos.json` or `linux.json` and replace the image directory with your real acquisition path. All examples disable mask prediction. Supply your own validated CellProfiler `.cppipe` files before running scientific analysis.

```bash
imf run --manifest examples/manifests/macos.json --dry-run
```

Run `pip install -e '.[dev]'` and `python -m unittest discover -s tests -v` for development. PowerShell users can use `.venv\Scripts\python.exe` instead of activating the environment. The CI matrix checks Python 3.12 on all platforms and Python 3.9 on Linux/Windows, plus a separate Intel macOS job.
