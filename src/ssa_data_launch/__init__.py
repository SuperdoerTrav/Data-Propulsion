"""Public launch reference data distributed separately from SSATK."""

import json
import csv
from importlib.resources import files

__all__ = [
    "apollo11_benchmark",
    "apollo11_provenance",
    "apollo11_sic_reference_provenance",
    "apollo11_sii_initial_reference_provenance",
    "apollo11_sii_source_closed_provenance",
    "data_resource",
    "falcon_first_gp_provenance",
    "falcon_first_gp_records",
    "nasa42_case17",
    "nasa42_case17_provenance",
    "read_apollo11_sic_reference",
    "read_apollo11_sii_initial_reference",
    "read_apollo11_sii_source_closed_samples",
    "read_nasa42_case17_reference",
]


def data_resource(relative_path):
    """Return one installed launch data resource as an importlib Traversable."""
    parts = str(relative_path).replace("\\", "/").split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("relative_path must be a safe nonempty package-relative path")
    resource = files(__name__).joinpath("data")
    for part in parts:
        resource = resource.joinpath(part)
    if not resource.is_file():
        raise FileNotFoundError(f"launch data resource not found: {relative_path}")
    return resource


def apollo11_provenance():
    """Return the source and limitations record for the Apollo 11 benchmark."""
    resource = data_resource("benchmarks/apollo11/provenance.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def apollo11_benchmark():
    """Return the audited Apollo 11 event and parking-orbit summary."""
    resource = data_resource("benchmarks/apollo11/apollo11_benchmark.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def apollo11_sic_reference_provenance():
    """Return source and closure metadata for the 38-sample S-IC arc."""
    resource = data_resource(
        "benchmarks/apollo11/apollo11_sic_reference.csv.provenance.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def apollo11_sii_initial_reference_provenance():
    """Return source and closure metadata for the initial five-record S-II segment."""
    resource = data_resource(
        "benchmarks/apollo11/apollo11_sii_initial_reference.csv.provenance.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def apollo11_sii_source_closed_provenance():
    """Return coverage and exclusions for sparse source-closed S-II samples."""
    resource = data_resource(
        "benchmarks/apollo11/apollo11_sii_source_closed_samples.csv.provenance.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def falcon_first_gp_provenance():
    """Return provenance and limitations for the Falcon first-GP records."""
    resource = data_resource("benchmarks/falcon/falcon_first_gp.provenance.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def falcon_first_gp_records():
    """Return four CelesTrak GP OMM records for Falcon 9 and Falcon Heavy."""
    resource = data_resource("benchmarks/falcon/falcon_first_gp.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def read_apollo11_sic_reference():
    """Read the source-closed Apollo 11 S-IC operational state history."""
    resource = data_resource("benchmarks/apollo11/apollo11_sic_reference.csv")
    text_columns = {
        "phase", "event", "event_side", "event_source", "source_pages",
        "transcription_corrections",
    }
    with resource.open("r", encoding="utf-8", newline="") as handle:
        return [
            {
                key: value if key in text_columns or value == "" else float(value)
                for key, value in row.items()
            }
            for row in csv.DictReader(handle)
        ]


def read_apollo11_sii_initial_reference():
    """Read source-closed S-II staging/early-ascent operational states."""
    resource = data_resource(
        "benchmarks/apollo11/apollo11_sii_initial_reference.csv"
    )
    text_columns = {
        "phase", "event", "event_side", "event_source", "source_pages",
        "transcription_corrections",
    }
    with resource.open("r", encoding="utf-8", newline="") as handle:
        return [
            {
                key: value if key in text_columns or value == "" else float(value)
                for key, value in row.items()
            }
            for row in csv.DictReader(handle)
        ]


def read_apollo11_sii_source_closed_samples():
    """Read sparse S-II samples with source-closed state-vector norms."""
    resource = data_resource(
        "benchmarks/apollo11/apollo11_sii_source_closed_samples.csv"
    )
    text_columns = {
        "phase", "event", "event_side", "event_source", "source_pages",
        "transcription_corrections",
    }
    with resource.open("r", encoding="utf-8", newline="") as handle:
        return [
            {
                key: value if key in text_columns or value == "" else float(value)
                for key, value in row.items()
            }
            for row in csv.DictReader(handle)
        ]


def nasa42_case17():
    """Return NASA NESC's idealized two-stage Atmospheric Case 17 inputs."""
    resource = data_resource("benchmarks/nasa42_case17/case.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def nasa42_case17_provenance():
    """Return the source hashes and extraction metadata for Case 17."""
    resource = data_resource("benchmarks/nasa42_case17/provenance.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def read_nasa42_case17_reference():
    """Read three anonymized NASA check-case outputs at one-second epochs.

    ``tool_id`` remains a string; every other CSV column is returned as a
    float. The rows are inter-tool reference solutions, not flight truth.
    """
    resource = data_resource("benchmarks/nasa42_case17/reference_1s.csv")
    with resource.open("r", encoding="utf-8", newline="") as handle:
        return [
            {
                key: value if key == "tool_id" else float(value)
                for key, value in row.items()
            }
            for row in csv.DictReader(handle)
        ]
