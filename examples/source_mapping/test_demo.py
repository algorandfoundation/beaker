from feature_gates import FeatureGates  # type: ignore[import]

from tests.conftest import check_application_artifacts_output_stability


class SourceMapEnabled:
    def __enter__(self) -> None:
        FeatureGates.set_sourcemap_enabled(True)  # noqa: FBT003

    def __exit__(self, *args: object) -> None:
        FeatureGates.set_sourcemap_enabled(False)  # noqa: FBT003


def test_demo() -> None:
    with SourceMapEnabled():
        from examples.source_mapping import demo

        demo.main()


def test_output_stability() -> None:
    with SourceMapEnabled():
        from examples.source_mapping import app

        check_application_artifacts_output_stability(
            app=app.source_mapped_app, dir_per_test_file=False
        )
