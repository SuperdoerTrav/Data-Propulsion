"""Pinned Apollo 11 event and insertion benchmark data."""

from hashlib import sha256
import json
from math import hypot

import pytest

from ssa_data_launch import (
    apollo11_benchmark,
    apollo11_sic_reference_provenance,
    data_resource,
    nasa42_case17,
    nasa42_case17_provenance,
    read_apollo11_sic_reference,
    read_nasa42_case17_reference,
)
from scripts.extract_apollo11_profile import (
    _VISUALLY_VERIFIED_TRANSCRIPTIONS,
    _apply_visually_verified_transcriptions,
    _tsv_rows,
)
from scripts.extract_nasa42_case17 import _normalize_model_payload


def test_tesseract_tsv_preserves_quotes_as_ocr_text():
    """TSV's OCR quote glyph must not make DictReader consume later records."""
    tsv = "\n".join((
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        '5\t1\t1\t1\t1\t1\t700\t100\t50\t20\t90\t10.00',
        '5\t1\t1\t1\t1\t2\t900\t100\t50\t20\t90\t"Q8',
        '5\t1\t1\t1\t2\t1\t700\t130\t50\t20\t90\t15.00',
        '5\t1\t1\t1\t2\t2\t900\t130\t50\t20\t90\t123.4',
    ))
    rows = _tsv_rows(tsv)
    assert [[word["text"] for word in row] for row in rows] == [
        ["10.00", '"Q8'],
        ["15.00", "123.4"],
    ]


def test_apollo_sic_visual_transcriptions_close_135s_and_separation_states():
    row_135 = {
        "8": 6417864.63,
        "25": 641697443.0,
        "26": 25963.1,
        "27": 103672.6,
    }
    row_separation = {"8": 6440658.81, "5": 2765.96}
    merged = {
        (phase, time_s): {}
        for phase, time_s, _column in _VISUALLY_VERIFIED_TRANSCRIPTIONS
    }
    merged[("s_ic", 135.0)] = row_135
    merged[("s_ic", 161.59)] = row_separation
    _apply_visually_verified_transcriptions(merged)

    assert [row_135[str(column)] for column in (25, 26, 27)] == [
        6416974.3, 35963.1, 100672.6,
    ]
    assert row_135["5"] == 1989.82
    assert hypot(
        row_135["25"], row_135["26"], row_135["27"]
    ) - row_135["8"] == pytest.approx(
        0.0837356, abs=1e-6,
    )
    assert [
        row_separation[str(column)] for column in range(25, 31)
    ] == [6438562.7, 39054.5, 159600.6, 858.782, 115.035, 2626.743]
    assert hypot(
        row_separation["25"], row_separation["26"], row_separation["27"]
    ) - row_separation["8"] == pytest.approx(0.1040648, abs=1e-6)
    assert hypot(
        row_separation["28"], row_separation["29"], row_separation["30"]
    ) - row_separation["5"] == pytest.approx(-0.0029572, abs=1e-6)
    assert any(
        "PDF p.18" in note for note in row_135["transcription_corrections"]
    )
    assert row_135["source_pages"] == {13, 18}
    assert not any(
        note.startswith("space-fixed component 27 changed from")
        for note in row_135["transcription_corrections"]
    )


def test_dave_ml_packaging_normalizes_only_line_endings_and_trailing_space():
    source = (
        b'<DAVEfunc>\r\n'
        b'  <description>Model description</description>  \r\n'
        b'  <equation> x + y </equation>\r\n'
        b'</DAVEfunc>\r\n'
    )
    assert _normalize_model_payload(source) == (
        b'<DAVEfunc>\n'
        b'  <description>Model description</description>\n'
        b'  <equation> x + y </equation>\n'
        b'</DAVEfunc>\n'
    )


