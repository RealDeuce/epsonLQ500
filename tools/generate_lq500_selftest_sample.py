#!/usr/bin/env python3
"""Generate an ESC/P stream matching the LQ-500 draft self-test sample page."""

from __future__ import annotations

import argparse
from pathlib import Path


ESC = b"\x1b"

HEADER_ADDR = 0x6100
SPACE_ADDR = 0x618E
POINTER_TABLE_ADDR = 0x61AA
PITCH_10_ADDR = 0x6190

# DIP/panel state visible in Scanned sample.pdf page 1.
DEFAULT_SELECTED_IDS = {
    0x00,  # table headers
    0x01,  # USA
    0x09,  # Roman
    0x0D,  # Condensed invalid
    0x17,  # Italic CG table
    0x13,  # CSF mode invalid
    0x19,  # 11 inch page length
    0x1B,  # 61-line CSF page length
    0x11,  # 1" skip invalid
    0x15,  # Auto LF invalid
    0x1D,  # 1 KB receive buffer
    0x1F,  # Unidirectional graphics
    0x2B,  # 10 pitch
}


def ff_string(rom: bytes, addr: int) -> bytes:
    end = rom.index(0xFF, addr)
    return rom[addr:end]


def nul_string(rom: bytes, addr: int) -> bytes:
    end = rom.index(0x00, addr)
    return rom[addr:end]


def selector_string(rom: bytes, addr: int) -> tuple[int, bytes]:
    raw = ff_string(rom, addr)
    if not raw:
        return 0, b""
    return raw[0], raw[1:]


def pointer_rows(rom: bytes) -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    pos = POINTER_TABLE_ADDR
    while True:
        left = rom[pos] | (rom[pos + 1] << 8)
        pos += 2
        if left == 0:
            break
        right = rom[pos] | (rom[pos + 1] << 8)
        pos += 2
        rows.append((left, right))
    return rows


def set_emphasized(on: bool) -> bytes:
    return ESC + (b"E" if on else b"F")


def lq500_plain_draft_10() -> bytes:
    return (
        ESC + b"@"
        + lq500_quality_family("draft", "roman")
        + ESC + b"!\x00"
        + ESC + b"p\x00"
        + b"\x12"
        + ESC + b"P"
        + ESC + b"T"
    )


def lq500_quality_family(quality: str, family: str) -> bytes:
    family_id = 1 if family == "sans-serif" else 0
    return (
        ESC + b"x" + (b"\x01" if quality == "lq" else b"\x00")
        + ESC + b"k" + bytes([family_id])
    )


def lq500_plain_lq_10(family: str) -> bytes:
    return (
        ESC + b"@"
        + lq500_quality_family("lq", family)
        + ESC + b"!\x00"
        + ESC + b"p\x00"
        + b"\x12"
        + ESC + b"P"
        + ESC + b"T"
    )


def emit_selected_string(selector: int, text: bytes, selected: set[int]) -> bytes:
    return set_emphasized(selector in selected) + text + set_emphasized(False)


def rolling_ascii_line(start: int, columns: int) -> bytes:
    chars = []
    value = start
    for _ in range(columns):
        chars.append(value)
        value += 1
        if value == 0x7F:
            value = 0x20
    return bytes(chars)


def generate(rom: bytes, selected: set[int], rows: int, columns: int) -> bytes:
    out = bytearray()
    out += lq500_plain_draft_10()

    out += ff_string(rom, HEADER_ADDR) + b"\r\n\r\n"

    for left_addr, right_addr in pointer_rows(rom):
        left_id, left = selector_string(rom, left_addr)
        right_id, right = selector_string(rom, right_addr)
        out += emit_selected_string(left_id, left, selected)
        out += ff_string(rom, SPACE_ADDR) * 10
        out += emit_selected_string(right_id, right, selected)
        out += b"\r\n"

    out += b"\r\n"
    out += b"Draft" + nul_string(rom, PITCH_10_ADDR) + b"\r\n"

    start = 0x20
    for _ in range(rows):
        out += rolling_ascii_line(start, columns) + b"\r\n"
        start += 1
        if start == 0x7F:
            start = 0x20

    out += b"\x0c"
    return bytes(out)


def generate_lq(rom: bytes, selected: set[int], rows_per_section: int, columns: int) -> bytes:
    out = bytearray()
    out += lq500_plain_lq_10("roman")

    out += ff_string(rom, HEADER_ADDR) + b"\r\n\r\n"

    for left_addr, right_addr in pointer_rows(rom):
        left_id, left = selector_string(rom, left_addr)
        right_id, right = selector_string(rom, right_addr)
        out += emit_selected_string(left_id, left, selected)
        out += ff_string(rom, SPACE_ADDR) * 10
        out += emit_selected_string(right_id, right, selected)
        out += b"\r\n"

    out += b"\r\n"

    start = 0x20
    sections = [("roman", b"Roman 10"), ("sans-serif", b"Sans Serif 10")] * 4
    for family, label in sections:
        out += lq500_quality_family("lq", family)
        out += label + b"\r\n"
        for _ in range(rows_per_section):
            out += rolling_ascii_line(start, columns) + b"\r\n"
            start += 1
            if start == 0x7F:
                start = 0x20

    out += b"\x0c"
    return bytes(out)


def parse_selected_ids(raw: str) -> set[int]:
    if not raw:
        return set(DEFAULT_SELECTED_IDS)
    return {int(part, 0) for part in raw.split(",") if part.strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rom",
        type=Path,
        default=Path("roms/lq500_3c_m25a10pa_internal_prom.bin"),
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=72)
    parser.add_argument("--columns", type=int, default=80)
    parser.add_argument("--quality", choices=("draft", "lq"), default="draft")
    parser.add_argument(
        "--selected-ids",
        default="",
        help="Comma-separated selector IDs; defaults match Scanned sample.pdf",
    )
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    selected = parse_selected_ids(args.selected_ids)
    if args.quality == "lq":
        args.out.write_bytes(generate_lq(rom, selected, args.rows, args.columns))
    else:
        args.out.write_bytes(generate(rom, selected, args.rows, args.columns))


if __name__ == "__main__":
    main()
