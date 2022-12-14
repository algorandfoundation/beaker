from examples.golf.main import SortedIntegers
from tests.conftest import check_application_artifacts_output_stability


def test_output_stability():
    app = SortedIntegers()
    check_application_artifacts_output_stability(app, dir_name="artifacts")
