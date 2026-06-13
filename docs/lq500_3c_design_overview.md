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
| Text/render core | `0F16h-2DCDh` | Character state, glyph metric lookup, work-buffer layout, and render-band advancement. |
| Inline render table/fill | `2DCEh-3FFFh` | Small inline dispatch tail at `2DCEh-2DE2h`, then unused `FFh` fill through `3FFFh`. |
| Character dispatcher and glyph transforms | `4008h-5793h` | `PBLS` secondary body containing character classification, font-state selection, and many bitmap expansion transforms. |
| Static data/tables | `6000h-739Ah` | Identity/remap table, strings, character-set tables, mechanism timing tables, and render geometry tables. |
| Service/test UI | `739Bh-7B73h` | Data-dump, DIP/status printout, bidirectional adjustment/calibration UI, and string/number formatting helpers. |

## Panel, DIP, and Host I/O

The most useful hardware-facing split so far is:

| Address | Working label | Current read |
| --- | --- | --- |
| `0582h` | `isr_gate_f000_input_capture_buffer` | Interrupt path that reads `F000h`, stores the byte into the shared `EE20h` input buffer, restores `F002h`, and toggles `F001h` bits when the buffer state changes. Candidate parallel-port data path. |
| `05E2h` | `isr_rxb_host_receive_buffer` | CPU `RXB` receive interrupt path. It checks `ER`, handles NUL/error cases, and writes into the same `EE20h` input buffer as the `F000h` path. |
| `4EEAh` | `read_panel_buttons_debounced` | Returns a compact button/action bitfield: `01h` = LINE FEED/AUTO LOAD, `02h` = FORM FEED, `04h` = ON LINE. Bidirectional-adjustment mode waits for return to zero before accepting another action. |
| `4F37h` | `read_dip_switches_and_panel_pa_bits` | Startup switch read. Calls the ADC/table reader twice, writes `VV00`/`VV01`, then folds PA bits `04h` and `08h` into `VV01`. |
| `4F54h` | `read_adc_switch_table_bits` | Walks compact tables at `4F96h`/`4F9Fh`; each entry chooses an `F002h`/ADC mode through `508Dh` and compares the resulting sample against a threshold. |
| `4FB1h` | `sample_vr_adjustment_adc_offsets` | Startup and bidirectional-adjustment sampler. It averages ADC channels and stores signed/clamped offsets in the `EE28h` area used by the adjustment UI. |

This means the DIP switches and service-panel inputs are likely a mix of direct
port bits and analog/multiplexed switch reads. The code does not support a
simple "one DIP bank equals one CPU port" model.

Known bit-level handles:

| Signal in code | Current meaning |
| --- | --- |
| `PC bit 20h` | Debounced by `4EF9h`; returned from `4EEAh` as `01h` = LINE FEED/AUTO LOAD. |
| `PC bit 10h` | Debounced by `4EF9h`; returned from `4EEAh` as `02h` = FORM FEED. |
| `PC bit 08h` plus `F2` | Sampled by `4F21h`; returned from `4EEAh` as `04h` = ON LINE. |
| `PA bits 04h/08h` | Sampled by `4F37h` after the two ADC switch-table reads and merged into `VV01`. |
| `PA bit 10h` | Used repeatedly in data-dump and service flows as a wait/confirm-style input. |
| PA5 / `PA mask 20h` | Raw input sampled by startup carriage home-seek code around `51F7h-5241h`. Schematic review shows PA5 has a 15K pullup to `+5 V`, and the HOME switch closes to ground, so clear samples are active-low HOME assertions. |
| `PA bit 00h` / `PB bit 80h` | Written by `7B52h` during service/adjustment UI setup. |

## Self-Test Status Header

The LINE FEED/AUTO LOAD and FORM FEED power-on paths share the same status
printer after selecting draft or letter-quality mode. The flow is:

| Address | Role |
| --- | --- |
| `74CBh` | Draft self-test entry; sets `VV23.2`. |
| `74CFh` | Letter Quality self-test entry; clears `VV23.2`. |
| `7552h` | Prints the `6100h` firmware header string (`L5217B`) and advances output. |
| `75C7h` | Saves `VV22`/`VV23`/`VV24`, selects the status print style, walks the two-column pointer table at `61AAh`, and restores the previous style. |
| `760Ah` | Builds the selected status selector IDs in `FF00h` from `VV00`/`VV01`. |
| `76C2h` | Prints one selector-prefixed status string, emphasized only when its selector byte is present in the `FF00h` selected-ID list. |

