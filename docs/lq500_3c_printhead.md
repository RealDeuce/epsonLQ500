# LQ-500 3C Printhead

This page tracks printhead and pin firing. It is intentionally separate from
carriage operation: carriage work covers carriage position, timing, current,
home seek, and F003/TM control. Paper feed is in
`docs/lq500_3c_paper_feed.md`.

## Current Anchors

`F004h/F005h` look like the head-interface registers. `045Dh` initializes
`F004=20h` and clears three writes through `F005h`; the print path later uses
the same registers as a burst-output target.

| Address | Working label | Evidence |
| --- | --- | --- |
| `08D0h` | `arm_head_f005_burst_output` | Writes `F004=0C0h`, presets alternate-register `BC=F005h`, loads source/count pointers from `EF75h`/`EF79h`, programs `TM1/TMM`, and jumps back into the print timer path. |
| `0978h` | `isr_head_f005_burst_transfer_reload` | In alternate registers, writes three bytes from `DE` to `BC`; because `08D0h` set `BC=F005h`, this is a strong candidate 24-pin data burst. Direction follows `VV61.0`; `ETM0` is reloaded from `ECNT + EE3Ah`. |
| `563Ch` | `setup_head_fire_timing_and_data_pointers` | Derives `EF79h` from `EF64h`, stores alternate-register source pointers at `EF75h`/`EF77h`, seeds timing constants `001Bh` and `000Eh`, and writes `F004=20h` via `5681h`. |
| `5681h` | `write_f004_head_idle_or_arm_value` | Writes the same `20h` value to `F004` used during CPU/port initialization. |

## Current Interpretation

The main unresolved detail is whether `F005h` is a direct 24-pin latch or a
gate-array staging port. Firmware evidence says the data is emitted as three
successive bytes, forward or reverse depending on print direction.

This area has not yet been deeply decoded. The next pass should follow how the
render path prepares the three-byte rows consumed by `0978h`, then connect the
timer reloads to printhead fire timing.

## Next Workstream

- Determine whether `F005h` is a direct pin latch or a gate-array staging port.
- Map the three emitted bytes to physical pins.
- Trace how render buffers feed the `EF75h`/`EF77h` pointers consumed by the
  burst ISR.
- Decode the timing relationship between `ETM0`, `EE3Ah`, carriage direction,
  and firing windows.
