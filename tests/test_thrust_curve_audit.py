"""Audit every packaged solid-motor thrust curve against its own catalog data.

A packaged curve's own samples must integrate to a total impulse consistent
with the sidecar's ``totImpulseNs`` and with the NAR/TRA impulse class it is
filed under, and the samples themselves must be physically sane (increasing
time, non-negative thrust, ending at zero). See
``src/ssa_data_propulsion/data/propulsion/source_audit.md`` for the audit
history and the rationale behind each exception below.
"""
from __future__ import annotations

import csv
import json

import pytest

from ssa_data_propulsion import data_resource, open_text

THRUST_CURVE_DIR = "propulsion/thrust_curves/solid_motor_pd/thrustcurve_org"

# NAR/TRA total-impulse class table (Ns); each class doubles the previous.
IMPULSE_CLASS_LIMITS = {
    "1/8A": (0.00, 0.3125),
    "1/4A": (0.3126, 0.625),
    "1/2A": (0.626, 1.25),
    "A": (1.26, 2.50),
    "B": (2.51, 5.00),
    "C": (5.01, 10.00),
    "D": (10.01, 20.00),
    "E": (20.01, 40.00),
    "F": (40.01, 80.00),
    "G": (80.01, 160.00),
    "H": (160.01, 320.00),
    "I": (320.01, 640.00),
    "J": (640.01, 1280.00),
    "K": (1280.01, 2560.00),
    "L": (2560.01, 5120.00),
    "M": (5120.01, 10240.00),
    "N": (10240.01, 20480.00),
    "O": (20480.01, 40960.00),
}

# A packaged curve must integrate to within this fraction of its own catalog
# totImpulseNs. This is the primary accuracy gate: it is what would have
# caught the Estes C6 curve (which integrated 13.6% high), and it is checked
# together with the class-limit assertion below so a curve cannot silently
# drift into a different impulse class than the one it is filed under.
IMPULSE_TOLERANCE = 0.10

# Certified/manufacturer curves whose integrated impulse is still beyond
# IMPULSE_TOLERANCE, keyed by simfile ID. Each has a certified or
# manufacturer provenance, stays within its stated NAR/TRA class, and has no
# better in-package alternative, so these are recorded exceptions rather than
# removed curves or a loosened tolerance. See source_audit.md for the full
# table of measured vs. catalog values.
IMPULSE_TOLERANCE_EXCEPTIONS = {
    "5f4294d20002e90000000869": (
        "AeroTech M6000ST: certified measurement integrates to ~9605 Ns vs "
        "catalog 8247.1 Ns; catalog figure differs from the certified data."
    ),
    "5f4294d20002e9000000083d": (
        "Loki I316-SF: certified measurement integrates to ~474 Ns vs "
        "catalog 408.6 Ns; catalog figure differs from the certified data."
    ),
    "5f4294d20002e900000000ad": (
        "Ellis J330: certified measurement integrates to ~853 Ns vs catalog "
        "737.8 Ns; catalog figure differs from the certified data."
    ),
    "5f4294d20002e900000000fd": (
        "RATT H70: certified measurement integrates to ~177 Ns vs catalog "
        "207.5 Ns; catalog figure differs from the certified data."
    ),
    "5f4294d20002e900000000e7": (
        "Hypertek 440CC125J-J250: certified measurement integrates to ~644 "
        "Ns vs catalog 744.5 Ns; catalog figure differs from the certified "
        "data."
    ),
    "5f4294d20002e900000000a9": (
        "Ellis I230: certified measurement integrates to ~611 Ns vs catalog "
        "540 Ns; catalog figure differs from the certified data."
    ),
    "5f4294d20002e900000000a5": (
        "Ellis I150: certified measurement integrates to ~387 Ns vs catalog "
        "346.2 Ns; catalog figure differs from the certified data."
    ),
    "5f4294d20002e90000000877": (
        "AeroTech J1799N (RASP): certified measurement integrates to ~1074 "
        "Ns vs catalog 1214.8 Ns; catalog figure differs from the certified "
        "data."
    ),
    "5f4294d20002e90000000878": (
        "AeroTech J1799N (RockSim): certified measurement integrates to "
        "~1076 Ns vs catalog 1214.8 Ns; catalog figure differs from the "
        "certified data."
    ),
    "5f4294d20002e900000000eb": (
        "Hypertek 835CC125J-K240: certified measurement integrates to "
        "~1423 Ns vs catalog 1292 Ns; catalog figure differs from the "
        "certified data."
    ),
    "5f4294d20002e90000000881": (
        "Hypertek 835CC125J-K240 (second certified simfile): integrates to "
        "~1423 Ns vs catalog 1292 Ns; catalog figure differs from the "
        "certified data."
    ),
}

