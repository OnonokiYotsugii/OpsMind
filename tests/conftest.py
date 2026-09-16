def pytest_addoption(parser):
    parser.addoption("--mysql", action="store_true", help="Require and run real MySQL tests.")

    parser.addoption("--embedding", action="store_true", help="Use prepared local embedding model.")
