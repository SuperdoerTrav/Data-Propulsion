# SSA Propulsion and Launch Data

This repository builds the `ssa-data-propulsion` Python distribution. It
contains provenance-tracked propulsion resources and optional launch
reference data for scientific software. Installable modules are:

- `ssa_data_propulsion`: propulsion and engine reference data.
- `ssa_data_launch`: Apollo 11 source summaries, NASA NESC Case 17 inter-tool
  verification inputs, and postlaunch Falcon 9/Falcon Heavy orbital fits.

Both modules ship in the same distribution. The current combined data payload
is well below PyPI's 100 MB per-file upload limit. If a future wheel or source
distribution approaches that limit, split launch and propulsion into separate
distributions before publishing the oversized artifact.

## Launch Reference Data

The Apollo 11 package records selected events, launch and insertion states,
mass checkpoints, and source discrepancies from NASA reports. The reports
themselves are not redistributed, and the operational guidance record is not
independent flight truth.

`benchmarks/apollo11/apollo11_sic_reference.csv` adds a source-closed
space-fixed state history from first motion through S-IC/S-II separation:
38 records with only the time/event fields, six state components, scalar
geocentric radius/speed used for closure, and provenance columns. OCR-derived
mass, aerodynamic, attitude, and other side channels are intentionally
excluded. Position-vector norm residuals are at most 0.410 m and
velocity-vector norm residuals are at most 0.186 m/s against scalar values in
the report. This is an operational trajectory reference, not raw telemetry or
independent flight truth.
Recreate it with the pinned-report extractor:

```bash
python3 scripts/extract_apollo11_profile.py \
  --phase s_ic --output /tmp/apollo11_sic_reference.csv
```

`benchmarks/apollo11/apollo11_sii_initial_reference.csv` adds five early
S-II event/sample states at 161.59, 162.22, 165.22, 170, and 175 s from first
motion. The 161.59 s row is the post-separation state; the S-IC package retains
the same-epoch pre-separation state. All six space-fixed components were
visually checked against NASA CR-61291 Table 2.2, PDF p. 35, and each state's
vector norms close to the report's scalar radius and speed within 0.5 m and
0.2 m/s. This sparse operational guidance reference is not a continuous
trajectory, raw telemetry, or independent flight truth. Recreate and validate
it from the pinned report with:

```bash
python3 scripts/extract_apollo11_profile.py \
  --phase s_ii_initial --output /tmp/apollo11_sii_initial_reference.csv
```
Its provenance sidecar also records five visually transcribed Table 2.2
geodetic checkpoints from PDF p. 27 at the same epochs for source-frame
closure checks.

`benchmarks/apollo11/apollo11_sii_source_closed_samples.csv` is a broader but
still sparse set of 23 S-II samples selected from the 84 event/sample epochs
in Table 2.2. The extractor includes rows only when all six state components
and scalar radius/speed are present, their norm residuals are within 0.5 m and
0.2 m/s, and state-field OCR changes have visual verification. Its provenance
sidecar lists 16 incomplete, 3 closure-failed, and 42 correction-withheld
epochs. The samples contain gaps and do not define a continuous trajectory or
flight-validation arc. Recreate them with:

```bash
python3 scripts/extract_apollo11_profile.py \
  --phase s_ii_closed --output /tmp/apollo11_sii_source_closed_samples.csv
```

The experimental extractor for the report's full 5-second trajectory table is
retained under `scripts/`, but it does not currently pass source-closure
checks because it misses the S-II center-engine-cutoff row. No full-profile
trajectory is included.

The NASA NESC Case 17 package contains the published idealized two-stage
verification model and anonymized reference histories. It is not a flown
vehicle or a flight-validation dataset. See each benchmark's `provenance.json`
for source hashes, transformations, units, limitations, and unresolved
discrepancies.

`benchmarks/falcon/falcon_first_gp.json` contains CelesTrak's earliest
available General Perturbations (GP) records for the EUTELSAT 10B Falcon 9
launch and the ARABSAT-6A Falcon Heavy launch. Each launch has one payload fit
and one rocket-body fit. These are Space Surveillance Network observation-fit
mean elements propagated with Simplified General Perturbations 4 (SGP4), not
telemetry, Cartesian separation states, or as-flown ascent histories. The
records include no covariance or stated orbit-fit accuracy. CelesTrak's
documented defaults identify the omitted fields as Earth-centered, TEME,
UTC, and SGP4. Use them only for explicitly labeled postlaunch orbital-fit
comparisons; do not infer ascent performance or insertion accuracy from them.
See the adjacent provenance JSON for query URLs, access date, source hashes,
and data-use limitations.

The package's MIT license applies to software, not automatically to the
included datasets. Dataset source rights and attribution are documented in
`NOTICE` and the per-resource provenance records.

For a local source install and verification:

```bash
python3 -m pip install -e .
python3 -m pytest
python3 -m build
python3 -m twine check dist/*
```

LLNL-CODE-2015996
