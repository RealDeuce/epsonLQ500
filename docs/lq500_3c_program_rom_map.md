# LQ-500 3C Program ROM First-Pass Code Map

Source dump:

- `roms/lq500_3c_m25a10pa_internal_prom.bin`
- CRC32 `cf3ba9da`
- SHA1 `7275ef3547ad1bbb12210d626c796a827f308bb6`
- Disassembly: `roms/lq500_3c_m25a10pa_internal_prom.asm`
- First-pass labels: `data/lq500_3c_program_labels.tsv`
- `6000h-6FFFh` data usage: `data/lq500_3c_6000_block_usage.tsv`
- `7000h-7FFFh` data/code usage: `data/lq500_3c_7000_block_usage.tsv`
- Parsed command dispatch tables: `data/lq500_3c_command_dispatch_tables.tsv`
- Carriage path trace: `data/lq500_3c_carriage_path.tsv`
- Audited command behavior table: `data/lq500_3c_command_behaviors.tsv`
- Self-test status selector table: `data/lq500_3c_selftest_status_selectors.tsv`
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
| `0582h-09C1h` | Interrupt handlers and mechanism dispatch | ISRs buffer data from `F000h`/`RXB`, manipulate `F001h/F002h`, update timers, pulse carriage timing, and run the likely head-data burst ISR. |
| `0A0Bh-0B3Fh` | Input consumer and small helpers | Includes the shared host-input byte reader at `0A0Bh`, parameter readers, F001 disable sequence, nibble shifts, delay loops, and a direct `F002` write helper at `0B23h`. |
| `0E8Bh-0F15h` | Buffer/window bounds helpers | Uses `FF00h`, `EE4Ch`, `EE5Ch`, `EE5Eh`, and `EFBF`; likely print-buffer/string bounds logic. |
| `0F16h-2DCDh` | Core text/render/print logic | Many small mode-flag helpers and high-fan-in rendering routines. This is the least-labeled large code body so far. |
| `2DCEh-2DE2h` | Inline dispatch tail table | `2DC8h` loads `DE=2DCEh`; this short table-like tail belongs to the preceding render/CALT dispatch path, not to the following fill. |
| `2DE3h-3FFFh` | Fill | All `0xFF`. |
| `4000h-5793h` | Main input decode and secondary code body | Starts with `PBLS` signature at `4000h`; reset checks this area for external PROM handling. Contains the `400Bh` host-byte decode loop, printable-character setup, and substantial hardware helpers. |
| `5794h-5FFFh` | Fill | All `0xFF`. |
| `6000h-60FFh` | Host-byte remap table | Literal bytes `00h-FFh`, consumed by `4038h` before printable/control classification. |
| `6100h-67EFh` | Service/diagnostic strings and status tables | Contains `L5217B`, `Data Dump Mode`, CSF messages, pitch text, the self-test status pointer table, and selector-prefixed DIP/status text. |
| `67F0h-689Bh` | Render/glyph lookup tables | Pointer and setup tables consumed by `264Fh`, overlapping lookup tables at `682Eh`/`6834h`, and an indexed glyph metric lookup base at `6844h`. |
| `689Ch-6943h` | International character substitution table | Consumed by `1464h`; `ESC R n` sets the country row offset used by this table. |
| `6944h-695Fh` | Command dispatcher code | Table scanner reached from the main input loop at `400Fh`. |
| `6960h-696Dh` | Unresolved table/code fragment | No traced xref yet; sits between dispatcher code and the primary command table. |
| `696Eh-6A59h` | Command dispatch tables | Count-prefixed primary and ESC command tables consumed by `6944h`/`695Bh`. |
| `6A5Ah-6FFFh` | Fill | All `0xFF`. |
| `7001h-7218h` | Mechanism/head timing and output tables | `5635h` selects timing records at `7005h`/`7088h`; `540Dh` indexes the overlapping PA/PB output jump table at `7007h`. |
| `7219h-7286h` | CR0/timing lookup table | `06DFh` indexes the `7219h` table from the CR0 range; `55E4h` directly loads a word at `725Fh`. |
| `7287h-72D8h` | Mechanism delay/sequence tables | `5253h` walks delay/sequence data around `7287h` and `72AFh`; `5719h` also indexes from `72B3h`. |
| `72D9h-739Ah` | Render geometry lookup tables | `21F1h-2322h` consume small byte/word tables at `7307h`, `7317h`, `7341h`, `735Bh`, `736Bh`, `737Bh`, and `738Bh`. |
| `739Bh-7B73h` | Service/self-test/adjustment code | Includes power-on service dispatch, data-dump mode, self-test status printing, bidirectional adjustment/calibration UI, embedded adjustment strings, and PA/PB output helpers. |
| `7B74h-7FFFh` | Fill | All `0xFF`. |

