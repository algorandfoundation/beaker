import inspect
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from beaker import Application, LogicSignature, LogicSignatureTemplate, sandbox


def check_application_artifacts_output_stability(
    app: Application,
    dir_name: str | None = None,
    output_dir: Path | None = None,
    *,
    dir_per_test_file: bool = True,
) -> None:
    """Test that the contract output hasn't changed for an Application, using git diff

    This gives us confidence in output stability when making internal changes to Beaker.

    The output will be placed next to the class definition location, by default in a
    directory named <class name>.artifacts/

    Args:
        app (beaker.Application): an instantiated application to compile
        dir_name (str | None): optional name for directory, if you just want to customise the name
        output_dir (pathlib.Path | None): optional full path to place output, for full control
        dir_per_test_file:

    """
    if dir_name and output_dir:
        raise ValueError("Only one of dir_name and output_dir should be specified")

    algod_client = sandbox.get_algod_client()
    spec = app.build(algod_client)

    if output_dir is None:
        caller_frame = inspect.stack()[1]
        caller_path = Path(caller_frame.filename).resolve()
        caller_dir = caller_path.parent
        if dir_per_test_file:
            caller_dir /= caller_path.stem
        output_dir = caller_dir / (dir_name or f"{app.name}.artifacts")

    output_dir_did_exist = output_dir.is_dir()

    output_dir_str = str(output_dir.resolve())
    spec.export(output_dir)
    assert output_dir.is_dir()
    git_diff = subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            "--no-ext-diff",
            "--no-color",
            output_dir_str,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # first fail if there are any changes to already committed files, you must manually add them in that case
    assert git_diff.returncode == 0, git_diff.stdout

    # if first time running, fail in case of accidental change to output directory
    if not output_dir_did_exist:
        pytest.fail(
            f"New output folder created at {output_dir_str} from contract {app.__class__.__qualname__} - "
            "if this was intentional, please commit the files to the git repo"
        )


def check_lsig_output_stability(
    lsig: LogicSignature | LogicSignatureTemplate, output_path: Path | None = None
) -> None:
    assert lsig.program is not None

    if output_path is not None:
        output_path.parent.mkdir(exist_ok=True, parents=True)
    else:
        caller_frame = inspect.stack()[1]
        caller_name = caller_frame.function
        caller_path = Path(caller_frame.filename).resolve()
        caller_dir = caller_path.parent
        output_dir = caller_dir / "lsig_teal"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{caller_name}.lsig.teal"

    output_did_exist = output_path.is_file()

    output_path_str = str(output_path.resolve())
    output_path.write_text(lsig.program)
    git_diff = subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            "--no-ext-diff",
            "--no-color",
            output_path_str,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # first fail if there are any changes to already committed files, you must manually add them in that case
    assert git_diff.returncode == 0, git_diff.stdout

    # if first time running, fail in case of accidental change to output directory
    if not output_did_exist:
        pytest.fail(
            f"New output file created at {output_path_str} from logic-signature - "
            "if this was intentional, please commit the file to the git repo"
        )


@pytest.fixture(autouse=True, scope="function")
def reset_pyteal() -> Iterator[None]:
    """Reset all known PyTeal global values to prevent tests from interfering with each other"""

    from pyteal.ast.scratch import NUM_SLOTS, ScratchSlot
    from pyteal.ast.subroutine import SubroutineDefinition, SubroutineEval

    # reset globals
    SubroutineEval._current_proto = None
    SubroutineDefinition.nextSubroutineId = 0
    ScratchSlot.nextSlotId = NUM_SLOTS

    yield  # let the test run
