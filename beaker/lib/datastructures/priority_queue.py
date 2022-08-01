from pyteal import *
from typing import List
from application import GlobalStorageValue

ou = OpUp(OpUpMode.OnCall)


class PriorityQueue:
    def __init__(self, box_name: str, box_size: Int, lt: Int, type_spec: abi.TypeSpec):
        self.box_name_str = box_name
        self.box_name = Bytes(box_name)
        self.box_size = box_size
        self.type_spec = type_spec
        self.lt = lt
        self.type_size = Int(abi.size_of(self.type_spec))
        self.counter = GlobalStorageValue(self.box_name_str, TealType.uint64)

    def initialize(self) -> Expr:
        return BoxCreate(self.box_name, self.box_size)

    def count(self) -> Expr:
        """count returns the number of elements in the priority queue, tracked by global state var"""
        return self.counter.get()

    def insert(self, thing: abi.BaseType) -> Expr:
        """insert adds a new element in sorted order"""
        return pq_insert(self.box_name, thing.encode(), self.lt)

    def update(self, idx: Expr, thing: abi.BaseType) -> Expr:
        """insert adds a new element in sorted order"""
        return pq_write(self.box_name, idx, thing.encode())

    def delete(self, thing: abi.BaseType) -> Expr:
        """delete removes a given element by finding it in the pq then removing it by index"""
        return self.remove(self.search(thing))

    def pop(self) -> Expr:
        """pop removes the first element from the pq and returns it after resorting the pq"""
        return pq_pop(self.box_name, self.type_size, self.lt)

    def remove(self, idx: Expr) -> Expr:
        """remove removes an element by its index"""
        return pq_remove(self.box_name, idx, self.type_size, self.lt)

    def peek(self) -> Expr:
        """peak reads the root element but doesn't modify the pq"""
        return pq_read(self.box_name, Int(0), self.type_size)

    def get(self, idx: abi.Uint64) -> Expr:
        """get returns an element at a given index"""
        return pq_read(self.box_name, idx.get(), self.type_size)

    def search(self, thing: abi.BaseType) -> Expr:
        """search tries to find the element in the pq"""
        return pq_search(self.box_name, thing.encode())


##### pq counter stored in global state
def pq_count(key):
    return App.globalGet(key)


def pq_count_incr(key):
    return App.globalPut(key, pq_count(key) + Int(1))


def pq_count_decr(key):
    return App.globalPut(key, pq_count(key) - Int(1))


# pq idx helpers
def child_idx_left(pos) -> Expr:
    return (pos * Int(2)) + Int(1)


def child_idx_right(pos) -> Expr:
    return (pos * Int(2)) + Int(2)


def parent_idx(pos) -> Expr:
    return If(pos % Int(2) == Int(0), pos - Int(2), pos - Int(1)) / Int(2)


#### pq read/writes
def pq_write(key, idx, val):
    return BoxReplace(key, idx * Len(val), val)


def pq_read(key, idx, len):
    return BoxExtract(key, idx * len, len)


def pq_zero(key, idx, len):
    return pq_write(key, idx, BytesZero(len))


@Subroutine(TealType.uint64)
def unsorted(a, b, lt):
    """unsorted takes a and b as bytes and lt as the sort order,
    returning whether or not the elements are in correct order
    """
    return If(
        Or(Len(a) == Int(0), Len(b) == Int(0)),
        Int(0),
        If(
            lt,
            # sorted_lt checks to see if a is less than b by comparing the price|sequence both uint64
            BytesLt(Extract(a, Int(0), Int(2 * 8)), Extract(b, Int(0), Int(2 * 8))),
            # sorted_gt checks to see if a is greater than b by comparing the price|~sequence both uint64
            BytesGt(
                Concat(
                    Extract(a, Int(0), Int(8)),
                    BytesNot(Extract(a, Int(8), Int(8))),
                ),
                Concat(
                    Extract(b, Int(0), Int(8)),
                    BytesNot(Extract(b, Int(8), Int(8))),
                ),
            ),
        ),
    )


## pq operations
@Subroutine(TealType.none)
def pq_insert(key, val, sort):
    return Seq(
        # Write the first element in the last spot
        pq_write(key, pq_count(key), val),
        # Restore heap invariant starting with the last element
        pq_upheap(key, pq_count(key), Len(val), sort),
        # Increment the counter
        pq_count_incr(key),
    )