## High-Confidence Routines

| Address | Working label | Notes |
| --- | --- | --- |
| `0180h` | `boot_reset_entry` | First executed code. Clears `A000h`, `8000h`, `FF00h`, checks external PROM signature, then calls init routines. |
| `045Dh` | `init_cpu_ports_timers_gate_array` | Writes `EOM`, `PA`, `PB`, `PC`, motor-control registers, timer mode, `F004`, `F005`, and `F003`. |
| `049Ch` | `memclear_hl_bc` | Simple `A=0; STAX (HL+); DCR C/B` clear loop. |
| `0582h` | `isr_gate_f000_input_capture_buffer` | Interrupt path reads `F000h` through the gate-array window and stores the byte into the shared `EE20h` input buffer. Candidate parallel-port data path. |
| `05E2h` | `isr_rxb_host_receive_buffer` | Reads `RXB`, checks `ER`, stores received byte into the `EE20h` buffer with temporary `F002` bank changes. |
| `07D0h` | `paper_feed_pb2_release_delay_state` | FE1 tail-exit state reached from `VV37=10h`; changes the state to `20h`, calls `540Dh`, and releases active-low `PB2` to high/hold through the `EF60=00` / `5498h` path. |
| `08D0h` | `arm_head_f005_burst_output` | Writes `F004=0C0h`, presets alternate-register `BC=F005h`, loads head-data/timing pointers, and arms the timer path. Strong candidate head-fire setup. |
| `0908h` | `carriage_gate_array_tm_pulse` | Writes `MB=03h`, pulses `PC bit 7`, and updates motion counters. Service manual Figure 2-34 identifies CPU `CO1`/`PC7` as the E01A05KA carriage gate-array `TM` input. |
| `093Eh` | `paper_feed_pb_bits_3_4_phase_update_candidate` | Rotates the `VV16` phase via `0953h`/`095Fh`, then updates position/state helpers. |
| `096Ah` | `write_pb_bits_3_4_stepper_phase_outputs` | Maps `VV16 & 18h` directly to `PB & 18h`; `18h` is a port mask, not a pin name. Service manual Figure 2-47 identifies paper-feed phase signals as `PB3`/`PB4`, matching these mask bits if bit numbering is zero-based. |
| `0978h` | `isr_head_f005_burst_transfer_reload` | Writes three bytes through alternate-register `BC`, which `08D0h` presets to `F005h`; likely 24-pin head data burst. |
| `0A0Bh` | `read_next_host_input_byte` | Consumes from the shared input buffer using `EE22h` as the read pointer and `EE1Eh` as the pending count. This is `CALT ($0080)`. |
| `0B23h` | `write_bank_register_f002` | Single-purpose helper: `MOV ($F002),A; RET`. |
| `2530h` | `esc_J_immediate_forward_feed` | `ESC J n`: reads one byte and enters the immediate-feed path with a positive distance. |
| `2534h` | `shared_immediate_feed_or_advance_entry` | Shared `ESC J`/`ESC j` entry; marks `VV:C1` bits `E0h` and normally jumps through `1FEAh`/`2048h` into the signed vertical-advance setup at `256Eh`. |
| `2568h` | `esc_j_immediate_reverse_feed_fx80_compat` | `ESC j n`: FX-80 compatibility reverse feed; reads one byte and enters the same immediate-feed path with the high byte set to `80h`. |
| `2864h` | `process_pending_vertical_advance_distance` | If the pending `EE7Ah` distance is nonzero, stores the magnitude in `EF40h`, sets `VV38h.3`, and calls the timed output scheduler at `5676h`. |
| `400Bh` | `main_input_decode_loop` | Top-level loop: read host byte, classify with `4038h`, print if printable, dispatch if command/control. |
| `4038h` | `classify_input_character_and_select_style_state` | Classifies printable bytes and sets font/style state; printable bytes skip over the command dispatcher. |
| `4EE4h` | `txb_send_byte_wait_fst` | Waits for `FST`, then writes `TXB`. |
| `4EEAh` | `read_panel_buttons_debounced` | Returns panel bits `01h` LINE FEED/AUTO LOAD, `02h` FORM FEED, and `04h` ON LINE from debounced `PC`/`F2` inputs. |
| `4F2Fh` | `delay_03e8` | Loads `BC=03E8h`, delays via `CALT ($0090)`. |
| `4F37h` | `read_dip_switches_and_panel_pa_bits` | Startup DIP/panel read. Uses table-driven ADC switch reads and then folds in direct PA bits. |
| `4F54h` | `read_adc_switch_table_bits` | Consumes compact tables at `4F96h`/`4F9Fh`, samples ADC via `508Dh`, and builds switch bitfields. |
| `4FB1h` | `sample_vr_adjustment_adc_offsets` | Averages/clamps ADC-derived adjustment values used at startup and by bidirectional adjustment mode. |
| `51F7h` | `startup_carriage_home_seek_entry` | Only traced caller is startup at `0340h`; branches on `PA bit 20h`, sets `VV61` carriage direction/mode values, and calls the timed home-seek sequence at `5253h`. |
| `5253h` | `startup_carriage_home_seek_timed_sequence` | Drives table-based carriage delays, samples `PA bit 20h` via `5306h`, pulses PC7 through `0908h`, and selects carriage current states through `546Ah`/`547Eh`. |
| `540Dh` | `mechanism_output_state_dispatch` | Selects output states from `VV37`/`EFxx`. With uPD7810 skip semantics, `VV62!=0` reaches the `PB mask 04h` set/clear branch matching the service-manual active-low `PB2` paper-feed drive/hold control; `VV62==0` indexes the `7007h` PA/PB jump table. |
| `546Ah` | `carriage_current_hold_state` | Carriage current state: `PB & 20h=1`, `PA & 02h=1`, `PB & 40h=1`. Manual says PB5 high is hold current; schematic review shows PB1 is AFXT/AUTOFEED and PA1 goes through a transistor to STK69818 pins 9/11, so PA1 is the SPDH speed-high selector despite the manual table's PB1 label. |
| `5474h` | `carriage_current_drive_high_candidate` | Carriage current state: final `PB & 20h=0`, `PA & 02h=1`, `PB & 40h=1`, mapping to the 0.67 A row. |
| `547Eh` | `carriage_current_drive_mid_candidate` | Carriage current state: final `PB & 20h=0`, `PA & 02h=1`, `PB & 40h=0`, mapping to the 0.61 A row; used by startup home seek. |
| `5488h` | `carriage_current_drive_low_candidate` | Carriage current state: final `PB & 20h=0`, `PA & 02h=0`, `PB & 40h=1`, mapping to the 0.23 A row; target of the `7007h` jump table. |
| `558Dh` | `arm_timed_mechanism_record` | Sets `VV37=1`, loads a timing/control record via `55B1h`, calls `540Dh`, and arms `ETM1`/`FE1`. |
| `55B1h` | `load_mechanism_timing_record_into_ef49` | Copies a `17h`-byte timing/control record from the selected `7005h`/`7088h` table into `EF49h`. |
| `563Ch` | `setup_head_fire_timing_and_data_pointers` | Seeds `EF75h`/`EF77h`/`EF79h` and timing constants before writing `F004=20h`; likely head-fire setup state. |
| `5676h` | `schedule_output_from_ef38_state` | Shared output scheduler reached from vertical advance and head/setup paths; copies `EF38h` state to `EF6Dh`, writes `F004=20h`, and branches on copied `VV6D.3`. Command feed takes the `569Ah-56C5h` path and sets `VV62=1` before timed-record setup. |
| `6944h` | `dispatch_control_or_esc_command` | Count-prefixed command-table scanner; primary table starts at `696Eh`, ESC table at `699Ch`. |
| `739Bh` | `power_on_panel_mode_dispatch` | Dispatches `VV0C` startup panel mode: Draft self-test, LQ self-test, data dump, or bidirectional adjustment. |
| `74CBh` | `draft_self_test_entry` | Power-on LINE FEED/AUTO LOAD self-test path; sets `VV23.2` before the common self-test printer. |
| `74CFh` | `letter_quality_self_test_entry` | Power-on FORM FEED self-test path; clears `VV23.2` before the common self-test printer. |
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
- `F004h/F005h`: initialized at `0487h-0492h`; `08D0h` writes `F004=0C0h`
  and presets alternate-register `BC=F005h`, while `0978h` writes three bytes
  through that pointer. `5681h` writes the idle/arm value `F004=20h`.