# motor-class-boundary-exact curves audited and accepted in source_audit.md:
# their catalog totImpulseNs sits at (or a fraction of a percent from) the
# edge of its class, so ordinary trapezoid quadrature noise from a reduced
# RASP/RockSim sample can legitimately land a hair outside the printed class
# limits without the curve being wrong.
CLASS_BOUNDARY_EXCEPTIONS = {
    "aerotech_h55w_rasp_5f4294d20002e90000000021.csv",
    "aerotech_hp_h45w_rasp_5f4294d20002e900000007fd.csv",
    "aerotech_hp_h45w_rocksim_5f9242d71bca580004171737.csv",
    "aerotech_hp_i65w_rasp_5f4294d20002e900000007fa.csv",
    "aerotech_hp_i65w_rocksim_5f9244721bca580004171749.csv",
    "aerotech_i218r_rasp_5f4294d20002e90000000037.csv",
    "aerotech_i350r_rasp_5f4294d20002e90000000795.csv",
    "aerotech_i350r_rocksim_5f9245f61bca58000417179b.csv",
    "aerotech_i65w_rasp_5f4294d20002e90000000047.csv",
    "aerotech_m1939w_rasp_5f4294d20002e9000000008f.csv",
    "estes_b4_rasp_5f4294d20002e90000000834.csv",
    "kba_l1000s_rasp_5f4294d20002e900000000fb.csv",
    "quest_a3_rasp_666a56b5071776000212afe3.csv",
    "quest_b6w_rasp_60ae6058d83fc60004c69f18.csv",
    "quest_b6w_rocksim_618ed8392bb16e00041a2ec5.csv",
}

# Gross-error sanity bounds, not accuracy checks: RASP/RockSim simulator
# files are deliberately reduced to a handful of samples, so a coarse sample
# can legitimately miss the true peak thrust or run its decay tail past the
# catalog's burnout-threshold convention by a large margin without being
# wrong. These bounds exist only to catch something categorically broken
# (e.g. a unit-conversion mistake or a swapped/truncated file), not to
# assert the sample closely matches the catalog figure.
BURN_TIME_MIN_TOLERANCE_S = 2.0  # catches a curve many times longer/shorter than its catalog burn
BURN_TIME_RELATIVE_TOLERANCE = 0.75  # ditto, scaled for long-burning motors
MAX_THRUST_TOLERANCE = 1.0  # catches a peak thrust off by more than 2x (e.g. a unit mixup)


def _trapz(times: list[float], thrusts: list[float]) -> float:
    total = 0.0
    for i in range(1, len(times)):
        dt = times[i] - times[i - 1]
        total += 0.5 * (thrusts[i] + thrusts[i - 1]) * dt
    return total


def _load_index_rows():
    with open_text(f"{THRUST_CURVE_DIR}/index.csv") as handle:
        return list(csv.DictReader(handle))


def _curve_ids():
    return [row["csv_path"] for row in _load_index_rows()]


@pytest.fixture(scope="module")
def index_rows():
    return {row["csv_path"]: row for row in _load_index_rows()}


