def binary_search(arr, val, start, end):
    if start > end:
        return start

    if start == end:
        if arr[start] > val:
            return start
        return start + 1

    mid = (start + end) // 2

    if arr[mid] < val:
        return binary_search(arr, val, mid + 1, end)
    elif arr[mid] > val:
        return binary_search(arr, val, start, mid - 1)
    else:
        return mid


arr: list[int] = []
for x in [37, 23, 0, 31, 22, 17, 12, 72, 31, 46, 100, 88, 54]:
    j = binary_search(arr, x, 0, len(arr) - 1)
    arr = arr[:j] + [x] + arr[j:]
    print(arr)
