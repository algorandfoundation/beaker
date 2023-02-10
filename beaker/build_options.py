import dataclasses

from pyteal import MAX_PROGRAM_VERSION, OptimizeOptions

__all__ = [
    "BuildOptions",
]


@dataclasses.dataclass(kw_only=True)
class BuildOptions:
    avm_version: int = MAX_PROGRAM_VERSION
    """defines the #pragma version used in output"""
    scratch_slots: bool = True
    """Cancel contiguous store/load operations that have no load dependencies elsewhere. 
       default=True"""
    frame_pointers: bool | None = None
    """Employ frame pointers instead of scratch slots during compilation.
       Available and enabled by default from AVM version 8"""
    assemble_constants: bool = True
    """When true, the compiler will produce a program with fully
        assembled constants, rather than using the pseudo-ops `int`, `byte`, and `addr`. These
        constants will be assembled in the most space-efficient way, so enabling this may reduce
        the compiled program's size. Enabling this option requires a minimum AVM version of 3.
        Defaults to True."""

    @property
    def optimize_options(self) -> OptimizeOptions:
        return OptimizeOptions(
            scratch_slots=self.scratch_slots,
            frame_pointers=self.frame_pointers,
        )
