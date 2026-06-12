# LQ-500 3C Program ROM First-Pass Code Map

Source dump:

- `roms/lq500_3c_m25a10pa_internal_prom.bin`
- CRC32 `cf3ba9da`
- SHA1 `7275ef3547ad1bbb12210d626c796a827f308bb6`
- Disassembly: `roms/lq500_3c_m25a10pa_internal_prom.asm`
- First-pass labels: `data/lq500_3c_program_labels.csv`
- Parsed command dispatch tables: `data/lq500_3c_command_dispatch_tables.tsv`
- Recursive vector trace: `data/lq500_3c_vector_trace.md`
- Editable trace roots: `data/lq500_3c_trace_roots.tsv`

This map is intentionally conservative. Labels marked low or medium confidence
are working names based on nearby constants, register accesses, strings, and
call shape. They should be renamed as control-flow and hardware behavior are
confirmed.

## Address Space Notes

The dumped ROM is a 32 KiB program PROM mapped at CPU `0000h-7FFFh`. The
firmware uses external windows and buffers outside this ROM:

| Address/range | Current meaning |
| --- | --- |
| `8000h` / `8600h` | CG/RAM banked window candidates used by glyph/metric routines. |
| `A000h` | Touched during reset as a separate memory/window area. |
| `EE00h-EFFFh` | Main RAM/state page used heavily by firmware variables and pointers. |
| `FF00h` | Scratch/print string buffer. |
| `F000h` | Gate-array/status or host data byte read by the `0582h` ISR. Candidate parallel-port input path, but the exact board signal is still unconfirmed. |
| `F001h` | Gate-array control/select register. Manual says bit 7 low selects external PROM when valid. Firmware also toggles bits 0, 1, 2, and 3 here. |
| `F002h` | Gate-array bank register. Manual says bank lines 7 and 6 are involved in CG selection. |
| `F003h` | Gate-array/status or mode register; initialized from `VV15`. |
| `F004h-F005h` | Gate-array/head-interface registers touched during CPU/port init and print paths. |

## Top-Level Segments

| Range | Label | Evidence |
| --- | --- | --- |
| `0000h-006Fh` | Vector stubs | Reset jumps to `0180h`; other vector slots jump to `0978h`, `0582h`, `0668h`, and `05E2h`; unused vector bytes are mostly self-looping `ff`/`JR`. |
| `0070h-0077h` | `PBLS` signature | Reset compares bytes at `0070h` against `4000h`, which also begins with `PBLS`. |
| `0080h-00BFh` | `CALT` fast-call area | Many one-byte `CALT` calls target `0080h-00BEh`. Needs target-by-target alignment work. |
| `0180h-02FFh` | Reset/boot sequence | Initializes stack/MM/V page, clears memory, probes optional external PROM, reads gate-array state, and derives initial DIP/status bits. |
| `038Bh-0571h` | Initialization and memory/window probes | Clears RAM state, initializes ports/timers/gate-array registers, probes `8000h` bank/window, computes page checksums. |
| `0582h-09C1h` | Interrupt handlers and mechanism dispatch | ISRs buffer data from `F000h`/`RXB`, manipulate `F001h/F002h`, update timers, and dispatch mechanism state from `VV37`. |
| `0A0Bh-0B3Fh` | Input consumer and small helpers | Includes the shared host-input byte reader at `0A0Bh`, parameter readers, F001 disable sequence, nibble shifts, delay loops, and a direct `F002` write helper at `0B23h`. |
| `0E8Bh-0F15h` | Buffer/window bounds helpers | Uses `FF00h`, `EE4Ch`, `EE5Ch`, `EE5Eh`, and `EFBF`; likely print-buffer/string bounds logic. |
| `0F16h-2DE2h` | Core text/render/print logic | Many small mode-flag helpers and high-fan-in rendering routines. This is the least-labeled large code body so far. |
| `2DE3h-3FFFh` | Fill | All `0xFF`. |
| `4000h-5793h` | Main input decode and secondary code body | Starts with `PBLS` signature at `4000h`; reset checks this area for external PROM handling. Contains the `400Bh` host-byte decode loop, printable-character setup, and substantial hardware helpers. |
| `5794h-5FFFh` | Fill | All `0xFF`. |
| `6000h-60FFh` | Identity byte table | Literal bytes `00h-FFh`; not code. |
| `6100h-67FFh` | Self-test/data-dump/menu strings and tables | Contains `L5217B`, `Data Dump Mode`, CSF messages, DIP-switch menu text, pitch text, and pointer/table data. |
| `6854h-6A59h` | Character set / translation tables | Non-code table data with visible character-set fragments. |
| `6A5Ah-6FFFh` | Fill | All `0xFF`. |
| `7007h-721Fh` | Mechanism/output tables | `540Dh` indexes a jump table at `7007h`; `0668h` indexes a CR0 lookup table around `7219h`. |
| `739Bh-7B73h` | Service/self-test/adjustment code | Includes data-dump mode and bidirectional adjustment mode routines, string printer, and PA/PB output helpers. |
| `7B74h-7FFFh` | Fill | All `0xFF`. |

