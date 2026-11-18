"""Check release metadata, launch-data compactness and required wheel resources."""

import argparse
from email.parser import BytesParser
from pathlib import Path
import tarfile
import zipfile

REQUIRED = {
    "ssa_data_launch/data/benchmarks/flight_sources.json",
    "ssa_data_launch/data/benchmarks/apollo11/postflight_uncertainties.json",
    "ssa_data_launch/data/benchmarks/apollo11/apollo11_sic_reference.csv",
    "ssa_data_launch/data/benchmarks/apollo11/apollo11_sii_initial_reference.csv",
    "ssa_data_launch/data/benchmarks/apollo11/apollo11_sii_source_closed_samples.csv",
    "ssa_data_launch/data/benchmarks/falcon/falcon_first_gp.json",
    "ssa_data_launch/data/benchmarks/nasa42_case17/reference_1s.csv",
}
LAUNCH_SUFFIXES = {".py", ".json", ".csv", ".dml"}
UPLOAD_LIMIT = 100 * 1024 * 1024
LAUNCH_LIMIT = 512 * 1024


def check(directory, version):
    wheels = list(directory.glob("*.whl"))
    sdists = list(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("release directory must contain exactly one wheel and one sdist")
    for artifact in (*wheels, *sdists):
        if artifact.stat().st_size >= UPLOAD_LIMIT:
            raise ValueError(f"artifact exceeds conservative 100 MiB ceiling: {artifact}")
    with zipfile.ZipFile(wheels[0]) as archive:
        if archive.testzip():
            raise ValueError("wheel CRC check failed")
        names = set(archive.namelist())
        if not REQUIRED <= names:
            raise ValueError(f"missing wheel resources: {sorted(REQUIRED - names)}")
        metadata_name, = (name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        if metadata["Name"] != "ssa-data-propulsion" or metadata["Version"] != version:
            raise ValueError("wheel name/version differs from requested release")
        launch_bytes = 0
        for item in archive.infolist():
            if item.is_dir() or not item.filename.startswith("ssa_data_launch/"):
                continue
            if Path(item.filename).suffix not in LAUNCH_SUFFIXES:
                raise ValueError(f"unexpected launch file type: {item.filename}")
            launch_bytes += item.file_size
        if launch_bytes >= LAUNCH_LIMIT:
            raise ValueError("launch namespace exceeds 512 KiB compactness budget")
    with tarfile.open(sdists[0], "r:gz") as archive:
        members = archive.getmembers()
        source_names = {"/".join(member.name.split("/")[2:])
                        for member in members if "/src/" in member.name}
        if not REQUIRED <= source_names:
            raise ValueError("sdist does not contain every required launch resource")
        for member in members:
            if "AGENTS.md" in member.name or "/bundles/" in member.name:
                raise ValueError(f"working notes/evidence bundle leaked into sdist: {member.name}")
    print(f"PASS: {version}; launch namespace {launch_bytes} bytes; "
          f"wheel {wheels[0].stat().st_size} bytes; sdist {sdists[0].stat().st_size} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--version", required=True)
    arguments = parser.parse_args()
    check(arguments.directory, arguments.version)
