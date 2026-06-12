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
| `PA bit 20h` | Used by feed/mechanism setup flows around `51F7h-5241h`; likely paper/feed related, not fully named yet. |
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

Current priority is paper advance/retard, carriage movement, and pin firing.
Cut-sheet feeder and other option-specific mechanisms should stay secondary
unless they share one of these output paths.

### Paper Feed Stepper Phase

The service manual identifies the paper-feed motor as a 4-phase, 48-pole motor
driven with 2-2 phase excitation. Each phase switch advances paper by `1/180`
inch, and the CPU controls it open loop. The motor drive frequency is `400 PPS`,
matching one phase switch every `2.5 ms`. Figure 2-47 also identifies `PB2` as
the active-low paper-feed drive signal: when `PB2` is low, Q27 turns on and
supplies `+24 V`; when not driven, `+5 V` is supplied through `R36`/`D11` to
hold the motor. The same text identifies `PB3` as phase A/B and `PB4` as phase
C/D.

That makes the firmware's `PB04h` and `PB18h` paths the strongest paper-feed
hardware anchors:

| Address | Working label | Evidence |
| --- | --- | --- |
| `0908h` | `paper_feed_step_timing_pulse_candidate` | Writes `MB=03h`, pulses `PC bit 7` low then high, and updates `VV61`/position counters. It is called directly by the print ISR and by the timed motion sequence at `5303h`. |
| `093Eh` | `paper_feed_pb18_phase_update_candidate` | Chooses phase direction from `VV61 bit 0`, calls `0953h` or `095Fh`, then updates position/state through `54A0h`, `54C9h`, and `5538h`. |
| `0953h` | `rotate_pb18_phase_positive` | Rotates `VV16` right with wrap and sets `EA=+1`. |
| `095Fh` | `rotate_pb18_phase_negative` | Rotates `VV16` left with wrap and sets `EA=-1`. |
| `096Ah` | `write_pb18_stepper_phase_outputs` | Stores the new `VV16` phase and maps `VV16 & 18h` directly onto `PB & 18h`; if service-manual bit numbering is zero-based, this is `PB3`/`PB4`. |
| `5498h`/`549Ch` | `PB04h` drive/hold control inside `540Dh` | `549Ch` clears `PB04h` and `5498h` sets `PB04h`. This matches service-manual `PB2` active-low +24 V paper-feed drive enable versus +5 V hold. |

The service-manual excitation sequence makes the `PB18h` states concrete:

| Step | `PB18h` | `PB3` | `PB4` | Energized phases |
| --- | --- | --- | --- | --- |
| 0 | `18h` | H | H | A + C |
| 1 | `08h` | H | L | A + D |
| 2 | `00h` | L | L | B + D |
| 3 | `10h` | L | H | B + C |

Reset initializes `VV16=CCh`, so the masked output starts at `08h` / step 1.
The manual labels the table order as clockwise and says clockwise feeds paper
forward, while counterclockwise feeds paper in reverse. The `0953h`
rotate-right path advances `08h -> 00h -> 10h -> 18h -> 08h`, matching the
increasing manual step order; the `095Fh` rotate-left path reverses that order.

The previous working label treated `PB18h` as carriage phase output. Figure
2-47 makes that unlikely unless the schematic's `PB3`/`PB4` labels are not
CPU-port bit labels. Carriage movement should be re-found after paper feed is
settled.

### Head / Pin Firing

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

### Paper Feed / Retard Candidate

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
| `5676h` | `schedule_output_from_ef38_state` | Copies `EF38h` state to `EF6Dh`, writes `F004h=20h`, and routes into the timed-record arm path. |
| `558Dh`/`55B1h` | `arm_timed_mechanism_record` / `load_mechanism_timing_record_into_ef49` | Loads timing/control records from `7005h`/`7088h` into `EF49h`, calls `540Dh`, and arms `ETM1`/`FE1`. |
| `540Dh` | `mechanism_output_state_dispatch` | Maps `VV37` state bits to `EFxx` state bytes and indexes the `7007h` jump table when `VV62 != 0`; with `VV62 == 0`, it uses the simple `PB04h` output case, matching the service-manual paper-feed motor drive/hold control. |
| `51F7h` | `startup_mechanism_pa20_motion_entry` | Only traced caller is startup at `0340h`. Branches on `PA bit 20h`, seeds `VV61` with direction/mode values, and calls the timed sequence at `5253h` with short or long distances. |
| `5253h` | `mechanism_pa20_timed_step_sequence` | Starts by selecting output state `547Eh`, walks timing tables around `7287h`/`72AFh`, samples `PA bit 20h` through `5306h`, then restores output state `546Ah`. |
| `5306h` | `sample_pa20_during_motion_delay` | Splits a delay interval into thirds and samples `PA bit 20h` three times. |
| `546Ah`/`5474h`/`547Eh`/`5488h` | `mechanism_phase_state_*_pa_pb_candidate` | Four PA/PB output states involving `PB20h`, `PA02h`, and `PB40h`. These are likely actuator phases, but the exact paper-feed assignment still needs confirmation. |

The candidate phase outputs are:

| State | Final PA/PB effect |
| --- | --- |
| `546Ah` | `PB20=1`, `PA02=1`, `PB40=1` |
| `5474h` | `PB20=0`, `PA02=1`, `PB40=1` |
| `547Eh` | `PB20=0`, `PA02=1`, `PB40=0` |
| `5488h` | `PB20=0`, `PA02=0`, `PB40=1` |

Because `ESC J`/`ESC j` prove a software feed-distance path and the service
manual says one phase switch equals `1/180` inch, the next paper-feed pass
should count `PB18h` phase updates and `PB04h` drive-enable windows per
`EE7Ah`/`EE86h`/`EF40h` unit. The PA20-driven `51F7h-5253h` path still looks
paper related, but the `PB20h`/`PA02h`/`PB40h` table should remain a separate
mechanism table until it is tied to a schematic signal.

The service manual gives paper-feed acceleration intervals of `3.33`, `2.87`,
`2.65`, `2.53`, and steady `2.50 ms`; deceleration is the reverse, and moves
under 10 steps use no acceleration or deceleration. ROM words in the
`725Fh-7286h` region line up with this profile if `0C00h` is the steady
`2.50 ms` count: `0FFCh`, `0DC6h`, `0CB8h`, `0C24h`, and `0C00h` correspond to
about `3.333`, `2.871`, `2.650`, `2.529`, and `2.500 ms`. That implies a timer
tick of about `0.8138 us` for this table.

The PA20 startup timed-step routine at `5253h` contains an explicit 10-step
split that matches the manual rule's shape. The loop at `529Ah` walks up to
nine table-driven intervals from `7287h`, then `52BDh` subtracts `000Ah` from
the requested count. A zero remainder branches at `52C3h` to the decel/tail
path, while a nonzero remainder enters the longer steady loop using the
`72ADh` timing entry. This proves the literal threshold exists in the firmware,
but it is in the PA20/startup mechanism path; the normal `ESC J` path still
appears to encode its short/long behavior through the derived `EF3Bh`/`EF3Eh`
partition fields rather than a traced literal `000Ah` compare.

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
