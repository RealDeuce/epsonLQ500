# LQ-500 3C Carriage Operation

This page tracks carriage movement only: carriage position, home seek, motor
timing, current selection, F003 control bits, and the gate-array TM pulse. Print
pin firing is intentionally out of scope and belongs in
`docs/lq500_3c_printhead.md`.

Primary data files:

- `data/lq500_3c_carriage_path.tsv`
- `data/lq500_3c_carriage_home_seek.tsv`
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

- Short `0004h` probe when PA mask 20h starts clear.
- Long `13ECh` seek when PA mask 20h starts set or becomes set after the probe.
- Fixed `000Ah` confirmation move across the edge.
- HOME asserted after the confirmation/move-away check is an error condition.
- Final long `13ECh` seek before success.
- `5306h` samples PA5 through PA mask 20h three times per interval; `D` increments only for
  PA mask 20h clear samples.
- Success seeds `EF0F=EF11=0003h`.

`53B9h` later compares requested positions against `EF0F` with a `001Ah`
limit. This may relate to the manual's 22 phase-switch print-area offset, but
the exact firmware expression of that offset is not proven.

## Timing And Scheduler

The carriage timing words at `7287h-72AEh` are in 10 us units and line up with
the manual carriage acceleration/deceleration tables. Examples include
`0162h` near `3.56 ms`, `00E7h` at `2.31 ms`, `00C8h` at `2.00 ms`, `00A6h`
at `1.66 ms`, and `007Ah` at `1.22 ms`.

Normal carriage scheduling uses five-byte records at `72B3h-72D8h`, indexed by
`(VV6F & 7) * 5` in `5715h`. `56CEh-56D3h` copies each record to
`EF7C..EF80`; `EF7C` can become `VV63`, `EF7D` is the `TM1` reload-cycle
length, and `EF7E..EF80` are cyclic `TM1` reload bytes consumed at
`09ACh-09BCh`.

The confirmed normal-scheduler entry is the print ISR path `086Ah->563Ch`,
which enters through `567Fh` without setting `VV6D.3` and ORs `VV6F` with
`04h`. That constrains immediate `72B3h` record selection to indices `4..7`.
The runtime queue around `FFB0h + 15*slot` can restore the same 15-byte state
into either `EF38..EF46` or the live `EF6D..EF7B` window; see
`data/lq500_3c_carriage_scheduler_contexts.tsv`.

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
  seek leg.
- During normal `540Dh` dispatch, selected state-byte bit 7 controls F003 bit
  0 before the byte is masked with `7Fh` for the current-state jump table.
- After record setup, `5625h-5630h` maps `VV61.0` to F003 bit 1.

Manual Table 2-4 says F003 bit 0 selects 2-2 versus 1-2 excitation and bit 1
selects CW/CCW. Table 2-7 should be treated as the carriage mode index into the
detailed Tables 2-8 and 2-9, not as a separate polarity source.

## Open Items

- Resolve F003 bit1/`VV61.0` direction polarity for the startup home probe,
  move-away check, and final return-to-home leg.
- Map `VV3A`/`VV6F` selector values to the Table 2-7 rows, then use Tables
  2-8/2-9 for the detailed carriage mode behavior.
- Identify the producer for queued scheduler state in the `FFB0h + 15*slot`
  ring.
