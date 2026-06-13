# Epson LQ-500 ROM analysis

This repository contains working reverse-engineering notes, tools, and
reference documents for the Epson LQ-500 printer firmware.

It exists to support LQ-500 printer emulation in Dreamulator:

https://github.com/RealDeuce/Dreamulator/

The goal is not to create a generic printer reference.  The goal is to keep the
evidence needed to implement a ROM-derived LQ-500 output path: resident fonts,
pitch selection, print effects, downloaded-character behavior, graphics modes,
bidirectional adjustment, paper motion, carriage timing, printhead output, DIP
switch behavior, and command dispatch details.

## Why this exists

Dreamulator already has printer output paths for other printers where the
rendering behavior is derived from the original device rather than from a
generic substitute font.  The LQ-500 should follow the same model.

The LQ-500 firmware ROM and service manual contain enough printer behavior to
identify:

- the command parser and ESC/P control-character dispatch paths;
- parallel and serial host interfaces with ring-buffer management, ACK/BUSY
  handshake, and XON/XOFF flow control;
- the E01A05KA (6C) gate-array register protocol for host data, status/control
  signals, bank selection, and carriage control;
- the E05A02LA head gate-array three-byte latch interface, HPW pulse-width
  timing, and voltage-compensated drive control;
- 24-pin printhead wire-to-connector-to-physical-column mapping;
- carriage home seek, speed modes, acceleration/deceleration profiles, phase
  excitation, current control, and the normal carriage scheduler;
- paper-feed motor control, phase switching, drive/hold, and command-feed
  timing;
- startup DIP switch and ADC panel-switch reading;
- VR1/VR2 bidirectional adjustment with per-mode correction units;
- service/self-test, data-dump, and bidirectional-adjustment calibration UI.

Keeping dump hashes, analysis documents, data tables, and trace outputs
together makes the Dreamulator implementation reproducible.  When the emulator
needs a behavioral detail, this repository should show whether that detail is
already known, where it came from, and which ROM offsets are useful for
confirming it.

## Repository contents

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Workspace map: file inventory, trace workflow, current code anchors, and style conventions. |
| `docs/lq500_3c_design_overview.md` | Architecture notes: execution shape, gate-array registers, input pipeline, command dispatch, mechanical subsystems, and service/test paths. |
| `docs/lq500_3c_program_rom_map.md` | Conservative program ROM map: segment ranges, high-confidence routine table, gate-array register summary, and host-to-parser pipeline. |
| `docs/lq500_3c_paper_feed.md` | Paper advance/retard: PB2 drive/hold, PB3/PB4 phase switching, ESC J/j feed distance, and timing. |
| `docs/lq500_3c_carriage_operation.md` | Carriage home seek, position/timing, current selection, PC7/TM gate-array pulse, F003 control, and the normal scheduler. |
| `docs/lq500_3c_printhead.md` | E05A02LA head gate-array commands, three-byte latch burst output, HPW timing, and voltage-compensated pulse control. |
| `docs/lq500_reference.md` | Extracted manual facts: printer profile, host interface circuit, buffer architecture, character sets, DIP switches, speed modes, printhead specs, and paper-feed motor details. |
| `docs/rom_dump_handoff.md` | Resume point and current analysis state. |
| `data/lq500_3c_program_labels.tsv` | Working symbol labels for the 3C program ROM. |
| `data/lq500_3c_command_dispatch_tables.tsv` | Parsed primary and ESC command dispatch tables. |
| `data/lq500_3c_command_behaviors.tsv` | Audited command behavior: parameter consumption, state updates, and evidence. |
| `data/lq500_3c_host_interface_path.tsv` | Host interface pipeline: interrupt vectors, ring buffer, ACK/BUSY, XON/XOFF, and consumer flow control. |
| `data/lq500_3c_printhead_path.tsv` | Printhead mechanical-output path and E05A02LA command/data behavior. |
| `data/lq500_3c_printhead_wire_map.tsv` | E05A02LA H1..H24 pin/output to CN5/CN6 connector and physical wire placement. |
| `data/lq500_3c_bidirectional_adjustment.tsv` | VR1/VR2 correction slots, manual units, firmware consumers, and emulator offset limits. |
| `data/lq500_3c_carriage_*.tsv` | Carriage path, home seek, sequence records, speed modes, timing profiles, output states, scheduler contexts, mode state, and F003 control paths. |
| `data/lq500_3c_paper_*.tsv` | Paper advance path and feed timing. |
| `data/lq500_3c_mechanism_timing_records.tsv` | Decoded mechanism timing-record bytes. |
| `data/lq500_3c_6000_block_usage.tsv` | Consumer map for the 6000h-6FFFh data/code block. |
| `data/lq500_3c_7000_block_usage.tsv` | Consumer map for the 7000h-7FFFh mechanism/render/service block. |
| `data/lq500_3c_trace_roots.tsv` | Editable recursive trace roots for the MAME-based tracer. |
| `data/lq500_3c_vector_trace.*` | Generated trace outputs (TSV, JSON, Markdown). |
| `tools/trace_upd7810_unidasm.py` | Recursive disassembly tracer using MAME's `unidasm`. |
| `patches/minipro-lq500-4c-custom-prom.patch` | Optional minipro source patch for custom 4C pin-22/A16 read experiments. |
| `epsonlq-500servicemanual.pdf` | LQ-500/L-1000 service/technical manual. |

