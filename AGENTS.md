# LQ-500 Reverse-Engineering Notes

This workspace maps the Epson LQ-500 `3C` program PROM and `4C` CG/font ROM.
Keep the work evidence-based: labels should cite local code shape, trace output,
manual notes, or hardware measurements.

## Local-Only Files

- `roms/` is intentionally ignored by git. It contains ROM dumps and
  ROM-derived disassemblies.
- Do not commit ROM images, split banks, programmer read attempts, or generated
  disassembly listings derived from those ROM bytes.
- The docs may reference files under `roms/`; those references are for local
  analysis and are expected to be unresolved in a clean checkout.

## Main Files

- `docs/rom_dump_handoff.md`: resume point and current state.
- `docs/lq500_3c_program_rom_map.md`: conservative program ROM map.
- `docs/lq500_3c_design_overview.md`: architecture notes and current theory.
- `docs/lq500_reference.md`: extracted manual facts.
- `data/lq500_3c_program_labels.tsv`: working symbol labels.
- `data/lq500_3c_command_dispatch_tables.tsv`: parsed primary/ESC command
  dispatch tables.
- `data/lq500_3c_command_behaviors.tsv`: audited command behavior notes,
  parameter consumption, state updates, and evidence.
- `data/lq500_3c_trace_roots.tsv`: editable recursive trace roots.

## Trace Workflow

Use the local MAME disassembler:

```sh
python3 tools/trace_upd7810_unidasm.py \
  --rom roms/lq500_3c_m25a10pa_internal_prom.bin \
  --unidasm ../mame/unidasm \
  --out-prefix data/lq500_3c_vector_trace \
  --roots-file data/lq500_3c_trace_roots.tsv
```

The trace outputs are TSV/JSON/Markdown under `data/`. Add hand-confirmed
computed targets to `data/lq500_3c_trace_roots.tsv`, then rerun the tracer.
Do not automatically promote every untraced gap; many are tables, fill bytes,
or skipped-over instruction bytes.

## Current Code Anchors

- `0582h`: candidate parallel/gate-array host input ISR into the shared buffer.
- `05E2h`: CPU `RXB` host input ISR into the same buffer.
- `0A0Bh`: shared input-byte consumer, exposed via `CALT ($0080)`.
- `400Bh`: top-level host-byte decode loop.
- `4038h`: printable-byte classifier and font/style selector.
- `6944h`: table-driven command dispatcher.
- `696Eh`: primary control-command table.
- `699Ch`: ESC command table.
- `4F37h`/`4F54h`: startup DIP/panel switch reads via ADC/table logic.
- `4EEAh`: debounced panel button/action reader.

## Style

- Use TSV for trace tables and hand-maintained dispatch tables.
- Keep labels conservative. Prefer names like `candidate`, `compat`, or
  `unknown` when the behavior is not proven.
- Keep hardware measurements separate from firmware inference, and note which
  is which.
