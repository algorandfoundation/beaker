from tests.conftest import check_application_artifacts_output_stability
from examples.wormhole.contract import OracleDataCache
from examples.wormhole.main import demo


def test_demo():
    demo()


def test_output_stability():
    app = OracleDataCache()
    check_application_artifacts_output_stability(
        app, dir_name="spec", dir_per_test_file=False
    )