## High-Confidence Routines

| Address | Working label | Notes |
| --- | --- | --- |
| `0180h` | `boot_reset_entry` | First executed code. Clears `A000h`, `8000h`, `FF00h`, checks external PROM signature, then calls init routines. |
| `045Dh` | `init_cpu_ports_timers_gate_array` | Writes `EOM`, `PA`, `PB`, `PC`, motor-control registers, timer mode, `F004`, `F005`, and `F003`. |
| `049Ch` | `memclear_hl_bc` | Simple `A=0; STAX (HL+); DCR C/B` clear loop. |
| `0582h` | `isr_gate_f000_input_capture_buffer` | Interrupt path reads `F000h` through the gate-array window and stores the byte into the shared `EE20h` input buffer. Candidate parallel-port data path. |
| `05E2h` | `isr_rxb_host_receive_buffer` | Reads `RXB`, checks `ER`, stores received byte into the `EE20h` buffer with temporary `F002` bank changes. |
| `0A0Bh` | `read_next_host_input_byte` | Consumes from the shared input buffer using `EE22h` as the read pointer and `EE1Eh` as the pending count. This is `CALT ($0080)`. |
| `0B23h` | `write_bank_register_f002` | Single-purpose helper: `MOV ($F002),A; RET`. |
| `2530h` | `esc_J_immediate_forward_feed` | `ESC J n`: reads one byte and enters the immediate-feed path with a positive distance. |
| `2568h` | `esc_j_immediate_reverse_feed_fx80_compat` | `ESC j n`: FX-80 compatibility reverse feed; reads one byte and enters the same immediate-feed path with the high byte set to `80h`. |
| `400Bh` | `main_input_decode_loop` | Top-level loop: read host byte, classify with `4038h`, print if printable, dispatch if command/control. |
| `4038h` | `classify_input_character_and_select_style_state` | Classifies printable bytes and sets font/style state; printable bytes skip over the command dispatcher. |
| `4EE4h` | `txb_send_byte_wait_fst` | Waits for `FST`, then writes `TXB`. |
| `4EEAh` | `read_panel_buttons_debounced` | Returns service-panel action bits from debounced `PC`/`F2` inputs; used directly by bidirectional adjustment. |
| `4F2Fh` | `delay_03e8` | Loads `BC=03E8h`, delays via `CALT ($0090)`. |
| `4F37h` | `read_dip_switches_and_panel_pa_bits` | Startup DIP/panel read. Uses table-driven ADC switch reads and then folds in direct PA bits. |
| `4F54h` | `read_adc_switch_table_bits` | Consumes compact tables at `4F96h`/`4F9Fh`, samples ADC via `508Dh`, and builds switch bitfields. |
| `4FB1h` | `sample_vr_adjustment_adc_offsets` | Averages/clamps ADC-derived adjustment values used at startup and by bidirectional adjustment mode. |
| `6944h` | `dispatch_control_or_esc_command` | Count-prefixed command-table scanner; primary table starts at `696Eh`, ESC table at `699Ch`. |
| `755Dh` | `print_ff_or_nul_terminated_string` | Reads bytes from `HL` until `00h` or `FFh`, outputting through character helpers. |
| `7719h` | `data_dump_mode_routine` | Uses strings at `6116h`, `612Eh`, `613Ch`, and `615Eh`; clearly handles data-dump paper length messaging. |
| `7818h` | `bidirectional_adjustment_mode` | Prints `7A18h` string `Bi-d Adjustment Mode`, then `VR1`, `VR2`, and out-of-range strings. |

## Gate Array / Bank Register Anchors

The most important hardware anchors for CG/ROM-bank work are:

- `F001h`: touched in reset at `01BFh`/`01E3h`, ISR paths at `05C0h` and
  `0A85h`, and the helper cluster at `4DECh-4EDEh`.
- `F002h`: written in ISR buffering paths (`05B6h`, `060Eh`, `062Dh`,
  `064Ah`, `065Eh`, `06EEh`) and helper paths (`084Eh`, `086Eh`, `089Fh`,
  `08C6h`, `0A46h`, `0A4Eh`, `0B23h`, `508Dh`, `7594h` reads it).
- `F003h`: initialized at `0497h`; updated at `0315h`, `0497h`, and `51F2h`.
- `F004h/F005h`: initialized at `0487h-0492h`, later used around `08D0h` and
  `5681h`.

The `4C` CG dump has a plausible pin-1-low and pin-1-high bank. Firmware
analysis should look for values written to `F002h` before reads from
`8000h-9FFFh`/`A000h`, especially routines that call `0B23h`, `508Dh`, or
directly write `F002h`.

## Host Input To Command Parser

