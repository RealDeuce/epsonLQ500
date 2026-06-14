# LQ-500 3C Printhead

This page tracks printhead mechanical output: head gate-array commands, the
three-byte latch burst, HPW/timer behavior, and voltage-compensated pulse
timing. It intentionally stops before character-generator and rendered glyph
details. Carriage operation is in `docs/lq500_3c_carriage_operation.md`; paper
feed is in `docs/lq500_3c_paper_feed.md`.

Primary data files:

- `data/lq500_3c_printhead_path.tsv`
- `data/lq500_3c_printhead_wire_map.tsv`

## Manual Anchors

Service-manual Figure 1-2 and pages 2-54 through 2-59 describe the head as a
24-solenoid, 12-by-2 staggered dot-wire assembly. Figure 5-3 is the clearest
wire-number placement reference: as drawn, the odd wires (`#1, #3, ... #23`)
are in the right column and the even wires (`#2, #4, ... #24`) are in the
left column. Figure 1-2 supplies the spacing: same-column vertical pitch is
`1/90"`; the even column is staggered by `1/180"` relative to the odd column.
The head drive is
`24 VDC +/- 10%`; the manual lists `16 ohms +/- 10%` coil resistance at
`25 C`, `0.12 A` typical current, `1.111 ms` / `900 Hz` solenoid drive
frequency, and a `415 us` to `435 us` driving pulse-width specification.
Figures 2-53 through 2-55 separately label the E05A02LA output /
print-driving pulse-width curve from roughly `287 us` at low drive voltage
down to roughly `230 us` at high drive voltage.

Appendix A connects the firmware-visible latch outputs to the head wiring.
Figure A-8 and Table A-7 map E05A02LA pins `1..8` to `H1..H8`, pins
`13..20` to `H9..H16`, and pins `34..41` to `H17..H24`. Figure A-9 labels
those as the first, second, and third data-latch blocks. Tables A-11 and A-12
cross-check the board connector side as CN5/CN6 `HD n` pins; Table A-12 is
split across the two page columns and continues through CN6 pin `15`, `HD3`.
The combined output, connector, and physical wire map is in
`data/lq500_3c_printhead_wire_map.tsv`.

The intra-byte order in each 8-bit latch is now treated as confirmed:
`D7` maps to the first wire in the latch block and `D0` maps to the last.
So `first_H1_H8` uses `D7..D0 -> H1..H8`, `second_H9_H16` uses
`D7..D0 -> H9..H16`, and `third_H17_H24` uses `D7..D0 -> H17..H24`.
This is reflected in `data/lq500_3c_printhead_wire_map.tsv` and in the rendered
glyph check for Roman `g` at 10 cpi LQ.

The head interface is the E05A02LA gate array. The manual identifies it as
three 8-bit data latches for `H1..H24`:

- `F004h` is the command port. Bit 7 selects the latch writing sequence
  (`0` ascending, `1` descending), bit 6 makes HPW valid, bit 5 resets the
  latch counter, and bits 4..0 are optional.
- `F005h` is the data port. Each write latches one byte and advances the
  internal counter; three writes fill the 24-bit head data set. The manual says
  data is protected against double writes by NANDing with the current latch
  contents.
- Latched head data is inverted and output while HPW is low when HPW is valid.
  The manual identifies CPU `PC6` as the HPW drive-pulse signal.

## ROM Behavior Model

The ROM uses `F004h/F005h` exactly as the manual's head gate-array command/data
ports:

- Init at `045Dh-0492h` writes `PC=C4h`, `F004=20h`, then writes three zero
  bytes to `F005h`. Under Table 2-18, `20h` means counter reset with HPW
  invalid and ascending latch order.
- The normal scheduler writes `F004=20h` again at `5681h` before entering the
  timed output path, resetting the latch counter while HPW is invalid.
