"""Build a pinned, compact NASA NESC two-stage launch verification case."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

CASE_URL = "https://nescacademy.nasa.gov/src/flightsim/Datasets/Atmos_17_TwoStageRocketToOrbit.zip"
CASE_ZIP_SHA256 = "d04448054c66efe6a31cdd5246b874245a60bb4bfdf39e9c5ed86d6176443cc4"
MODELS_URL = "https://nescacademy.nasa.gov/src/flightsim/Models/Atmospheric_models.zip"
MODELS_ZIP_SHA256 = "10e2dc267856ef37eaedbcdd16eb49a8c44b39301054de0fa78292c1c4aba3bc"
MODEL_PACKAGE_SHA256 = "0be22896aea43bde1cc726c53a91ff890a4cf1483094b10d132295d5c37f76cb"
MODEL_HASHES = {
    "twostage_aero.dml": "49df37f2ab8ad3b9c6f181bb3c32ad828304870371b3e058512c08e359579a27",
    "twostage_inertia.dml": "277707b8e1f26f99f6b2068c79a243bd3a450e325e2ef7dbc2f9a39e7b52570b",
    "twostage_prop.dml": "297cb7b8950a1ba5185fca98b5966cb8ad14cf76f8d2d0af9b17e7b0785197ee",
}
REFERENCE_HASHES = {
    "sim_04": "8ff5549895bc6f4b27f4529cab050dacbc563a6a3508c18aedcca5ae1bdc23e5",
    "sim_05": "f57b64733553a55d0b4369b210d047e8caa51cf0ea6cfa164a115051c2017633",
    "sim_06": "b5dda095cd1849b2460c5b5f0f3b0f30d454adf2258749d345c11b18cd3ccabd",
}

_REFERENCE_COLUMNS = (
    "eiPosition_ft_X", "eiPosition_ft_Y", "eiPosition_ft_Z",
    "eiVelocity_ft_s_X", "eiVelocity_ft_s_Y", "eiVelocity_ft_s_Z",
    "altitudeMsl_ft", "longitude_deg", "latitude_deg",
    "eulerAngle_deg_Yaw", "eulerAngle_deg_Pitch", "eulerAngle_deg_Roll",
    "bodyAngularRateWrtEi_deg_s_Roll", "bodyAngularRateWrtEi_deg_s_Pitch",
    "bodyAngularRateWrtEi_deg_s_Yaw", "airDensity_slug_ft3",
    "ambientPressure_lbf_ft2", "ambientTemperature_dgR",
    "aero_bodyForce_lbf_X", "aero_bodyForce_lbf_Y", "aero_bodyForce_lbf_Z",
    "aero_bodyMoment_ftlbf_L", "aero_bodyMoment_ftlbf_M",
    "aero_bodyMoment_ftlbf_N", "mach", "dynamicPressure_lbf_ft2",
)
_OUTPUT_COLUMNS = (
    "tool_id", "time_s",
    "position_eci_m_x", "position_eci_m_y", "position_eci_m_z",
    "velocity_eci_m_s_x", "velocity_eci_m_s_y", "velocity_eci_m_s_z",
    "altitude_msl_m", "longitude_deg_east", "latitude_deg",
    "euler_ned_yaw_deg", "euler_ned_pitch_deg", "euler_ned_roll_deg",
    "body_rate_wrt_ei_roll_rad_s", "body_rate_wrt_ei_pitch_rad_s",
    "body_rate_wrt_ei_yaw_rad_s",
    "density_kg_m3", "pressure_pa", "temperature_k",
    "aero_force_body_n_x", "aero_force_body_n_y", "aero_force_body_n_z",
    "aero_moment_body_nm_x", "aero_moment_body_nm_y", "aero_moment_body_nm_z",
    "mach", "dynamic_pressure_pa",
)
_FT_TO_M = 0.3048
_LBF_TO_N = 4.4482216152605
_SLUG_FT3_TO_KG_M3 = 515.3788183931961
_LBF_FT2_TO_PA = 47.88025898033584
_FT_LBF_TO_NM = 1.3558179483314
_EARTH_MU_M3_S2 = 3.986004418e14
_EARTH_EQUATORIAL_RADIUS_M = 6_378_137.0


def _cross(left, right):
    return (
        left[1]*right[2] - left[2]*right[1],
        left[2]*right[0] - left[0]*right[2],
        left[0]*right[1] - left[1]*right[0],
    )


def _norm(vector):
    return sum(value*value for value in vector)**0.5


def _terminal_perigee_altitude(row):
    """Two-body conic diagnostic for an archived terminal ECI state."""
    position = tuple(float(row[f"position_eci_m_{axis}"]) for axis in "xyz")
    velocity = tuple(float(row[f"velocity_eci_m_s_{axis}"]) for axis in "xyz")
    radius = _norm(position)
    angular_momentum = _cross(position, velocity)
    energy = 0.5*sum(value*value for value in velocity) - _EARTH_MU_M3_S2/radius
    eccentricity_vector = tuple(
        value/_EARTH_MU_M3_S2 - coordinate/radius
        for value, coordinate in zip(_cross(velocity, angular_momentum), position)
    )
    eccentricity = _norm(eccentricity_vector)
    semimajor_axis = -_EARTH_MU_M3_S2/(2.0*energy)
    return semimajor_axis*(1.0-eccentricity)-_EARTH_EQUATORIAL_RADIUS_M


def _download(url, expected_hash):
    with urlopen(url, timeout=60) as response:
        payload = response.read()
    actual = sha256(payload).hexdigest()
    if actual != expected_hash:
        raise ValueError(f"{url}: SHA-256 {actual} does not match pinned {expected_hash}")
    return payload


def _normalize_model_payload(payload):
    """Normalize line endings and trailing horizontal whitespace in DAVE-ML."""
    lines = payload.splitlines()
    normalized = b"\n".join(line.rstrip(b" \t\r") for line in lines)
    if payload.endswith((b"\n", b"\r")):
        normalized += b"\n"
    return normalized


def _model_members(model_archive):
    with ZipFile(io.BytesIO(model_archive)) as outer:
        package = outer.read("two-stage_package.zip")
    package_hash = sha256(package).hexdigest()
    if package_hash != MODEL_PACKAGE_SHA256:
        raise ValueError(f"NASA two-stage package SHA-256 mismatch: {package_hash}")
    with ZipFile(io.BytesIO(package)) as inner:
        models = {}
        for name, expected_hash in MODEL_HASHES.items():
            matches = [member for member in inner.namelist() if member.endswith("/"+name)]
            if len(matches) != 1:
                raise ValueError(f"NASA model archive does not contain one {name}")
            payload = inner.read(matches[0])
            actual = sha256(payload).hexdigest()
            if actual != expected_hash:
                raise ValueError(f"{name}: SHA-256 {actual} does not match pinned {expected_hash}")
            models[name] = _normalize_model_payload(payload)
    return models


def _record_at_one_second(rows, tool_id):
    selected = {}
    for source in rows:
        time_s = float(source["time"])
        sample_index = round(time_s)
        if abs(time_s-sample_index) > 0.001:
            continue
        converted = [tool_id, f"{sample_index:.1f}"]
        for column in _REFERENCE_COLUMNS:
            value = float(source[column])
            if column.startswith(("eiPosition_ft_", "altitudeMsl_ft")):
                value *= _FT_TO_M
            elif column.startswith("eiVelocity_ft_s_"):
                value *= _FT_TO_M
            elif column.startswith("bodyAngularRateWrtEi_deg_s_"):
                value *= 3.141592653589793/180.0
            elif column == "airDensity_slug_ft3":
                value *= _SLUG_FT3_TO_KG_M3
            elif column == "ambientPressure_lbf_ft2" or column == "dynamicPressure_lbf_ft2":
                value *= _LBF_FT2_TO_PA
            elif column == "ambientTemperature_dgR":
                value *= 5.0/9.0
            elif column.startswith("aero_bodyForce_lbf_"):
                value *= _LBF_TO_N
            elif column.startswith("aero_bodyMoment_ftlbf_"):
                value *= _FT_LBF_TO_NM
            converted.append(format(value, ".15g"))
        selected[sample_index] = converted
    if sorted(selected) != list(range(201)):
        raise ValueError(f"{tool_id}: expected samples 0-200 s at 1 s intervals")
    return [selected[index] for index in range(201)]


def build(output):
    """Write a new output directory; refuse to overwrite prior evidence."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    case_dir = output/"nasa42_case17"
    model_dir = case_dir/"models"
    case_dir.mkdir()
    model_dir.mkdir()
    model_archive = _download(MODELS_URL, MODELS_ZIP_SHA256)
    case_archive = _download(CASE_URL, CASE_ZIP_SHA256)
    models = _model_members(model_archive)
    for name, payload in models.items():
        (model_dir/name).write_bytes(payload)

    reference_path = case_dir/"reference_1s.csv"
    with ZipFile(io.BytesIO(case_archive)) as archive:
        reference_members = {}
        for tool_id in ("sim_04", "sim_05", "sim_06"):
            name = f"Atmos_17_TwoStageRocketToOrbit/Atmos_17_{tool_id}.csv"
            payload = archive.read(name)
            actual = sha256(payload).hexdigest()
            if actual != REFERENCE_HASHES[tool_id]:
                raise ValueError(f"{name}: SHA-256 {actual} does not match pinned {tool_id}")
            reader = csv.DictReader(io.StringIO(payload.decode("utf-8")))
            reference_members[tool_id] = _record_at_one_second(reader, tool_id)
    with reference_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(_OUTPUT_COLUMNS)
        for tool_id in ("sim_04", "sim_05", "sim_06"):
            writer.writerows(reference_members[tool_id])

    config = {
        "schema": "ssa_data_launch.nasa42_case.v1",
        "case_id": "nasa_nesc_atmospheric_case_17_two_stage_rocket",
        "source": {
            "citation": "NASA Engineering and Safety Center, NESC-RP-12-00770, Check-Cases for Verification of 6-Degree-of-Freedom Flight Vehicle Simulations, Volume II: Appendices, Appendix B.1.6 and C.1.20",
            "url": "https://ntrs.nasa.gov/citations/20150001264",
            "report_pdf_sha256": "2786f37fa02dba67e776de294038f7d8734b3de2cdd14d70b70a0db4b52f41f0",
            "models_page": "NESC Academy 2015 Flight Simulation Checkcases",
            "models_url": "https://nescacademy.nasa.gov/flightsim/2015",
            "models_archive_url": MODELS_URL,
            "models_archive_sha256": MODELS_ZIP_SHA256,
            "nested_model_archive_sha256": MODEL_PACKAGE_SHA256,
        },
        "classification": "IDEALIZED_INTERTOOL_VERIFICATION_CASE_NOT_REAL_FLIGHT",
        "scenario": {
            "initial_geodetic": {"latitude_deg": 0.0, "longitude_deg_east": 0.0, "altitude_m": 0.0},
            "initial_euler_nasa_yaw_pitch_roll_deg": [90.0, 55.22, 0.0],
            "initial_velocity_eci_m_s": [0.1, 465.1010849, 0.0],
            "initial_velocity_frame_note": (
                "Components are radial-outward, east, north in the case EI "
                "frame; 0.1 m/s is the published local-up velocity and the "
                "east component includes launch-site co-rotation."
            ),
            "initial_body_rate_relative_to_launch_site_roll_pitch_yaw_deg_s": [0.0, 0.0, 0.0],
            "reference_initial_body_rate_wrt_ei_roll_pitch_yaw_deg_s": [
                0.0, -0.00417807413224, 0.0
            ],
            "reference_initial_body_rate_sample_time_s": 0.0,
            "reference_initial_body_rate_note": (
                "An anonymized trajectory output at t=0; this is not the "
                "published scenario input, which specifies zero body rate "
                "relative to the rotating launch site."
            ),
            "duration_s": 200.0,
            "interstage_coast_after_first_burnout_s": 96.79,
            "guidance": "None; stable unguided vehicle pitches over under gravity",
            "gravity": "Earth point mass plus J2 using WGS-84 geodesy",
            "atmosphere": "U.S. Standard Atmosphere 1976; no wind; density set to zero above 86 km",
            "angular_momentum_flux_fraction": 0.5,
            "angular_momentum_flux_source": (
                "NESC-RP-12-00770, Volume II, Appendix B.1.6, p. 33; "
                "external simulation logic, not twostage_inertia.dml"
            ),
        },
        "source_discrepancies": [
            {
                "topic": "initial_velocity",
                "report_value": "0.32808399 ft/s upward relative to the launch site (0.1 m/s)",
                "model_package_readme_value": "0.1 ft/s along body X",
                "selected_basis": "Volume II, Appendices, pp. 34 and 68; the selected upward 0.1 m/s component is corroborated by the three trajectory CSVs",
            },
            {
                "topic": "initial_body_rate_frame",
                "scenario_value": "zero relative to the rotating launch site",
                "trajectory_output_value": "bodyAngularRateWrtEi includes the Earth-rate transformation",
                "selected_basis": "Volume II, Appendices, p. 68 for initial conditions and p. 56 for output-frame definitions",
            },
            {
                "topic": "thermosphere_outputs",
                "detail": "SIM 6 retains nonzero atmospheric fields above 86 km; NASA excludes these channels from Case 17 comparison",
                "selected_basis": "Volume II, Appendices, p. 595",
            },
            {
                "topic": "initial_vehicle_geometry",
                "detail": "The vehicle center of mass starts at sea level, placing the lower vehicle below the surface",
                "selected_basis": "Volume II, Appendices, p. 34",
            },
            {
                "topic": "yaw_inertia",
                "report_value": "Table 16 lists Izz equal to Ixx",
                "model_value": "twostage_inertia.dml computes Izz equal to Iyy",
                "selected_basis": "The simulator follows the explicit DAVE-ML output equation; both values are retained",
            },
        ],
        "vehicle": {
            "stage_1": {
                "length_m": 25.0,
                "diameter_m": 3.0,
                "dry_mass_kg": 35000.0,
                "propellant_mass_kg": 180000.0,
                "thrust_n": 17000000.0,
                "specific_impulse_s": 360.0,
            },
            "stage_2": {
                "length_m": 10.0,
                "diameter_m": 3.0,
                "dry_mass_kg": 15000.0,
                "propellant_mass_kg": 80000.0,
                "payload_mass_kg": 4000.0,
                "thrust_n": 5000000.0,
                "specific_impulse_s": 390.0,
            },
            "aerodynamics": {
                "reference_area_m2": 7.0,
                "reference_lengths_m": [3.0, 3.0, 3.0],
                "alpha_force_breakpoints_deg": [-10, -8, -6, -4, -2, 0, 2, 4, 6, 8, 10],
                "lift_coefficients": [-1.6, -1.0, -0.73, -0.49, -0.24, 0, 0.24, 0.49, 0.73, 1.0, 1.6],
                "drag_coefficients": [0.48, 0.38, 0.31, 0.25, 0.23, 0.21, 0.23, 0.25, 0.31, 0.38, 0.48],
                "beta_force_breakpoints_deg": [-10, -8, -6, -4, -2, 0, 2, 4, 6, 8, 10],
                "sideforce_coefficients": [1.6, 1.0, 0.73, 0.49, 0.24, 0, -0.24, -0.49, -0.73, -1.0, -1.6],
                "alpha_moment_breakpoints_deg": [-20, 0, 20],
                "pitch_moment_coefficients": [0.6, 0.0, -0.6],
                "beta_moment_breakpoints_deg": [-20, 0, 20],
                "yaw_moment_coefficients": [-0.6, 0.0, 0.6],
                "roll_moment_coefficients": [0.0],
                "source_files": ["twostage_aero.dml"],
            },
            "mass_properties": {
                "stage_1_ignition": {
                    "mass_kg": 314000.0, "cg_from_nose_aft_m": 16.918790,
                    "inertia_body_kg_m2": [353250.0, 33501637.473461, 33501637.473461],
                    "table_16_inertia_body_kg_m2": [353250.0, 33501637.473461, 353250.0],
                },
                "stage_1_burnout": {
                    "mass_kg": 134000.0, "cg_from_nose_aft_m": 9.421642,
                    "inertia_body_kg_m2": [150750.0, 10886636.572139, 10886636.572139],
                    "table_16_inertia_body_kg_m2": [150750.0, 10886636.572139, 150750.0],
                },
                "stage_2_ignition": {
                    "mass_kg": 99000.0, "cg_from_nose_aft_m": 4.797980,
                    "inertia_body_kg_m2": [111375.0, 941063.762626, 941063.762626],
                    "table_16_inertia_body_kg_m2": [111375.0, 941063.762626, 111375.0],
                },
                "stage_2_burnout": {
                    "mass_kg": 19000.0, "cg_from_nose_aft_m": 3.947368,
                    "inertia_body_kg_m2": [21375.0, 212384.868421, 212384.868421],
                    "table_16_inertia_body_kg_m2": [21375.0, 212384.868421, 21375.0],
                },
                "interpolation": "Linear in remaining stage propellant fraction, per twostage_inertia.dml",
                "inertia_interpretation": (
                    "DAVE-ML computes Izz from Iyy; the printed NASA Table 16 lists "
                    "Izz equal to Ixx. Both records are retained."
                ),
                "source_files": ["twostage_inertia.dml"],
            },
            "propulsion_source_files": ["twostage_prop.dml"],
        },
        "reference": {
            "archive_url": CASE_URL,
            "archive_sha256": CASE_ZIP_SHA256,
            "source_csv_hashes": REFERENCE_HASHES,
            "sample_csv": "reference_1s.csv",
            "sample_interval_s": 1.0,
            "sample_count_per_tool": 201,
            "tools_anonymized_in_report": ["sim_04", "sim_05", "sim_06"],
            "meaning": "Three participating-tool solutions for the specified idealized model; a verification family, not empirical flight truth.",
            "noncomparable_channels": [
                "density_kg_m3",
                "pressure_pa",
                "temperature_k",
                "mach",
                "dynamic_pressure_pa",
            ],
            "noncomparable_channel_condition": (
                "Do not compare these channels across tools above 86 km; NASA reports "
                "that one tool used a thermosphere model and excludes them."
            ),
        },
        "limitations": [
            "The source describes an unpublished conceptual rocket model; its aero data are noted as V-2-at-Mach-3 inspired and other values have no further attribution.",
            "NASA Case 17 is a numerical inter-tool verification case, not a flown vehicle or real-world launch event.",
            "The model-package README and report disagree on initial velocity magnitude and direction: the report gives 0.32808399 ft/s (0.1 m/s) upward, while the README gives 0.1 ft/s along body X; the report's upward component matches the archived trajectories.",
            "The scenario's initial body rates are zero relative to the rotating launch site; stored WrtEi rate histories include Earth rotation.",
            "NASA Table 16 and twostage_inertia.dml disagree on yaw inertia; the simulator follows the DAVE-ML equation and retains the printed table values separately.",
            "Atmospheric density, pressure, temperature, Mach and dynamic pressure are excluded from cross-tool comparison above 86 km.",
            "The specified center of mass begins at sea level, so the conceptual vehicle geometry overlaps the ground.",
            "The published source says a 0.001 s step is recommended and the case is sensitive to staging and rotational inertia assumptions.",
            "NASA reports inter-tool differences including 21.6 ft position difference at 200 s for one 1000 Hz comparison and much larger deviation for an alternate inertia model.",
            "The reference CSVs are anonymized simulation outputs; they are not treated as a single truth trajectory.",
        ],
    }
    config_path = case_dir/"case.json"
    config_path.write_text(json.dumps(config, indent=2)+"\n", encoding="utf-8")
    terminal_perigee_audit = {
        "epoch_s": 200.0,
        "central_mu_m3_s2": _EARTH_MU_M3_S2,
        "reference_radius_m": _EARTH_EQUATORIAL_RADIUS_M,
        "perigee_altitude_m": {
            tool_id: _terminal_perigee_altitude(
                dict(zip(_OUTPUT_COLUMNS, reference_members[tool_id][-1]))
            )
            for tool_id in ("sim_04", "sim_05", "sim_06")
        },
        "status": "SOURCE_DISCREPANCY",
        "interpretation": (
            "All archived terminal ECI vectors produce below-surface osculating "
            "two-body perigees under these constants, contrary to the report's "
            "greater-than-125-km statement. The source's perigee frame/time/gravity "
            "convention is unresolved."
        ),
    }
    terminal_perigee_discrepancy = {
        "topic": "terminal_perigee_claim",
        "report_value": "Greater than 125 km for the specified rotating Earth",
        "archived_history_check": (
            "All three terminal 200 s ECI vectors have below-surface two-body "
            "perigees under the recorded Earth constants"
        ),
        "resolution": (
            "Unresolved; the report's perigee frame, epoch, or gravity convention "
            "is not identified by the archived output CSVs."
        ),
    }
    provenance = {
        "schema": "ssa_data_launch.nasa42_case_provenance.v1",
        "case_id": config["case_id"],
        "payload": {
            "config": "benchmarks/nasa42_case17/case.json",
            "config_sha256": sha256(config_path.read_bytes()).hexdigest(),
            "reference_csv": "benchmarks/nasa42_case17/reference_1s.csv",
            "reference_csv_sha256": sha256(reference_path.read_bytes()).hexdigest(),
            "model_files": {
                name: {
                    "path": f"benchmarks/nasa42_case17/models/{name}",
                    "sha256": sha256(payload).hexdigest(),
                    "source_sha256": MODEL_HASHES[name],
                }
                for name, payload in models.items()
            },
        },
        "reference_csv_columns": list(_OUTPUT_COLUMNS),
        "reference_frame_and_datum": {
            "position_eci_m": (
                "Earth-centered inertial (EI) axes for each anonymized simulation. "
                "The archived t=0 states place +X radial-outward, +Y east, and "
                "+Z north at the equatorial launch site; the axes are treated as "
                "inertial thereafter. This orientation is inferred from the "
                "outputs and is not a published GCRF alignment."
            ),
            "velocity_eci_m_s": (
                "Earth-centered inertial velocity in the corresponding EI axes; "
                "not Earth-fixed velocity."
            ),
            "eci_frame_orientation_epoch_s": 0.0,
            "eci_frame_axes": (
                "+X radial-outward, +Y east, +Z north at the equatorial launch "
                "site at t=0; inferred from archived outputs and not a published "
                "GCRF alignment."
            ),
            "altitude_msl_m": "Mean sea-level altitude",
            "longitude_deg_east": "Geodetic longitude, east-positive",
            "latitude_deg": "Geodetic latitude",
            "euler_ned_*_deg": "Body attitude relative to local geodetic NED axes; yaw, pitch, roll order",
            "body_rate_wrt_ei_*_rad_s": "Body components of angular rate relative to Earth inertial axes; roll, pitch, yaw order",
            "scenario_initial_body_rate": "Zero relative to the rotating launch site, as specified by the model-package input description",
            "reference_initial_body_rate": "A t=0 trajectory-output sample in the EI frame; not a scenario input",
        },
        "source": config["source"],
        "extraction": {
            "reference_sample_rule": "For each anonymized simulation CSV, retain source samples at integer seconds 0 through 200 without interpolation; convert source imperial units to SI with stated exact conversion constants.",
            "model_normalization": (
                "Verify original DAVE-ML SHA-256 values, then strip trailing "
                "spaces/tabs and normalize line endings to LF; retain original "
                "and packaged hashes separately."
            ),
            "source_sample_count": {key: 20001 if key != "sim_06" else 2001 for key in REFERENCE_HASHES},
            "packaged_sample_count": {key: 201 for key in REFERENCE_HASHES},
        },
        "limitations": config["limitations"],
        "source_discrepancies": [
            *config["source_discrepancies"],
            terminal_perigee_discrepancy,
        ],
        "derived_reference_audits": {
            "terminal_two_body_conic": terminal_perigee_audit,
        },
    }
    (case_dir/"provenance.json").write_text(json.dumps(provenance, indent=2)+"\n", encoding="utf-8")
    return case_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory; never overwritten")
    args = parser.parse_args(argv)
    path = build(args.output)
    print(path)


if __name__ == "__main__":
    main()
