#!/usr/bin/env python3
"""Extract emulator-ready tables from LQ-500 3C program ROM and 4C CG ROM.

Reads:
  roms/lq500_3c_m25a10pa_internal_prom.bin  (32K program PROM)
  roms/lq500_4c_m10a10la_cg_128k_custom_prom.bin  (128K CG ROM)

Writes TSV files to data/.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def le16(data: bytes, off: int) -> int:
    return data[off] | (data[off + 1] << 8)


def le24(data: bytes, off: int) -> int:
    return data[off] | (data[off + 1] << 8) | (data[off + 2] << 16)


def signed8(v: int) -> int:
    return v - 256 if v >= 128 else v


# ---------------------------------------------------------------------------
# 4C CG ROM extraction
# ---------------------------------------------------------------------------

CONFIG_BITS = {
    0: "elite",      # 12 cpi
    1: "proportional",
    2: "lq",          # set = LQ, clear = Draft
    4: "condensed",
    6: "italic",
}


def decode_config(cfg: int) -> str:
    """Human-readable config string from the VV:A6-style config byte."""
    parts = []
    quality = "LQ" if cfg & 0x04 else "Draft"
    parts.append(quality)
    if cfg & 0x01:
        parts.append("Elite")
    if cfg & 0x02:
        parts.append("Proportional")
    if cfg & 0x10:
        parts.append("Condensed")
    if cfg & 0x40:
        parts.append("Italic")
    return " ".join(parts)


FAMILY_NAMES = {0x00: "Roman", 0x01: "SansSerif", 0xFF: "Block"}


def extract_4c_font_directory(rom4c: bytes, outdir: Path) -> list[dict]:
    """Parse the 4C font directory at page 0 and write TSV."""
    header = rom4c[0]
    record_count = header & 0x3F
    size_flag = header & 0xC0

    # Determine record size from the flag.  Empirically, the resident 4C
    # ROM uses 15-byte records (size_flag=$40).
    if size_flag == 0x40:
        rec_size = 15
    else:
        rec_size = 12

    records = []
    for i in range(record_count):
        base = 1 + i * rec_size
        family = rom4c[base]
        config = rom4c[base + 1]
        byte2 = rom4c[base + 2]
        byte3 = rom4c[base + 3]
        metrics_base = le16(rom4c, base + 4)

        if rec_size == 15:
            byte6 = rom4c[base + 6]
            dim1 = rom4c[base + 7]
            dim2 = rom4c[base + 8]
            byte9 = rom4c[base + 9]
            byte10 = rom4c[base + 10]
            byte11 = rom4c[base + 11]
            name_ptr = le24(rom4c, base + 12)
        else:
            byte6 = 0
            dim1 = 0
            dim2 = 0
            byte9 = 0
            byte10 = 0
            byte11 = 0
            name_ptr = 0

        # Read font name string (NUL- or non-ASCII-terminated)
        name_str = ""
        if name_ptr < len(rom4c):
            chars = []
            for j in range(20):
                b = rom4c[name_ptr + j]
                if b == 0 or b >= 0x80:
                    break
                chars.append(chr(b))
            name_str = "".join(chars)

        family_name = FAMILY_NAMES.get(family, f"Unknown_{family:02X}")
        config_desc = decode_config(config)

        records.append({
            "index": i,
            "family": family,
            "family_name": family_name,
            "config": config,
            "config_desc": config_desc,
            "byte2": byte2,
            "byte3": byte3,
            "metrics_base": metrics_base,
            "byte6": byte6,
            "dim1": dim1,
            "dim2": dim2,
            "byte9": byte9,
            "byte10": byte10,
            "byte11": byte11,
            "name_ptr": name_ptr,
            "name_str": name_str,
        })

    # Write directory TSV
    path = outdir / "lq500_4c_font_directory.tsv"
    with open(path, "w") as f:
        f.write("index\tfamily\tfamily_name\tconfig\tconfig_desc\tbyte2\tbyte3"
                "\tmetrics_base\tbyte6\tdim1\tdim2\tbyte9\tbyte10\tbyte11"
                "\tname_ptr\tname_str\n")
        for r in records:
            f.write(f"{r['index']}\t"
                    f"0x{r['family']:02X}\t{r['family_name']}\t"
                    f"0x{r['config']:02X}\t{r['config_desc']}\t"
                    f"0x{r['byte2']:02X}\t0x{r['byte3']:02X}\t"
                    f"0x{r['metrics_base']:04X}\t"
                    f"0x{r['byte6']:02X}\t"
                    f"0x{r['dim1']:02X}\t0x{r['dim2']:02X}\t"
                    f"0x{r['byte9']:02X}\t0x{r['byte10']:02X}\t"
                    f"0x{r['byte11']:02X}\t"
                    f"0x{r['name_ptr']:05X}\t{r['name_str']}\n")
    print(f"  {path.name}: {record_count} directory records")
    return records


def extract_4c_font_glyphs(rom4c: bytes, outdir: Path,
                           records: list[dict]) -> None:
    """Extract per-character metrics and glyph bitmap data for each font."""
    for rec in records:
        metrics_base = rec["metrics_base"]
        family_name = rec["family_name"]
        config = rec["config"]

        # Character range: $20-$EF for normal fonts, $00-$FF for Block ($FF)
        if rec["family"] == 0xFF:
            first_char = 0x00
            last_char = 0xFF
        else:
            first_char = 0x20
            last_char = 0xEF

        # Sanitize filename
        config_desc = rec["config_desc"].replace(" ", "_")
        fname = f"lq500_4c_font_{rec['index']:02d}_{family_name}_{config_desc}.tsv"
        path = outdir / fname

        chars_with_data = 0
        with open(path, "w") as f:
            f.write("char_code\tchar\tstart\twidth\tadvance"
                    "\tglyph_ptr\tglyph_data_hex\n")
            for ch in range(first_char, last_char + 1):
                off = metrics_base + ch * 6
                if off + 6 > len(rom4c):
                    break
                start = rom4c[off]
                width = rom4c[off + 1]
                advance = rom4c[off + 2]
                glyph_ptr = le24(rom4c, off + 3)

                # Read glyph bitmap (3 bytes per column)
                glyph_hex = ""
                if width > 0 and glyph_ptr > 0 and glyph_ptr + width * 3 <= len(rom4c):
                    cols = []
                    for c in range(width):
                        b0 = rom4c[glyph_ptr + c * 3]
                        b1 = rom4c[glyph_ptr + c * 3 + 1]
                        b2 = rom4c[glyph_ptr + c * 3 + 2]
                        cols.append(f"{b0:02X}{b1:02X}{b2:02X}")
                    glyph_hex = " ".join(cols)
                    chars_with_data += 1

                # Printable ASCII label
                label = chr(ch) if 0x20 <= ch < 0x7F else ""

                f.write(f"0x{ch:02X}\t{label}\t{start}\t{width}\t{advance}"
                        f"\t0x{glyph_ptr:05X}\t{glyph_hex}\n")

        print(f"  {fname}: {chars_with_data} glyphs"
              f" ({first_char:#04x}-{last_char:#04x})")


def extract_4c_secondary_metrics(rom4c: bytes, outdir: Path) -> None:
    """Extract the secondary metrics from page 15 (offset $1E000)."""
    path = outdir / "lq500_4c_secondary_metrics.tsv"

    # Two bases: $0000 and $0600 relative to page 15
    page15 = 0x1E000
    bases = [
        ("base_0000", page15 + 0x0000),
        ("base_0600", page15 + 0x0600),
    ]

    with open(path, "w") as f:
        f.write("base\tchar_code\tchar\tbyte0\tbyte1\tbyte2"
                "\tbyte3\tbyte4\tbyte5\n")
        for base_name, base_off in bases:
            for ch in range(0x00, 0x100):
                off = base_off + ch * 6
                if off + 6 > len(rom4c):
                    break
                b = [rom4c[off + i] for i in range(6)]
                # Skip all-zero entries
                if all(x == 0 for x in b):
                    continue
                label = chr(ch) if 0x20 <= ch < 0x7F else ""
                f.write(f"{base_name}\t0x{ch:02X}\t{label}\t"
                        f"0x{b[0]:02X}\t0x{b[1]:02X}\t0x{b[2]:02X}\t"
                        f"0x{b[3]:02X}\t0x{b[4]:02X}\t0x{b[5]:02X}\n")

    count_0 = sum(1 for ch in range(256)
                  if any(rom4c[page15 + ch * 6 + i] for i in range(6)))
    count_6 = sum(1 for ch in range(256)
                  if page15 + 0x600 + ch * 6 + 6 <= len(rom4c)
                  and any(rom4c[page15 + 0x600 + ch * 6 + i] for i in range(6)))
    print(f"  {path.name}: base_0000={count_0} entries, base_0600={count_6} entries")


# ---------------------------------------------------------------------------
# 3C program ROM extraction
# ---------------------------------------------------------------------------

COUNTRY_NAMES = [
    "USA", "France", "Germany", "UK", "Denmark_I", "Sweden", "Italy",
    "Spain_I", "Japan", "Norway", "Denmark_II", "Spain_II", "Latin_America",
]


def extract_3c_international_substitution(rom3c: bytes, outdir: Path) -> None:
    """Extract the international character substitution table at $689C.

    The firmware at $1464 uses the formula: replacement = rom[$689C + VV:BB +
    match_index], where VV:BB = country × 12.  Country 0 (USA) reads directly
    from the 12 base codes at $689C, producing identity mappings.  Countries
    1-12 read from the subsequent rows.

    The ESC R handler at $1455 has LTI A,$0D, rejecting n >= 13.  The user
    manual documents Korea (13) and Legal (64) for the broader ESC/P family,
    but this ROM build only supports countries 0-12.  Twelve unused bytes at
    $6938-$6943 sit between the last country row and the command dispatcher
    at $6944.
    """
    table_off = 0x689C
    # 12 base ASCII codes that are substitutable
    base_codes = [rom3c[table_off + i] for i in range(12)]
    path = outdir / "lq500_3c_international_substitution.tsv"
    with open(path, "w") as f:
        # Header: country name, then each base code as a column
        header = "country"
        for code in base_codes:
            header += f"\t0x{code:02X}_{chr(code)}"
        f.write(header + "\n")

        # Country 0 (USA) reads from $689C+0 = base codes (identity).
        # Country n reads from $689C + n*12.
        for country_idx in range(13):
            row_off = table_off + country_idx * 12
            row = [rom3c[row_off + i] for i in range(12)]
            name = COUNTRY_NAMES[country_idx] if country_idx < len(COUNTRY_NAMES) else f"Country_{country_idx}"
            line = name
            for j, b in enumerate(row):
                orig = base_codes[j]
                if b == orig:
                    label = chr(b) if 0x20 <= b < 0x7F else ""
                    line += f"\t0x{b:02X}_{label}"
                elif 0x20 <= b < 0x7F:
                    line += f"\t0x{b:02X}_{chr(b)}"
                else:
                    line += f"\t0x{b:02X}"
            f.write(line + "\n")

    print(f"  {path.name}: {len(base_codes)} codes × {len(COUNTRY_NAMES)} countries")


GRAPHICS_MODE_NAMES = {
    0: "8pin_60dpi",
    1: "8pin_120dpi",
    2: "8pin_120dpi_hspeed",
    3: "8pin_240dpi",
    4: "8pin_80dpi_CRT_I",
    6: "8pin_90dpi_CRT_II",
    32: "24pin_60dpi",
    33: "24pin_120dpi",
    38: "24pin_90dpi_CRT_III",
    39: "24pin_180dpi",
}


def extract_3c_graphics_modes(rom3c: bytes, outdir: Path) -> None:
    """Extract the graphics mode validation table at $0D5D."""
    table_off = 0x0D5D
    path = outdir / "lq500_3c_graphics_modes.tsv"
    with open(path, "w") as f:
        f.write("mode\tmode_name\tcolumn_stride\tmode_flags\t"
                "is_24pin\tadjacent_ok\tmulti_pass\tnotes\n")
        for i in range(10):
            off = table_off + i * 3
            mode = rom3c[off]
            stride = rom3c[off + 1]
            flags = rom3c[off + 2]
            is_24pin = "yes" if flags & 0x80 else "no"
            # flags bit 1: adjacent dot printing allowed
            adj = "yes" if flags & 0x02 else "no"
            # multi-pass: modes with VV:6F bit 1 (from VV:3A)
            multi = "yes" if mode in (1, 3, 4, 33, 39) else "no"
            name = GRAPHICS_MODE_NAMES.get(mode, f"mode_{mode}")
            f.write(f"{mode}\t{name}\t{stride}\t0x{flags:02X}\t"
                    f"{is_24pin}\t{adj}\t{multi}\t\n")

    print(f"  {path.name}: 10 modes")


def extract_3c_render_geometry(rom3c: bytes, outdir: Path) -> None:
    """Extract the 7 render geometry tables at $7307-$739A."""
    tables = [
        ("cell_width_byte", 0x7307, 1, "Character cell width per mode"),
        ("rtl_base_word", 0x7317, 2, "Right-to-left base offset"),
        ("ltr_correction_word", 0x7341, 2, "Left-to-right VR correction offset"),
        ("rtl_stride_word", 0x735B, 2, "Right-to-left stride addend"),
        ("ltr_clip_word", 0x736B, 2, "Left-to-right clip limit addend"),
        ("ltr_clip_base_word", 0x737B, 2, "Left-to-right clip base"),
        ("col_stride_word", 0x738B, 2, "Image buffer column stride (3=LQ, 4=Draft)"),
    ]

    # Each table has entries indexed by (VV:3A & 7), so 8 entries
    num_entries = 8

    path = outdir / "lq500_3c_render_geometry.tsv"
    with open(path, "w") as f:
        # Build header
        header = "mode_index"
        for name, _, _, _ in tables:
            header += f"\t{name}"
        f.write(header + "\n")

        for idx in range(num_entries):
            line = str(idx)
            for _, base, width, _ in tables:
                off = base + idx * width
                if width == 1:
                    val = rom3c[off]
                else:
                    val = le16(rom3c, off)
                line += f"\t0x{val:04X}" if width == 2 else f"\t0x{val:02X}"
            f.write(line + "\n")

    print(f"  {path.name}: {len(tables)} tables × {num_entries} entries")


def extract_3c_remap_table(rom3c: bytes, outdir: Path) -> None:
    """Extract non-identity entries from the $6000 character remap table."""
    table_off = 0x6000
    path = outdir / "lq500_3c_remap_exceptions.tsv"
    count = 0
    with open(path, "w") as f:
        f.write("input\tinput_char\toutput\toutput_char\n")
        for i in range(256):
            val = rom3c[table_off + i]
            if val != i:
                in_label = chr(i) if 0x20 <= i < 0x7F else ""
                out_label = chr(val) if 0x20 <= val < 0x7F else ""
                f.write(f"0x{i:02X}\t{in_label}\t0x{val:02X}\t{out_label}\n")
                count += 1

    print(f"  {path.name}: {count} non-identity entries")


def extract_3c_8pin_expansion(rom3c: bytes, outdir: Path) -> None:
    """Extract the 8-pin to 24-pin expansion bit mapping.

    The firmware at $0C95-$0CD0 maps each input bit to a specific
    output byte (C/D/E → bytes 0/1/2 of the 3-byte column) and mask.
    These are hardcoded constants in the instruction stream, extracted
    from the firmware trace.
    """
    # Mapping from firmware trace at $0C95:
    # input bit 7 → C.$C0, bit 6 → C.$18, bit 5 → C.$03,
    # bit 4 → D.$60, bit 3 → D.$0C, bit 2 → D.$01+E.$80,
    # bit 1 → E.$30, bit 0 → E.$06
    mapping = [
        (7, 0, 0xC0, "pins 1-2 (doubled)"),
        (6, 0, 0x18, "pins 4-5 (doubled, gap at 3)"),
        (5, 0, 0x03, "pins 7-8 (doubled)"),
        (4, 1, 0x60, "pins 10-11 (doubled)"),
        (3, 1, 0x0C, "pins 13-14 (doubled)"),
        (2, 1, 0x01, "pin 16 (split across bytes)"),
        # bit 2 also sets E.$80:
        # handled as second entry below
        (1, 2, 0x30, "pins 19-20 (doubled)"),
        (0, 2, 0x06, "pins 22-23 (doubled)"),
    ]

    path = outdir / "lq500_3c_8pin_expansion_map.tsv"
    with open(path, "w") as f:
        f.write("input_bit\toutput_byte\toutput_mask\tnotes\n")
        for bit, byte_idx, mask, note in mapping:
            f.write(f"{bit}\t{byte_idx}\t0x{mask:02X}\t{note}\n")
        # Extra entry for the split bit 2 → E.$80
        f.write(f"2\t2\t0x80\tpin 17 (split: D.01 + E.80)\n")

    print(f"  {path.name}: 9 mapping entries (8 input bits, 1 split)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract LQ-500 ROM tables for emulator use")
    parser.add_argument("--rom3c",
                        default="roms/lq500_3c_m25a10pa_internal_prom.bin",
                        help="Path to 3C program ROM (32K)")
    parser.add_argument("--rom4c",
                        default="roms/lq500_4c_m10a10la_cg_128k_custom_prom.bin",
                        help="Path to 4C CG ROM (128K)")
    parser.add_argument("--outdir", default="data",
                        help="Output directory for TSV files")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)

    # Read ROMs
    rom3c_path = Path(args.rom3c)
    rom4c_path = Path(args.rom4c)

    if not rom3c_path.exists():
        print(f"Error: 3C ROM not found: {rom3c_path}", file=sys.stderr)
        sys.exit(1)
    if not rom4c_path.exists():
        print(f"Error: 4C ROM not found: {rom4c_path}", file=sys.stderr)
        sys.exit(1)

    rom3c = rom3c_path.read_bytes()
    rom4c = rom4c_path.read_bytes()

    if len(rom3c) != 32768:
        print(f"Warning: 3C ROM is {len(rom3c)} bytes (expected 32768)",
              file=sys.stderr)
    if len(rom4c) != 131072:
        print(f"Warning: 4C ROM is {len(rom4c)} bytes (expected 131072)",
              file=sys.stderr)

    print("=== 4C CG ROM extraction ===")
    records = extract_4c_font_directory(rom4c, outdir)
    extract_4c_font_glyphs(rom4c, outdir, records)
    extract_4c_secondary_metrics(rom4c, outdir)

    print()
    print("=== 3C program ROM extraction ===")
    extract_3c_international_substitution(rom3c, outdir)
    extract_3c_graphics_modes(rom3c, outdir)
    extract_3c_render_geometry(rom3c, outdir)
    extract_3c_remap_table(rom3c, outdir)
    extract_3c_8pin_expansion(rom3c, outdir)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
