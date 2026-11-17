# SSA Propulsion and Launch Data

This repository builds the `ssa-data-propulsion` Python distribution. It
contains provenance-tracked propulsion resources and optional launch
reference data for scientific software. Installable modules are:

- `ssa_data_propulsion`: propulsion and engine reference data.
- `ssa_data_launch`: Apollo 11 source summaries and the NASA NESC Case 17
  inter-tool verification inputs.

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
38 records, including 5 s samples and event epochs. Position-vector norm
residuals are at most 0.410 m and velocity-vector norm residuals are at most
0.186 m/s against scalar values in the report. This is an operational
trajectory reference, not raw telemetry or independent flight truth.
Recreate it with the pinned-report extractor:

```bash
python3 scripts/extract_apollo11_profile.py \
  --phase s_ic --output /tmp/apollo11_sic_reference.csv
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
