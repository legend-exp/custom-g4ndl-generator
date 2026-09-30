# custom-g4ndl-generator

A tool to make custom [G4NDL](https://geant4.web.cern.ch/) neutron-data
libraries for Geant4. A YAML config file selects cross sections and scales them
or replaces parts of them with your own data. The rest of the library is copied
without change.

## Quick start

```bash
pip install .
custom-g4ndl config.yaml --source JEFF-3.3 --output ./out
```

`config.yaml`:

```yaml
customization:
  Capture:
    CrossSection:
      32_76_Germanium:
        scale: 1.68
```

This writes `./out/JEFF-3.3/`, a copy of JEFF-3.3 with the Ge-76 capture cross
section multiplied by 1.68. To use it in Geant4, see [Use in Geant4](#use-in-geant4).

A full example with measured data: {doc}`examples/ge76`.

## Config file and data

### Adjustments

The `customization` block follows the folder layout of the library. The keys
are the folder and file names in the library. The `.z` suffix is optional.

```yaml
customization:
  Capture:
    CrossSection:
      32_76_Germanium:
        scale: 1.68                # multiply sigma
        substitute: 76GE_XS.yaml   # replace an energy range
```

- `scale` multiplies σ everywhere outside the substitution range.
- `substitute` replaces the energy range it spans, from its lowest to its
  highest energy. This data is not scaled.
- Only files in `CrossSection` folders can be adjusted.

### Substitution data

A list of `[E, sigma]` pairs, E in eV and σ in barn. Give it in-line:

```yaml
        substitute:
          - [0.0257, 0.1543]
          - [0.0258, 0.1542]
```

or as a YAML file with the same list, relative to the config file:

```yaml
# 76GE_XS.yaml
- [0.0257, 0.1543]
- [0.0258, 0.1542]
```

Geant4 interpolates linearly between the points. Give enough points to follow
the shape of the cross section.

### Options

The config file can also set the command-line options. A value on the command
line overrides the value in the file.

```yaml
source: JEFF-3.3      # library to start from, see below
output: ./out         # output folder
rename: MYLIB         # name of the output library (default: source name)
tarball: true         # also write MYLIB.tar.gz
force: true           # overwrite an existing output
```

Run `custom-g4ndl --help` for all options.

## Source libraries

`source` can be:

| Source | Example |
| --- | --- |
| Geant4 dataset name | `G4NDL.4.7.1`, `G4TENDL.1.4` |
| IAEA name | `JEFF-3.3`, `ENDF-VIII.0`, `JENDL-5.0` |
| URL to a `.tar.gz` | `https://.../mylib.tar.gz` |
| local archive | `/data/G4NDL4.7.1.tar.gz` |
| local folder | `/data/G4NDL4.7.1` |

A name is the file name of the archive without `.tar.gz`. A name that contains
`G4` is a Geant4 dataset; all other names are IAEA libraries. The tool
downloads it from one of these sites:

- **Geant4 datasets**: the Geant4
  [download page](https://geant4.web.cern.ch/download/) of each release lists
  its datasets. Older releases:
  [all releases](https://geant4.web.cern.ch/download/all.html).
  - `G4NDL` is the default neutron library.
  - `G4TENDL` holds the TENDL data for neutrons, protons, deuterons, tritons, ³He and
    alpha particles. Use it as the source to adjust these cross sections.
- **IAEA** (evaluated libraries converted to the G4NDL format): the
  [IAEA Geant4 libraries](https://www-nds.iaea.org/geant4/) page lists all
  libraries and their archive names, for example `JEFF-4.0`, `ENDF-B-VIII.1`,
  `JENDL-5.0` or `CENDL-3.2`.

Downloads are kept in `~/.cache/custom-g4ndl-generator` (change it with
`cache-dir`).

The IAEA libraries do not have the folders `IsotopeProduction`, `JENDL_HE`,
`ThermalScattering` and `Inelastic/Gammas`, which Geant4 needs. The tool copies
them from a full G4NDL library, by default G4NDL 4.7.1. Set a different one
with `base-library`:

```yaml
source: JEFF-3.3
base-library: /data/G4NDL4.7.1
```

## Use in Geant4

Geant4 reads the neutron data from the folder in the variable
`G4NEUTRONHPDATA`. Set it to the absolute path of the new library:

```bash
custom-g4ndl config.yaml --source JEFF-3.3 --output ./out

export G4NEUTRONHPDATA="$(pwd)/out/JEFF-3.3"
ls "$G4NEUTRONHPDATA"   # Capture/ Elastic/ IsotopeProduction/ ...
```

For a library made from `G4TENDL`, set
`G4PARTICLEHPDATA` instead.

Then run the Geant4 application as usual. Put the `export` lines in the job
script, or in `~/.bashrc` to make the change permanent.

- Set the variable to the folder that contains `Capture/`, not to `./out` or
  to the `.tar.gz` file.
- On a different computer: run with `--tarball`, copy `out/JEFF-3.3.tar.gz`,
  extract it, and set the variable to the extracted folder.
- The physics list must use the high-precision neutron models (names that end
  in `_HP`, for example `QGSP_BIC_HP` or `Shielding`). Other physics lists do
  not read these data.

```{toctree}
:hidden:

examples/ge76
```