The candidate parallel input path now traces through to ESC/P command dispatch:

| Stage | Address/state | Notes |
| --- | --- | --- |
| Write side | `0582h` / `05E2h` | `F000h` gate-array input and CPU `RXB` input both write bytes to the buffer at `EE20h`. |
| Buffer state | `EE20h`, `EE22h`, `EE1Eh` | `EE20h` is the write pointer, `EE22h` is the read pointer, and `EE1Eh` is the pending-byte count. Startup initializes the pointers to `8500h`. |
| Read side | `0A0Bh` | `CALT ($0080)` waits for pending data, reads one byte from `EE22h`, advances/wraps the pointer, decrements `EE1Eh`, and returns the byte. |
| Decode loop | `400Bh` | Reads one host byte, calls `4038h`, and uses skip-return behavior to choose printable output versus command dispatch. |
| Command dispatch | `6944h`, `696Eh`, `699Ch` | Primary controls dispatch through the table at `696Eh`; `ESC` reads the next byte and dispatches through the ESC table at `699Ch`. |

Primary control table at `696Eh` has 14 entries: `ESC`, `LF`, `CR`, `BEL`,
`BS`, `HT`, `VT`, `FF`, `SO`, `SI`, `DC2`, `DC3`, `DC4`, and `CAN`.
The parsed primary and ESC tables are mirrored in
`data/lq500_3c_command_dispatch_tables.tsv` for handler naming work.

FX-80 comparison notes:

- `ESC j n` is documented in the FX-80 notes as immediate reverse feed by
  `n/216` inch. LQ-500's `2568h` handler has the expected paired shape with
  `ESC J`: `ESC J` builds `HL=00nn`, while `ESC j` builds `HL=80nn`, then both
  enter the same immediate-feed path.
- `ESC s n` is documented in the FX-80 notes as half-speed mode. LQ-500's
  table points it at `0A0Bh`, so the firmware consumes one parameter but no
  state change has been identified yet.
- `ESC r n` and `ESC h n` were not found in the checked FX-80 notes. Their
  LQ-500 entries also point at `0A0Bh`, so they currently look like
  one-parameter compatibility/no-op consumers.

## String/Data Regions

Important FF-delimited strings:

| Address | Text |
| --- | --- |
| `6100h` | `L5217B` |
| `6107h` | `Data Dump Mode` |
| `6116h` | `This is the first line.` |
| `612Eh` | `This is line ` |
| `613Eh` | `This paper is too long for CSF.` |
| `615Eh` | `This paper is too short for CSF.` |
| `617Fh` | `(8.5mm)` |
| `6187h` | `(22mm)` |
| `6190h-61A8h` | Pitch names: `10`, `12`, `15`, `Proportional` |
| `6231h-67EEh` | DIP-switch and menu-print strings. |
| `7A18h` | `Bi-d Adjustment Mode` |
| `7A2Dh` | `VR1 = ` |
| `7A34h` | `VR2 = ` |
| `7A3Dh` | ` (out of range)` |

## Current Uncertainties

- The exact uPD7810 vector names for `0008h`, `0010h`, `0018h`, and `0028h`
  still need datasheet correlation.
- The `CALT` area at `0080h-00BEh` needs aligned disassembly by actual CALT
  target, not linear decoding.
- Recursive trace unresolved indirect exits currently include `JEA` at
  `02DCh`, `240Ah`, `5468h`, and `761Ch`; these need manual target recovery.
- The large core region `0F16h-2DE2h` needs command-parser and glyph-renderer
  separation. The current labels only mark high-fan-in helpers.
- `4000h-5793h` may be alternate/external-PROM-related code or a second major
  firmware body behind the `PBLS` check. It is real code, not filler.
- The relationship between `F002h` writes and the 4C pin-1-low/high CG banks is
  not yet resolved.

## Next Pass

1. Build xrefs around `0582h`, `05E2h`, `4EEAh`, `4F37h`, `4F54h`, `4FB1h`,
   and service-mode callers to separate host input, panel buttons, DIP switch
   defaults, and VR/adjustment reads.
2. Correlate `VV00`/`VV01` bits from `4F37h` against the documented DIP switch
   defaults in `docs/lq500_reference.md`.
3. Build xrefs around every `F002h` write and nearby `8000h`/`8600h` reads.
4. Split `0F16h-2DE2h` into command parsing, font/style state, and glyph fetch
   helpers by tracing high-fan-in calls (`1677h`, `1DDFh`, `1DFEh`, `2011h`,
   `24D4h`, `26F1h`).
5. Align and label the `CALT` service stubs.
6. Cross-reference ESC/P command constants from `data/lq500_commands.json`
   against immediate comparisons in the disassembly.
7. Recover the computed `JEA` targets, add confirmed targets to
   `data/lq500_3c_trace_roots.tsv`, and rerun
   `tools/trace_upd7810_unidasm.py`.
