from scripts.collect_runtime_licenses import collect_runtime_licenses


def test_browser_tls_runtime_notice_is_in_distribution(tmp_path):
    records = collect_runtime_licenses(tmp_path / 'licenses')
    record = next((item for item in records if item['name'].lower().replace('_', '-') == 'curl-cffi'), None)
    assert record is not None, 'Vimeo TLS dependency must ship its notice'
    assert record['license_files']
    assert all((tmp_path / 'licenses' / name).is_file() for name in record['license_files'])
