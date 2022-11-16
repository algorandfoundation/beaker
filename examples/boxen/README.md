The TAO of Boxes
----------------
# Box Consensus params

    BoxFlatMinBalance = 0.002500
    BoxByteMinBalance = 0.000400
    MaxBoxSize = 32k 
    MaxAppBoxReferences = 8
    BytesPerBoxReference = 1k

    Max box bytes accessible in 1 app call: 8k
    Max box bytes accessible in 16 app calls: 128k

If a `map` is required, a box per key should be used

> To know what the key to reference, ask the app to tell us what the key should be

A common pattern will likely be map keyed by the address of the user

If a `list` is required it must be <128k if you intend to to access the entire list and it'd have to be split across 4 boxes (128/32)

- For an 8 byte element, this may contain 16000 elements
- For a 32 byte element, this may contain 4000 elements
- For a 128 byte element, this may contain 1000 elements

Static Vs Dynamic element types in a list

- Static type should be preferred so a list index can be directly mapped can be mapped directly to a byte offset index
- Dynamic typed lists mean we'd have to iterate through the structure, reading each's `length` (and length of contained elements) to find the right offset from which to read the data 


# Basic Box usage

```py
 name = Bytes("name")
 val = Bytes("val")
 size = Int(1)
 start = Int(1)

 BoxCreate(name, size) # Create a new box of size
 BoxDelete(name) # Delete box

 BoxExtract(name, start, size) # Get `size` bytes from box starting from `start`
 BoxReplace(name, start, val) # Overwrite whatever is in the box from start to len(val)
 BoxPut(name, val) # Write all contents of `val` to box starting from 0

 BoxGet(name) # Get the full contents of this box (will panic >4k)
 BoxLen(name) # Get the size of this box
```