# LQ-500 3C Carriage Operation

This page tracks carriage movement only: carriage position, home seek, motor
timing, current selection, F003 control bits, and the gate-array TM pulse. Print
pin firing is intentionally out of scope and belongs in
`docs/lq500_3c_printhead.md`.

Primary data files:

- `data/lq500_3c_carriage_path.tsv`
- `data/lq500_3c_carriage_home_seek.tsv`
- `data/lq500_3c_carriage_speed_modes.tsv`
- `data/lq500_3c_carriage_sequence_records.tsv`
- `data/lq500_3c_carriage_output_state_records.tsv`
- `data/lq500_3c_carriage_scheduler_contexts.tsv`
- `data/lq500_3c_vv3a_mode_selector.tsv`
- `data/lq500_3c_carriage_mode_state.tsv`
- `data/lq500_3c_f003_control_paths.tsv`

## Hardware Anchors

Service-manual pages 68-85 identify the carriage motor as a gate-array mediated
stepper path. CPU `CO1`/`PC7` feeds the E01A05KA gate-array `TM` input; after
each pulse, the gate array performs carriage phase switching. Firmware `0908h`
pulses `PC7` and is therefore the carriage phase-step pulse anchor.

The manual's carriage control prose assigns the motor control port to `F003h`.
Its Table 2-4 header is printed as `WR F002H`, which is treated as a table typo:
firmware uses `VV15`/`F003h` through direct writes and CALT helpers for carriage
control.

| Address | Working label | Evidence |
| --- | --- | --- |
| `0908h` | `carriage_gate_array_tm_pulse` | Writes `MB=03h`, pulses `PC bit 7` low then high, and updates motion counters. Service manual Figure 2-34 identifies CPU `CO1`/`PC7` as the E01A05KA carriage gate-array `TM` input. |
| `00B8h`/`00BAh`/`51E9h`/`51EDh`/`51F2h` | `write_carriage_control_f003_from_vv15` | CALT vectors at `00B8h`/`00BAh` enter the root-confirmed `51EDh` AND helper and `51E9h` OR helper. `51F0h` stores the updated `VV15`, and `51F2h` writes `F003h`. |
| `546Ah`/`5474h`/`547Eh`/`5488h` | `carriage_current_*` | Four PA/PB output states involving `PB mask 20h`, `PA mask 02h`, and `PB mask 40h`. They match the manual carriage-current control shape if the manual's `PB1 SPDH` label is treated as `PA1`, which the schematic routes through a transistor to STK69818 pins 9/11. |

## Startup Home Seek

Startup calls the carriage home-seek path at `51F7h-5253h`. This path samples
raw `PA mask 20h`, runs carriage timing tables, and pulses the gate-array `TM` input
rather than the paper-feed `PB3`/`PB4` phase bits. Schematic review identifies
this input as physical PA5 with a 15K pullup to `+5 V`. The HOME switch is at
the far-left end of carriage travel and closes to ground, so a clear sample is
an active-low HOME assertion.

The branch sequence is decoded in `data/lq500_3c_carriage_home_seek.tsv`:

- If HOME is asserted at entry, a short `0004h` rightward probe checks whether
  the carriage can move off the switch.
- If HOME is open at entry, or becomes open after the short probe, a long
  `13ECh` leftward seek runs until HOME is asserted.
- A fixed `000Ah` rightward move-away check must leave HOME open.
- HOME asserted after the confirmation/move-away check is an error condition.
- A final long `13ECh` leftward return must assert HOME before success.
- `5306h` samples PA5 through PA mask 20h three times per interval; `D` increments only for
  PA mask 20h clear samples.
- Success seeds `EF0F=EF11=0003h`.

`53B9h` later compares requested positions against `EF0F` with a `001Ah`
limit. This may relate to the manual's 22 phase-switch print-area offset, but
the exact firmware expression of that offset is not proven.

## Speed Modes And Timing

Service-manual Table 2-7 is the carriage speed grouping:

| Manual mode | Drive frequency | Excitation | Constant speed | Firmware profile |
| --- | ---: | --- | ---: | --- |
| x3 | 900 PPS | 2-2 | 1.11 ms | `runtime_record_0` |
| x2 | 600 PPS | 2-2 | 1.66 ms | `runtime_record_1` |
| x1.5 | 900 PPS | 1-2 | 1.11 ms | `runtime_record_2` |
| x1 | 600 PPS | 1-2 | 1.66 ms | `runtime_record_3` |