@Subroutine(TealType.bytes)
def pq_pop(key, len, sort):
    return Seq(
        # Read the top element
        (top := ScratchVar()).store(BoxExtract(key, Int(0), len)),
        # Decrement the counter so we have the correct last element
        pq_count_decr(key),
        # Swap last for first
        pq_swap(key, Int(0), pq_count(key), len),
        # Restore heap property
        pq_downheap(key, Int(0), len, sort),
        # Zero out bytes for the last one
        pq_zero(key, pq_count(key), len),
        # Return the top element
        top.load(),
    )


@Subroutine(TealType.none)
def pq_remove(key, idx, len, sort):
    return Seq(
        # Decrement the counter
        pq_count_decr(key),
        # Swap the index to remove for last
        pq_swap(key, idx, pq_count(key), len),
        # Restore heap invariant
        pq_downheap(key, idx, len, sort),
        # Zero out bytes for the last one (the one we're removing)
        pq_zero(key, pq_count(key), len),
    )


@Subroutine(TealType.none)
def pq_swap(key, aidx, bidx, len):
    return Seq(
        # Store a and b in scratch
        (a := ScratchVar()).store(pq_read(key, aidx, len)),
        (b := ScratchVar()).store(pq_read(key, bidx, len)),
        # Write b to a index
        pq_write(key, bidx, a.load()),
        # Write a to b index
        pq_write(key, aidx, b.load()),
    )


@Subroutine(TealType.uint64)
def pq_search(key, val):
    i = ScratchVar()
    init = i.store(Int(0))
    cond = i.load() < pq_count(key)
    iter = i.store(i.load() + Int(1))
    return Seq(
        For(init, cond, iter).Do(
            If(val == pq_read(key, i.load(), Len(val)), Return(i.load()))
        ),
        # lie
        pq_count(key) + Int(1),
    )


# pq Heap invariant restoring operations
@Subroutine(TealType.none)
def pq_upheap(key, idx, len, sort_lt):
    """pq_upheap restores the heap invariant property starting from a given index up the heap
    by comparing the child with its parent, if needed, we swap the items and check again
    """
    return If(
        idx != Int(0),
        Seq(
            ou.ensure_budget(Int(500)),
            (p_pos := ScratchVar()).store(parent_idx(idx)),
            If(
                unsorted(
                    pq_read(key, idx, len),
                    pq_read(key, p_pos.load(), len),
                    sort_lt,
                ),
                Seq(
                    pq_swap(key, idx, p_pos.load(), len),
                    pq_upheap(key, p_pos.load(), len, sort_lt),
                ),
            ),
        ),
    )


@Subroutine(TealType.none)
def pq_downheap(key, idx, len, sort_lt):
    """pq_downheap restores the heap invariant property starting from a given index down the heap
    by comparing a parent with its children, if one or the other is larger we swap the items and check again
    we preferr to swap the right element if both are larger
    """
    return If(
        idx < pq_count(key),
        Seq(
            ou.ensure_budget(Int(500)),
            (curr_idx := ScratchVar()).store(idx),
            (left_idx := ScratchVar()).store(child_idx_left(idx)),
            (right_idx := ScratchVar()).store(child_idx_right(idx)),
            # Check the left side first
            If(
                left_idx.load() < pq_count(key),
                If(
                    unsorted(
                        pq_read(key, left_idx.load(), len),
                        pq_read(key, curr_idx.load(), len),
                        sort_lt,
                    ),
                    curr_idx.store(left_idx.load()),
                ),
            ),
            # Check the right side second
            If(
                right_idx.load() < pq_count(key),
                If(
                    unsorted(
                        pq_read(key, right_idx.load(), len),
                        pq_read(key, curr_idx.load(), len),
                        sort_lt,
                    ),
                    curr_idx.store(right_idx.load()),
                ),
            ),
            # If largest is now different than current swap them and start over
            If(
                curr_idx.load() != idx,
                Seq(
                    pq_swap(key, idx, curr_idx.load(), len),
                    pq_downheap(key, curr_idx.load(), len, sort_lt),
                ),
            ),
        ),
    )
