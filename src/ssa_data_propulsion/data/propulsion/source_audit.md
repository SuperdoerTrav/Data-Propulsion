# Propulsion Source Audit

Retrieved: 2026-08-22

This file records the current propulsion-data search so future imports do not
repeat the same source review or accidentally package data without clear rights.

## Packaged Sources

- ThrustCurve.org public-domain RASP/RockSim samples: 596 solid/hybrid motor
  time-thrust curves under `thrust_curves/solid_motor_pd/thrustcurve_org/` as
  originally imported; 582 remain after the 2026-10-26 audits below removed
  14 curves found to be inconsistent with their own catalog metadata.
- NASA NTRS 20100042402: NEXT TT10 electric-propulsion thrust comparison
  table under `throttle_maps/electric/next_tt10_thrust_comparison.csv`.
- NASA NTRS 20210023838: HERMeS TDU-3 electric-propulsion reference and
  expanded firing-condition table under
  `throttle_maps/electric/hermes_tdu3_throttle_map.csv`.
- NASA NTRS 20210015721: AEPS ETU-2 electric-propulsion reference and Power
  and Propulsion Element firing-condition table under
  `throttle_maps/electric/aeps_etu2_throttle_map.csv`.
- NASA NTRS 19980016322: SPT-140 Hall-thruster steady-state performance
  points under `throttle_maps/electric/spt140_performance_map.csv`.
- NASA NTRS digitized thrust curves: three public/export-clear plotted curves
  under `thrust_curves/digitized/nasa_ntrs/`.
  - NTRS 19730015083, Fig. 7: TE-M-521-5 apogee kick motor axial thrust.
  - NTRS 19900003335, Fig. 2.1: RSRM-3B reconstructed vacuum thrust.
  - NTRS 20090026004, Fig. 8: RS-18 normalized startup/shutdown thrust shape.
  Each CSV has a sidecar JSON with figure citation, uncertainty estimate,
  columns, and validation notes. Source PDFs and rendered plot images are not
  redistributed.

## Reviewed But Not Packaged

- NASA NTRS 19780059628, Space Shuttle SRB thrust shape design: public but
  rights metadata is `OTHER`; do not package without manual rights review.
- NASA NTRS 20100027316, Rocketdyne F-1 Saturn V first-stage engine: public
  historical description with design thrust, specific impulse, and startup
  narrative, but not a numeric curve source.
- NASA NTRS 20100021053, J-2X upper-stage engine: public overview with
  design-level thrust, specific impulse, and duration values, but not a
  numeric curve source.
- NASA NTRS 20140002697, NASA MSFC tri-gas thruster: public and
  export-clear, but the useful table is an `Isp` summary by catalyst
  configuration, not a time-thrust curve.
- NASA NTRS 19720014170, electrothermal hydrazine resistojet model
  specification: public and export-clear, but it provides requirements and
  operating limits rather than measured curves.
- NASA NTRS 20190030438, electrothermal ablation-fed pulsed plasma thruster:
  public and export-clear, but data are plotted impulse-bit trends; no
  tabular per-pulse curve was found in the extracted text.

## 2026-10-26 Thrust Curve Integrity Audit

Every curve in `thrust_curves/solid_motor_pd/thrustcurve_org/index.csv` (596
curves at the time) was independently re-integrated with a trapezoid rule and
compared against its own JSON sidecar (`totImpulseNs`, `burnTimeS`,
`maxThrustN`) and against the NAR/TRA total-impulse class table:

| Class | Range (Ns) | Class | Range (Ns) |
| --- | --- | --- | --- |
| 1/8A | 0.00-0.3125 | H | 160.01-320.00 |
| 1/4A | 0.3126-0.625 | I | 320.01-640.00 |
| 1/2A | 0.626-1.25 | J | 640.01-1280.00 |
| A | 1.26-2.50 | K | 1280.01-2560.00 |
| B | 2.51-5.00 | L | 2560.01-5120.00 |
| C | 5.01-10.00 | M | 5120.01-10240.00 |
| D | 10.01-20.00 | N | 10240.01-20480.00 |
| E | 20.01-40.00 | O | 20480.01-40960.00 |
| F | 40.01-80.00 | | |
| G | 80.01-160.00 | | |

Distribution of `|integrated impulse - totImpulseNs| / totImpulseNs`: median
0.6%, mean 1.7%, 90th percentile 4.1%, max 21.2%. 48 curves exceed 5%, 17
exceed 10%, and 24 curves (mostly within 1% of a class boundary that the
catalog itself places exactly at the limit, e.g. a motor whose official
impulse is exactly 5.00 Ns at the B/C line) integrate to a value just outside
their stated class — those boundary-exact cases are ordinary quadrature noise,
not data errors, and were left alone.

