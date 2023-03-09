from collections.abc import Iterator

import pytest


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
