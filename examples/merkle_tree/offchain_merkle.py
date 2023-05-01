import hashlib

EMPTY_HASH = hashlib.sha256(b"").digest()
RIGHT_EMPTY_HASH = b"\xaa" + EMPTY_HASH
LEFT_EMPTY_HASH = b"\xbb" + EMPTY_HASH


class MerkleTree:
    def __init__(self, height: int):
        self.root = Leaf(height)
        self.max_records = 2**height
        self.size = 0

    def append(self, value: str) -> list[bytes]:
        if self.size == self.max_records:
            return []
        self.size += 1
        return self.root.append(value)

    def verify(self, value: str) -> list[bytes]:
        return self.root.verify(value)

    def update(self, old_value: str, new_value: str) -> list[bytes]:
        return self.root.update(old_value, new_value)


class Leaf:
    def __init__(self, height: int):
        self.height = height
        if height == 0:
            self.left_sibling = None
            self.right_sibling = None
            self.value = EMPTY_HASH
        else:
            self.left_sibling = Leaf(height - 1)
            self.right_sibling = Leaf(height - 1)
            self.value = hashlib.sha256(
                self.left_sibling.value + self.right_sibling.value
            ).digest()

    def append(self, value: str) -> list[bytes]:
        if self.height == 0:
            if self.value == EMPTY_HASH:
                self.value = hashlib.sha256(value.encode("utf-8")).digest()
                return [self.value]
            else:
                return []

        assert self.left_sibling is not None
        assert self.right_sibling is not None

        left = self.left_sibling.append(value)
        if len(left) > 0:
            sib = RIGHT_EMPTY_HASH
            if self.right_sibling.value != EMPTY_HASH:
                self.value = hashlib.sha256(
                    self.left_sibling.value + self.right_sibling.value
                ).digest()
                sib = b"\xaa" + self.right_sibling.value
            else:
                self.value = hashlib.sha256(
                    self.left_sibling.value + EMPTY_HASH
                ).digest()
            return [*left, sib]

        right = self.right_sibling.append(value)
        if len(right) > 0:
            sib = b"\xbb" + self.left_sibling.value
            self.value = hashlib.sha256(
                self.left_sibling.value + self.right_sibling.value
            ).digest()
            return [*right, sib]

        return []

    def verify(self, value: str) -> list[bytes]:
        if self.height == 0:
            if self.value == hashlib.sha256(value.encode("utf-8")).digest():
                return [value.encode()]
            else:
                return []

        assert self.left_sibling is not None
        assert self.right_sibling is not None

        left = self.left_sibling.verify(value)
        if len(left) > 0:
            sib = RIGHT_EMPTY_HASH
            if self.right_sibling.value != EMPTY_HASH:
                sib = b"\xaa" + self.right_sibling.value
            return [*left, sib]

        right = self.right_sibling.verify(value)
        if len(right) > 0:
            sib = b"\xbb" + self.left_sibling.value
            return [*right, sib]

        return []

    def update(self, old_value: str, new_value: str) -> list[bytes]:
        if self.height == 0:
            if self.value == hashlib.sha256(old_value.encode("utf-8")).digest():
                self.value = hashlib.sha256(new_value.encode("utf-8")).digest()
                return [old_value.encode(), new_value.encode()]
            else:
                return []

        assert self.left_sibling is not None
        assert self.right_sibling is not None

        left = self.left_sibling.update(old_value, new_value)
        if len(left) > 0:
            sib = RIGHT_EMPTY_HASH
            if self.right_sibling.value != EMPTY_HASH:
                self.value = hashlib.sha256(
                    self.left_sibling.value + self.right_sibling.value
                ).digest()
                sib = b"\xaa" + self.right_sibling.value
            else:
                self.value = hashlib.sha256(
                    self.left_sibling.value + EMPTY_HASH
                ).digest()
            return left[:-1] + [sib] + left[-1:]

        right = self.right_sibling.update(old_value, new_value)
        if len(right) > 0:
            sib = LEFT_EMPTY_HASH
            if self.left_sibling.value != EMPTY_HASH:
                self.value = hashlib.sha256(
                    self.left_sibling.value + self.right_sibling.value
                ).digest()
                sib = b"\xbb" + self.left_sibling.value
            else:
                self.value = hashlib.sha256(
                    EMPTY_HASH + self.right_sibling.value
                ).digest()

            return right[:-1] + [sib] + right[-1:]
        return []