This explains the manual's "prints current DIP switch settings" behavior. The
strings at `6230h-67EFh` contain all possible values, while `760Ah` chooses one
selector per status group. `76C2h` sets `VV24.4` before printing each value and
clears it only for unselected values, so the selected row is printed in
emphasized/bold mode. It is not using the double-strike flag; `VV24.6` is the
separate `ESC G`/`ESC H` double-strike bit.

The extracted selector text is mirrored in
`data/lq500_3c_selftest_status_selectors.tsv`.

The larger `6000h-6FFFh` block is now split by consumer in
`data/lq500_3c_6000_block_usage.tsv`. The service-visible text runs from
`6100h` through `67EFh`; the rest of the block is lookup and dispatch data:
`6000h` is the host-byte remap table used by `4038h`, `67F0h-689Bh` is
render/glyph setup data, `689Ch-6943h` is the international character
substitution table used by `1464h`, and `696Eh-6A59h` is the primary/ESC command
dispatch table area. The two CSF parenthesized strings at `617Fh` and `6187h`
have no direct traced consumer yet.

The adjacent `7000h-7B73h` region is split by consumer in
`data/lq500_3c_7000_block_usage.tsv`. The important split is that
`7001h-739Ah` is normal mechanism/timing/render lookup data, while
`739Bh-7B73h` is executable service/test code. The service block contains the
power-on panel dispatch, data dump, self-test status printing, and the
bidirectional adjustment/calibration UI. The adjustment UI starts at `7818h`,
prints `Bi-d Adjustment Mode`, displays `VR1`/`VR2`, reads panel actions via
`4EEAh`, and refreshes ADC-derived offset values via `4FB1h`.

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

## Command Behavior Audit

Detailed command behavior is tracked in
`data/lq500_3c_command_behaviors.tsv`. That table mirrors all 76 entries from
`data/lq500_3c_command_dispatch_tables.tsv` and records parameter consumption,
raw state updates, evidence addresses, and audit status.

Current split:

| Status | Meaning |
| --- | --- |
| `audited` | Handler is small enough or direct enough that parameter consumption and state effects are recorded as raw firmware behavior. |
| `audited_partial` | Entry behavior is traced far enough to identify parameters and key state updates, but shared render/feed/graphics/user-character machinery still needs deeper decomposition. |
| `needs_hardware_correlation` | Firmware behavior is known, but the documented command effect depends on external signal meaning. |

High-confidence simple handlers now include the style/pitch flags (`ESC E/F`,
`ESC G/H`, `ESC 4/5`, `ESC P/M/g`, `ESC p`, `ESC W`, `SO/SI/DC2/DC4`), MSB
control (`ESC #`, `ESC =`, `ESC >`), tab selection (`ESC /`), line-spacing raw updates
(`ESC 0/2/3/A`), and compatibility/no-op consumers (`ESC s/r/h`). Larger
paths that still need follow-up are the shared feed/advance path
(`LF/CR/FF/VT`, `ESC J/j`), graphics (`ESC *` and `ESC K/L/Y/Z`), and
user-defined character commands (`ESC &`, `ESC :`).

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

## Mechanical Outputs

Mechanical documentation is split by subsystem:

| Subsystem | Detailed doc | Scope |
| --- | --- | --- |
| Paper Feed | `docs/lq500_3c_paper_feed.md` | Paper advance/retard, `PB2` drive/hold, `PB3`/`PB4` phase switching, ESC J/j feed distance, and paper-feed timing. |
| Carriage Operation | `docs/lq500_3c_carriage_operation.md` | Carriage home seek, position/timing, current selection, `PC7`/`TM`, and `F003h` control. |
| Printhead | `docs/lq500_3c_printhead.md` | Head-interface registers, print-data burst output, and future pin firing analysis. |

Keep these domains separate. Print pin firing is a head-output workstream, not
part of carriage movement, even though normal printing couples head timing to
carriage motion.