## ROM summary

Two ROMs are involved:

### 3C program PROM

The main firmware is a 32 KiB program PROM mapped at CPU `0000h-7FFFh`.  It is
labeled `M25A10PA` on the board and is read as a 27C256-class device.

The CPU is NEC uPD7810 family.  The recursive trace is generated locally using:

```sh
python3 tools/trace_upd7810_unidasm.py \
  --rom roms/lq500_3c_m25a10pa_internal_prom.bin \
  --unidasm ../mame/unidasm \
  --out-prefix data/lq500_3c_vector_trace \
  --roots-file data/lq500_3c_trace_roots.tsv
```

### 4C CG/font ROM

The character-generator ROM is a 128 KiB custom PROM at board position 4C.
The schematic confirms pin 1 is A15, so each 64 KiB A16 bank has valid
internal addressing.  The dump was obtained using a minipro-compatible reader
with the patch in `patches/`.

ROM dumps are local-only files under `roms/` (gitignored).  They are not
distributed in this repository.

## Key firmware structures

The main command/control loop starts at `400Bh`.  It fetches bytes from the
input ring buffer via `CALT ($0080)` -> `0A0Bh`, classifies printable bytes
at `4038h`, and dispatches commands through the table-driven scanner at
`6944h`.

The primary control-command table is at `696Eh` (14 entries including ESC, LF,
CR, FF, BS, HT, VT, SO, SI, and others).  The ESC command table is at `699Ch`
(62 entries).  Both tables are count-prefixed byte/handler pairs.

Mechanical output is split across three subsystems:

- **Paper feed**: `093Eh`/`096Ah` rotate PB3/PB4 stepper phases; `540Dh`
  controls PB2 drive/hold; timing comes from the `7088h`/`70BFh` tables.
- **Carriage**: `0908h` pulses PC7/TM; `51F7h`/`5253h` handle startup home
  seek; `5719h` indexes the `72B3h` scheduler records; `7005h` provides
  runtime timing/output profiles.
- **Printhead**: `5681h` resets the E05A02LA latch counter; `08D0h` arms the
  direction-dependent burst; `0978h` emits three bytes to F005h and reloads
  ETM0 from the voltage-compensation table at `72DBh`.

The host input pipeline uses a ring buffer in external RAM at `8500h`, fed by
the parallel ISR (`0582h`, reads F000h) and the serial ISR (`05E2h`, reads
RXB), with ACK/BUSY parallel handshake and XON/XOFF serial flow control.

## How this should be used by Dreamulator work

Use this repository as the evidence pack for the LQ-500 implementation:

1. Keep local ROM dumps under `roms/` (gitignored).  Use the 3C program PROM
   and 4C CG ROM as canonical source images.
2. Use `docs/lq500_3c_design_overview.md` for architecture, gate-array
   registers, input pipeline, and mechanical subsystem overview.
3. Use `docs/lq500_3c_program_rom_map.md` for ROM segment layout and
   high-confidence routine addresses.
4. Use `data/lq500_3c_command_behaviors.tsv` for per-command parameter
   consumption and state updates.
5. Use the subsystem docs (`printhead.md`, `carriage_operation.md`,
   `paper_feed.md`) and their companion TSV data files for mechanical output
   behavior.
6. Use `docs/lq500_reference.md` for service-manual facts that are not
   otherwise derivable from the ROM trace.
7. When a new emulator behavior is unclear, add the new trace and derived
   output here first, then port the behavior into Dreamulator.

The desired end state in Dreamulator is an LQ-500 output path whose glyphs,
command behavior, and mechanical semantics come from this ROM analysis rather
than from host fonts or approximations.
