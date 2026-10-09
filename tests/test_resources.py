from ssapy_data_propulsion import data_resource, iter_data_files


def test_component_data_is_packaged():
    assert data_resource().is_dir()
    assert next(iter_data_files()).is_file()
