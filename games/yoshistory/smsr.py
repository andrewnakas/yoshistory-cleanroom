"""Yoshi's Story "CMPR"/"SMSR00" container (decoder at 0x8006F560 in the US ROM) and our own encoder.

File on ROM:  "CMPR", u32 comp_size, u32 dec_size, u32 0,          (read first by the DMA manager)
              "SMSR00\0\0", u32 dec_size, u32 raw_off,              (comp_size bytes from here)
              u16 stream: flag words (16 bits, MSB first) interleaved with links,
              raw bytes at 0x10 + raw_off (relative to the SMSR header).
Flag 1 = copy one raw byte.  Flag 0 = link u16: length (x >> 12) + 3, distance (x & 0xFFF) + 1.
"""
import struct

CMPR = b"CMPR"
SMSR = b"SMSR00\0\0"


def decode(buf, off=0):
    """buf[off:] starts at "CMPR". Returns (data, total size on ROM incl. CMPR header)."""
    assert buf[off:off + 4] == CMPR, hex(off)
    comp, dec = struct.unpack_from(">II", buf, off + 4)
    s = off + 0x10
    assert buf[s:s + 6] == SMSR[:6]
    dec2, raw = struct.unpack_from(">II", buf, s + 8)
    assert dec2 == dec
    cp = s + 0x10
    rp = cp + raw
    out = bytearray()
    bits = 0
    flags = 0
    while len(out) < dec:
        if bits == 0:
            flags = struct.unpack_from(">H", buf, cp)[0]
            cp += 2
            bits = 16
        if flags & 0x8000:
            out.append(buf[rp])
            rp += 1
        else:
            x = struct.unpack_from(">H", buf, cp)[0]
            cp += 2
            n = (x >> 12) + 3
            p = len(out) - (x & 0xFFF) - 1
            for _ in range(n):
                out.append(out[p])
                p += 1
        flags = (flags << 1) & 0xFFFF
        bits -= 1
    return bytes(out[:dec]), 0x10 + comp


def _matches(data):
    """Greedy LZ parse with one-step lazy matching: list of ('r', byte) / ('l', dist, len)."""
    n = len(data)
    head = {}
    prev = [-1] * n
    toks = []

    def find(i):
        best, bd = 0, 0
        if i + 3 > n:
            return 0, 0
        j = head.get(data[i:i + 3], -1)
        tries = 64
        lim = min(18, n - i)
        while j >= 0 and i - j <= 4096 and tries:
            k = 0
            while k < lim and data[j + k] == data[i + k]:
                k += 1
            if k > best:
                best, bd = k, i - j
                if k == lim:
                    break
            j = prev[j]
            tries -= 1
        return best, bd

    def insert(i):
        if i + 3 <= n:
            key = data[i:i + 3]
            prev[i] = head.get(key, -1)
            head[key] = i

    i = 0
    while i < n:
        ln, d = find(i)
        if ln >= 3:
            insert(i)
            ln2, _ = find(i + 1) if i + 1 < n else (0, 0)
            if ln2 > ln:
                toks.append(("r", data[i]))
                i += 1
                continue
            toks.append(("l", d, ln))
            for k in range(i + 1, i + ln):
                insert(k)
            i += ln
        else:
            insert(i)
            toks.append(("r", data[i]))
            i += 1
    return toks


def encode(data):
    """Returns the full ROM file: CMPR header + SMSR00 stream, padded to 4 bytes (retail files are packed
    4-aligned; the header's size field is what the DMA manager reads after the 16-byte CMPR header)."""
    data = bytes(data)
    toks = _matches(data)
    ctl = bytearray()
    raw = bytearray()
    for g in range(0, len(toks), 16):
        grp = toks[g:g + 16]
        fl = 0
        for k, t in enumerate(grp):
            if t[0] == "r":
                fl |= 0x8000 >> k
        ctl += struct.pack(">H", fl)
        for t in grp:
            if t[0] == "r":
                raw.append(t[1])
            else:
                ctl += struct.pack(">H", ((t[2] - 3) << 12) | (t[1] - 1))
    body = SMSR + struct.pack(">II", len(data), len(ctl)) + bytes(ctl) + bytes(raw)
    body += bytes(-len(body) % 4)
    return CMPR + struct.pack(">III", len(body), len(data), 0) + body


def find_all(rom):
    """Offsets of every CMPR file in the ROM."""
    out = []
    p = rom.find(CMPR)
    while p >= 0:
        if rom[p + 0x10:p + 0x16] == SMSR[:6]:
            out.append(p)
        p = rom.find(CMPR, p + 4)
    return out
