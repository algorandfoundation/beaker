def get_class_attributes(cls: type, use_legacy_ordering: bool = False) -> list[str]:
    """Get all class attribute names include names of ancestors, preserving declaration order"""
    if not use_legacy_ordering:
        attr_names = [
            key
            for klass in reversed(cls.__mro__)
            for key in klass.__dict__
            if not key.startswith("__")
        ]
    else:
        # TODO: REMOVE THIS HACK! the above should suffice, but to temporarily maintain output stability
        #       we leave this in for now
        immediate = [n for n in cls.__dict__.keys() if not n.startswith("__")]
        ancestors = [
            key
            for klass in reversed(cls.__mro__)
            for key in sorted(klass.__dict__.keys())
            if not key.startswith("__")
        ]
        attr_names = [*immediate, *ancestors]
    # unique-ify values, preserving order
    attr_names = list(dict.fromkeys(attr_names))
    return attr_names