### Paper Feed

The service manual identifies the paper-feed motor as a 4-phase, 48-step motor
driven with 2-2 phase excitation. Each phase switch advances paper by `1/180`
inch, and the CPU controls it open loop. The motor drive frequency is `400 PPS`,
matching one phase switch every `2.5 ms`. Figure 2-47 also identifies `PB2` as
the active-low paper-feed drive signal: when `PB2` is low, Q27 turns on and
supplies `+24 V`; when not driven, `+5 V` is supplied through `R36`/`D11` to
hold the motor. The same text identifies `PB3` as phase A/B and `PB4` as phase
C/D.

That makes the firmware's `PB mask 04h` and `PB mask 18h` paths the strongest
paper-feed hardware anchors. These are bit masks on the 8-bit `PB` port, not
schematic pin names:

| Address | Working label | Evidence |
| --- | --- | --- |
| `093Eh` | `paper_feed_pb_bits_3_4_phase_update_candidate` | Chooses phase direction from `VV61 bit 0`, calls `0953h` or `095Fh`, then updates position/state through `54A0h`, `54C9h`, and `5538h`. |
| `0953h` | `rotate_pb_bits_3_4_phase_positive` | Rotates `VV16` right with wrap and sets `EA=+1`. |
| `095Fh` | `rotate_pb_bits_3_4_phase_negative` | Rotates `VV16` left with wrap and sets `EA=-1`. |
| `096Ah` | `write_pb_bits_3_4_stepper_phase_outputs` | Stores the new `VV16` phase and maps `VV16 & 18h` directly onto `PB & 18h`; if service-manual bit numbering is zero-based, this is `PB3`/`PB4`. |
| `5498h`/`549Ch` | `PB mask 04h` drive/hold control inside `540Dh` | `549Ch` clears `PB & 04h` low and `5498h` sets `PB & 04h` high. This matches service-manual `PB2` active-low +24 V paper-feed drive enable versus +5 V hold. In the command-feed `VV62!=0` branch, record value `01h` takes the `549Ch` drive-on path; other values take the `5498h` hold path. |

The service-manual excitation sequence makes the `PB & 18h` masked states
concrete:

| Step | `PB & 18h` | `PB3` | `PB4` | Energized phases |
| --- | --- | --- | --- | --- |
| 0 | `18h` | H | H | A + C |
| 1 | `08h` | H | L | A + D |
| 2 | `00h` | L | L | B + D |
| 3 | `10h` | L | H | B + C |

Reset initializes `VV16=CCh`, so `PB & 18h` starts at `08h` / step 1.
The manual labels the table order as clockwise and says clockwise feeds paper
forward, while counterclockwise feeds paper in reverse. The `0953h`
rotate-right path advances `08h -> 00h -> 10h -> 18h -> 08h`, matching the
increasing manual step order; the `095Fh` rotate-left path reverses that order.
The command path preserves the sign bit into `EF61`/`VV61`: `ESC J` clears
`VV61.0` and therefore selects `0953h`, while `ESC j` sets `VV61.0` and selects
`095Fh`.

The previous working label treated `PB mask 18h` as carriage phase output. Figure
2-47 makes that unlikely unless the schematic's `PB3`/`PB4` labels are not
CPU-port bit labels. Carriage movement is now anchored separately through the
gate-array `TM` pulse on CPU `PC7`.

### Carriage Operation

Service-manual pages 68-85 identify the carriage motor as a gate-array mediated
stepper path. CPU `CO1`/`PC7` feeds the E01A05KA `TM` input; after each pulse,
the gate array performs the carriage phase switching. The manual's carriage
control table is printed as `WR F002H`, while surrounding text says the carriage
motor control port is assigned to `F003h`. Firmware writes `F003h` through
`51F2h`, so `F003h` is the working ROM anchor unless the schematic proves the
manual table address instead.