@pytest.mark.parametrize("csv_name", _curve_ids())
def test_packaged_curve_matches_catalog(csv_name, index_rows):
    row = index_rows[csv_name]
    simfile_id = row["simfile_id"]

    with open_text(f"{THRUST_CURVE_DIR}/{csv_name}") as handle:
        reader = csv.DictReader(handle)
        times = []
        thrusts = []
        for sample in reader:
            times.append(float(sample["time_s"]))
            thrusts.append(float(sample["thrust_n"]))

    assert len(times) >= 2, f"{csv_name}: curve needs at least two samples"
    assert all(
        times[i] > times[i - 1] for i in range(1, len(times))
    ), f"{csv_name}: sample times are not strictly increasing"
    assert all(t >= 0 for t in thrusts), f"{csv_name}: negative thrust sample present"
    assert thrusts[-1] == 0, f"{csv_name}: curve does not end at zero thrust"

    integrated_impulse = _trapz(times, thrusts)
    burn_time = times[-1] - times[0]
    max_thrust = max(thrusts)

    metadata_path = row["metadata_path"]
    with open_text(f"{THRUST_CURVE_DIR}/{metadata_path}") as handle:
        motor = json.load(handle)["motor"]

    cat_impulse = motor["totImpulseNs"]
    cat_burn = motor["burnTimeS"]
    cat_max_thrust = motor.get("maxThrustN")

    impulse_err = abs(integrated_impulse - cat_impulse) / cat_impulse
    if simfile_id not in IMPULSE_TOLERANCE_EXCEPTIONS:
        assert impulse_err <= IMPULSE_TOLERANCE, (
            f"{csv_name}: trapezoid impulse {integrated_impulse:.4f} Ns differs "
            f"from catalog totImpulseNs {cat_impulse} Ns by {impulse_err:.1%}, "
            f"exceeding the {IMPULSE_TOLERANCE:.0%} tolerance"
        )

    burn_err = abs(burn_time - cat_burn)
    burn_tolerance = max(BURN_TIME_MIN_TOLERANCE_S, BURN_TIME_RELATIVE_TOLERANCE * cat_burn)
    assert burn_err <= burn_tolerance, (
        f"{csv_name}: sampled burn time {burn_time:.3f}s differs from "
        f"catalog burnTimeS {cat_burn}s by {burn_err:.3f}s (gross-error bound)"
    )

    # maxThrustN is absent from a number of catalog records (not something
    # this repository can repair without re-fetching from thrustcurve.org),
    # so only check it when the catalog actually reports a value.
    if cat_max_thrust:
        max_thrust_err = abs(max_thrust - cat_max_thrust) / cat_max_thrust
        assert max_thrust_err <= MAX_THRUST_TOLERANCE, (
            f"{csv_name}: sampled max thrust {max_thrust:.3f} N differs from "
            f"catalog maxThrustN {cat_max_thrust} N by {max_thrust_err:.1%} "
            "(gross-error bound)"
        )

    impulse_class = row["impulse_class"]
    assert impulse_class in IMPULSE_CLASS_LIMITS, (
        f"{csv_name}: unknown impulse class '{impulse_class}'"
    )
    lo, hi = IMPULSE_CLASS_LIMITS[impulse_class]
    if csv_name not in CLASS_BOUNDARY_EXCEPTIONS:
        assert lo <= integrated_impulse <= hi, (
            f"{csv_name}: trapezoid impulse {integrated_impulse:.4f} Ns falls "
            f"outside class {impulse_class} limits [{lo}, {hi}] Ns"
        )


def test_index_matches_packaged_files():
    """Every index.csv row has an existing CSV+JSON pair and vice versa."""

    rows = _load_index_rows()
    index_csv_names = {row["csv_path"] for row in rows}

    packaged_csv_names = {
        resource.name
        for resource in data_resource(THRUST_CURVE_DIR).iterdir()
        if resource.name.endswith(".csv") and resource.name != "index.csv"
    }

    assert index_csv_names == packaged_csv_names, (
        "index.csv and the packaged *.csv files have diverged: "
        f"in index only: {index_csv_names - packaged_csv_names}; "
        f"on disk only: {packaged_csv_names - index_csv_names}"
    )


def test_impulse_tolerance_exceptions_are_still_present():
    """The exception mapping should only ever reference packaged curves."""

    simfile_ids = {row["simfile_id"] for row in _load_index_rows()}
    stale = set(IMPULSE_TOLERANCE_EXCEPTIONS) - simfile_ids
    assert not stale, f"exception entries for simfile IDs no longer packaged: {stale}"