The `4C` CG dump is now a stable 128 KiB custom PROM read. The schematic
reportedly confirms `4C` pin 1 is `A15`, so each 64 KiB A16 bank has valid
low/high `A15` halves. The 4C jumper/schematic evidence points to a banked
1 Mbit arrangement: `J5` ties pin 1 / `A15` to `BK2` on the `6C` E01A05KA gate
array, `J6` wires pin 20 `/CE`, and the hard-to-read `A16/OE` label appears to
be `A16` wired to `BK3`, not `/OE`. Native T48 `AT27C011@DIP28` and
`D27C011@DIP28` reads mirrored only the A16-low 64 KiB bank; patched custom
PROM reads captured the distinct pin-22-high/A16-high bank and a full 128 KiB
image ordered as A16-low then A16-high. Firmware analysis should look for
values written to `F002h` before reads from
`8000h-9FFFh`/`A000h`, especially routines that call `0B23h`, `508Dh`, or
directly write `F002h`.

## Mechanical Output Anchors

The current mechanical priority order is paper advance/retard, carriage
movement, and pin firing. Option mechanisms such as the cut-sheet feeder remain
lower priority unless they share these paths.

| Mechanism | Best current anchors | Firmware evidence |
| --- | --- | --- |
| Paper feed phase / drive | `093Eh`, `0953h`, `095Fh`, `096Ah`, `540Dh`, `5498h`, `549Ch` | Service manual Figure 2-47 says the paper-feed motor is a 4-phase 48-step motor using 2-2 phase excitation, one phase switch per `1/180` inch, with a `400 PPS` drive frequency matching the `2.5 ms` steady timing word. It identifies `PB2` as active-low +24 V drive/hold control and `PB3`/`PB4` as phase A/B and C/D; firmware maps `VV16 & 18h` to `PB & 18h` and controls `PB & 04h` in `540Dh`. The `18h`/`04h` values are PB port masks, not pin names. `549Ch` clears `PB & 04h` low for +24 V drive; `5498h` sets it high for hold. The manual labels the excitation-table order clockwise/paper-forward, and firmware `0953h` follows that order from the reset-start phase. |
| Carriage phase / current | `0908h`, `51F2h`, `51F7h`, `5253h`, `5306h`, `546Ah`, `5474h`, `547Eh`, `5488h`, `7287h`, `72B3h` | Service manual Figure 2-34 identifies CPU `CO1`/`PC7` as the E01A05KA carriage gate-array `TM` input; firmware `0908h` pulses that bit when `VV62=0`. Startup `51F7h-5253h` samples the `PA bit 20h` HOME candidate while walking carriage timing tables and pulsing `TM`. `51F2h` writes carriage control state to `F003h`. The `546Ah-5488h` states match the manual's carriage-current control shape; schematic review shows PB1 is AFXT/AUTOFEED and PA1 goes through a transistor to STK69818 pins 9/11, so PA1 is the SPDH speed-high selector despite the manual table's PB1 label. |
| Head / pin firing | `08D0h`, `0978h`, `563Ch`, `5681h` | `08D0h` arms `F004/F005` and timer state; `0978h` emits three bytes to `F005h`; `563Ch` prepares source/count pointers. |
| Paper feed / retard command path | `2530h`, `2534h`, `2048h`, `2568h`, `256Eh`, `2864h`, `5676h`, `558Dh`, `55B1h`, `540Dh` | `ESC J` and FX-80-compatible `ESC j` enter the signed vertical advance path, then nonzero pending distance reaches the timed output scheduler through `2864h`/`5676h`. Because `2864h` sets `VV38.3`, `5676h` copies that to `VV6D.3` and takes the `569Ah-56C5h` path, setting `VV62=1`, `VV63=0`, and `EF64` from the feed-distance state. |

