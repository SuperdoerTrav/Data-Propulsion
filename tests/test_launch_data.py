"""Pinned Apollo 11 event and insertion benchmark data."""

from hashlib import sha256
import json
from math import hypot

import pytest

from ssa_data_launch import (
    apollo11_benchmark,
    apollo11_sic_reference_provenance,
    apollo11_sii_initial_reference_provenance,
    apollo11_sii_source_closed_provenance,
    data_resource,
    falcon_first_gp_provenance,
    falcon_first_gp_records,
    nasa42_case17,
    nasa42_case17_provenance,
    read_apollo11_sic_reference,
    read_apollo11_sii_initial_reference,
    read_apollo11_sii_source_closed_samples,
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
    assert [
        (row["time_s"], row["latitude_deg_north"], row["longitude_deg_west"])
        for row in provenance["validation"]["geodetic_frame_checkpoints"]
    ] == [
        (0.0, 28.6084, -80.60),
        (40.0, 28.6083, -80.60),
        (80.0, 28.6208, -80.56),
        (100.0, 28.6436, -80.48),
        (135.0, 28.7363, -80.15),
        (161.59, 28.8658, -79.69),
    ]
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


def test_apollo11_early_sii_reference_is_hash_pinned_and_source_closed():
    provenance = apollo11_sii_initial_reference_provenance()
    resource = data_resource(
        "benchmarks/apollo11/apollo11_sii_initial_reference.csv"
    )
    rows = read_apollo11_sii_initial_reference()

    assert sha256(resource.read_bytes()).hexdigest() == provenance["output_sha256"]
    assert provenance["source_pdf_sha256"] == (
        "55b94c5947c91a3cd0539601517c82941a04ec9631dbb90458275664b855a7b3"
    )
    assert provenance["status"] == (
        "SOURCE_CLOSED_OPERATIONAL_GUIDANCE_REFERENCE; NOT FLIGHT TRUTH"
    )
    assert len(rows) == provenance["record_count"] == 5
    assert [row["time_from_first_motion_s"] for row in rows] == [
        161.59, 162.22, 165.22, 170.0, 175.0,
    ]
    assert all(row["phase"] == "s_ii" for row in rows)
    assert rows[0]["event"] == "S-IC/S-II SEP"
    assert rows[0]["event_side"] == "post_reset"
    assert rows[1]["event"] == "S-II ENGINE START"
    assert rows[2]["event"] == "S-II 90 THRUST"
    assert all("35" in row["source_pages"].split(";") for row in rows)
    assert all("PDF p.35" in row["transcription_corrections"] for row in rows)
    expected_states = {
        161.59: (
            6440658.81, 2765.96,
            (6438562.7, 39054.5, 159600.6),
            (858.782, 115.035, 2626.743),
        ),
        162.22: (
            6441239.5, 2764.33,
            (6439101.9, 39127.0, 161255.5),
            (852.869, 115.006, 2626.956),
        ),
        165.22: (
            6443959.75, 2760.10,
            (6441618.8, 39471.8, 169139.3),
            (825.870, 114.858, 2631.143),
        ),
        170.0: (
            6448169.69, 2777.47,
            (6445482.7, 40020.2, 181783.1),
            (791.375, 114.513, 2659.883),
        ),
        175.0: (
            6452435.13, 2801.37,
            (6449355.2, 40591.7, 195168.8),
            (757.676, 114.094, 2694.544),
        ),
    }
    for row in rows:
        radius, speed, position, velocity = expected_states[
            row["time_from_first_motion_s"]
        ]
        assert row["geocentric_radius_m"] == radius
        assert row["inertial_speed_m_s"] == speed
        assert tuple(row[f"space_fixed_{axis}_m"] for axis in "xyz") == position
        assert tuple(row[f"space_fixed_v{axis}_m_s"] for axis in "xyz") == velocity

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
        validation["max_abs_position_norm_residual_m"], abs=1e-12,
    )
    assert max(speed_residuals) == pytest.approx(
        validation["max_abs_velocity_norm_residual_m_s"], abs=1e-12,
    )
    assert max(position_residuals) <= validation["position_norm_tolerance_m"]
    assert max(speed_residuals) <= validation["velocity_norm_tolerance_m_s"]
    assert provenance["scope"]["interpretation"] == (
        "Sparse source-closed early S-II states; not a continuous trajectory, "
        "flight truth, or ascent validation."
    )
    assert [
        (
            point["time_s"],
            point["latitude_deg_north"],
            point["longitude_deg_west"],
            point["source_pdf_page"],
        )
        for point in validation["geodetic_frame_checkpoints"]
    ] == [
        (161.59, 28.8658, -79.69, 27),
        (162.22, 28.8695, -79.68, 27),
        (165.22, 28.8872, -79.61, 27),
        (170.0, 28.9154, -79.51, 27),
        (175.0, 28.9453, -79.40, 27),
    ]