| Address | Working label | Evidence |
| --- | --- | --- |
| `0908h` | `carriage_gate_array_tm_pulse` | Writes `MB=03h`, pulses `PC bit 7` low then high, and updates motion counters. Service manual Figure 2-34 identifies CPU `CO1`/`PC7` as the E01A05KA carriage gate-array `TM` input. |
| `00B8h`/`00BAh`/`51E9h`/`51EDh`/`51F2h` | `write_carriage_control_f003_from_vv15` | CALT vectors at `00B8h`/`00BAh` enter the root-confirmed `51EDh` AND helper and `51E9h` OR helper. `51F0h` stores the updated `VV15`, and `51F2h` writes `F003h`. Manual carriage-control bits are enable, phase polarity, direction, and excitation mode. |
| `51F7h` | `startup_carriage_home_seek_entry` | Only traced caller is startup at `0340h`. Branches on raw `PA mask 20h` set/clear state, seeds `VV61` with direction/mode values, and calls the timed seek sequence at `5253h`. |
| `5253h` | `startup_carriage_home_seek_timed_sequence` | Selects current state `547Eh`, walks carriage timing tables around `7287h`/`72AFh`, samples PA5 through `PA mask 20h` at `5306h`, pulses `PC7` through `0908h`, then restores hold state `546Ah`. |
| `5306h` | `sample_pa5_low_count_during_carriage_delay` | Splits a delay interval into thirds and samples PA5 through `PA mask 20h` three times; `D` increments only for PA mask 20h clear samples. |
| `546Ah`/`5474h`/`547Eh`/`5488h` | `carriage_current_*` | Four PA/PB output states involving `PB mask 20h`, `PA mask 02h`, and `PB mask 40h`. These match the manual's carriage-current control shape; schematic review shows `PB1` is `AFXT` to CNI/parallel `AUTOFEED`, while `PA1` goes through a transistor to STK69818 pins 9/11, so `PA1`/`PA & 02h` is the `SPDH` speed-high selector despite the manual table's `PB1` label. |

The carriage startup seek now explains the old home-input path. The service manual
describes checking the HOME signal during initialization after a timed 2-2 phase
excitation interval, and Figure 2-44 says the printing area starts 22 phase
switches after home. That fits `51F7h-5253h`: it is startup-only in the current
trace, samples raw `PA mask 20h`, runs carriage timing tables, and pulses the
gate-array `TM` input rather than the paper-feed `PB3`/`PB4` phase bits.
Schematic review identifies this input as PA5 with a 15K pullup to `+5 V`; the
HOME switch closes to ground, so PA mask 20h clear firmware samples are
active-low HOME assertions.
The startup branch sequence is decoded in
`data/lq500_3c_carriage_home_seek.tsv`: the firmware distinguishes raw PA mask 20h
set/clear states, performs a short `0004h` probe when PA mask 20h starts clear, a
fixed `000Ah` confirmation move across the edge, and long `13ECh` seeks on the
other legs. `5306h` samples PA5 through PA mask 20h three times per timing interval and increments
`D` only for PA mask 20h clear samples. The success path seeds `EF0F=EF11=0003h`;
`53B9h` later compares requested positions against `EF0F` with a `001Ah` limit,
but the exact firmware expression of the manual's 22 phase-switch print-area
offset is still not proven.

The carriage timing words at `7287h-72AEh` are in 10 us units and line up with
the manual carriage acceleration/deceleration tables: examples include `0162h`
near `3.56 ms`, `00E7h` at `2.31 ms`, `00C8h` at `2.00 ms`, `00A6h` at
`1.66 ms`, and `007Ah` at `1.22 ms`. The adjacent five-byte records at
`72B3h-72D8h` are indexed by `(VV6F & 7) * 5` in the carriage scheduler; see
`data/lq500_3c_carriage_sequence_records.tsv`. `56CE-56D3h` copies each record
to `EF7C..EF80`; `EF7C` can become `VV63`, `EF7D` is the `TM1` reload-cycle
length, and `EF7E..EF80` are the cyclic `TM1` reload bytes used at
`09AC-09BCh`.

The `VV63` value selects one of the normal `7005h` timing/output records copied
to `EF49..EF60`; decoded output bytes are in
`data/lq500_3c_carriage_output_state_records.tsv`. `540Dh` maps `VV37` state
bits to slots such as `EF4Bh`, `EF4Dh`, `EF4Eh`, `EF53h`, `EF55h`, `EF56h`,
`EF5Bh`, or `EF60h`. In normal carriage mode (`VV62=0`), it strips bit 7 from
the copied byte and indexes the `7007h` current-state jump table. Thus raw
bytes `03h` and `83h` select normalized index 3 and reach `5488h`; records
`0` and `1` use the low-current state through `EF4Dh`/`EF4Eh`, while records
`2` through `4` use it through `EF4Dh=83h`.

