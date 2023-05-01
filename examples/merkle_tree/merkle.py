from typing import Literal

import pyteal as pt


@pt.Subroutine(pt.TealType.bytes)
def hash_concat(left: pt.Expr, right: pt.Expr) -> pt.Expr:
    return pt.Sha256(pt.Concat(left, right))


# [u8 left/right, u256 digest]
RIGHT_SIBLING_PREFIX = pt.Int(170)  # 0xaa
U264 = pt.abi.StaticBytes[Literal[33]]


@pt.Subroutine(pt.TealType.uint64)
def is_right_sibling(sibling: pt.Expr) -> pt.Expr:
    # if a sibling starts with 0xaa (170) byte, then it's a right sibling.
    return pt.GetByte(sibling, pt.Int(0)) == RIGHT_SIBLING_PREFIX


TREE_HEIGHT = 3  # idk
TreeHeight = Literal[3]  # idk
DigestSize = 32

Data = pt.abi.DynamicBytes
Direction = pt.abi.Byte

Leaf = pt.abi.StaticBytes[Literal[32]]

PathElement = pt.abi.StaticBytes[Literal[33]]
Path = pt.abi.StaticArray[PathElement, TreeHeight]


@pt.Subroutine(pt.TealType.bytes)
def calc_root(leaf: pt.Expr, path: Path) -> pt.Expr:
    """
    Calculates the root of the Merkle tree from a specific leaf.
    Expects its siblings in the 'Txn.application_args' array.
    :param init_value: the hash value of the leaf to start the computation from
    :return: the hash value of the expected root
    """
    return pt.Seq(
        (result := pt.ScratchVar(pt.TealType.bytes)).store(leaf),
        # go over all siblings along the path to the top hash
        pt.For(
            (i := pt.ScratchVar()).store(pt.Int(0)),
            i.load() < pt.Int(TREE_HEIGHT),
            i.store(i.load() + pt.Int(1)),
        ).Do(
            (elem := pt.abi.make(PathElement)).set(path[i.load()]),
            result.store(
                pt.If(is_right_sibling(elem.get()))
                .Then(
                    hash_concat(
                        result.load(),
                        pt.Extract(elem.get(), pt.Int(1), pt.Int(32)),
                    )
                )
                .Else(
                    hash_concat(
                        pt.Extract(elem.get(), pt.Int(1), pt.Int(32)),
                        result.load(),
                    )
                )
            ),
        ),
        result.load(),
    )


@pt.Subroutine(pt.TealType.bytes)
def calc_init_root() -> pt.Expr:
    """
    Calculates the root of an empty Merkle tree
    :return:
    """
    i = pt.ScratchVar(pt.TealType.uint64)
    result = pt.ScratchVar(pt.TealType.bytes)
    return pt.Seq(
        result.store(pt.Sha256(pt.Bytes(""))),
        pt.For(
            i.store(pt.Int(0)),
            i.load() < pt.Int(TREE_HEIGHT),
            i.store(i.load() + pt.Int(1)),
        ).Do(result.store(pt.Sha256(pt.Concat(result.load(), result.load())))),
        result.load(),
    )