def test_apollo11_sii_sparse_samples_fail_closed_and_audit_exclusions():
    provenance = apollo11_sii_source_closed_provenance()
    resource = data_resource(
        "benchmarks/apollo11/apollo11_sii_source_closed_samples.csv"
    )
    rows = read_apollo11_sii_source_closed_samples()
    validation = provenance["validation"]

    assert sha256(resource.read_bytes()).hexdigest() == provenance["output_sha256"]
    assert provenance["source_pdf_sha256"] == (
        "55b94c5947c91a3cd0539601517c82941a04ec9631dbb90458275664b855a7b3"
    )
    assert provenance["status"] == (
        "PARTIAL_SOURCE_CLOSED_OPERATIONAL_GUIDANCE_SAMPLES; NOT FLIGHT TRUTH"
    )
    assert len(rows) == validation["record_count"] == 53
    assert validation["candidate_record_count"] == 84
    assert len(validation["incomplete_records"]) == 7
    assert len(validation["closure_failed_records"]) == 2
    assert len(validation["review_withheld_records"]) == 22
    assert (
        len(rows)
        + len(validation["incomplete_records"])
        + len(validation["closure_failed_records"])
        + len(validation["review_withheld_records"])
        == validation["candidate_record_count"]
    )
    times = [row["time_from_first_motion_s"] for row in rows]
    assert times == validation["sample_times_s"] == sorted(times)
    assert rows[0]["time_from_first_motion_s"] == 161.59
    assert rows[0]["event_side"] == "post_reset"
    expected_manual_samples = {
        180.0: (2826.64, 6456565.75, 6453059.8, 41161.1, 208729.7,
                724.193, 113.676, 2729.928),
        201.42: (2947.38, 6472793.75, 6467060.6, 43576.1, 268865.9,
                 584.008, 111.808, 2886.782),
        200.0: (2938.77, 6471789.69, 6466225.4, 43417.3, 264777.1,
                593.132, 111.936, 2876.111),
        205.0: (2969.45, 6475284.25, 6469110.6, 43975.9, 279251.9,
                561.007, 111.483, 2913.841),
        210.0: (3000.23, 6478664.63, 6471841.2, 44532.4, 293913.7,
                532.027, 111.144, 2950.591),
        215.0: (3031.04, 6481949.88, 6474435.3, 45087.3, 308756.2,
                505.490, 110.798, 2986.539),
        225.0: (3095.61, 6488242.81, 6479216.6, 46192.4, 338990.5,
                450.693, 110.238, 3060.636),
        240.0: (3198.52, 6496994.25, 6485355.8, 47839.4, 385755.3,
                367.708, 109.346, 3175.433),
        245.0: (3234.48, 6499731.75, 6487124.6, 48385.5, 401730.5,
                339.815, 109.108, 3214.725),
        250.0: (3271.25, 6502381.25, 6488753.8, 48930.5, 417903.4,
                311.822, 108.871, 3254.537),
        255.0: (3308.86, 6504943.69, 6490242.6, 49474.3, 434276.7,
                283.724, 108.649, 3294.884),
        260.0: (3347.30, 6507420.38, 6491590.8, 50017.0, 450853.1,
                255.521, 108.438, 3335.773),
        265.0: (3386.62, 6509812.56, 6492797.7, 50558.7, 467635.4,
                227.225, 108.231, 3377.250),
        270.0: (3426.80, 6512121.63, 6493862.9, 51099.3, 484626.6,
                198.813, 108.030, 3419.321),
        280.0: (3509.79, 6516494.88, 6495565.1, 52177.6, 519247.6,
                141.562, 107.637, 3505.286),
        285.0: (3552.60, 6518561.81, 6496200.9, 52715.3, 536883.5,
                112.737, 107.442, 3549.190),
        290.0: (3596.30, 6520550.69, 6496692.3, 53252.1, 554740.5,
                83.769, 107.246, 3593.721),
        295.0: (3640.87, 6522463.06, 6497038.4, 53787.8, 572821.7,
                54.649, 107.049, 3638.888),
        300.0: (3686.34, 6524300.19, 6497238.5, 54322.5, 591130.4,
                25.371, 106.849, 3684.703),
        305.0: (3732.71, 6526063.63, 6497291.8, 54856.3, 609669.9,
                -4.074, 106.645, 3731.180),
        310.0: (3779.99, 6527754.75, 6497197.4, 55389.0, 628443.4,
                -33.698, 106.440, 3778.338),
        315.0: (3828.20, 6529375.25, 6496954.5, 55920.7, 647454.4,
                -63.512, 106.234, 3826.195),
        320.0: (3877.35, 6530926.44, 6496561.9, 56451.3, 666706.5,
                -93.529, 106.025, 3874.770),
        325.0: (3927.46, 6532410.06, 6496018.8, 56980.9, 686203.3,
                -123.764, 105.812, 3924.081),
        330.0: (3978.54, 6533827.56, 6495323.9, 57509.4, 705948.5,
                -154.230, 105.598, 3974.145),
        335.0: (4030.61, 6535180.56, 6494476.1, 58036.9, 725946.0,
                -184.938, 105.379, 4024.981),
        340.0: (4083.67, 6536470.69, 6493474.1, 58563.2, 746199.6,
                -215.901, 105.160, 4076.606),
        345.0: (4137.76, 6537699.56, 6492316.7, 59088.5, 766713.3,
                -247.134, 104.940, 4129.038),
        350.0: (4192.88, 6538868.88, 6491002.3, 59612.6, 787491.3,
                -278.646, 104.714, 4182.302),
        355.0: (4249.07, 6539980.50, 6489529.8, 60135.6, 808537.7,
                -310.454, 104.485, 4236.423),
    }
    sample_fields = (
        "inertial_speed_m_s", "geocentric_radius_m",
        "space_fixed_x_m", "space_fixed_y_m", "space_fixed_z_m",
        "space_fixed_vx_m_s", "space_fixed_vy_m_s", "space_fixed_vz_m_s",
    )
    for time_s, expected_values in expected_manual_samples.items():
        assert time_s in times
        sample = next(
            row for row in rows
            if row["time_from_first_motion_s"] == time_s
        )
        assert tuple(sample[field] for field in sample_fields) == expected_values
        assert all(
            f"table 2.2 column {column}: manually verified" in (
                sample["transcription_corrections"].lower()
            )
            for column in (5, 8, 25, 26, 27, 28, 29, 30)
        )
    assert validation["geodetic_frame_checkpoints"] == [
        {
            "time_s": time_s,
            "latitude_deg_north": latitude,
            "longitude_deg_west": longitude_west,
            "source_table": "2.2",
            "source_pdf_page": 27,
            "printed_page": 21,
        }
        for time_s, latitude, longitude_west in (
            (180.0, 28.9754, -79.29),
            (185.0, 29.0059, -79.18),
            (190.0, 29.0367, -79.06),
            (195.0, 29.0678, -78.95),
            (200.0, 29.0992, -78.83),
            (201.42, 29.1082, -78.79),
            (205.0, 29.1310, -78.71),
            (210.0, 29.1631, -78.59),
            (215.0, 29.1954, -78.46),
            (220.0, 29.2281, -78.34),
            (225.0, 29.2611, -78.21),
            (230.0, 29.2943, -78.08),
            (235.0, 29.3279, -77.95),
            (240.0, 29.3617, -77.82),
            (245.0, 29.3958, -77.69),
            (250.0, 29.4303, -77.55),
            (255.0, 29.4650, -77.41),
            (260.0, 29.5000, -77.27),
            (265.0, 29.5354, -77.13),
            (270.0, 29.5710, -76.98),
            (275.0, 29.6069, -76.84),
            (280.0, 29.6431, -76.69),
            (285.0, 29.6796, -76.54),
            (290.0, 29.7164, -76.38),
            (295.0, 29.7535, -76.23),
            (300.0, 29.7909, -76.07),
            (305.0, 29.8286, -75.91),
            (310.0, 29.8665, -75.75),
            (315.0, 29.9048, -75.58),
            (320.0, 29.9433, -75.41),
            (325.0, 29.9822, -75.24),
            (330.0, 30.0213, -75.07),
            (335.0, 30.0607, -74.89),
            (340.0, 30.1004, -74.71),
            (345.0, 30.1403, -74.53),
            (350.0, 30.1806, -74.35),
            (355.0, 30.2211, -74.16),
            (360.0, 30.2619, -73.97),
            (365.0, 30.3030, -73.78),
        )
    ]
    assert times[-1] == 545.0
    assert max(right-left for left, right in zip(times, times[1:])) > 5.0
    assert all(
        row["phase"] == "s_ii"
        and row["source_pages"]
        and (
            not row["transcription_corrections"]
            or "manually verified" in row["transcription_corrections"]
        )
        for row in rows
    )

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
    assert max(position_residuals) == pytest.approx(
        validation["max_abs_position_norm_residual_m"], abs=1e-12,
    )
    assert max(speed_residuals) == pytest.approx(
        validation["max_abs_velocity_norm_residual_m_s"], abs=1e-12,
    )
    assert max(position_residuals) <= validation["position_norm_tolerance_m"]
    assert max(speed_residuals) <= validation["velocity_norm_tolerance_m_s"]
    assert "sparse" in validation["interpretation"]


def test_falcon_first_gp_records_are_pinned_and_cover_both_vehicle_families():
    records = falcon_first_gp_records()
    provenance = falcon_first_gp_provenance()
    resource = data_resource("benchmarks/falcon/falcon_first_gp.json")

    assert sha256(resource.read_bytes()).hexdigest() == provenance["payload_sha256"]
    assert len(records) == provenance["record_count"] == 4
    assert {
        (record["OBJECT_ID"], record["OBJECT_NAME"], record["EPOCH"])
        for record in records
    } == {
        ("2022-157A", "EUTELSAT 10B", "2022-11-23T05:18:12.220992"),
        ("2022-157B", "FALCON 9 R/B", "2022-11-23T08:32:56.609664"),
        ("2019-021A", "ARABSAT-6A", "2019-04-12T00:41:56.374080"),
        ("2019-021B", "FALCON HEAVY R/B", "2019-04-12T02:59:52.266336"),
    }
    assert all(record["CLASSIFICATION_TYPE"] == "U" for record in records)
    assert provenance["status"] == "PUBLIC_GP_FITS; NOT ASCENT TELEMETRY"
    assert "covariance" not in provenance


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
