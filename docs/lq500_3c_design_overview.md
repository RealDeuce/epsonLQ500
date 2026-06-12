# LQ-500 3C Firmware Design Overview

This is a working map of the 3C program PROM architecture. Names are based on
the vector trace, high fan-in call sites, hardware register accesses, and local
instruction patterns. Treat medium/low-confidence labels as useful handles, not
final symbol names.

## Execution Shape

The firmware is organized around a small set of layers:

| Layer | Main addresses | Current role |
| --- | --- | --- |
| Vector and CALT layer | `0000h-00BFh` | Reset/IRQ stubs plus compact one-byte service calls. |
| Boot/init | `0180h-0571h` | Clears RAM/windows, probes optional PROM/CG windows, initializes ports/timers/gate-array registers. |
| Real-time I/O | `0582h-09C1h` | Interrupt handlers for `F000h` gate data, serial RXB, timers, and print mechanism state. |
| Text/render core | `0F16h-2DCEh` | Character state, glyph metric lookup, work-buffer layout, and render-band advancement. |
| Character dispatcher and glyph transforms | `4008h-5793h` | `PBLS` secondary body containing character classification, font-state selection, and many bitmap expansion transforms. |
| Static data/tables | `6000h-73FFh` | Identity/remap table, strings, character-set tables, mechanism tables. |
| Service/test UI | `739Bh-7B73h` | Data-dump, DIP/status printout, bidirectional adjustment, and string/number formatting helpers. |

## Panel, DIP, and Host I/O

The most useful hardware-facing split so far is:

| Address | Working label | Current read |
| --- | --- | --- |
| `0582h` | `isr_gate_f000_input_capture_buffer` | Interrupt path that reads `F000h`, stores the byte into the shared `EE20h` input buffer, restores `F002h`, and toggles `F001h` bits when the buffer state changes. Candidate parallel-port data path. |
| `05E2h` | `isr_rxb_host_receive_buffer` | CPU `RXB` receive interrupt path. It checks `ER`, handles NUL/error cases, and writes into the same `EE20h` input buffer as the `F000h` path. |
| `4EEAh` | `read_panel_buttons_debounced` | Returns a compact button/action bitfield. Bidirectional-adjustment mode treats returned values `01h`, `02h`, and `04h` as panel actions and waits for a return to zero before accepting another action. |
| `4F37h` | `read_dip_switches_and_panel_pa_bits` | Startup switch read. Calls the ADC/table reader twice, writes `VV00`/`VV01`, then folds PA bits `04h` and `08h` into `VV01`. |
| `4F54h` | `read_adc_switch_table_bits` | Walks compact tables at `4F96h`/`4F9Fh`; each entry chooses an `F002h`/ADC mode through `508Dh` and compares the resulting sample against a threshold. |
| `4FB1h` | `sample_vr_adjustment_adc_offsets` | Startup and bidirectional-adjustment sampler. It averages ADC channels and stores signed/clamped offsets in the `EE28h` area used by the adjustment UI. |

This means the DIP switches and service-panel inputs are likely a mix of direct
port bits and analog/multiplexed switch reads. The code does not support a
simple "one DIP bank equals one CPU port" model.

Known bit-level handles:

| Signal in code | Current meaning |
| --- | --- |
| `PC & 30h` | Debounced by `4EF9h`, returned from `4EEAh` as action bits `02h` and `01h`. |
| `PC bit 08h` plus `F2` | Sampled by `4F21h`, returned from `4EEAh` as action bit `04h`. |
| `PA bits 04h/08h` | Sampled by `4F37h` after the two ADC switch-table reads and merged into `VV01`. |
| `PA bit 10h` | Used repeatedly in data-dump and service flows as a wait/confirm-style input. |
| `PA bit 20h` | Used by feed/mechanism setup flows around `51F7h-5241h`; likely paper/feed related, not fully named yet. |
| `PA bit 00h` / `PB bit 80h` | Written by `7B52h` during service/adjustment UI setup. |

## Input Pipeline

The host input path from the candidate parallel ISR to the parser now has a
clear shape:

1. `0582h` (`isr_gate_f000_input_capture_buffer`) reads a byte from `F000h` and
   writes it to the ring buffer at the `EE20h` write pointer.
2. `05E2h` (`isr_rxb_host_receive_buffer`) is the alternate CPU `RXB` receive
   path and writes into the same buffer.
3. Both ISR paths increment the pending-byte count at `EE1Eh`; startup seeds
   both `EE20h` and `EE22h` to `8500h`.
4. `0A0Bh` (`read_next_host_input_byte`) waits for `EE1Eh` to become nonzero,
   reads one byte through the `EE22h` read pointer using `F002h=0C0h`, advances
   `EE22h`, decrements `EE1Eh`, and returns the byte in `A`.
5. `400Bh` (`main_input_decode_loop`) calls that reader via `CALT ($0080)`,
   classifies the byte with `4038h`, and then either enters printable output at
   `4012h` or command dispatch at `6944h`.

The command dispatcher is table-driven:

| Address | Role |
| --- | --- |
| `6944h` | Pushes `400Bh` as the loop return, scans a count-prefixed byte/target table, and jumps to a matched handler. |
| `696Eh` | Primary control-command table: `ESC`, `LF`, `CR`, `BEL`, `BS`, `HT`, `VT`, `FF`, `SO`, `SI`, `DC2`, `DC3`, `DC4`, `CAN`. |
| `695Bh` | ESC entry from the primary table; reads the next byte through `0AB2h` and switches to the ESC table. |
| `699Ch` | ESC command table with 62 byte/handler entries, including `ESC @`, line spacing/page commands, graphics commands, and style commands. |

This proves the candidate parallel path and the CPU `RXB` path converge before
ESC/P parsing. Command handlers consume their parameters by calling the same
input-byte helpers, so tracing parser behavior should start from the two command
tables rather than from the ISR bodies.

FX-80 compatibility cross-checks:

| Command | LQ-500 handler | Current interpretation |
| --- | --- | --- |
| `ESC j n` | `2568h` | Matches FX-80 reverse-feed compatibility. The LQ-500 handler reads `n`, sets `H=80h`, and enters the shared immediate-feed path used by `ESC J` with `H=00h`. |
| `ESC s n` | `0A0Bh` | FX-80 half-speed compatibility candidate. LQ-500 consumes one parameter but no state change is identified yet. |
| `ESC r n` | `0A0Bh` | Not found in the FX-80 notes checked so far. LQ-500 consumes one parameter only, likely preserving stream sync for a compatibility command. |
| `ESC h n` | `0A0Bh` | Not found in the FX-80 notes checked so far. LQ-500 consumes one parameter only, likely preserving stream sync for a compatibility command. |

## Character Path

The probable normal character flow is:

1. A byte is read by `400Bh` through the shared input-buffer consumer at
   `0A0Bh`.
2. It is classified by `4038h` (`classify_input_character_and_select_style_state`).
3. Font/style state is copied into `VV21`, `VV22`, and `VV1F`.
4. Extended printable ranges are checked by `2824h`.
5. Glyph metrics are derived by the `1Cxxh-1Dxxh` family:
   - `1CF2h` selects `8000h` or `8600h` and reads per-character metrics into `EF99`/`EF9B`.
   - `1D65h` reconciles glyph width and active buffer pointers.
   - `1DDFh`/`1DFEh` compute source/work pointers around `EE88`.
6. The glyph is expanded into a work buffer by one of the `43DDh-4C36h` transform paths.
7. The print/render advance path enters through `2011h` and reaches the larger `256Eh`/`29xxh` loops.

## Glyph Transform Families

The `43DDh-4C36h` region looks like the resident bitmap expansion engine. It
uses `VV99` as an active width/count and `VV:CF` as a destination stride.
`EE88`/`EE8A` are source/work pointers; `EF95`, `EF97`, and `EF9B` are glyph
metric or edge pointers.

Notable helpers:

| Address | Working label | Evidence |
| --- | --- | --- |
| `45B1h` | `or_shifted_columns_left_into_work_buffer` | Shifts source data left and ORs into destination bytes. |
| `45F8h` | `or_shifted_columns_right_into_work_buffer` | Mirrors the left-shift helper using right shifts. |
| `463Fh` | `xor_or_mask_shifted_columns_into_work_buffer` | Uses `XRAX`/masking while walking destination columns. |
| `4664h` | `adjust_glyph_width_and_right_edge_metrics` | Updates `VV99`, `EF95`, `EF97`, and `EF9B`. |
| `49ADh` | `expand_high_nibble_to_2bit_pairs` | Converts high-nibble bits into paired masks `C0/30/0C/03`. |
| `49C5h` | `condense_or_mask_glyph_columns` | Uses inverted masks and halves/condenses metrics afterward. |
| `4AA8h` | `copy_2byte_glyph_columns_to_3byte_work_rows` | Copies 2 source bytes plus a zero byte, with order selected by a flag. |
| `4ACEh` | `write_packed_glyph_nibbles_to_work_buffer` | Writes packed groups into destination offsets `0/3/6/9`. |

This strongly suggests that the 4C CG data is not a single direct framebuffer
layout. The program ROM contains multiple format converters for different pitch,
quality, width, and style combinations.

## Service/Test Path

The `739Bh-7B73h` block is a service UI layer:

- `73AFh` prints a data-dump style grid using the `8000h` work window.
- `746Fh` converts nibbles to ASCII hex.
- `7476h` prints a single dump cell through the same character classifier used
  by normal text.
- `755Dh` prints `00h`/`FFh` terminated strings.
- `7719h` handles the documented data dump paper length messaging.
- `7818h` handles bidirectional adjustment mode and its `VR1`/`VR2` display,
  using `4EEAh` panel-action reads and `4FB1h` ADC offset refreshes.

## Open Naming Questions

- Confirm whether the `0582h` `F000h` ISR is the Centronics/parallel data path
  or an intermediate gate-array FIFO/status path fed by the parallel interface.
- The exact meaning of style bits in `VV22`, `VV23`, `VV27`, `VV28`, `VV29`,
  `VV2A`, `VV88`, and `VV89` still needs correlation against ESC/P commands.
- `4008h` is reached after the `PBLS` check but shares normal character and
  render code, so it should be treated as a resident secondary body, not
  necessarily as an external option ROM.
- The `JEA` computed jumps at `02DCh`, `240Ah`, `5468h`, and `761Ch` need
  target recovery. `761Ch` is clearly part of service/status string assembly.