The service manual now resolves the physical paper-feed unit: one phase switch
is `1/180` inch. The command-feed path now traces to `VV62=1`, so the `0668h`
FE1 ISR calls `093Eh` for `PB` bits 3/4 phase updates and then decrements/reloads
`EF64h`. The command distance maps cleanly to phase switches: `n=0` does not
schedule timed paper motion at `2864h`; `n=1..10` uses the short path with
`EF64=n`; `n>=11` uses five lead steps, `EF64=n-10` middle steps, and five tail
steps. Both active paths therefore produce exactly `n` calls to `093Eh` and
exactly `n` `PB3`/`PB4` phase changes. The `VV62=0` branch is now treated as
carriage/head timed output: it pulses `0908h`/`PC7`/`TM` instead of calling the
paper `PB3`/`PB4` phase helper.

The service-manual 2-2 excitation table maps firmware `PB & 18h` states to phase
pairs as `18h=A+C`, `08h=A+D`, `00h=B+D`, and `10h=B+C`. Reset seeds
`VV16=CCh`, giving initial `PB & 18h=08h`. The `0953h` rotate-right helper walks
`08h -> 00h -> 10h -> 18h -> 08h`; `095Fh` walks the reverse order. `ESC J`
builds a positive distance, leaves `VV61.0` clear, and selects `0953h`. `ESC j`
builds the signed/reverse `80nn` form, sets `VV61.0`, and selects `095Fh`.

