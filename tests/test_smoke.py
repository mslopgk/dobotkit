def test_package_imports_and_has_version():
    import dobotkit
    assert isinstance(dobotkit.__version__, str)
    assert dobotkit.__version__.count(".") >= 1