def test_apollo11_summary_is_hash_pinned_and_keeps_provenance():
    benchmark_resource = data_resource("benchmarks/apollo11/apollo11_benchmark.json")
    provenance = json.loads(
        data_resource("benchmarks/apollo11/provenance.json").read_text(encoding="utf-8")
    )
    benchmark = json.loads(benchmark_resource.read_text(encoding="utf-8"))

    assert sha256(benchmark_resource.read_bytes()).hexdigest() == provenance["payload"]["sha256"]
    assert benchmark["source"]["pdf_sha256"] == provenance["source"]["pdf_sha256"]
    assert benchmark["source"]["report_number"] == "NASA CR-61291"
    assert benchmark["classification"] == "REAL_TIME_OPERATIONAL_GUIDANCE_REFERENCE"
    assert benchmark["limitations"] == provenance["extraction"]["limitations"]
    comparison, = (
        source for source in benchmark["source"]["comparison_sources"]
        if source["pdf_sha256"] == (
            "3314d99654ebb2ac3e3ef0ab70a84be9519a5f071cf1362118b2b20a6f161dea"
        )
    )
    assert comparison["pdf_sha256"] == (
        "3314d99654ebb2ac3e3ef0ab70a84be9519a5f071cf1362118b2b20a6f161dea"
    )
    assert comparison["reported_value"]["value"] == 735.0
    assert comparison["reported_value"]["converted_value_pa"] == pytest.approx(
        35191.990351, abs=1e-6,
    )
    sp238, = (
        source for source in benchmark["source"]["comparison_sources"]
        if source["pdf_sha256"] == (
            "8b7192503c5b74dc1bc9686b6bd84560f6bbbf14fa851449ddd8ddaad6137d5d"
        )
    )
    assert sp238["citation"].startswith("Apollo 11 Mission Report, NASA SP-238")
    assert sp238["printed_page"] == 71
    assert sp238["reported_value"]["value"] == 735.0
    assert "not the MSC-00171 report" in sp238["note"]
    technical_summary, = (
        source for source in benchmark["source"]["comparison_sources"]
        if source["pdf_sha256"] == (
            "3df6731e9cae9e22f291f69c30e336a5429711de2e1c674b8d38048ad00653b6"
        )
    )
    assert technical_summary["pdf_page"] == 39
    assert technical_summary["vehicle_mass_data"]["snapshots"][1] == {
        "event": "liftoff", "value": 6398500,
    }
    assert technical_summary["approximate_propellant_consumption"][1]["value_lb"] == 971450


def test_apollo11_published_event_sequence_and_parking_orbit_values():
    benchmark = apollo11_benchmark()
    events = benchmark["events"]
    by_id = {event["id"]: event for event in events}

    assert len(by_id) == len(events) == 11
    assert [event["time_s"] for event in events] == sorted(
        event["time_s"] for event in events
    )
    assert by_id["maximum_dynamic_pressure"]["time_s"] == 81.0
    assert by_id["s_ic_center_engine_cutoff"]["time_s"] == 135.0
    assert by_id["s_ic_outboard_engine_cutoff"]["time_s"] == 160.819
    assert by_id["s_ii_center_engine_cutoff_table_2_1"]["time_s"] == 459.8
    assert by_id["s_ii_center_engine_cutoff_table_2_4"]["time_s"] == 462.0
    assert by_id["s_ii_engine_cutoff"]["time_s"] == 551.384
    assert by_id["s_ivb_guidance_cutoff_signal_1"]["time_s"] == 699.22793
    assert by_id["parking_orbit_insertion"]["time_s"] == 709.23

    assert benchmark["maximum_dynamic_pressure"] == {
        "time_s": 81.0,
        "value_pa": 34725.243,
        "source_table": "2.4",
    }
    launch_state = benchmark["table_2_2_launch_state"]
    assert launch_state["source_pdf_page"] == 18
    assert abs(hypot(*launch_state["position_m"])-launch_state["geocentric_radius_m"]) < 0.2
    assert abs(hypot(*launch_state["velocity_m_s"])-launch_state["inertial_speed_m_s"]) < 0.01
    checkpoints = benchmark["table_2_2_frame_checkpoints"]
    assert len(checkpoints) == 4
    assert [row["time_s"] for row in checkpoints] == sorted(
        row["time_s"] for row in checkpoints
    )
    assert all(row["source_table"] == "2.2" for row in checkpoints)
    mass_ledger = benchmark["table_2_2_mass_ledger"]
    sic_split = [row for row in mass_ledger
                 if row["event"] == "s_ic_s_ii_separation"]
    s2_split = [row for row in mass_ledger
                if row["event"] == "s_ii_s_ivb_separation"]
    assert [row["event_side"] for row in sic_split] == ["pre_reset", "post_reset"]
    assert [row["event_side"] for row in s2_split] == ["pre_reset", "post_reset"]
    assert abs(
        sic_split[0]["total_vehicle_mass_kg"]-sic_split[1]["total_vehicle_mass_kg"]-165460.77
    ) < 1e-8
    assert abs(
        s2_split[0]["total_vehicle_mass_kg"]-s2_split[1]["total_vehicle_mass_kg"]-46450.49
    ) < 1e-8
    mass_discrepancy = next(
        item for item in benchmark["source_discrepancies"]
        if item["event"] == "s_ii_cutoff_to_s_ivb_ullage_mass"
    )
    assert mass_discrepancy["reported_mass_increase_kg"] == 919.32
    insertion = benchmark["parking_orbit_insertion"]
    assert insertion["geocentric_radius_m"] == 6563308.7
    assert insertion["inertial_speed_m_s"] == 7793.1014
    assert insertion["inertial_path_angle_deg"] == 90.001449
    assert insertion["inclination_deg"] == 32.531447
    assert insertion["eccentricity"] == 0.0010449
    assert insertion["orbital_period_s"] == 5284.3769
    state = benchmark["table_2_2_insertion_state"]
    assert state["source_pdf_page"] == 54
    assert abs(hypot(*state["position_m"])-insertion["geocentric_radius_m"]) < 0.1
    assert abs(hypot(*state["velocity_m_s"])-insertion["inertial_speed_m_s"]) < 0.001
    discrepancies = benchmark["source_discrepancies"]
    assert len(discrepancies) == 4
    assert all(item["resolution"].startswith("Unresolved") for item in discrepancies)