8 curves combined a >5% impulse error with an integrated value that lands in
a different NAR/TRA class than the one recorded in `index.csv`, which is a
genuine, not just numerical, inconsistency. `scripts/import_thrustcurve_pd.py`
(referenced above) is not present in this repository, and thrustcurve.org
returned HTTP 503 "Offline for Maintenance" on 2026-10-26, so no replacement
certified/manufacturer sim file could be fetched. Each was removed from the
package and `index.csv`:

- `estes_c6_rasp_5f4294d20002e90000000833.csv` (Estes C6, user, +13.6%,
  integrates to 10.02 Ns, above the 10.00 Ns C-class ceiling). This was the
  only packaged Estes C6 curve.
- `aerotech_hp_g138t_rasp_5f4294d20002e90000000768.csv` (user, +6.0%, 166.6
  Ns vs. the 160.00 Ns G-class ceiling).
- `aerotech_k458w_rasp_5f4294d20002e9000000006d.csv` (cert, +6.4%, 2622.9 Ns
  vs. the 2560.00 Ns K-class ceiling).
- `kosdon_h155f_rasp_5f4294d20002e90000000803.csv` (cert, -7.4%, 148.8 Ns,
  below the 160.01 Ns H-class floor).
- `tsp_d20_rasp_66a2fb7fd1517d00027c3ff0.csv` (user, +14.1%, 22.8 Ns, above
  the 20.00 Ns D-class ceiling).
- `tsp_e20_rasp_66a2fd86d1517d00027c4109.csv` (user, +11.3%, 40.1 Ns, above
  the 40.00 Ns E-class ceiling).
- `aerotech_n2700w_ps_rasp_674b7dfd5f568e00027083df.csv` and
  `aerotech_n2700w_ps_rocksim_674b7feb5f568e0002708522.csv` (user, -6.1%,
  9990.7 Ns, below the 10240.01 Ns N-class floor). A third, already-packaged
  simfile for the same motor,
  `aerotech_n2700w_ps_rasp_6625852af307ea0002dc20c5.csv`, integrates to
  10321.6 Ns (-3.0%, inside the N class) and was kept, so this motor remains
  represented without needing a network fetch.

Remaining curves with a >5% impulse error but no class violation (about 40,
mostly `source: user`) were left packaged; this is a known characteristic of
community-submitted RASP/RockSim sample files and is tracked here as a
quality caveat for a future audit once thrustcurve.org is reachable and the
import script exists in-repo again, rather than treated as a packaging
defect.

`quest_micro_maxx_ii_rasp_5f4294d20002e9000000078b.csv` had `impulse_class`
recorded as `A` in `index.csv`, but its own `totImpulseNs` (0.218) and its
`commonName` (`1/8A0.3`) both say it is a 1/8A motor. Corrected the
`index.csv` `impulse_class` field to `1/8A`; the curve itself was not
touched. The JSON sidecar's `motor.impulseClass` field was left as `A` since
it is a provenance snapshot of the upstream catalog record.

`aerotech_m1939w_rasp_5f4294d20002e9000000008f.csv` integrates close to its
catalog impulse (-2.3%, under the 5% action threshold) but its catalog
`totImpulseNs` (10481.5 Ns) is itself just above the 10240.00 Ns M-class
ceiling. This was left unchanged: manufacturers sometimes certify a motor
into a class by product line/average test impulse rather than the single
reported value, and a 2.4% boundary overage is not strong enough evidence of
a mislabeled record without an independent source to check against.

Three curves did not end at zero thrust, which a `.eng`/RASP sample is
expected to do. `aerotech_l2775st_ps_rasp_66266b86f307ea0002dca9a7.csv` had a
second, already-packaged simfile for the same motor
(`aerotech_l2775st_ps_rasp_66256f4df307ea0002dc1865.csv`, impulse error
0.02%, burn time within 0.04s, max thrust within 0.03%) and was removed in
favor of it, again without needing a network fetch.
`loki_i426lb_rasp_66229b94f873440002ab2f24.csv` and
`loki_j670lb_rasp_66229756f873440002ab2cbc.csv` had no in-package
alternative and thrustcurve.org was unreachable, so both were removed. 585
curves remain packaged.

