"""Published engineering bounds and compact source-index consistency."""

from hashlib import sha256
import json

from ssa_data_launch import (
    apollo11_postflight_uncertainties,
    data_resource,
    flight_source_catalog,
)


def test_postflight_bounds_preserve_published_component_estimates():
    """D5-15560-6 p.5-3: literal SI component bounds, not inferred covariance."""
    record = apollo11_postflight_uncertainties()
    assert record["source"]["printed_page"] == "5-3"
    assert record["source"]["pdf_page"] == 69
    assert [row[1:] for row in record["estimates"]] == [
        [60.0, 0.4], [350.0, 0.7], [500.0, 1.0],
        [750.0, 1.5], [1500.0, 2.0],
    ]
    assert record["units"] == {"position": "m", "velocity": "m/s"}
    assert record["frame"].startswith("PACSS10")
    assert record["confidence_level"] is None
    assert record["covariance"] is None


def test_source_catalog_links_existing_resources_and_matching_provenance():
    """Metadata contract: existing files and source identities, no invented data."""
    catalog = flight_source_catalog()
    sources = {source["id"]: source for source in catalog["sources"]}
    assert len(sources) == len(catalog["sources"])
    for source in sources.values():
        assert source["url"].startswith("https://")
        for resource in source["resources"]:
            assert data_resource("benchmarks/" + resource).is_file()
    uncertainties = apollo11_postflight_uncertainties()
    assert sources[uncertainties["source_id"]]["pdf_sha256"] == (
        uncertainties["source"]["pdf_sha256"]
    )
    assert set(catalog["missing_data"]) == {"apollo", "falcon", "artemis"}
    assert sources["artemis_postflight_validation"]["resources"] == []
    assert sources["falcon_eutelsat_webcast"]["resources"] == []
    assert sources["falcon_arabsat_webcast"]["resources"] == []


def test_existing_falcon_payload_is_not_duplicated_or_modified():
    """Integrity: four records still match the established provider payload digest."""
    resource = data_resource("benchmarks/falcon/falcon_first_gp.json")
    provenance = json.loads(data_resource(
        "benchmarks/falcon/falcon_first_gp.provenance.json"
    ).read_text())
    assert sha256(resource.read_bytes()).hexdigest() == provenance["payload_sha256"]


def test_new_source_resources_stay_compact():
    """Packaging budget: metadata plus estimates remain below 16 KiB."""
    resources = [
        data_resource("benchmarks/flight_sources.json"),
        data_resource("benchmarks/apollo11/postflight_uncertainties.json"),
    ]
    assert sum(len(resource.read_bytes()) for resource in resources) < 16 * 1024