The service-manual acceleration profile is `3.33`, `2.87`, `2.65`, `2.53`,
then `2.50 ms`, with deceleration in reverse and no accel/decel for short
moves. The ROM timing words around `725Fh-7286h` contain matching values:
`0FFCh`, `0DC6h`, `0CB8h`, `0C24h`, and `0C00h` convert to about `3.333`,
`2.871`, `2.650`, `2.529`, and `2.500 ms` if `0C00h` is the steady interval.
The entry gate at `0675h` handles `VV37=1` before the first phase update: the
initial state routes through `07BBh`, calls `540Dh` with the drive-on record
value, then jumps back to `067Ah` for the first `093Eh` phase update. Thus
`PB2` drive is enabled before the first counted phase change.

The normal command-feed path now has a traced short-move gate:
`55D4h-55E8h` handles the `VV62=1` path, compares `EF64h` with the low byte at
`708Eh` (`0Bh`), and for counts below `000Bh` sets `VV36 & 04h`, loads
`EF51=725Fh`, and leaves `EF64h` as the original command count. Counts
`>=000Bh` fall through `55EEh-560Eh`; with the `708Eh` record fields, this
subtracts five lead plus five tail steps and stores `EF64h=count-10` for the
middle segment. The same record seeds `EF4F=725Fh` and `EF57=7269h`; the FE1
ISR walks these at `0772h` and `0799h`. The first five words at `725Fh` are
`1086h`, `0DC6h`, `0CB8h`, `0C24h`, `0C00h`; the first five at `7269h` are
`0C24h`, `0C24h`, `0CB8h`, `0DC6h`, `0FFCh`. The command-feed first lead word
is about `3.44 ms`, so it appears to be a ROM-revised first movement interval
relative to the manual's `3.33 ms` `tc1`. The carriage home-seek routine at
`5253h` has a separate 10-step-shaped split: `52BDh` subtracts `000Ah` after
the first nine indexed intervals, and the zero-remainder path skips the long
steady loop.

The final `PB2` release is in the `VV37=20h` state. `VV37=10h` selects
`EF5B=01` and keeps `PB2` low during the `EF59` delay. On the next FE1 pass,
`07D0h-07D6h` changes the state to `20h` and calls `540Dh`; that state falls
through the selector to `EF60`. `EF60` is outside the `EF49..EF5F` record copy
and has no traced direct writer, so it remains zeroed. The zero value takes the
`5498h` branch and sets `PB & 04h` high for hold before the later `EF5C`/`EF5E`
delays and final FE1 masking.

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