Several packaged curves (6 of the curves checked above, plus others)
integrate to a total impulse or run to a sampled burn time noticeably longer
than the catalog `burnTimeS`, because the catalog burn time uses a standard
burnout-threshold convention while the packaged RASP/RockSim sample runs out
the full thrust decay tail to true zero. This is expected and is not a data
defect; the packaged regression test's burn-time tolerance accounts for it.

61 of the 582 remaining curves have no `maxThrustN` in their catalog sidecar
at all (the field was never populated by the original import). The
regression test skips the max-thrust check for those curves rather than
treating a missing field as a failure; re-running the (currently absent)
import script against a live thrustcurve.org would be the way to backfill it.

A regression test enforcing these checks for every packaged curve lives at
`tests/test_thrust_curve_audit.py`.

## 2026-10-26 Follow-up: Tightened Impulse Tolerance

The first pass above used a 25% impulse tolerance in the regression test,
which was loose enough to let a repeat of the Estes C6 defect (+13.6%)
through. The policy is now: a packaged curve must integrate to within 10% of
its sidecar `totImpulseNs`, in addition to the class-limit check above.
Re-running the independent trapezoid audit against the 585 curves packaged
at that point found 14 curves beyond 10%.

Three were `source: user` curves with no certified/manufacturer provenance
and were removed:

- `aerotech_m6000st_rocksim_5f924ab81bca5800041717fe.csv` (AeroTech M6000ST,
  +16.5%). A certified simfile for the same motor,
  `aerotech_m6000st_rasp_5f4294d20002e90000000869.csv`, is already packaged
  and was kept (it is itself beyond 10%; see the exception list below).
- `amw_sk_98_17500_rasp_601a296b66316a0004301376.csv` (AMW SK-98-17500,
  +20.4%). No alternate simfile is packaged for this motor and
  thrustcurve.org is unreachable, so it was dropped rather than replaced.
- `aerotech_g78g_l_rocksim_5f92410b1bca580004171722.csv` (AeroTech G78G/L,
  +21.2%). A second, already-packaged simfile for the same motor,
  `aerotech_g78g_l_rasp_682f41400b264d0002aaad78.csv`, integrates to within
  0.15% of the catalog impulse and was kept instead, so no network fetch was
  needed.

582 curves remain packaged.

The remaining 11 curves beyond 10% are all `source: cert`. None of them
cross a NAR/TRA class boundary, so these read as the certified simfile's own
measured burn disagreeing with the catalog's separately reported
`totImpulseNs` figure, not a packaging defect, and there is no better
alternative to swap in. They are kept and recorded, by simfile ID, in the
`IMPULSE_TOLERANCE_EXCEPTIONS` mapping in
`tests/test_thrust_curve_audit.py` so the test documents rather than hides
them:

| Simfile ID | Motor | Integrated (Ns) | Catalog totImpulseNs | Error |
| --- | --- | --- | --- | --- |
| `5f4294d20002e90000000869` | AeroTech M6000ST | 9604.6 | 8247.1 | +16.5% |
| `5f4294d20002e9000000083d` | Loki I316-SF | 474.0 | 408.6 | +16.0% |
| `5f4294d20002e900000000ad` | Ellis J330 | 853.3 | 737.8 | +15.7% |
| `5f4294d20002e900000000fd` | RATT H70 | 176.8 | 207.5 | -14.8% |
| `5f4294d20002e900000000e7` | Hypertek 440CC125J-J250 | 644.1 | 744.5 | -13.5% |
| `5f4294d20002e900000000a9` | Ellis I230 | 610.5 | 540.0 | +13.1% |
| `5f4294d20002e900000000a5` | Ellis I150 | 387.4 | 346.2 | +11.9% |
| `5f4294d20002e90000000877` | AeroTech J1799N (RASP) | 1074.4 | 1214.8 | -11.6% |
| `5f4294d20002e90000000878` | AeroTech J1799N (RockSim) | 1075.7 | 1214.8 | -11.4% |
| `5f4294d20002e900000000eb` | Hypertek 835CC125J-K240 | 1422.7 | 1292.0 | +10.1% |
| `5f4294d20002e90000000881` | Hypertek 835CC125J-K240 (2nd cert file) | 1422.7 | 1292.0 | +10.1% |

## Current Gaps

- Redistributable time-thrust curves for flight-like cold-gas,
  monopropellant, bipropellant, and large liquid engines remain unresolved.
- Electric propulsion is represented by steady-state throttle/performance
  maps rather than transient curves, which is normally the more useful input
  for low-thrust orbit propagation.
- Manufacturer datasheets and unlicensed curve files remain excluded even if
  they are easy to find online.
