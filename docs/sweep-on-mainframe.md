# Running the sweep on mainframe

The bounded seed sweep (`pytest -m sweep`) renders ~85 lane/seed cases and is
minutes of CPU. On the laptop it pegs a 2C/4T Skylake-U (measured 90 °C with the
fan already at its maximum). Run it on `mainframe` instead.

## Why a container

- `pyproject.toml` pins `requires-python = ">=3.15,<3.16"`.
- mainframe's **host** Python is 3.14.8, so it cannot install this project.
- The `radio-indiegen` runtime image already has Python 3.15 and the
  numpy/scipy/soundfile deps; it just does not ship `tests/` or pytest.

The `sweep` build target (`docker build --target sweep`) is that image plus
`tests/`, `tools/`, and the dev extras (pytest/ruff/mypy), with
`python -m pytest` as its entrypoint.

## Command

From a checkout on mainframe (`/home/kbdejavu/servers/indiegenerator`):

```sh
./scripts/sweep.sh
```

It builds `indiegen-sweep` from that checkout and runs `pytest -q -m sweep`.
Extra arguments are appended, so `./scripts/sweep.sh --collect-only` collects
only, and `./scripts/sweep.sh -k motorik` runs one lane.

Equivalent without the script:

```sh
docker build --target sweep -t indiegen-sweep .
docker run --rm indiegen-sweep -q -m sweep
```

## State ownership

`data/indiegen/state.json` is the seed cursor. It is read and written **only**
by `src/indiegen/serve.py`: no test references it (`grep -rn state.json tests/`
is empty) and the sweep renders in memory. Therefore:

- **The serve loop owns `state.json`.** On the production host that is the
  `radio-indiegen` container on mainframe (`/var/lib/indiegen`).
- **Sweep runs are stateless** and cannot fork the cursor, on any host.
- The throwaway `--rm` container mounts no music or state volumes and does not
  touch the running `radio-indiegen` container.

## The laptop

The laptop path still works (its venv is Python 3.15). It is simply no longer
the default and should not be the documented way to run the sweep.
