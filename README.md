# custom-g4ndl-generator

Generate custom [G4NDL](https://geant4.web.cern.ch/) neutron-data libraries in
which the **Ge-76 radiative-capture cross section**
(`Capture/CrossSection/32_76_Germanium`) is scaled and/or replaced with the
n_TOF measurement of Ge-76(n,γ)
([Phys. Rev. C **104**, 044610](https://journals.aps.org/prc/abstract/10.1103/PhysRevC.104.044610)).

These custom libraries are used for Ge-77(m) production studies in LEGEND
(see [legend-simflow#265](https://github.com/legend-exp/legend-simflow/issues/265)).
Only the `32_76_Germanium` capture file is modified; the rest of the library is
copied through unchanged.

## Install

```bash
pip install -e .
```

## Usage

```
custom-g4ndl --source <NAME|URL|dir|tarball> --output DIR [options]
```

The `--source` can be:

* a **G4NDL library name**, downloaded from
  `https://cern.ch/geant4-data/datasets/<NAME>.tar.gz`
  (e.g. `G4NDL.4.5`, `G4NDL.4.7.1`),
* an **IAEA library name**, downloaded from
  `https://nds.iaea.org/geant4/libraries/<NAME>.tar.gz`
  (e.g. `JEFF-3.3`, `ENDF-VIII.0`, `JENDL-4.0u`, `ENDF-B-VIII.1`, `JENDL-5.0`),
* a full `https://…` URL to such a `.tar.gz`,
* a local `.tar.gz` / `.tgz` / `.tar` archive, or
* an already-extracted library **directory**.

Examples:

```bash
# Download JEFF-3.3 from IAEA, apply the default scaling + n_TOF substitution
custom-g4ndl --source JEFF-3.3 --output ./out

# Use a library you already have on disk, custom scale factor
custom-g4ndl --source /data/G4NDL4.7 --output ./out --scale 1.5

# Global scaling only, no substitution
custom-g4ndl --source ENDF-VIII.0 --output ./out --no-substitution

# Supply your own substitution table
custom-g4ndl --source JEFF-3.3 --output ./out --substitution my_xs.dat
```

Each run writes `DIR/<name>/` (the modified library, directly usable by Geant4)
and `DIR/<name>.tar.gz`. Point Geant4 at the directory via the neutron-HP data
environment variable, e.g. `G4NEUTRONHPDATA` / `G4PARTICLEHPDATA`.

### Options

| Option | Description |
| --- | --- |
| `--scale FACTOR` | Global scale factor for σ (default `1.68`). |
| `--substitution FILE` | n_TOF `(E, σ)` table (default: bundled `76GE_XS.dat`). |
| `--no-substitution` | Scale only; skip substitution. |
| `--legacy-energy-shift` | Reproduce the legacy `E/factor` artifact on the below-range tail (energy ÷ factor, σ left unscaled) instead of the default uniform σ scaling (see below). |
| `--base-library SOURCE` | Full G4NDL used to fill in folders a translated library omits (default: a pinned `G4NDL.4.7.1` download). Accepts a dir / `.tar.gz` / IAEA name / G4NDL name / URL, like `--source`. |
| `--allow-incomplete` | Write the library even when the omitted folders cannot be filled in (produces a library Geant4 cannot fully use). |
| `--cache-dir DIR` | Where downloads/extractions are cached. |
| `--rename NAME` | Name of the output library directory. |
| `--no-tarball` | Skip the `.tar.gz`. |
| `--force` | Overwrite an existing output directory. |
| `-v`, `-vv` | More verbose logging. |

## What the adjustment does

With substitution enabled (the default), for scale `factor`:

| energy region | output `(E, σ)` |
| --- | --- |
| `E < E_min` (below the n_TOF range) | `(E, σ × factor)` — see note |
| `E_min ≤ E ≤ E_max` (~0.026 eV – 52 keV) | n_TOF `(E, σ)` (fully replaced) |
| `E > E_max` | `(E, σ × factor)` |

> **Note.** By default σ is scaled uniformly by `factor` and the energy grid is
> left unchanged, matching the current per-library production datasets (e.g.
> `generated_xs/32_76_Germanium_JEFF-3.3_n_TOF_scaled`). Pass
> `--legacy-energy-shift` to instead reproduce an artifact of the original
> `merge_cross_sections.py`: on the below-range tail the energy is divided by
> `factor` and σ is left at its original (unscaled) value — this reproduces the
> older `generated_xs/32_76_Germanium_n_TOF_scaled`.

With `--no-substitution`, every σ is multiplied by `factor` and the energy grid
is left unchanged.

## Completing translated libraries

The IAEA-translated libraries (`JEFF-3.3`, `ENDF-VIII.0`, `JENDL-*`) are
**deliberately incomplete**: they ship only the ENDF-derived reactions
(`Capture`, `Elastic`, `Fission`, `Inelastic`) and, per their own README, must
have four folders overlaid from a full G4NDL distribution before Geant4 can use
them:

* `IsotopeProduction`,
* `JENDL_HE`,
* `ThermalScattering`,
* `Inelastic/Gammas`.

`custom-g4ndl` detects any of these that the source omits and copies them in from
a base G4NDL (`--base-library`, default: a pinned `G4NDL.4.7.1` download).
Existing library data is never overwritten — only the missing folders are filled.
If the folders are missing and no base can supply them, the run aborts
rather than emit a silently-broken library; pass `--allow-incomplete` to override.

```bash
# JEFF-3.3, with the four missing folders overlaid from a G4NDL you have on disk
custom-g4ndl --source JEFF-3.3 --output ./out --base-library /data/G4NDL4.7.1
```

## Workflow: generate a library and load it into Geant4

End-to-end, from a source library to a Geant4 run:

```bash
# 1. Generate. Writes ./out/JEFF-3.3/ (the library) and ./out/JEFF-3.3.tar.gz.
#    --base-library fills in the folders JEFF-3.3 omits (see above); drop it to
#    use the pinned default G4NDL download instead.
custom-g4ndl --source JEFF-3.3 --output ./out --base-library /data/G4NDL4.7.1

# 2. Point Geant4's neutron/particle-HP data at the generated directory.
#    Use an ABSOLUTE path; export it in your shell (or .bashrc, or job script).
export G4NEUTRONHPDATA="$(pwd)/out/JEFF-3.3"
#    Geant4 >= 11 reads the generalized particle-HP variable instead:
export G4PARTICLEHPDATA="$G4NEUTRONHPDATA"

# 3. Run your Geant4 application as usual. It now uses the adjusted Ge-76
#    capture cross section. Sanity-check the variable actually points at a
#    library root (should list Capture/ Elastic/ IsotopeProduction/ ...):
ls "$G4NEUTRONHPDATA"
```

Notes:

* Set the variable to the **library directory** (the one containing `Capture/`),
  not to `./out` and not to the `.tar.gz`.
* Which variable Geant4 honors depends on its version — `G4NEUTRONHPDATA` for the
  neutron-HP models, `G4PARTICLEHPDATA` for the particle-HP models in Geant4 ≥ 11.
  Exporting both is harmless and portable.
* To deploy elsewhere, copy the `.tar.gz`, extract it, and point the variable at
  the extracted directory.

## G4NDL cross-section format

A G4NDL `Capture/CrossSection` file is G4NDL's internal representation (not
literal ENDF-6): a small header followed by a flat stream of `(energy, σ)` pairs,
three pairs per line. Three header families are supported transparently (tab /
`G4NDL`-string / bare); individual `.z` (zlib) compressed files are handled too.
See `src/custom_g4ndl_generator/g4ndl.py`.

## Development

```bash
pip install -e '.[dev]'   # runtime + pytest + pre-commit + black + pydocstyle
pytest

# Install the git hooks so black + documentation checks run on every commit:
pre-commit install
pre-commit run --all-files   # run them once over the whole tree
```

The hooks (`.pre-commit-config.yaml`) run [black](https://black.readthedocs.io/)
formatting and [pydocstyle](https://www.pydocstyle.org/) documentation checks
(numpy convention, package sources only), plus basic file hygiene. The same
checks and the test suite (Python 3.9–3.12) run in CI on every push and pull
request — see [`.github/workflows/tests.yml`](.github/workflows/tests.yml).
