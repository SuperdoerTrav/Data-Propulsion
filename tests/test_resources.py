from ssa_data_propulsion import data_resource, iter_data_files
from ssa_data_launch import data_resource as launch_data_resource


def test_component_data_is_packaged():
    assert data_resource().is_dir()
    assert next(iter_data_files()).is_file()


def test_launch_benchmark_data_is_packaged():
    assert launch_data_resource(
        "benchmarks/apollo11/apollo11_benchmark.json"
    ).is_file()
    assert launch_data_resource("benchmarks/nasa42_case17/reference_1s.csv").is_file()
