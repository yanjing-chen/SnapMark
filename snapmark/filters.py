"""Pure-Python image filters shared by GTK renderer and tests."""

def box_blur_bytes(pixels: bytes, width: int, height: int, channels: int, radius: int) -> bytes:
    """Two-pass sliding-window blur, independent of GTK; keeps alpha unchanged.

    Work is linear in pixel count rather than quadratic in kernel radius.
    """
    if not pixels or width < 1 or height < 1 or channels not in (3, 4):
        return bytes(pixels)
    radius = max(1, min(48, int(radius)))
    source = bytearray(pixels)
    tmp = bytearray(len(source))
    dst = bytearray(len(source))
    # Repeat edge pixels to avoid dark halos at the clipped region edge.
    for y in range(height):
        base = y * width * channels
        sums = [0, 0, 0]
        for ix in range(-radius, radius + 1):
            offset = base + min(width - 1, max(ix, 0)) * channels
            for channel in range(3):
                sums[channel] += source[offset + channel]
        div = 2 * radius + 1
        for x in range(width):
            dest = base + x * channels
            for channel in range(3):
                tmp[dest + channel] = sums[channel] // div
            if channels == 4:
                tmp[dest + 3] = source[dest + 3]
            left = base + max(x - radius, 0) * channels
            right = base + min(x + radius + 1, width - 1) * channels
            for channel in range(3):
                sums[channel] += source[right + channel] - source[left + channel]
    for x in range(width):
        sums = [0, 0, 0]
        for iy in range(-radius, radius + 1):
            offset = (min(height - 1, max(iy, 0)) * width + x) * channels
            for channel in range(3):
                sums[channel] += tmp[offset + channel]
        for y in range(height):
            dest = (y * width + x) * channels
            for channel in range(3):
                dst[dest + channel] = sums[channel] // div
            if channels == 4:
                dst[dest + 3] = tmp[dest + 3]
            left = (max(y - radius, 0) * width + x) * channels
            right = (min(y + radius + 1, height - 1) * width + x) * channels
            for channel in range(3):
                sums[channel] += tmp[right + channel] - tmp[left + channel]
    return bytes(dst)


