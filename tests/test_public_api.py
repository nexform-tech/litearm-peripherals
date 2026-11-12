import litearm_peripherals as sdk


def test_all_names_resolve() -> None:
    for name in sdk.__all__:
        assert hasattr(sdk, name), name


def test_dunder_all_has_no_duplicates() -> None:
    assert len(sdk.__all__) == len(set(sdk.__all__))


def test_version_is_a_string() -> None:
    assert isinstance(sdk.__version__, str)
    assert sdk.__version__


def test_expected_public_classes() -> None:
    for name in ("QuickLink", "WristFT", "PeripheralHub", "Sample", "QuickLinkStatus", "HubStatus"):
        assert name in sdk.__all__