The F003 control helper call paths are decoded in
`data/lq500_3c_f003_control_paths.tsv`. `CALT ($00B8)` is the AND-update
vector to `51EDh`, and `CALT ($00BA)` is the OR-update vector to `51E9h`.
Startup home seek uses those vectors to set up F003 bits 0 and 1 for each seek
leg. During normal `540Dh` dispatch, selected state-byte bit 7 controls F003
bit 0 before the byte is masked with `7Fh` for the current-state jump table;
after record setup, `5625h-5630h` maps `VV61.0` to F003 bit 1. This ties the
record high bit to the manual excitation-select bit and `VV61.0` to the manual
direction bit, while exact active polarity is still left to manual/schematic
correlation.

The normal carriage scheduler path is now separated from the paper-feed
`5676h` callers. `5676h` copies fifteen bytes from `EF38..EF46` to
`EF6D..EF7B`; the byte mapping makes `EF3A` become `VV6F`, which is the record
selector masked by `5715h`. The currently traced external `5676h` callers all
set `VV38.3` first, so they take the `569Ah-56C5h` path rather than `56C8h`.
The confirmed normal-scheduler entry is the print ISR path `086Ah->563Ch`,
which enters through `567Fh` without setting `VV6D.3` and ORs `VV6F` with
`04h`, constraining the immediate `72B3h` record selection to indices `4..7`.
The runtime queue around `FFB0h + 15*slot` can restore the same 15-byte state
into either `EF38..EF46` or the live `EF6D..EF7B` window; see
`data/lq500_3c_carriage_scheduler_contexts.tsv`.

`VV3A` is the shared low-level mode selector behind this. Render code masks
`VV3A & 07h` for the `7307h`/`730Fh`/`7317h` geometry tables, while scheduler
state copies put the same selector byte into `VV6F` for the carriage TM1 record
selection. `563Ch` also uses `VV6F.1` as a count-scale bit: when set, `EF64` is
halved before being saved as `EF79`. The current side-by-side selector map is in
`data/lq500_3c_vv3a_mode_selector.tsv`; exact user-facing speed/excitation mode
names still need bit-polarity correlation, but the current states selected by
the normal `7005h` records and the F003 helper call paths are now decoded
separately.

The selector state path is now separated from the selector value table in
`data/lq500_3c_carriage_mode_state.tsv`. `4038h` copies a saved print/style bank
into `VV1F`; setup paths preserve that value in `VV31` and `VV32`; active
render/movement paths restore `VV31`/`VV32` into `VV3A`; and the scheduler-state
copy makes source+2 become `VV6F`. This proves the state plumbing into the
carriage records, but not the manual Table 2-7 excitation-mode name for each
record because the F003 bit polarity still needs to be correlated with the
manual mode names.

### Printhead

This is intentionally separate from carriage movement. The carriage work covers
carriage position, timing, current, home seek, and F003/TM control; pin firing
will be decoded as its own output group.

`F004h/F005h` look like the head-interface registers. `045Dh` initializes
`F004=20h` and clears three writes through `F005h`; the print path later uses
the same registers as a burst-output target.

| Address | Working label | Evidence |
| --- | --- | --- |
| `08D0h` | `arm_head_f005_burst_output` | Writes `F004=0C0h`, presets alternate-register `BC=F005h`, loads source/count pointers from `EF75h`/`EF79h`, programs `TM1/TMM`, and jumps back into the print timer path. |
| `0978h` | `isr_head_f005_burst_transfer_reload` | In alternate registers, writes three bytes from `DE` to `BC`; because `08D0h` set `BC=F005h`, this is a strong candidate 24-pin data burst. Direction follows `VV61 bit 0`; `ETM0` is reloaded from `ECNT + EE3Ah`. |
| `563Ch` | `setup_head_fire_timing_and_data_pointers` | Derives `EF79h` from `EF64h`, stores alternate-register source pointers at `EF75h`/`EF77h`, seeds timing constants `001Bh` and `000Eh`, and writes `F004=20h` via `5681h`. |
| `5681h` | `write_f004_head_idle_or_arm_value` | Writes the same `20h` value to `F004` used during CPU/port initialization. |