def test_apollo11_sic_reference_is_hash_pinned_and_source_closed():
    provenance = apollo11_sic_reference_provenance()
    resource = data_resource("benchmarks/apollo11/apollo11_sic_reference.csv")
    rows = read_apollo11_sic_reference()

    assert sha256(resource.read_bytes()).hexdigest() == provenance["output_sha256"]
    assert provenance["source_pdf_sha256"] == (
        "55b94c5947c91a3cd0539601517c82941a04ec9631dbb90458275664b855a7b3"
    )
    assert provenance["status"] == (
        "SOURCE_CLOSED_OPERATIONAL_GUIDANCE_REFERENCE; NOT FLIGHT TRUTH"
    )
    assert len(rows) == provenance["record_count"] == 38
    assert all(row["phase"] == "s_ic" for row in rows)
    assert set(rows[0]) == {
        "time_from_first_motion_s",
        "event",
        "phase",
        "geocentric_radius_m",
        "inertial_speed_m_s",
        "space_fixed_x_m",
        "space_fixed_y_m",
        "space_fixed_z_m",
        "space_fixed_vx_m_s",
        "space_fixed_vy_m_s",
        "space_fixed_vz_m_s",
        "event_side",
        "event_source",
        "transcription_corrections",
        "source_pages",
    }
    assert [row["time_from_first_motion_s"] for row in rows] == sorted(
        row["time_from_first_motion_s"] for row in rows
    )

    events = {row["event"]: row["time_from_first_motion_s"] for row in rows if row["event"]}
    assert events["S-IC CECO"] == 135.0
    assert events["S-IC OECO"] == 160.82
    assert events["S-IC/S-II SEP"] == 161.59

    position_residuals = [
        abs(hypot(
            row["space_fixed_x_m"],
            row["space_fixed_y_m"],
            row["space_fixed_z_m"],
        )-row["geocentric_radius_m"])
        for row in rows
    ]
    speed_residuals = [
        abs(hypot(
            row["space_fixed_vx_m_s"],
            row["space_fixed_vy_m_s"],
            row["space_fixed_vz_m_s"],
        )-row["inertial_speed_m_s"])
        for row in rows
    ]
    validation = provenance["validation"]
    assert max(position_residuals) == pytest.approx(
        validation["max_abs_position_norm_residual_m"], abs=1e-9,
    )
    assert max(speed_residuals) == pytest.approx(
        validation["max_abs_velocity_norm_residual_m_s"], abs=1e-9,
    )
    assert max(position_residuals) <= validation["position_norm_tolerance_m"]
    assert max(speed_residuals) <= validation["velocity_norm_tolerance_m_s"]
    row_135 = next(row for row in rows if row["time_from_first_motion_s"] == 135.0)
    assert {"13", "14", "18"} <= set(row_135["source_pages"].split(";"))
    separation = next(row for row in rows if row["event"] == "S-IC/S-II SEP")
    assert separation["event_side"] == "pre_reset"
    assert "18" in separation["source_pages"].split(";")


def test_apollo11_launch_site_longitude_conventions_close():
    benchmark = apollo11_benchmark()
    site = benchmark["launch_site"]
    assert abs(site["longitude_deg_east"] - 360.0 - site["longitude_deg_west"]) < 1e-12
    assert site["latitude_deg_north"] == 28.608422


