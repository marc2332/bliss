from bliss.icat.client.url import normalize_url


def test_normlize_url():
    url = "sub.name.root"
    expected = "//sub.name.root"
    assert normalize_url(url) == expected

    url = "sub.name.root"
    expected = "http://sub.name.root"
    assert normalize_url(url, default_scheme="http") == expected
    url = "https://sub.name.root"
    expected = "https://sub.name.root"
    assert normalize_url(url, default_scheme="http") == expected

    url = "sub.name.root"
    expected = "//sub.name.root:80"
    assert normalize_url(url, default_port=80) == expected
    url = "https://sub.name.root"
    expected = "https://sub.name.root:80"
    assert normalize_url(url, default_port=80) == expected

    url = "sub.name.root"
    expected = "http://sub.name.root:80"
    assert normalize_url(url, default_scheme="http", default_port=80) == expected
    url = "https://sub.name.root:8080"
    expected = "https://sub.name.root:8080"
    assert normalize_url(url, default_port=80) == expected

    url = "sub.name.root:8080"
    expected = "http://sub.name.root:8080"
    assert normalize_url(url, default_scheme="http", default_port=80) == expected
    url = "https://sub.name.root"
    expected = "https://sub.name.root:80"
    assert normalize_url(url, default_scheme="http", default_port=80) == expected

    url = "sub.name.root:8080"
    expected = "http://sub.name.root:8080"
    assert normalize_url(url, default_scheme="http", default_port=80) == expected
    url = "https://sub.name.root:8080"
    expected = "https://sub.name.root:8080"
    assert normalize_url(url, default_scheme="http", default_port=80) == expected
