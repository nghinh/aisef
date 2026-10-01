from ledgerlock import normalize_key          # the story's own package: absent at the parent SHA


def test_AC_S_01_1_normalizes():
    assert normalize_key("a") == "a"
