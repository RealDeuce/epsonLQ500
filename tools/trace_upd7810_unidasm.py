#!/usr/bin/env python3
"""Conservative recursive tracer using MAME unidasm output.

This is intentionally architecture-light: MAME does the instruction decoding,
and this script classifies control-flow by mnemonic. It is good enough to map
directly reachable code and likely data gaps in the LQ-500 program ROM.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path


LINE_RE = re.compile(
    r"^([0-9a-fA-F]{4}):\s+((?:[0-9a-fA-F]{2}\s+)+)\s*([A-Z][A-Z0-9]*)\s*(.*)$"
)
TARGET_RE = re.compile(r"\$([0-9A-Fa-f]{4})")
ROOT_RE = re.compile(r"^\s*(?:0x)?([0-9A-Fa-f]{1,4})\s*(?:,|#|$|\s)")
TABULAR_DELIMITER = "\t"


TERMINAL = {"RET", "RETI", "RETS", "STOP", "HALT"}
UNCONDITIONAL = {"JMP", "JR"}
CONDITIONAL = {"JRE"}
CALLS = {"CALL", "CALF", "CALT"}
INDIRECT_CALLS = {"CALB"}
INDIRECT_TERMINAL = {"JEA"}


# uPD7810 has skip-producing instructions rather than a rich conditional
# branch set. If a skip flag is set, the CPU suppresses the next instruction.
# Static tracing therefore follows both the normal fallthrough and the
# instruction after the next instruction for every possible skip producer.
SKIP_PREFIXES = (
    "SK",
    "SLRC",
    "SLLC",
    "ADDNC",
    "GTA",
    "SUBNB",
    "LTA",
    "NEA",
    "EQA",
    "ONA",
    "OFFA",
    "ONAX",
    "OFFAX",
    "NEAX",
    "EQAX",
    "DADDNC",
    "DGT",
    "DSUBNB",
    "DLT",
    "DON",
    "DOFF",
    "DNE",
    "DEQ",
    "BIT",
    "OFFI",
    "ONI",
    "EQI",
    "NEI",
    "GTI",
    "LTI",
    "DCR",
    "INR",
    "JB",
)


@dataclass(frozen=True)
class Insn:
    addr: int
    size: int
    op: str
    rest: str
    text: str


def parse_insn(text: str) -> Insn | None:
    first = text.splitlines()[0] if text else ""
    match = LINE_RE.match(first)
    if not match:
        return None
    addr = int(match.group(1), 16)
    bytes_text = match.group(2).split()
    return Insn(
        addr=addr,
        size=len(bytes_text),
        op=match.group(3),
        rest=match.group(4).strip(),
        text=first.rstrip(),
    )


class Decoder:
    def __init__(self, unidasm: Path, rom: Path, cache_path: Path | None = None):
        self.unidasm = unidasm
        self.rom = rom
        self.cache_path = cache_path
        self.cache: dict[int, Insn | None] = {}
        if cache_path and cache_path.exists():
            raw = json.loads(cache_path.read_text())
            for addr_text, value in raw.items():
                addr = int(addr_text, 16)
                self.cache[addr] = Insn(**value) if value is not None else None

    def decode(self, addr: int) -> Insn | None:
        if addr in self.cache:
            return self.cache[addr]
        if addr < 0 or addr >= 0x8000:
            self.cache[addr] = None
            return None
        cmd = [
            str(self.unidasm),
            str(self.rom),
            "-arch",
            "upd7810",
            "-basepc",
            f"0x{addr:04x}",
            "-skip",
            f"0x{addr:04x}",
            "-count",
            "0x8",
        ]
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        insn = parse_insn(proc.stdout)
        if insn is not None and insn.addr != addr:
            insn = None
        self.cache[addr] = insn
        return insn

    def save_cache(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            f"0x{addr:04X}": None
            if insn is None
            else {
                "addr": insn.addr,
                "size": insn.size,
                "op": insn.op,
                "rest": insn.rest,
                "text": insn.text,
            }
            for addr, insn in sorted(self.cache.items())
        }
        self.cache_path.write_text(json.dumps(raw, indent=2) + "\n")


def direct_targets(insn: Insn) -> list[int]:
    targets = [int(match.group(1), 16) for match in TARGET_RE.finditer(insn.rest)]
    return [target for target in targets if 0 <= target < 0x8000]


def add_edge(edges: dict[int, set[int]], src: int, dst: int | None) -> None:
    if dst is not None and 0 <= dst < 0x8000:
        edges[src].add(dst)


def is_skip_producer(insn: Insn) -> bool:
    return insn.op.startswith(SKIP_PREFIXES)


def add_skip_successor(decoder: Decoder, next_addrs: list[int], fallthrough: int) -> None:
    next_insn = decoder.decode(fallthrough)
    if next_insn is not None:
        next_addrs.append(fallthrough + next_insn.size)


def dedupe_roots(roots: list[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for root in roots:
        if 0 <= root < 0x8000 and root not in seen:
            seen.add(root)
            out.append(root)
    return out


def read_roots_file(path: Path) -> list[int]:
    if not path.exists():
        raise FileNotFoundError(path)
    roots: list[int] = []
    if path.suffix.lower() == ".csv":
        with path.open(newline="") as f:
            reader = csv.DictReader(row for row in f if not row.lstrip().startswith("#"))
            if reader.fieldnames and "address" in reader.fieldnames:
                for row in reader:
                    value = (row.get("address") or "").strip()
                    if value:
                        roots.append(int(value, 0))
                return roots
    if path.suffix.lower() == ".tsv":
        with path.open(newline="") as f:
            reader = csv.DictReader(
                (row for row in f if not row.lstrip().startswith("#")),
                delimiter=TABULAR_DELIMITER,
            )
            if reader.fieldnames and "address" in reader.fieldnames:
                for row in reader:
                    value = (row.get("address") or "").strip()
                    if value:
                        roots.append(int(value, 0))
                return roots

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = ROOT_RE.match(line)
        if match:
            roots.append(int(match.group(1), 16))
    return roots


def trace(decoder: Decoder, roots: list[int]):
    seen: set[int] = set()
    code_bytes: set[int] = set()
    decoded: dict[int, Insn] = {}
    edges: dict[int, set[int]] = defaultdict(set)
    xrefs: dict[int, set[int]] = defaultdict(set)
    unresolved: dict[int, str] = {}
    queue: deque[int] = deque(roots)

    while queue:
        addr = queue.popleft()
        if addr in seen or not (0 <= addr < 0x8000):
            continue
        insn = decoder.decode(addr)
        if insn is None:
            unresolved[addr] = "decode failed"
            continue
        seen.add(addr)
        decoded[addr] = insn
        for off in range(insn.size):
            if 0 <= addr + off < 0x8000:
                code_bytes.add(addr + off)

        fallthrough = addr + insn.size
        next_addrs: list[int] = []
        targets = direct_targets(insn)

        if insn.op == "illegal":
            unresolved[addr] = insn.text
            continue
        if insn.op in TERMINAL:
            continue
        elif insn.op in INDIRECT_CALLS:
            unresolved[addr] = insn.text
            next_addrs.append(fallthrough)
        elif insn.op in INDIRECT_TERMINAL:
            unresolved[addr] = insn.text
            continue
        elif insn.op in CALLS:
            next_addrs.append(fallthrough)
            next_addrs.extend(targets)
        elif insn.op in UNCONDITIONAL:
            next_addrs.extend(targets)
        elif insn.op in CONDITIONAL:
            next_addrs.append(fallthrough)
            next_addrs.extend(targets)
        elif is_skip_producer(insn):
            next_addrs.append(fallthrough)
            add_skip_successor(decoder, next_addrs, fallthrough)
        else:
            next_addrs.append(fallthrough)

        for dst in next_addrs:
            if not (0 <= dst < 0x8000):
                continue
            add_edge(edges, addr, dst)
            xrefs[dst].add(addr)
            if dst not in seen:
                queue.append(dst)

    return decoded, code_bytes, edges, xrefs, unresolved


def group_ranges(addrs: set[int], limit: int = 0x8000) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    i = 0
    while i < limit:
        if i not in addrs:
            i += 1
            continue
        start = i
        while i + 1 < limit and i + 1 in addrs:
            i += 1
        ranges.append((start, i + 1))
        i += 1
    return ranges


def classify_gap(data: bytes, lo: int, hi: int) -> str:
    chunk = data[lo:hi]
    if chunk and all(byte == 0xFF for byte in chunk):
        return "fill_ff"
    if chunk and all(byte == 0x00 for byte in chunk):
        return "fill_00"
    printable = sum(1 for byte in chunk if byte in (0x00, 0xFF) or 0x20 <= byte < 0x7F)
    if chunk and printable / len(chunk) > 0.75:
        return "likely_text_or_table"
    return "likely_data_or_untraced_code"


def write_outputs(
    out_prefix: Path,
    rom_data: bytes,
    roots: list[int],
    decoded: dict[int, Insn],
    code_bytes: set[int],
    edges: dict[int, set[int]],
    xrefs: dict[int, set[int]],
    unresolved: dict[int, str],
) -> None:
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    data_bytes = set(range(len(rom_data))) - code_bytes
    code_ranges = group_ranges(code_bytes, len(rom_data))
    data_ranges = group_ranges(data_bytes, len(rom_data))

    used_roots_tsv = out_prefix.with_suffix(".used_roots.tsv")
    with used_roots_tsv.open("w", newline="") as f:
        writer = csv.writer(f, delimiter=TABULAR_DELIMITER, lineterminator="\n")
        writer.writerow(["address", "status"])
        for root in roots:
            writer.writerow([f"0x{root:04X}", "decoded" if root in decoded else "unresolved"])

    segments_tsv = out_prefix.with_suffix(".segments.tsv")
    with segments_tsv.open("w", newline="") as f:
        writer = csv.writer(f, delimiter=TABULAR_DELIMITER, lineterminator="\n")
        writer.writerow(["start", "end_exclusive", "size", "kind", "classification"])
        for lo, hi in code_ranges:
            writer.writerow([f"0x{lo:04X}", f"0x{hi:04X}", hi - lo, "trace_code", ""])
        for lo, hi in data_ranges:
            writer.writerow([f"0x{lo:04X}", f"0x{hi:04X}", hi - lo, "not_reached", classify_gap(rom_data, lo, hi)])

    frontier_tsv = out_prefix.with_suffix(".frontier.tsv")
    with frontier_tsv.open("w", newline="") as f:
        writer = csv.writer(f, delimiter=TABULAR_DELIMITER, lineterminator="\n")
        writer.writerow(["address", "kind", "size", "classification", "text"])
        for addr, text in sorted(unresolved.items()):
            writer.writerow([f"0x{addr:04X}", "unresolved_stop", "", "", text])
        for lo, hi in data_ranges:
            classification = classify_gap(rom_data, lo, hi)
            if classification == "likely_data_or_untraced_code":
                writer.writerow([f"0x{lo:04X}", "untraced_gap_start", hi - lo, classification, ""])

    insn_tsv = out_prefix.with_suffix(".instructions.tsv")
    with insn_tsv.open("w", newline="") as f:
        writer = csv.writer(f, delimiter=TABULAR_DELIMITER, lineterminator="\n")
        writer.writerow(["address", "size", "op", "xrefs", "successors", "text"])
        for addr in sorted(decoded):
            insn = decoded[addr]
            writer.writerow(
                [
                    f"0x{addr:04X}",
                    insn.size,
                    insn.op,
                    " ".join(f"0x{x:04X}" for x in sorted(xrefs.get(addr, set()))),
                    " ".join(f"0x{x:04X}" for x in sorted(edges.get(addr, set()))),
                    insn.text,
                ]
            )

    summary_json = out_prefix.with_suffix(".summary.json")
    md = out_prefix.with_suffix(".md")
    summary = {
        "roots": [f"0x{root:04X}" for root in roots],
        "decoded_instruction_count": len(decoded),
        "code_bytes": len(code_bytes),
        "not_reached_bytes": len(data_bytes),
        "code_ranges": [[f"0x{lo:04X}", f"0x{hi:04X}", hi - lo] for lo, hi in code_ranges],
        "data_ranges": [
            [f"0x{lo:04X}", f"0x{hi:04X}", hi - lo, classify_gap(rom_data, lo, hi)]
            for lo, hi in data_ranges
        ],
        "unresolved": {f"0x{addr:04X}": text for addr, text in sorted(unresolved.items())},
        "outputs": {
            "used_roots_tsv": str(used_roots_tsv),
            "segments_tsv": str(segments_tsv),
            "frontier_tsv": str(frontier_tsv),
            "instructions_tsv": str(insn_tsv),
            "summary_json": str(summary_json),
            "markdown": str(md),
        },
    }
    summary_json.write_text(json.dumps(summary, indent=2) + "\n")

    lines = [
        "# LQ-500 3C Recursive Trace Map",
        "",
        "Roots: " + ", ".join(f"`0x{root:04X}`" for root in roots),
        "",
        f"- Decoded instructions: `{len(decoded)}`",
        f"- Reached code bytes: `{len(code_bytes)}`",
        f"- Not reached bytes: `{len(data_bytes)}`",
        "",
        "## Reached Code Ranges",
        "",
        "| Start | End | Size |",
        "| --- | --- | ---: |",
    ]
    for lo, hi in code_ranges:
        lines.append(f"| `0x{lo:04X}` | `0x{hi:04X}` | {hi - lo} |")
    lines.extend(["", "## Not-Reached Ranges", "", "| Start | End | Size | Classification |", "| --- | --- | ---: | --- |"])
    for lo, hi in data_ranges:
        lines.append(f"| `0x{lo:04X}` | `0x{hi:04X}` | {hi - lo} | {classify_gap(rom_data, lo, hi)} |")
    lines.extend(["", "## Unresolved Stops", ""])
    if unresolved:
        lines.extend(f"- `0x{addr:04X}`: `{text}`" for addr, text in sorted(unresolved.items()))
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Direct calls/jumps are followed.",
            "- Conditional `JRE` follows both target and fallthrough.",
            "- uPD7810 skip-producing instructions follow both fallthrough and skipped-next-instruction paths.",
            "- `RET`, `RETI`, and `RETS` terminate a path.",
            "- `JEA`, `illegal`, and failed decodes are treated as unresolved stops.",
            "- `.frontier.tsv` is the iterative follow-up file; hand-confirmed entry points belong in the roots TSV passed by `--roots-file`.",
            "- Indirect jump tables and computed calls need manual follow-up.",
            "",
        ]
    )
    md.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--unidasm", required=True, type=Path)
    parser.add_argument("--out-prefix", required=True, type=Path)
    parser.add_argument(
        "--roots",
        default="0x0000,0x0004,0x0008,0x0010,0x0018,0x0028,0x0060",
        help="Comma-separated root addresses.",
    )
    parser.add_argument(
        "--roots-file",
        type=Path,
        help="Optional TSV/CSV/text file of root addresses. TSV/CSV files should use an address column.",
    )
    parser.add_argument(
        "--decode-cache",
        type=Path,
        help="Optional JSON cache for per-address decoder results. Defaults beside the output prefix.",
    )
    args = parser.parse_args()

    roots = [int(part, 0) for part in args.roots.split(",") if part.strip()]
    if args.roots_file:
        roots.extend(read_roots_file(args.roots_file))
    roots = dedupe_roots(roots)
    rom_data = args.rom.read_bytes()
    decode_cache = args.decode_cache or args.out_prefix.with_suffix(".decode_cache.json")
    decoder = Decoder(args.unidasm, args.rom, decode_cache)
    try:
        decoded, code_bytes, edges, xrefs, unresolved = trace(decoder, roots)
    finally:
        decoder.save_cache()
    write_outputs(args.out_prefix, rom_data, roots, decoded, code_bytes, edges, xrefs, unresolved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
