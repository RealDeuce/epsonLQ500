# LQ-500 3C Paper Feed

This page tracks paper advance and reverse feed. Carriage operation is in
`docs/lq500_3c_carriage_operation.md`; printhead firing is in
`docs/lq500_3c_printhead.md`.

Primary data files:

- `data/lq500_3c_paper_advance_path.tsv`
- `data/lq500_3c_paper_feed_timing.tsv`
- `data/lq500_3c_mechanism_timing_records.tsv`

## Hardware Anchors

The service manual identifies the paper-feed motor as a 4-phase, 48-step motor
driven with 2-2 phase excitation. Each phase switch advances paper by `1/180`
inch, and the CPU controls it open loop. The steady drive frequency is
`400 PPS`, matching one phase switch every `2.5 ms`.

Figure 2-47 identifies:

- `PB2`: active-low paper-feed drive signal. Low turns Q27 on and supplies
  `+24 V`; when not driven, `+5 V` is supplied through `R36`/`D11` for hold.
- `PB3`: phase A/B select.
- `PB4`: phase C/D select.

Firmware anchors:

| Address | Working label | Evidence |
| --- | --- | --- |
| `093Eh` | `paper_feed_pb_bits_3_4_phase_update_candidate` | Chooses phase direction from `VV61.0`, calls `0953h` or `095Fh`, then updates position/state through `54A0h`, `54C9h`, and `5538h`. |
| `0953h` | `rotate_pb_bits_3_4_phase_positive` | Rotates `VV16` right with wrap and sets `EA=+1`. Used by forward `ESC J`. |
| `095Fh` | `rotate_pb_bits_3_4_phase_negative` | Rotates `VV16` left with wrap and sets `EA=-1`. Used by reverse `ESC j`. |
| `096Ah` | `write_pb_bits_3_4_stepper_phase_outputs` | Stores the new `VV16` phase and maps `VV16 & 18h` directly onto `PB & 18h`; if service-manual bit numbering is zero-based, this is `PB3`/`PB4`. |
| `5498h`/`549Ch` | `PB mask 04h` drive/hold control inside `540Dh` | `549Ch` clears `PB & 04h` low and `5498h` sets `PB & 04h` high. This matches service-manual `PB2` active-low +24 V drive enable versus +5 V hold. |

## Phase Sequence

The service-manual 2-2 excitation table maps firmware `PB & 18h` states to
phase pairs as:

| Step | `PB & 18h` | `PB3` | `PB4` | Energized phases |
| --- | --- | --- | --- | --- |
| 0 | `18h` | H | H | A + C |
| 1 | `08h` | H | L | A + D |
| 2 | `00h` | L | L | B + D |
| 3 | `10h` | L | H | B + C |

Reset initializes `VV16=CCh`, so `PB & 18h` starts at `08h` / step 1. The
manual labels the table order as clockwise and says clockwise feeds paper
forward. The `0953h` rotate-right helper walks
`08h -> 00h -> 10h -> 18h -> 08h`; `095Fh` walks the reverse order.

## Command Feed Path

Immediate feed commands are the best-resolved paper path:

- `ESC J n` at `2530h` builds a positive distance.
- FX-80-compatible `ESC j n` at `2568h` builds the signed/reverse `80nn` form.
- Both pass through `2534h`, `2048h`, `256Eh`, `2864h`, `5676h`,
  `558Dh`/`55B1h`, and `540Dh`.
- `2864h` sets `VV38.3`; after the `5676h` state copy this becomes `VV6D.3`,
  so command feed takes the `569Ah-56C5h` path.
- That path sets `VV62=1`, `VV63=0`, and `EF64` from the feed-distance state,
  selecting the `708Eh` timing record.

Because command feed runs with `VV62=1`, the FE1 ISR calls `093Eh` for
`PB3`/`PB4` phase updates. The separate `VV62=0` branch is carriage/head timed
output and pulses `0908h`/`PC7`/`TM` instead.

Command distance maps cleanly to phase switches:

- `n=0` does not schedule timed paper motion at `2864h`.
- `n=1..10` uses the short path with `EF64=n`.
- `n>=11` uses five lead steps, `EF64=n-10` middle steps, and five tail steps.

Both active paths produce exactly `n` calls to `093Eh` and exactly `n`
`PB3`/`PB4` phase changes. Since the service manual says one phase switch is
`1/180` inch, the command unit is one `1/180` inch phase switch.

## Timing And Drive Window

The manual acceleration profile is `3.33`, `2.87`, `2.65`, `2.53`, then
`2.50 ms`, with deceleration in reverse and no accel/decel for short moves.
The ROM timing words around `725Fh-7286h` contain matching values:
`0FFCh`, `0DC6h`, `0CB8h`, `0C24h`, and `0C00h` convert to about `3.333`,
`2.871`, `2.650`, `2.529`, and `2.500 ms` if `0C00h` is the steady interval.

The command-feed short-move gate is at `55D4h-55E8h`. Counts below `000Bh`
set `VV36 & 04h`, load `EF51=725Fh`, and leave `EF64` as the original command
count. Counts `>=000Bh` fall through `55EEh-560Eh`; with the `708Eh` record
fields this subtracts five lead plus five tail steps and stores
`EF64=count-10` for the middle segment.

The `708Eh` record seeds `EF4F=725Fh` and `EF57=7269h`; the FE1 ISR walks
these timing lists at `0772h` and `0799h`. The first five words at `725Fh` are
`1086h`, `0DC6h`, `0CB8h`, `0C24h`, `0C00h`; the first five at `7269h` are
`0C24h`, `0C24h`, `0CB8h`, `0DC6h`, `0FFCh`. The command-feed first lead word
is about `3.44 ms`, so it appears to be a ROM-revised first movement interval
relative to the manual's `3.33 ms` `tc1`. The only `0FFCh` words in the ROM are
at `7271h` and `7285h`; `7271h` is the fifth tail word from `EF57=7269h`, and
no traced forward or reverse command-feed path uses `0FFCh` as the first lead
interval.

The entry gate at `0675h` handles `VV37=1` before the first phase update:
`07BBh` calls `540Dh` with the drive-on record value, then jumps back to
`067Ah` for the first `093Eh` phase update. Thus active-low `PB2` drive is
enabled before the first counted phase change.

Final `PB2` release is in the `VV37=20h` state. `VV37=10h` selects `EF5B=01`
and keeps `PB2` low during the `EF59` delay. On the next FE1 pass,
`07D0h-07D6h` changes the state to `20h` and calls `540Dh`; that state falls
through the selector to `EF60`. For the selected `708Eh` command-feed record,
`EF60=00`, so the zero value takes the `5498h` branch and sets `PB & 04h` high
for hold before the later `EF5C`/`EF5E` delays and final FE1 masking.

Option mechanisms remain outside this paper-feed path unless they share
`PB2`/`PB3`/`PB4`.