def test_nasa42_case17_models_and_anonymized_reference_family_are_pinned():
    config = nasa42_case17()
    provenance = nasa42_case17_provenance()
    case_resource = data_resource("benchmarks/nasa42_case17/case.json")
    reference_resource = data_resource("benchmarks/nasa42_case17/reference_1s.csv")
    assert sha256(case_resource.read_bytes()).hexdigest() == provenance["payload"]["config_sha256"]
    assert sha256(reference_resource.read_bytes()).hexdigest() == provenance["payload"]["reference_csv_sha256"]
    assert b"\r\n" not in reference_resource.read_bytes()
    assert "normalize line endings to LF" in provenance["extraction"][
        "model_normalization"
    ]
    source_model_hashes = {
        "twostage_aero.dml": "49df37f2ab8ad3b9c6f181bb3c32ad828304870371b3e058512c08e359579a27",
        "twostage_inertia.dml": "277707b8e1f26f99f6b2068c79a243bd3a450e325e2ef7dbc2f9a39e7b52570b",
        "twostage_prop.dml": "297cb7b8950a1ba5185fca98b5966cb8ad14cf76f8d2d0af9b17e7b0785197ee",
    }
    for name, record in provenance["payload"]["model_files"].items():
        model_resource = data_resource(record["path"])
        model_bytes = model_resource.read_bytes()
        assert sha256(model_bytes).hexdigest() == record["sha256"]
        assert record["source_sha256"] == source_model_hashes[name]
        assert all(line == line.rstrip(b" \t\r") for line in model_bytes.splitlines())
    assert config["source"]["report_pdf_sha256"] == (
        "2786f37fa02dba67e776de294038f7d8734b3de2cdd14d70b70a0db4b52f41f0"
    )
    assert config["classification"] == "IDEALIZED_INTERTOOL_VERIFICATION_CASE_NOT_REAL_FLIGHT"
    assert config["scenario"]["duration_s"] == 200.0
    assert config["scenario"]["interstage_coast_after_first_burnout_s"] == 96.79
    assert config["scenario"]["initial_body_rate_relative_to_launch_site_roll_pitch_yaw_deg_s"] == [
        0.0, 0.0, 0.0,
    ]
    assert config["scenario"]["reference_initial_body_rate_wrt_ei_roll_pitch_yaw_deg_s"] == [
        0.0, -0.00417807413224, 0.0,
    ]
    assert config["scenario"]["reference_initial_body_rate_sample_time_s"] == 0.0
    assert "not the published scenario input" in config["scenario"][
        "reference_initial_body_rate_note"
    ]
    assert "east component includes launch-site co-rotation" in config["scenario"][
        "initial_velocity_frame_note"
    ]
    assert config["vehicle"]["stage_1"]["propellant_mass_kg"] == 180000.0
    assert config["vehicle"]["stage_2"]["propellant_mass_kg"] == 80000.0
    discrepancies = {item["topic"] for item in config["source_discrepancies"]}
    assert discrepancies == {
        "initial_velocity",
        "initial_body_rate_frame",
        "thermosphere_outputs",
        "initial_vehicle_geometry",
        "yaw_inertia",
    }
    velocity_discrepancy = next(
        item for item in config["source_discrepancies"]
        if item["topic"] == "initial_velocity"
    )
    assert "0.32808399 ft/s" in velocity_discrepancy["report_value"]
    frame = provenance["reference_frame_and_datum"]["position_eci_m"]
    assert "+X radial-outward, +Y east, and +Z north" in frame
    assert "not a published GCRF alignment" in frame
    assert provenance["reference_frame_and_datum"][
        "eci_frame_orientation_epoch_s"
    ] == 0.0
    mass_properties = config["vehicle"]["mass_properties"]
    assert mass_properties["stage_1_ignition"]["inertia_body_kg_m2"] == [
        353250.0, 33501637.473461, 33501637.473461,
    ]
    assert mass_properties["stage_1_ignition"]["table_16_inertia_body_kg_m2"] == [
        353250.0, 33501637.473461, 353250.0,
    ]
    perigee_audit = provenance["derived_reference_audits"]["terminal_two_body_conic"]
    assert perigee_audit["status"] == "SOURCE_DISCREPANCY"
    assert set(perigee_audit["perigee_altitude_m"]) == {"sim_04", "sim_05", "sim_06"}
    assert all(value < 0.0 for value in perigee_audit["perigee_altitude_m"].values())
    assert "terminal_perigee_claim" in {
        item["topic"] for item in provenance["source_discrepancies"]
    }
    assert "altitude_msl_m" in provenance["reference_csv_columns"]
    assert "body_rate_wrt_ei_pitch_rad_s" in provenance["reference_csv_columns"]
    assert "body_rate_pitch_rad_s" not in provenance["reference_csv_columns"]

    rows = read_nasa42_case17_reference()
    assert len(rows) == 603
    assert {row["tool_id"] for row in rows} == {"sim_04", "sim_05", "sim_06"}
    assert all(sum(row["time_s"] == t for row in rows) == 3 for t in range(201))
    sim04_final = next(row for row in rows if row["tool_id"] == "sim_04" and row["time_s"] == 200)
    assert sim04_final["altitude_msl_m"] == pytest.approx(824969.763884 * 0.3048, abs=1e-6)
