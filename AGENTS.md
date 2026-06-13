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
- `docs/lq500_3c_paper_feed.md`: paper advance/retard hardware, command path,
  timing, and drive-window notes.
- `docs/lq500_3c_carriage_operation.md`: carriage home seek, timing, current,
  F003 control, and scheduler notes.
- `docs/lq500_3c_printhead.md`: printhead register anchors and pin-firing
  workstream notes.
- `docs/lq500_reference.md`: extracted manual facts.
- `data/lq500_3c_program_labels.tsv`: working symbol labels.
- `data/lq500_3c_command_dispatch_tables.tsv`: parsed primary/ESC command
  dispatch tables.
- `data/lq500_3c_command_behaviors.tsv`: audited command behavior notes,
  parameter consumption, state updates, and evidence.
- `data/lq500_3c_6000_block_usage.tsv`: consumer map for the `6000h-6FFFh`
  data/code block.
- `data/lq500_3c_7000_block_usage.tsv`: consumer map for the `7000h-7FFFh`
  mechanism/render/service block.
- `data/lq500_3c_mechanism_timing_records.tsv`: decoded timing-record bytes
  copied by `55B1h` into `EF49h..EF60h`.
- `data/lq500_3c_paper_advance_path.tsv`: paper-feed command path from
  ESC/P distance setup to PB2/PB3/PB4 timed output.
- `data/lq500_3c_paper_feed_timing.tsv`: service-manual paper-feed
  acceleration/deceleration timings and ROM timing-word matches.
- `data/lq500_3c_carriage_path.tsv`: carriage manual anchors, home seek,
  current-control states, and PC7/TM timing-path notes.
- `data/lq500_3c_carriage_home_seek.tsv`: decoded startup `51F7h-5253h`
  PA5 / `PA mask 20h` HOME branch sequence and timed seek core.
- `data/lq500_3c_carriage_sequence_records.tsv`: decoded five-byte
  `72B3h-72D8h` carriage scheduler records copied to `EF7C..EF80`.
- `data/lq500_3c_carriage_timing_profiles.tsv`: runtime `7005h` carriage
  timing profile map tying `VV63` records to Tables 2-12 through 2-15.
- `data/lq500_3c_carriage_output_state_records.tsv`: decoded normal
  `7005h` record bytes that `540Dh` maps to carriage current states.
- `data/lq500_3c_f003_control_paths.tsv`: CALT vector and caller map for
  `VV15`/`F003h` carriage control-bit updates.
- `data/lq500_3c_carriage_scheduler_contexts.tsv`: callers and runtime-state
  paths around the normal `56C8h-5712h` carriage scheduler.
- `data/lq500_3c_vv3a_mode_selector.tsv`: shared `VV3A`/`VV6F` selector
  values across carriage TM1 records and render geometry tables.
- `data/lq500_3c_carriage_mode_state.tsv`: state plumbing from `VV1F` through
  `VV31`/`VV32`/`VV3A` to `VV6F` and `F003h` control-bit notes.
- `data/lq500_3c_trace_roots.tsv`: editable recursive trace roots.
- `patches/minipro-lq500-4c-custom-prom.patch`: optional minipro source patch
  for custom `4C` pin-22/A16 read experiments.

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

Treat `data/lq500_3c_vector_trace.instructions.tsv` as the source of truth for
decoded program-ROM instructions that are already covered by the recursive
trace. Do not rerun `unidasm` just to inspect an address range that is already
present in that TSV; read/filter the TSV instead. Rerun the tracer only after
adding missing roots, such as hand-confirmed computed jump/table targets, to
`data/lq500_3c_trace_roots.tsv`.

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
- When describing CPU port writes, distinguish bit masks from schematic signal
  names. Use wording such as `PB mask 18h` or `PB & 18h` for firmware masks,
  and reserve names like `PB3`/`PB4` for actual port bit lines from the
  schematic/manual.
- uPD7810 conditional operations skip the following instruction when their
  predicate is true. In the local MAME implementation, `ONI/ONIW` skip when
  any masked bit is set, `OFFI/OFFIW` skip when masked bits are clear,
  `NEI/NEIW` skip when not equal, `EQI/EQIW` skip when equal, and `DLT` skips
  on carry after subtraction, which corresponds to the left operand being less
  than the right operand.
- uPD7810 `MVI A,xx` uses the CPU `L1` overlay flag: the first consecutive
  `MVI A,xx` loads `A` and sets `L1`; later consecutive `MVI A,xx`
  instructions act as NOPs until an instruction that clears `L1`. Firmware uses
  this for compact selector lists such as `540Dh`.
- uPD7810 `BLOCK` copies one byte, increments source/destination, decrements
  `C`, and repeats by backing up `PC` until `C` underflows to `FFh`. Thus an
  initial `C=n` copies `n+1` bytes.
- uPD7810 `CALT` entries are vector-table entries, not linear code. For
  example, bytes at `00B8h`/`00BAh` are the vectors to `51EDh`/`51E9h`;
  do not treat the apparent linear disassembly at those bytes as executed code.