- The head arm path at `08D0h` writes `F004=40h` when `VV61.0` is clear and
  `F004=C0h` when `VV61.0` is set. `40h` is HPW-valid ascending order;
  `C0h` is HPW-valid descending order.
- The head ISR at `0978h` emits exactly three bytes through alternate-register
  `BC=F005h`. When `VV61.0` is clear it reads source bytes with `DE+`; when
  `VV61.0` is set it reads with `DE-`. Thus the ROM changes both the
  gate-array latch order and the firmware source-pointer direction together.

The ROM does not bit-bang `PC6` in the traced print path. After each three-byte
`F005h` burst, `0978h-0999h` reloads `ETM0` from `ECNT + EE3Ah`, changing
`EOM` from `05h` to `08h` around the reload. This is the traced firmware side
of HPW pulse timing; the electrical mapping to CPU `PC6` comes from the manual.

`EE3Ah` is the pulse-width addend. The FE1 path at `06D7h-06E9h` samples
`CR0`, accepts values in the `C2h..EDh` range, indexes the descending table at
`72DBh..7306h`, shifts the selected byte once, and stores the result at
`EE3Ah`. Larger `CR0` values select smaller table bytes, matching the manual's
drive-voltage curve where higher voltage requires shorter drive pulse width.
Out-of-range samples branch through `06F9h`, which changes the timed-output
state instead of updating `EE3Ah`.

The printhead path is coupled to carriage timing but is not a character
generator path. `563Ch` saves already-prepared source/count state into the
`EF75h`/`EF77h`/`EF79h` area, seeds the normal carriage/head scheduler, and the
FE1 state machine later reaches `08D0h` to arm the head burst in the
constant-speed print window. This document intentionally does not trace how
glyph bytes are produced before they become the three bytes consumed by
`0978h`.

## Code Anchors

| Address | Working label | Evidence |
| --- | --- | --- |
| `045Dh-0492h` | `init_head_gate_array_and_ports` | Initializes `PC=C4h`, writes `F004=20h`, then writes three zero bytes to `F005h`. |
| `06D7h-06E9h` | `update_head_hpw_width_from_cr0` | Reads `CR0`, range-checks it, indexes the `72DBh-7306h` descending pulse-width table through `HL=7219h` plus raw `CR0`, and stores the shifted result at `EE3Ah`. |
| `08D0h` | `arm_head_f005_burst_output` | Writes `F004=40h` or `F004=C0h` according to `VV61.0`, presets alternate-register `BC=F005h`, loads alternate source/count state from `EF75h`/`EF77h`, reloads `EF64h` from `EF79h`, programs `TM1/TMM`, and jumps back into the print timer path. |
| `0978h` | `isr_head_f005_burst_transfer_reload` | In alternate registers, writes three bytes to `F005h`; direction follows `VV61.0`. It then reloads `ETM0` from `ECNT + EE3Ah`, decrements the burst counter, and either schedules the next burst through `09ACh-09BCh` or clears the active state at `09A2h-09ABh`. |
| `563Ch` | `setup_head_fire_timing_and_data_pointers` | Derives `EF79h` from `EF64h`, stores alternate-register source/count state at `EF75h`/`EF77h`, seeds timing constants `001Bh` and `000Eh`, and enters the normal `VV62=0` scheduler. |
| `5681h` | `reset_head_gate_array_counter` | Writes `F004=20h`, matching Table 2-18 counter reset with HPW invalid. |
| `72DBh-7306h` | `head_hpw_voltage_compensation_table` | Descending bytes selected by raw `CR0` through `HL=7219h` plus `A`; larger input values produce smaller `EE3Ah` pulse-width addends. |

## Next Workstream

- Intra-byte mapping is now resolved (`D7..D0` to `Hn..Hn+7`) and used by the
  render pipeline assumptions; remaining uncertainty is limited to connector
  mechanical details already documented in the wire map.
- In a later rendering document, trace how character-generator/render buffers
  prepare the three-byte rows consumed by `0978h`.