- `ESC J n` is documented for the LQ-500 as `n/180` inch. The firmware injects
  `n` directly as `HL=00nn`, but LF and programmable line spacing use `EF8Bh`
  and `50EBh` before reaching the same vertical-advance path, so the physical
  step/microstep unit should be proven from the scheduler counters rather than
  assumed from the command parameter.
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
| `617Fh` | `(8.5mm)`; no traced consumer found yet. |
| `6187h` | `(22mm)`; no traced consumer found yet. |
| `6190h-61A8h` | Pitch names: `10`, `12`, `15`, `Proportional` |
| `61AAh-620Dh` | Self-test status pointer table: two pointers per printed row, ending with `0000h`. |
| `6230h-67EFh` | Selector-prefixed DIP/status strings. The first byte is matched against selected IDs in `FF00h`; matching rows print emphasized/bold. |
| `67F0h-6A59h` | Non-string lookup and dispatch data; see `data/lq500_3c_6000_block_usage.tsv`. |
| `7001h-739Ah` | Mechanism, timing, CR0, and render geometry lookup data; see `data/lq500_3c_7000_block_usage.tsv`. |
| `7A18h` | `Bi-d Adjustment Mode` |
| `7A2Dh` | `VR1 = ` |
| `7A34h` | `VR2 = ` |
| `7A3Dh` | ` (out of range)` |
| `7A4Dh` | space marker |
| `7A4Fh` | `+` |
| `7A51h` | `-` |

Startup panel mode dispatch:

| `VV0C` | Held button(s) | Mode |
| ---: | --- | --- |
| `01h` | LINE FEED/AUTO LOAD | Draft self-test at `74CBh` |
| `02h` | FORM FEED | Letter Quality self-test at `74CFh` |
| `03h` | LINE FEED/AUTO LOAD + FORM FEED | Data dump at `73AFh` |
| `08h` | ON LINE + FORM FEED + LINE FEED/AUTO LOAD, remapped from raw `07h` | Bidirectional adjustment at `7818h` |

## Current Uncertainties

- The exact uPD7810 vector names for `0008h`, `0010h`, `0018h`, and `0028h`
  still need datasheet correlation.
- The `CALT` area at `0080h-00BEh` needs aligned disassembly by actual CALT
  target, not linear decoding.
- Recursive trace unresolved indirect exits currently include `JEA` at
  `02DCh`, `240Ah`, `5468h`, and `761Ch`; these need manual target recovery.
- The large core region `0F16h-2DCDh` needs command-parser and glyph-renderer
  separation. The current labels only mark high-fan-in helpers.
- `4000h-5793h` may be alternate/external-PROM-related code or a second major
  firmware body behind the `PBLS` check. It is real code, not filler.
- The relationship between `F002h` writes and the 4C `BK2`/`A15`,
  `BK3`/`A16`, and `/CE` selection is not yet resolved.

## Next Pass

1. Build xrefs around `0582h`, `05E2h`, `4EEAh`, `4F37h`, `4F54h`, `4FB1h`,
   and service-mode callers to separate host input, panel buttons, DIP switch
   defaults, and VR/adjustment reads.
2. Correlate `VV00`/`VV01` bits from `4F37h` against the documented DIP switch
   defaults in `docs/lq500_reference.md`.
3. Continue carriage tracing from the service manual's driver signals by
   decoding the `72B3h-72D8h` carriage control records and the normal scheduler
   callers around `56C8h-5712h`.
4. Build xrefs around every `F002h` write and nearby `8000h`/`8600h` reads.
5. Split `0F16h-2DCDh` into command parsing, font/style state, and glyph fetch
   helpers by tracing high-fan-in calls (`1677h`, `1DDFh`, `1DFEh`, `2011h`,
   `24D4h`, `26F1h`).
6. Align and label the `CALT` service stubs.
7. Cross-reference ESC/P command constants from `data/lq500_commands.json`
   against immediate comparisons in the disassembly.
8. Recover the computed `JEA` targets, add confirmed targets to
   `data/lq500_3c_trace_roots.tsv`, and rerun
   `tools/trace_upd7810_unidasm.py`.