The Table 2-7 map is tracked in
`data/lq500_3c_carriage_speed_modes.tsv`. Tables 2-8 and 2-9 define the 2-2
and 1-2 drive sequences. Tables 2-12/2-13 carry the 2-2 accel/decel timings,
and Tables 2-14/2-15 carry the 1-2 accel/decel timings.

The runtime firmware anchors for those modes are the `7005h` record family
copied by `55B1h` into `EF49..EF60`. `VV4C`/`EF4F` drive the accel list,
`EF51` is the initial timer addend, `VV54`/`EF57` drive the decel list, and FE1
walks those lists at `0772h` and `0799h`. These are `ECNT` timer addends rather
than 10 us literals; `0999h` is about `2.00 ms`, `0554h` about `1.11 ms`,
`07F7h` about `1.66 ms`, and `0C7Ah` about `2.60 ms`. Runtime records are
decoded in `data/lq500_3c_carriage_timing_profiles.tsv`.

Home seek is not x3 or x2, and it is not a fifth Table 2-7 mode. The manual's
home-seek note identifies the 2-2 excitation system for a `20` or `30 ms` HOME
check interval, regardless of normal phase-switching timing. Firmware implements
that separate startup path with the compact `7287h-72AEh` delay table in
`5253h`, sampling PA5 through `5306h` and pulsing `PC7` through `0908h`, rather
than selecting the `7005h` x3/x2 runtime profiles.

Normal carriage scheduling uses five-byte records at `72B3h-72D8h`, indexed by
`(VV6F & 7) * 5` in `5715h`. `56CEh-56D3h` copies each record to
`EF7C..EF80`; `EF7C` can become `VV63`, `EF7D` is the `TM1` reload-cycle
length, and `EF7E..EF80` are cyclic `TM1` reload bytes consumed at
`09ACh-09BCh`. These selector rows are not themselves the manual speed
grouping; some rows select a Table 2-7 timing profile with alternate TM1 cycle
bytes. Their relation to Table 2-7 is tracked in
`data/lq500_3c_carriage_sequence_records.tsv` and
`data/lq500_3c_vv3a_mode_selector.tsv`.

The confirmed normal-scheduler entry is the print ISR path `086Ah->563Ch`,
which enters through `567Fh` without setting `VV6D.3` and ORs `VV6F` with
`04h`. That constrains immediate `72B3h` record selection to indices `4..7`.
The runtime queue producer is `28CEh-28EEh`: it waits while `VV82==04h`, copies
the `EF38..EF46` template into `FFB0h + 15*VV83`, increments the queued count,
and advances the write index. The FE1-side consumer at `08AAh-08C3h` copies
`FFB0h + 15*VV84` into the live `EF6D..EF7B` scheduler window; `09E5h-09F6h`
also probes the first byte of the pending read slot.

## Current And F003 Control

`VV63` selects one of the normal `7005h` timing/output records copied to
`EF49..EF60`. `540Dh` maps `VV37` state bits to slots such as `EF4Bh`,
`EF4Dh`, `EF4Eh`, `EF53h`, `EF55h`, `EF56h`, `EF5Bh`, or `EF60h`.

In normal carriage mode (`VV62=0`), `540Dh` strips bit 7 from the selected
state byte and indexes the `7007h` current-state jump table. Raw bytes `03h`
and `83h` both normalize to index 3 and reach `5488h`, the low-current state.
The normal record bytes are decoded in
`data/lq500_3c_carriage_output_state_records.tsv`.

F003 control paths are decoded in `data/lq500_3c_f003_control_paths.tsv`:

- `CALT ($00B8)` is the AND-update vector to `51EDh`.
- `CALT ($00BA)` is the OR-update vector to `51E9h`.
- Startup home seek uses those vectors to set up F003 bits 0 and 1 for each
  seek leg. In the startup sequence, F003 bit 1 set / `VV61.0` clear is the
  rightward move-away direction; F003 bit 1 clear / `VV61.0` set is the
  leftward return-to-home direction.
- During normal `540Dh` dispatch, selected state-byte bit 7 controls F003 bit
  0 before the byte is masked with `7Fh` for the current-state jump table.
- After record setup, `5625h-5630h` maps `VV61.0` to F003 bit 1.

Manual Table 2-4 says F003 bit 0 selects 2-2 versus 1-2 excitation and bit 1
selects CW/CCW. Table 2-7 should be treated as the carriage mode index into the
detailed Tables 2-8 and 2-9, not as a separate polarity source. The
`VV3A`/`VV6F` selector map now ties the F003 bit0 excitation side effect to the
same `VV63` runtime profile records that hold the 2-2 and 1-2
acceleration/deceleration data.
