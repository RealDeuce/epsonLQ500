# LQ-500 3C Paper Feed

This page documents traced ROM behavior for paper advance and reverse feed:
command-distance setup, timed FE1 output, `PB2` drive/hold control, and
`PB3`/`PB4` phase-state updates. Manual and schematic facts are used only as
evidence for signal names, electrical polarity, or physical units. Carriage
operation is in `docs/lq500_3c_carriage_operation.md`; printhead firing is in
`docs/lq500_3c_printhead.md`.

Primary data files:

- `data/lq500_3c_paper_advance_path.tsv`
- `data/lq500_3c_paper_feed_timing.tsv`
- `data/lq500_3c_mechanism_timing_records.tsv`

## ROM Behavior Model

The command paper-feed path has one counted output unit: a call to `093Eh`.
Each call rotates the paper-feed phase state, writes the new `PB & 18h` output
bits, and updates position state through `54A0h`, `54C9h`, and `5538h`.

Immediate feed commands are the best-resolved entry points:

- `ESC J n` at `2530h` builds a positive distance.
- FX-80-compatible `ESC j n` at `2568h` builds the signed/reverse `80nn` form.
- Both pass through `2534h`, `2048h`, `256Eh`, `2864h`, `5676h`,
  `558Dh`/`55B1h`, and `540Dh`.
- `2864h` sets `VV38.3`; after the `5676h` state copy this becomes `VV6D.3`,
  so command feed takes the `569Ah-56C5h` path.
- That path sets `VV62=1`, `VV63=0`, and `EF64` from the feed-distance state,
  selecting the `708Eh` timing record.

Because command feed runs with `VV62=1`, the FE1 ISR calls `093Eh` for paper
phase updates. The separate `VV62=0` branch is carriage/head timed output and
pulses `0908h`/`PC7`/`TM` instead.

Command distance maps to `093Eh` calls exactly:

- `n=0` does not schedule timed paper motion at `2864h`.
- `n=1..10` uses the short path with `EF64=n`.
- `n>=11` uses five lead steps, `EF64=n-10` middle steps, and five tail steps.

Both active paths produce exactly `n` calls to `093Eh` and exactly `n`
`PB & 18h` phase-state writes.

## Output Anchors

| Address | Working label | Evidence |
| --- | --- | --- |
| `093Eh` | `paper_feed_pb_bits_3_4_phase_update_candidate` | Chooses phase direction from `VV61.0`, calls `0953h` or `095Fh`, then updates position/state through `54A0h`, `54C9h`, and `5538h`. Reached by the `VV62=1` FE1 branch. |
| `0953h` | `rotate_pb_bits_3_4_phase_positive` | Rotates `VV16` right with wrap and sets `EA=+1`. Used by forward `ESC J`. |
| `095Fh` | `rotate_pb_bits_3_4_phase_negative` | Rotates `VV16` left with wrap and sets `EA=-1`. Used by reverse `ESC j`. |
| `096Ah` | `write_pb_bits_3_4_stepper_phase_outputs` | Stores the new `VV16` phase and maps `VV16 & 18h` directly onto `PB & 18h`. |
| `5498h`/`549Ch` | `PB mask 04h` drive/hold control inside `540Dh` | `549Ch` clears `PB & 04h` low and `5498h` sets `PB & 04h` high. Command feed uses this branch because `VV62=1`. |

## Phase Sequence

Reset initializes `VV16=CCh`, so the live `PB & 18h` phase state starts at
`08h`. `0953h` rotates the masked state right:

`08h -> 00h -> 10h -> 18h -> 08h`

`095Fh` rotates the same state in the reverse order:

`08h -> 18h -> 10h -> 00h -> 08h`

Signal evidence identifies these two PB bits as the paper-feed phase-select
lines. With that naming, the firmware states correspond to these phase pairs:

| Step | `PB & 18h` | `PB3` | `PB4` | Energized phases |
| --- | --- | --- | --- | --- |
| 0 | `18h` | H | H | A + C |
| 1 | `08h` | H | L | A + D |
| 2 | `00h` | L | L | B + D |
| 3 | `10h` | L | H | B + C |

The command path preserves the sign bit into `EF61`/`VV61`: `ESC J` clears
`VV61.0` and therefore selects `0953h`, while `ESC j` sets `VV61.0` and selects
`095Fh`.

## Timing And Drive Window

The command-feed short-move gate is at `55D4h-55E8h`. Counts below `000Bh`
set `VV36 & 04h`, load `EF51=725Fh`, and leave `EF64` as the original command
count. Counts `>=000Bh` fall through `55EEh-560Eh`; with the `708Eh` record
fields this subtracts five lead plus five tail steps and stores
`EF64=count-10` for the middle segment.

The `708Eh` record seeds `EF4F=725Fh` and `EF57=7269h`; the FE1 ISR walks
these timing lists at `0772h` and `0799h`. The first five words at `725Fh` are
`1086h`, `0DC6h`, `0CB8h`, `0C24h`, `0C00h`; the first five at `7269h` are
`0C24h`, `0C24h`, `0CB8h`, `0DC6h`, `0FFCh`.

Using the steady `0C00h` word as the `2.50 ms` interval gives a table scale of
about `0.8138 us` per count. On that scale the lead words are about `3.44`,
`2.87`, `2.65`, `2.53`, and `2.50 ms`, while the tail list ends at about
`3.33 ms`. The only `0FFCh` words in the ROM are at `7271h` and `7285h`;
`7271h` is the fifth tail word from `EF57=7269h`, and no traced forward or
reverse command-feed path uses `0FFCh` as the first lead interval.

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

## Signal And Unit Evidence

Signal/unit evidence identifies the paper-feed motor as a 4-phase, 48-step
motor driven with 2-2 phase excitation. Each phase switch advances paper by
`1/180` inch, and the steady drive frequency is `400 PPS`, or one phase switch
every `2.5 ms`. These facts give physical units to the ROM's counted `093Eh`
phase updates.

Figure 2-47 identifies:

- `PB2`: active-low paper-feed drive signal. Low turns Q27 on and supplies
  `+24 V`; when not driven, `+5 V` is supplied through `R36`/`D11` for hold.
- `PB3`: phase A/B select.
- `PB4`: phase C/D select.

Those signal names map the ROM's `PB mask 04h` branch to paper-feed drive/hold
control and `PB & 18h` writes to paper-feed phase selection. They are bit masks
on the CPU `PB` port; they are not separate schematic pin-name notation.
