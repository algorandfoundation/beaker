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

    with_sourcemaps: bool = False
    """When `True`, the compiler will produce a source map that associates
        each line of the generated TEAL program back to the original PyTeal source code. Defaults to `False`.  """
    annotate_teal: bool = False
    """When `True`, the compiler will produce a TEAL program with comments
        that describe the PyTeal source code that generated each line of the program. Defaults to `False`."""
    annotate_teal_headers: bool = False
    """When `True` along with `annotate_teal` being `True`, a header
        line with column names will be added at the top of the annotated teal. Defaults to `False`."""
    annotate_teal_concise: bool = False
    """When `True` along with `annotate_teal` being `True`, the compiler
        will provide fewer columns in the annotated teal. Defaults to `False`."""

    @property
    def optimize_options(self) -> OptimizeOptions:
        return OptimizeOptions(
            scratch_slots=self.scratch_slots,
            frame_pointers=self.frame_pointers,
        )