The main unresolved detail is whether `F005h` is a direct 24-pin latch or a
gate-array staging port. Firmware evidence says the data is emitted as three
successive bytes, forward or reverse depending print direction.

### Paper Feed Command Path

Paper advance and reverse feed should be followed through the immediate-feed
commands, then through the vertical-distance counters and timed output
scheduler. The useful target is the minimum countable movement: timing records
may determine rate and settling, but paper feed should eventually reduce to a
step or microstep count rather than the kind of position/timing ambiguity seen
with carriage motion.

| Address | Working label | Evidence |
| --- | --- | --- |
| `2530h` | `esc_J_immediate_forward_feed` | Builds a positive `HL=00nn` immediate-feed distance for `ESC J n`. |
| `2568h` | `esc_j_immediate_reverse_feed_fx80_compat` | Builds `HL=80nn` and enters the same feed path; this matches FX-80 `ESC j n` reverse-feed compatibility. |
| `2534h` | `shared_immediate_feed_or_advance_entry` | Shared `ESC J`/`ESC j` entry. Marks `VV:C1` bits `E0h`, then normally jumps through `1FEAh` and `2048h` into the broader advance setup at `256Eh`. |
| `2048h` | `shared_vertical_advance_dispatch` | Common LF/FF/ESC J dispatch. It can divert to the render path, but the pure advance route snapshots `EE44h`/`EE50h`/`EE4Eh` and jumps to `256Eh`. |
| `256Eh` | `setup_signed_vertical_advance_state` | Stores signed distance in `EE7Ah`, normalizes reverse distances into `EE86h`, and updates `VV38h`/`VV39h` flags. |
| `2864h` | `process_pending_vertical_advance_distance` | Bridge from pending distance to scheduler: a nonzero `EE7Ah` magnitude is stored in `EF40h`, `VV38h` bit `08h` is set, and `5676h` is called when the scheduler is available. |
| `5676h` | `schedule_output_from_ef38_state` | Copies `EF38h` state to `EF6Dh`, writes `F004h=20h`, and branches on copied `VV6D.3`. Since `ESC J`/`ESC j` set `VV38.3`, command feed takes `569Ah-56C5h`, which writes `EF61..EF64` from the `EF75` distance path and sets `VV62=1`, `VV63=0`. |
| `558Dh`/`55B1h` | `arm_timed_mechanism_record` / `load_mechanism_timing_record_into_ef49` | Loads timing/control records from `7005h`/`7088h` into `EF49h`, calls `540Dh`, and arms `ETM1`/`FE1`. Command feed reaches the `7088h` family because `VV62=1`; the first record at `708Eh` is selected because `VV63=0`. |
| `540Dh` | `mechanism_output_state_dispatch` | Maps `VV37` state bits to `EFxx` state bytes and then either indexes the `7007h` PA/PB jump table or uses the simple `PB mask 04h` branch. With uPD7810 skip semantics, `VV62==0` reaches the jump table, while `VV62!=0` reaches the `PB & 04h` branch used by command feed. |
| `51F7h` | `startup_carriage_home_seek_entry` | Startup-only carriage home-seek path. Branches on raw `PA mask 20h` set/clear state, seeds `VV61` with carriage direction/mode values, and calls the timed seek sequence at `5253h` with `0004h`, `000Ah`, or `13ECh`. |
| `5253h` | `startup_carriage_home_seek_timed_sequence` | Walks carriage timing tables around `7287h`/`72AFh`, samples PA5 through `PA mask 20h` at `5306h`, pulses the carriage gate-array `TM` input through `0908h`, restores hold current through `546Ah`, and waits through `72AFh`/`72B1h` delay words. |
| `5306h` | `sample_pa5_low_count_during_carriage_delay` | Splits a delay interval into thirds and samples PA5 through `PA mask 20h` three times; `D` increments only for PA mask 20h clear samples. |
| `546Ah`/`5474h`/`547Eh`/`5488h` | `carriage_current_*` | Four carriage-current control states involving `PB mask 20h`, `PA mask 02h`, and `PB mask 40h`; this matches the service-manual current-control shape with `PA1` as `SPDH`. The manual's `PB1` label is treated as a typo because schematic review shows `PB1` is `AFXT`/`AUTOFEED`, while `PA1` goes through a transistor to STK69818 pins 9/11. |

