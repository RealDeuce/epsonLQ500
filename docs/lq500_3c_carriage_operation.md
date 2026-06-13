# LQ-500 3C Carriage Operation

This page documents traced ROM behavior for carriage movement: startup home
seek, carriage position state, queued movement setup, timing records, current
selection, F003 control bits, and the gate-array TM pulse. Manual and schematic
facts are used only as evidence for signal names, electrical polarity, or
physical units. Print pin firing is intentionally out of scope and belongs in
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

## ROM Behavior Model

The ROM uses two carriage paths:

- Startup calls `51F7h`, which seeks the far-left HOME switch using timed
  `PC7`/`TM` pulses, PA5 sampling, and direct F003 direction/mode writes. On
  success it seeds `EF0F=EF11=0003h`.
- Runtime movement is queued through the print/scheduler path. `28CEh-28EEh`
  writes 15-byte movement templates into the `FFB0h` ring; the FE1-side
  consumer at `08AAh-08C3h` restores a queued slot into `EF6D..EF7B`; the
  normal carriage scheduler at `56C8h-5712h` selects a `72B3h` TM1 sequence
  record and a `7005h` timing/output record; the FE1 timing walkers at
  `0772h`/`0799h` and the `09ACh-09BCh` TM1 reload loop drive the timed
  output.

The physical carriage step output observed in ROM is `0908h`: it writes
`MB=03h`, pulses `PC bit 7` low then high, and updates motion counters. The ROM
does not directly bit-bang carriage phase windings on `PB3`/`PB4`; those are
the paper-feed phase lines.

The documented low-level carriage movement unit is one `0908h` `PC7`/`TM`
pulse, which the gate array converts into one carriage motor phase switch.
Figure 2-44 maps the 900 PPS normal-character case: two phase switches span
`1/60` inch, and the intervening half-dot positions are `120 DPI`. Thus a 2-2
excitation phase switch is `1/120` inch. In 1-2 excitation the gate-array drive
sequence has twice as many phase states for the same motor cycle, so one phase
switch is `1/240` inch. Figure 2-44 labels the 22-step span from HOME to the
print-area boundary as the acceleration area. The print area therefore starts
`22` phase-switching times after HOME, which is `22/120` inch in the 2-2 case
shown by Figure 2-44.

`53B9h` is the small relative-move gate. It compares a requested target in `HL`
against the home/reference position at `EF0F`; if the absolute difference is
greater than `001Ah`, it returns without scheduling. If the requested target is
within range, it passes the movement distance onward to `532Bh`, setting bit 7
of `H` for the reverse direction case.

## Signal Anchors

The schematic/manual identify the carriage motor as a gate-array mediated
stepper path. CPU `CO1`/`PC7` feeds the E01A05KA gate-array `TM` input; after
each pulse, the gate array performs carriage phase switching. That makes
firmware `0908h` the carriage phase-step pulse anchor.

Figure 2-44 supplies the carriage distance mapping for the 2-2, 900 PPS
printing case: one `PC7`/`TM` pulse produces one `1/120` inch phase switch.
For 1-2 excitation, one pulse is one half-step, or `1/240` inch.

The carriage control port is `F003h`: firmware writes the carriage control
shadow `VV15` to `F003h` through direct writes and CALT helpers. The manual's
Table 2-4 header is printed as `WR F002H`, but `F002h` is the bank-selector
path in the ROM work, so that header is treated as a manual typo rather than a
ROM behavior.

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

The startup path ends here. Later relative moves use `53B9h` to compare a
requested target against `EF0F` with a `001Ah` local-motion limit before
scheduling a move through `532Bh`; that is runtime scheduler behavior, not an
additional home-seek stage.

## Timing And Mode Records

The ROM runtime timing records copied by `55B1h` correspond to four normal
carriage speed/excitation groups:

| Firmware profile | Drive frequency | Excitation | Constant speed | Selector evidence |
| --- | ---: | --- | ---: | --- |
| `runtime_record_0` | 900 PPS | 2-2 | 1.11 ms | selected by `72B3h` index 0 |
| `runtime_record_1` | 600 PPS | 2-2 | 1.66 ms | selected by `72B8h` index 1 |
| `runtime_record_2` | 900 PPS | 1-2 | 1.11 ms | selected by `72BDh` index 2 |
| `runtime_record_3` | 600 PPS | 1-2 | 1.66 ms | selected by `72D1h` index 6; also used by alternate selector rows |

The decoded records are tracked in `data/lq500_3c_carriage_speed_modes.tsv`
and `data/lq500_3c_carriage_timing_profiles.tsv`. Manual Tables 2-7 through
2-15 are evidence for naming the excitation systems and timing units, but the
ROM behavior is the record selection and timer programming described here.

The runtime firmware anchors for those modes are the `7005h` record family
copied by `55B1h` into `EF49..EF60`. `VV4C`/`EF4F` drive the accel list,
`EF51` is the initial timer addend, `VV54`/`EF57` drive the decel list, and FE1
walks those lists at `0772h` and `0799h`. These are `ECNT` timer addends rather
than 10 us literals; `0999h` is about `2.00 ms`, `0554h` about `1.11 ms`,
`07F7h` about `1.66 ms`, and `0C7Ah` about `2.60 ms`. Runtime records are
decoded in `data/lq500_3c_carriage_timing_profiles.tsv`.

Home seek is not one of these runtime profiles. The ROM implements it through
the separate startup path at `5253h`, using the compact `7287h-72AEh` delay
table, PA5 sampling through `5306h`, and `PC7` pulses through `0908h`, rather
than selecting a `7005h` runtime timing profile.

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

The `VV3A`/`VV6F` selector map ties the F003 bit0 excitation side effect to the
same `VV63` runtime profile records that hold the 2-2 and 1-2
acceleration/deceleration data. Manual Table 2-4 is used only to name F003 bit
0 as the 2-2/1-2 excitation select and bit 1 as the direction select.
