def pytest_addoption(parser):
    parser.addoption("--mysql", action="store_true", help="Require and run real MySQL tests.")