The candidate phase outputs are:

| State | Final PA/PB effect |
| --- | --- |
| `546Ah` | `PB5=H`, `PA1/SPDH=H`, `PB6/SPDM=H` |
| `5474h` | `PB5=L`, `PA1/SPDH=H`, `PB6/SPDM=H` |
| `547Eh` | `PB5=L`, `PA1/SPDH=H`, `PB6/SPDM=L` |
| `5488h` | `PB5=L`, `PA1/SPDH=L`, `PB6/SPDM=H` |

Because `ESC J`/`ESC j` prove a software feed-distance path and the service
manual says one phase switch equals `1/180` inch, the current trace target is
to count `PB bits 3/4` phase updates and `PB mask 04h` drive-enable windows per
`EE7Ah`/`EE86h`/`EF40h` command unit. The command path is now known to set
`VV62=1` through the `EF61..EF64` block, so the `0668h` FE1 ISR calls `093Eh`
for `PB` bits 3/4 phase updates during counted feed steps. The separate
`VV62=0` FE1 branch calls `0908h`, the carriage gate-array `TM` pulse. The
entry gate at
`0675h` handles `VV37=1` before the first phase update: it routes through
`07BBh`, calls `540Dh` to drive `PB2` low, then jumps back to `067Ah` for the
first `093Eh` phase update. Thus PB2 drive is enabled before the first counted
phase change. The `PA mask 20h`-sampled `51F7h-5253h` path is now treated as carriage
home seek, not paper feed.

The service manual gives paper-feed acceleration intervals of `3.33`, `2.87`,
`2.65`, `2.53`, and steady `2.50 ms`; deceleration is the reverse, and moves
under 10 steps use no acceleration or deceleration. ROM words in the
`725Fh-7286h` region line up with this profile if `0C00h` is the steady
`2.50 ms` count: `0FFCh`, `0DC6h`, `0CB8h`, `0C24h`, and `0C00h` correspond to
about `3.333`, `2.871`, `2.650`, `2.529`, and `2.500 ms`. That implies a timer
tick of about `0.8138 us` for this table.

The command-feed setup has a traced short-move gate, but its polarity matters.
After `56ACh-56C3h` stores the command-feed count into `EF64` and sets
`VV62=1`, `55D4h-55E8h` checks the `VV62=1` path, loads the word at `708Eh`,
forces `H=00h`, and compares `EF64` against `000Bh`. With uPD7810 `DLT`
carry-skip semantics, counts below `000Bh` skip the `55E0h` jump, set
`VV36 & 04h`, load `EF51` from `725Fh`, and continue at `5621h` without
rewriting `EF64`. Thus command counts `1..10` take this special short-move
path. They do not walk the `EF4F`/`EF57` lead/tail lists; the FE1 path counts
down `EF64=n` directly, producing exactly `n` calls to `093Eh`.

Counts `>= 000Bh` take the normal segment setup at `55EEh-560Eh`. For the
selected `708Eh` record, `VV4C=05h` and `VV54=05h` are subtracted from the
current count, their high-bit halving flags are clear, and `VV53` does not
request doubling. The middle segment count stored to `EF64` is therefore
`count - 10`.

The same `708Eh` record copies `EF4F=725Fh` and `EF57=7269h`. The FE1 ISR walks
`EF4F` at `0772h` and `EF57` at `0799h`, advancing each pointer by one word.
The first five words from `725Fh` are `1086h`, `0DC6h`, `0CB8h`, `0C24h`, and
`0C00h`; the first five from `7269h` are `0C24h`, `0C24h`, `0CB8h`, `0DC6h`,
and `0FFCh`. These line up with the lead/tail split shape. The command-feed
first lead word `1086h` is about `3.44 ms`, while the manual-nominal `tc1`
would be about `0FFCh` / `3.33 ms`; because the later entries line up closely,
this looks like a ROM-revised first movement interval. The long path phase
count is five lead steps through `VV37=2` and
`VV4C`/`EF4F`, then `count-10` middle steps through `VV37=4` and `EF64`, then
five tail steps through `VV37=8` and `VV54`/`EF57`, again producing exactly
`n` calls to `093Eh`.

Boundary cases now fall out cleanly: `n=0` does not schedule timed paper
motion at `2864h`; `n=1` and `n=10` are direct short moves with `EF64=1` or
`EF64=10`; `n=11` is the first long move and becomes `5 + 1 + 5` counted phase
updates.

The PB2 drive window is now closed on the firmware side. After the tail
list/counter finishes, `078Ah-0790h` sets `VV37=10h` and calls `540Dh`; state
`10h` selects `EF5B=01`, so `PB2` remains low during the `EF59` delay loaded at
`0793h`. The next FE1 pass takes the `VV37.10h` state at `0699h`, enters
`07D0h`, changes the state to `VV37=20h`, and calls `540Dh` at `07D6h`. In the
normal, non-`80h` selector path, `540Dh` maps bits `04h/02h/08h/01h/10h` to
`EF53`/`EF4D`/`EF55`/`EF4B`/`EF5B`; state `20h` matches none and selects
`EF60`. `55CBh` uses `BLOCK` with `C=17h`, which copies `24` bytes into
`EF49..EF60`; for the selected `708Eh` command-feed record, `EF60=00`. That
zero record value takes the `5498h` path and sets `PB & 04h` high for the +5 V
hold state. The following `EF5C`/`EF5E` delays and `0836h` interrupt masking do
not issue another `PB & 04h` write. The carriage home-seek routine at `5253h`
contains a separate 10-step-shaped split: `529Ah` walks up to nine table-driven
intervals, then `52BDh` subtracts `000Ah` before choosing the steady loop.

## Service/Test Path

The `739Bh-7B73h` block is a service UI layer. It should be kept separate from
the preceding `7001h-739Ah` table region, which is consumed by normal
mechanism/timing and render-layout code:

- Startup builds `VV0C` from the panel bits: `01h` enters Draft self-test
  (LINE FEED/AUTO LOAD held), `02h` enters LQ self-test (FORM FEED held),
  `03h` enters data dump (LINE FEED plus FORM FEED), and `07h` is remapped to
  `08h` for bidirectional adjustment (ON LINE plus FORM FEED plus LINE FEED).
- `73AFh` prints a data-dump style grid using the `8000h` work window.
- `74CBh` is the Draft self-test entry; `74CFh` is the Letter Quality self-test
  entry. They differ by setting or clearing `VV23` bit `04h` before common
  self-test printing.
- `746Fh` converts nibbles to ASCII hex.
- `7476h` prints a single dump cell through the same character classifier used
  by normal text.
- `755Dh` prints `00h`/`FFh` terminated strings.
- `7719h` handles the documented data dump paper length messaging.
- `7818h` handles bidirectional adjustment mode and its `VR1`/`VR2` display,
  using `4EEAh` panel-action reads and `4FB1h` ADC offset refreshes.
- `79D4h`, `79F6h`, and `7A00h` are local adjustment display helpers for
  marker output, service strings, and value formatting.
- `7A18h-7A52h` holds the adjustment title, `VR1`/`VR2` labels, plus/minus
  markers, and the out-of-range string.
- `7AB2h-7B51h` maintains shared style/typeface selection state used by service
  and startup flows before `7B52h` reflects the selection on PA/PB outputs.

## Open Naming Questions

- Confirm whether the `0582h` `F000h` ISR is the Centronics/parallel data path
  or an intermediate gate-array FIFO/status path fed by the parallel interface.
- The exact meaning of style bits in `VV22`, `VV23`, `VV27`, `VV28`, `VV29`,
  `VV2A`, `VV88`, and `VV89` still needs correlation against ESC/P commands.
- `4008h` is reached after the `PBLS` check but shares normal character and
  render code, so it should be treated as a resident secondary body, not
  necessarily as an external option ROM.
- The `JEA` computed jumps at `02DCh`, `240Ah`, `5468h`, and `761Ch` need
  target recovery. `5468h` indexes the PA/PB mechanism-output table at `7007h`;
  `761Ch` is clearly part of service/status string assembly.
