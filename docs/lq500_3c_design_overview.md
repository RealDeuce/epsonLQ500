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
| `0582h` | `isr_parallel_input_buffer` | Parallel interface ISR: sets `F001h` software BUSY, reads `F000h` (auto-resets hardware BUSY per Table 2-20), stores byte into the `EE20h` ring buffer, increments `EE1Eh`, and generates an ACK pulse via `F001h` unless the buffer is full. |
| `05E2h` | `isr_serial_input_buffer` | Serial interface ISR: reads `RXB`, filters NUL/error/parity, writes into the same `EE20h` ring buffer, and manages XON/XOFF flow control through `4ECFh`/`4EE2h`. |
| `4EEAh` | `read_panel_buttons_debounced` | Returns a compact button/action bitfield: `01h` = LINE FEED/AUTO LOAD, `02h` = FORM FEED, `04h` = ON LINE. Bidirectional-adjustment mode waits for return to zero before accepting another action. |
| `4F37h` | `read_dip_switches_and_panel_pa_bits` | Startup switch read. Calls the ADC/table reader twice, writes `VV00`/`VV01`, then folds PA bits `04h` and `08h` into `VV01`. |
| `4F54h` | `read_adc_switch_table_bits` | Walks compact tables at `4F96h`/`4F9Fh`; each entry chooses an `F002h`/ADC mode through `508Dh` and compares the resulting sample against a threshold. |
| `4FB1h` | `sample_vr_adjustment_adc_offsets` | Startup and bidirectional-adjustment sampler. It averages ADC channels for VR1/VR2 and stores signed/clamped offsets in the `EE28h` slot table later consumed by the normal render geometry path at `21F1h-21FFh`. |

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
| PA5 / `PA mask 20h` | Raw input sampled by startup carriage home-seek code around `51F7h-5241h`. Schematic review shows PA5 has a 15K pullup to `+5 V`, and the far-left HOME switch closes to ground, so clear samples are active-low HOME assertions. |
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

This adjustment is not purely analog after the pots are read. Service-manual
Section 2.2.8 says the A/D converter reads bidirectional adjustment on
`AN2..AN7`, Section 4.3.2 says VR1 is Draft and VR2 is LQ, and Tables 4-4/4-5
define correction as print-start displacement. VR1 is `n/240` inch with valid
values `-7..+7`; VR2 is `n/720` inch with valid values `-11..+11`. Firmware
`4FB1h` converts ADC readings into the signed `EE28h` slot table, and normal
render geometry at `21F1h-21FFh` indexes that table with `VV3A & 07h`. For
emulator output, clamp applied bidirectional offset to `+/-1/480` inch for
Draft and `+/-1/1440` inch for LQ. See
`data/lq500_3c_bidirectional_adjustment.tsv`.

## Input Pipeline

The host input path is now fully confirmed against service-manual Table 2-20
(gate-array register map) and Section 2.2.10 (buffer architecture). The
primary data file is `data/lq500_3c_host_interface_path.tsv`.

### Gate-Array Registers

| Register | Read | Write |
| --- | --- | --- |
| `F000h` | Parallel data (DIN 7..0). Auto-resets hardware BUSY (Table 2-20 Note 1). | — |
| `F001h` | Status bits: bit 7 int/ext ROM, bit 5 STRB edge, bit 4 hw BUSY, bit 3 sw BUSY, bit 2 ACK, bit 1 ERR, bit 0 PE. | Sets the same signal bits. Power-on: sw BUSY high, ACK high, ERR high. |
| `F002h` | Bank register. | Bank select. `C0h` selects external RAM for buffer access. |
| `F003h` | Parallel data without BUSY reset. | Carriage control bits (separate function via `VV15`). |

### Ring Buffer Geometry

Startup at `0292h` seeds `EE20h` (write pointer) and `EE22h` (read pointer)
to `8500h`. DIP switch `VV01` bit 4 selects buffer size: 1K (`VV08=04h`,
buffer spans `8500h-88FFh`) or 8K (`VV08=1Fh`, buffer spans
`8500h-A3FFh`). The wrap page `VV07` equals `85h + VV08`. Both ISRs and
the consumer wrap their pointers to `8500h` when the high byte reaches
`VV07`.

### Parallel ISR (`0582h`)

Vectors: `0010h` and `0060h` both jump to `0582h`.

1. Guard: skips if `VV37 & 70h` (mechanism active). Masks `MKL` bit 3.
2. Reads `F001h`, ORs bit 3 (software BUSY active), writes back.
3. Saves `F002h` to `B`, writes `F002h=C0h` to access external RAM.
4. Reads `F000h` — this auto-resets hardware BUSY per Table 2-20 Note 1.
5. Stores byte at `EE20h` write pointer, advances, wraps on `VV07`.
6. Increments `EE1Eh` pending count.
7. Restores `F002h` from `B`.
8. Compares pending-count high byte against `VV08`:
   - Not full: generates ACK pulse via `F001h` — clears bit 2 (ACK low),
     clears bit 3 (software BUSY low), re-sets bit 2 (ACK high) — with
     NOP delay slots between writes.
   - Full: sets `VV09` bit 0, exits without ACK. Host sees continuous BUSY.

### Serial ISR (`05E2h`)

Vector: `0028h` jumps to `05E2h`.

1. Same mechanism guard and `MKH` mask. Saves VA, BC, HL, EA.
2. Reads `RXB`. Checks `ER` (serial error); if error, exits.
3. Filters: `VV09` bit 1 (overflow recovery), `VV0A` bit 6 (serial
   disabled gate), NUL byte — any of these causes an early exit.
4. If `VV0A` bit 3 is set, replaces the byte with `2Ah` (parity-error
   substitution character).
5. Saves `F002h`, sets `F002h=C0h`. Ring write/wrap/increment identical to
   the parallel ISR. Sets `F002h=00h` after the write.
6. Buffer-level check against `VV08`:
   - Full: sets `VV09` bit 1 (serial overflow), calls `4EE2h` (send XOFF).
   - Near-full (threshold `1BEFh` for 8K, `00EFh` for 1K): sets `VV09`
     bit 0, calls `4ECFh` (set software BUSY + send XOFF).

### Consumer (`0A0Bh`)

Reached via `CALT ($0080)`.

1. Polls `EE1Eh` until nonzero. While idle, checks panel buttons at
   `4EEAh`; ON LINE (bit 2) calls `4F24h`/`1FE4h`.
2. Sets `F002h=C0h`, reads byte from `EE22h` read pointer, restores
   `F002h=00h`. Wraps pointer on `VV07`.
3. Decrements `EE1Eh` atomically under DI via `CALT ($00AC)`.
4. Flow-control release: if `VV09` bit 0 was set (buffer was full), checks
   pending against a low-water threshold. If drained below threshold,
   clears `VV09` bit 0 and calls `4EB9h` (clear software BUSY, send XON).
   If `VV09` bit 6 (serial disabled), uses the `0A81h` F001 disable
   sequence instead.
5. Applies `EE8Fh` byte mask (OR high byte, AND low byte; initialized to
   `00FFh` = identity). Handles DC1 (`11h`) / DC3 (`13h`) XON/XOFF from
   host transparently.
6. Returns byte in `A` to the caller.

### Flow-Control Helpers

| Address | Role | Behavior |
| --- | --- | --- |
| `4EB9h` | Release host | Clears `F001h` bit 3 (software BUSY low). If serial XON/XOFF active (`VV0A` bit 4), sends DC1 (`11h`) via `TXB`. |
| `4ECFh` | Block host | Sets `F001h` bit 3 (software BUSY high). If serial active, sends DC3 (`13h`) via `TXB`. |
| `4EE2h` | Overflow XOFF | Sends DC3 (`13h`) via `TXB` without toggling `F001h`. |
| `0A81h` | Disable ACK/BUSY | `F001h` bit sequence: clear ACK, clear sw BUSY, set ACK. Used when serial is the only active interface. |

### Main Decode Loop

`400Bh` calls the consumer via `CALT ($0080)`, classifies the byte with
`4038h`, and then either enters printable output at `4012h` or command
dispatch at `6944h`.

The command dispatcher is table-driven:

| Address | Role |
| --- | --- |
| `6944h` | Pushes `400Bh` as the loop return, scans a count-prefixed byte/target table, and jumps to a matched handler. |
| `696Eh` | Primary control-command table: `ESC`, `LF`, `CR`, `BEL`, `BS`, `HT`, `VT`, `FF`, `SO`, `SI`, `DC2`, `DC3`, `DC4`, `CAN`. |
| `695Bh` | ESC entry from the primary table; reads the next byte through `0AB2h` and switches to the ESC table. |
| `699Ch` | ESC command table with 62 byte/handler entries, including `ESC @`, line spacing/page commands, graphics commands, and style commands. |

The parallel and serial paths converge before ESC/P parsing. Command handlers consume their parameters by calling the same
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

All major command paths are now traced. See the individual sections below
for graphics commands, character generation, print effects, and mechanical
output. Remaining command-level details are in
`data/lq500_3c_command_behaviors.tsv`.

## Line Spacing and Paper Feed Translation

Line spacing is stored in `EF8B` in 1/360 inch units:

| Command | Formula | Example |
| --- | --- | --- |
| `ESC 0` | `EF8B = 45` | 1/8 inch = 45/360 |
| `ESC 2` | `EF8B = 60` | 1/6 inch = 60/360 |
| `ESC A n` | `EF8B = n × 6` | n/60 inch |
| `ESC 3 n` | `EF8B = n × 2` | n/180 inch |

LF at `2011h` loads `EF8B` and calls `$50EB` to convert to paper-feed
phase steps. `$50EB` divides by 2 (DSLR → 1/180 inch steps, matching one
phase switch per 1/180 inch), with dithered rounding via `VV:93` to handle
odd values: the low bit alternates between rounding up and down on
successive lines to keep the average spacing correct.

## Page Formatting

| Register | Set by | Meaning |
| --- | --- | --- |
| `EF8D` | `ESC C` | Page length (1/360 inch). n lines: n × EF8B / 2. n inches: n × 180. |
| `EF8F` | `ESC N` | Skip-over-perforation boundary (n × EF8B / 2, clamped to page). |
| `VV:90` bit 7 | `ESC N`/`ESC O` | Skip-over-perf active. `ESC O` clears. |
| `EF91` | `ESC C` | Cleared when page length is set. |
| `EE5C` | `ESC Q` | Right margin (column position, clamped to max $2F89). |
| `EE5E` | `ESC l` | Left margin. Must be less than `EE5C`. |

FF at `201Fh` loads `EF8D` (page length) and advances to the next page
boundary. If `EF8D` is zero (no page length set), FF enters the shared
advance path at `2048h` without feeding.

## Justification

`ESC a n` (`$42C1`) selects justification mode by writing `VV:C1`:
n=0 left ($00), n=1 center ($80), n=2 right ($40), n=3 full ($20).
The command is rejected unless the current print position `EE4C`
equals the left margin `EE5E`.  After storing VV:C1, the handler
falls through to `$42E8` which computes `EEA5 = EE5C - EE4C`
(available line width from current position to right margin).

### VV:C1 Bit Map

| Bit | Mask | Meaning | Set/cleared by |
| --- | --- | --- | --- |
| 7 | $80 | Center justification mode | ESC a 1 |
| 6 | $40 | Right justification mode | ESC a 2 |
| 5 | $20 | Full justification mode | ESC a 3 |
| 4 | $10 | Deferred-render flag | `$2AEF`/`$2CE2` set; `$2AB6`/`$2B9B` clear |
| 3 | $08 | Render state flag | `$1A01` set; `$1A0B`/`$2D00`/`$2D0E` clear |
| 2 | $04 | Render state flag | `$1A0F` set; `$1A04`/`$2D00` clear |
| 1 | $02 | Justify-pending flag (triggers `$2B98` from decode loop) | `$1A08` set; `$1A0B`/`$2D0E` clear |
| 0 | $01 | Expand-spaces flag (full justification spacing active) | `$2B17` set; `$2B40` clear |

Bits 7:5 select the mode; bits 4:0 are runtime state flags.

### Decode Loop Integration

The main character loop at `$400B` has two justification checkpoints:

**Before rendering** (`$401E`): when full justification is active
(VV:C1 bit 5), `$4173` is called to check whether the current
character would overflow the right margin.  `$4173` computes
`EE4C + HL (char width)` and compares against `EE5C` (right margin).
If the character would overflow and the cursor is not at the left
margin, it forces a line feed via `CALL $2011` (LF handler) — this
is the automatic word-wrap trigger for full justification.

**After line-advance** (`$402B`): after `CALT ($0098)` (line advance
at `$1896`), the loop tests VV:C1 bit 5.  If full justification is
active, it skips the pending-justify check and loops back (full
justification defers spacing to line end).  Otherwise, it tests
VV:C1 bit 1 (justify-pending) and calls `$2B98` if set.

### Center and Right Justification (`$2ABE-$2ADC`)

When VV:C1 bit 1 triggers `$2B98` from the decode loop, the code
reaches `$2AB3` which calls `$2DC8` (setup), clears VV:C1 bit 4,
then branches on the mode bits:

1. `$2ADD` computes remaining space:
   - `$1A24` returns used width in BC (`EE48 - EE4A`).
   - `EEA5` (available width) minus used width → EA.
   - Clamped to zero on borrow.

2. **Center** (VV:C1 bit 7): remaining ÷ 2 via `DSLR EA` at `$2AC9`.
   **Right** (VV:C1 bit 6): full remaining used as offset.

3. The offset is added to four position registers (`EE48`, `EE4A`,
   `EE4C`, `EE6C`) via `CALT ($00B0)` at `$2ACF-$2ADB`, shifting
   the entire line rightward.

### Full Justification (`$2AEB-$2B68`)

When full justification reaches the spacing computation:

1. `$2AEB`: if VV:C1 bits 2+3 (`$0C`) are set, the render is
   deferred (sets bit 4, returns).

2. `$2AF3`: clears `EE91`/`EE93`, loads `EF9B` (advance), calls
   `$1A24` for used width, adds advance, and compares against
   `EEA5` (available width):

   - **Line fills the margin** (`used + advance >= available`, tested
     via `DSUBNB` skip-on-no-borrow at `$2B13`): sets VV:C1 bit 0
     (expand-spaces flag).  Divides the remaining space by `EE52`
     (word-space count from line buffer) via `CALT ($00A0)`.
     Quotient → `EE99`/`EE9B` (per-space expansion amount).
     Remainder → `EE95`/`EE97` (extra 1-unit expansion distributed
     to the first N spaces).

   - **Line too short** (`used + advance < available`): clears VV:C1
     bit 0 (no expansion).  Uses default spacing from `EE58`/`EE54`.

3. The computed values are copied to `EE9D` (8 bytes via BLOCK at
   `$2B5F`) for the render core.

`EE52` is the word-space counter, incremented at `$1920` (line buffer
write) alongside character data.  The division distributes remaining
space evenly across all inter-word gaps, with the remainder giving
one extra unit to the leftmost spaces — standard full-justification
arithmetic.

### Dot-Level Coordinates and Proportional Interaction

All justification position tracking uses dot units (1/360 inch).
`EE48` (max position reached) and `EE4A` (min position) are updated
at `$1995` (CALT `$009C`) after every character render: the current
position is compared against the running min/max via `DLT`/`DGT` and
the extremes are updated.  Since each character contributes its actual
dot-level width from the font metrics (`VV:99`/`EF9B`), proportional
and fixed-pitch characters are handled identically — there is no
column-count or character-count abstraction.

The full justification "line full" test at `$2B13` uses `>=` (via
`DSUBNB` skip-on-no-borrow), not `==`.  Proportional text that
overshoots the margin by a fractional amount still triggers space
expansion; the line does not need to land exactly at the margin.

## Tab Stops

**Horizontal tabs**: HT stop table at `$FF00` (scratch RAM), up to 31
entries stored in ascending order and zero-terminated. `ESC D` (`$0EEA`)
reads stop values from the host, inserts them sorted, and sets `VV:BC`
bit 7 to enable HT. HT (`$0E7D`) scans the table from `$FF00`, converts
each stop to a dot position via `CALT ($009E)` using `EFBF` as the column
metric, and advances to the first stop past the current position. The
position is clamped to the right margin (`EE5C`).

**Vertical tabs**: VT stop tables at `$FF20+` in scratch RAM, with up to
8 channels (selected by `ESC /`, stored in `VV:30`). Each channel's table
address is `$FF20 + channel × 2`. `ESC B` (`$426C`) stores up to 15
stops per channel, sorted and zero-terminated, with the current line
spacing `EF8B` saved at the channel's table base. VT (`$1F69`) loads
`VV:BE` (current channel), halves `EF8B` for position computation, and
advances to the next VT stop or triggers FF if past page end.

## International Character Substitution

`ESC R n` (`$1454`) sets `VV:BB = n × 12` (country offset, max n=12).
The substitution table at `$689C` has 12 substitutable ASCII positions
(`#$@[\]^`{|}~`), followed by 13 country rows of 12 replacement bytes.
Country 0 (USA) is the identity mapping. The substitution function at
`$1464` scans the 12 base codes for a match, then indexes the replacement
table at `$689C + VV:BB + match_index` to get the national character.

## User-Defined Character Download

`ESC & 0 n1 n2 [d0 d1 d2 data...]` (`$113D`) downloads characters n1
through n2. If the 8K input buffer is not available (`VV:09` bit 2
clear), the data is consumed and discarded. Otherwise:

- `$13CC` clears `$8900-$8A7F` (640 bytes = 128 × 5-byte index entries)
  under `F002=$C0` (external RAM) and sets `EF18 = $8B80` (data pointer).
- For each character: d0 = left space, d1 = body width, d2 = right space.
  Column data is d1 × 3 bytes (normal) or d1 × 2 bytes (super/subscript,
  per `VV:23` bit 4). Data grows downward from `$8B80` via `EF18`.
- `VV:1B` (font cache) is updated to reflect the new user-defined set.

At render time, `VV:26` bit 7 clear selects user-defined characters:
source `DE=$8900`, `F002=$C0` (external RAM) instead of the CG ROM.

## Character Path

The primary data file is `data/lq500_3c_cg_access_path.tsv`.

### Classification and Style State

1. `400Bh` reads a byte via `CALT ($0080)` → `0A0Bh`.
2. `4038h` remaps the byte through the `6000h` identity table, classifies it
   by range, and loads style state into the working copies `VV21`/`VV22`/
   `VV1F` from one of three source sets:
   - Normal ($20-$AF): from `VV:A2`/`VV:CA`/`VV:CB` (persistent font state
     set by `ESC k`, `ESC x`, `ESC !`, etc.).
   - Extended ($B0-$EF): from `VV:2D`/`VV:2E`/`VV:2F`, preserving `VV22`
     bit 3 (italic) from the main state.
   - User-defined ($80-$9F when `VV20` bit 5 set): from
     `VV:CC`/`VV:CD`/`VV:CE`.
3. Printable bytes return via RETS, skipping the `JMP $6944` command
   dispatch and entering the printable handler at `4012h`.

### CG Bank Selection

After classification, `4012h` → `CALT ($0096)` → `1845h` → `1B19h` stores
the character code in `VV:A0` and selects the CG data source:

- `VV:26` bit 7 set → CG ROM path via `1774h`.
- `VV:26` bit 7 clear → user-defined character path: `F002=C0h`,
  `DE=$8900` (external RAM).

For CG ROM characters, `1774h` selects the F002 bank value from the
`VV:04`/`VV:05` font configuration state:

| VV:04 bits | F002 | VV:A7 init | Likely font |
| --- | --- | --- | --- |
| Bit 6 clear, bit 5 clear | `$80` | `$80` | Draft default |
| Bit 6 set | `$81` | `$80` | Draft variant |
| Bits 6+5 set, bit 3 clear | `$82` | `$00` | LQ alt |
| Bits 6+5 set, bit 3 set | `$80` | `$00` | LQ default |
| Bit 7 set | uses VV:05 | varies | Alternate font set |

After writing F002, `17F5h` reads the font header byte at `$8000`.
The low 6 bits encode the record count; the top 2 bits encode a size
flag. At `180Ch`-`1812h` the header flag also updates `VV:A7`: bit 6
is cleared (`ANIW $BF`), then set (`ORIW $40`) when the flag is `$40`.
On the stock 4C (header `$4D`, flag `$40`), `VV:A7 = $40` after the
header parse — not `$00` as initially written by `17EBh`.

The size flag selects directory record size via `EQI C,$40` at `1729h`:
when `$40`, the 12-byte `LXI` at `172Ch` is skipped and the 15-byte
`LXI` at `172Fh` executes. The stock 4C uses 15-byte directory records.

### Glyph Record Fetch

At `1B4Bh`, the firmware reads the glyph metrics record:

- Record address = base + char_index × 5 (or 6 when `VV:A7` bit 6 set).
  On the stock 4C (`VV:A7 = $40`), records are always 6 bytes.
- Byte 0 → `EF97` (start column offset as word, `H=0`).
- Byte 1 → `VV99` (active width / column count).
- Byte 2 → sign-extended value (advance adjustment).
- Bytes 3-4-5 → glyph data pointer (16-bit LE address + bank/flag byte).
  Bit 7 of byte 5 is **not** an address bit — the `DSLL`/`RLL` rotation
  discards it. Instead it is a **half-resolution flag**: the firmware
  preserves it in `H` at `175Ah` and tests it at `1BC9h` (`OFFI H,$80`).
  When set, `$1E23` halves `VV:99` to `(width+1)/2` stored columns and
  sets `VV:29` bit 7 so the rendering pipeline (`$4C16`) doubles each
  column on output. See "Half-Resolution Glyphs" below.
- `EF9B` and `EF95` are derived from these metrics plus mode flags.

### Super/Subscript Font Selection

When super/subscript is active (VV:23 bit 4), the font reconfig at
`$164B` sets VV:A6 bit 4 (`$166B`: `OFFIW VV:23,$10; ORI A,$10`).
The font lookup at `$154E` (`$156E`: `OFFIW VV:A6,$10`) then branches
into a search path that matches 4C font directory entries with config
bit 4 set.  These entries have `dim1 = $10` (16 vertical dots) and
store glyphs as 2 bytes per column — pre-drawn at 2/3 height.  This
is the primary mechanism for vertical size reduction in LQ
super/subscript: the glyph source pointer itself changes to a smaller
font, not just the metrics.

The `$4AA8` 2→3 byte column conversion (effect #1) handles vertical
alignment via zero-fill.  Its gate at `$1ABBh` checks VV:27 bit 2.
VV:27 bit 2 reflects the character classifier path, NOT the user's
LQ/Draft quality selection: for $20-$AF characters, VV:22 is loaded
from VV:2E (3rd font search result) at `$4124`, which has bit 2 clear
(cleared at `$14C9` during font reconfig, never re-added).  For $B0+
characters, VV:22 bit 2 is forced set at `$409D`.  Therefore `$4AA8`
fires for **both Draft and LQ** super/subscript characters in the
$20-$AF range.  See "Super/Subscript Detail" below.

### Secondary Metric Stage for LQ Super/Subscript

The secondary read at `1CF2` is the LQ super/subscript metric lookup.
It provides matching width and advance values for the smaller glyphs
selected by the font reconfig above:

- `1CED` reaches this path only when control reaches `1CF0` and then enters
  `1CF2` instead of continuing at `1C15`.
- `1CF2` saves current `F002` in `B`, then loads `F002=$4F`.
- `1CF6` uses `VV28` bit 2 (mask `$04`) for base select: set -> `$8600`,
  clear -> `$8000`.
- Address is `base + VV:A0 * 6`.
- `byte0` is read and ignored by traced code.
- `byte1` is loaded into `EF99` (width/count).
- `byte2` is loaded into `EF9B` (advance).
- The fetch does this as `MOV D,$00 ; MOV E,A ; SDED EF99/EF9B`, so this
  secondary advance is effectively zero-extended before arithmetic.
- `F002` is restored to `B`.

`byte1` and `byte2` are treated as metrics here because the primary fetch
already uses the same records that way: `1B4Bh` maps byte1 → `VV99` and the
signed byte2 path into advance state; `2159h` then uses `EF9B` when moving
to the next cell.

The secondary metrics read complements the font selection and column
conversion: the font reconfig selects a 2-byte-per-column glyph set,
`$4AA8` converts to 3-byte columns with vertical alignment (upper or
lower 16 pins), and `$1CF2` provides matching narrower width/advance
values.  There is no traced operation at `$1CF2` that changes `EF97`
or applies a vertical baseline offset — vertical positioning is
handled entirely by `$4AA8`'s zero-fill placement.

The traced render path uses these values directly for placement:

- In `1E7F`, `EA = EE66 + 3 × EF97` gives destination buffer start
  (3-byte columns for LQ).
- `1E9A..1EA7` writes `VV99` columns, ORing 3 bytes per column.
- `1EA9..1EB8` sets `EE66 = EE66 + 3 × EF9B` for the next character.

No traced branch between this stage and the normal LQ render path (`4C16h`
and its callees) applies a super/subscript-driven vertical baseline shift or
other raster-y placement transform. Any later raster-style change comes from
other style effects that are independently gated.

Any subsequent metric-effect transformer (double-wide, italic, etc.) can still
change these numbers later, but the secondary metrics values are the
starting LQ super/subscript override for `VV99` and `EF9B`.

The extracted secondary files show 129 entries per table (`base_0000` and
`base_0600`), so they are not full 256-entry tables. In practice this means
super/subscript behavior is driven by an override-style secondary set rather
than a full remap, and width/advance output must follow the actual ROM bytes
for unlisted characters.

This path has no traced baseline or vertical-offset shift.  The
vertical size reduction comes from the font reconfig selecting 16-dot
glyphs (see "Super/Subscript Font Selection" above); this secondary
read provides the matching horizontal metrics.
Example (LQ):

- `'0'` (`0x30`) width/advance -> normal table (`$8000` base): width `0x13`, adv `0x02`;
  secondary table (`$8600`/`$8000` path): width `0x0D`, adv `0x01`.
- `'G'` (`0x47`) width/advance -> normal table (`$8000` base): width `0x06`, adv `0x09`;
  super/subscript table (`$8600` base): width `0x04`, adv `0x03`.
- No explicit secondary rows are present for `'g'` (`0x67`) or `'h'` (`0x68`) in
  the extracted TSV (`base_0000`/`base_0600`), so vertical-size differences for
  those characters are not documented by the traced secondary table.

### Second CG Read

After the initial metrics, when `VV27` bit 2 is set (LQ mode), the code reaches
`1CEDh` → `1CF2h`, which performs a second CG read:

- Sets `F002=$4F` (a fixed bank, distinct from the font-selected bank).
- Reads a 6-byte record at (`$8000` or `$8600`) + `VV:A0` × 6.
- `VV28` bit 2 selects the base: `$8600` when set, `$8000` when clear.
- Bytes 1 and 2 are loaded into `EF99`/`EF9B`.
- Restores `F002` and returns.

### International Character Substitution

When `VV21` bit 7 is set (extended-range characters at `$B0-$EF`), the
classifier calls `1464h`, which indexes the substitution table at
`689Ch-6943h`. The active country is set by `ESC R n`, which stores a row
offset into the table. This replaces specific character codes before they
reach the CG fetch path.

### 4C CG ROM Directory Structure

The 4C CG ROM is self-describing. Each banked page begins with a font
directory that the firmware scans to find the right font/pitch combination:

- **Header byte** at `$8000`: top 2 bits = record size flag (`$40` → 12
  bytes, else → 15 bytes), low 6 bits = number of directory records.
- **Directory records**: each starts with a font family ID byte (matched
  against `VV:A5` = typestyle from `ESC k`: 0=Roman, 1=Sans Serif) and a
  config byte (low 7 bits matched against `VV:A6` = compiled pitch/quality
  flags). The remaining bytes contain glyph data pointers and character
  range metadata.

At startup (`04A4h-04B7h`), the firmware probes F002 banks `$80`, `$00`,
and `$40` with multiple sub-page selectors. For each valid directory found,
it builds a capability bitmap in `VV:04`/`VV:05`:

| Bit | Meaning |
| --- | --- |
| 7 | Use alternate register (VV:04 → VV:05 fallback) |
| 6 | F002=base, sub-page=`$00` valid |
| 5 | F002=base+1, sub-page=`$00` valid |
| 4 | F002=base, sub-page=`$80` valid |
| 3 | F002=base+2 valid |

`VV:04` records the primary bank range; `VV:05` records the alternate
range. The complete bank mapping from `16A2h`/`16D0h`:

| Source | VV:0x bits | F002 | Chip |
| --- | --- | --- | --- |
| VV:04 | 6,5 clear | `$80` | External CG (CN3 font module) |
| VV:04 | 6 set, 5 clear | `$81` | External CG |
| VV:04 | 6+5 set, 3 clear | `$80` | External CG |
| VV:04 | 6+5 set, 3 set | `$82` | External CG |
| VV:05 | 6,5 clear | `$00` | 4MCG (5C) |
| VV:05 | 6 set, 5 clear | `$01` | 4MCG |
| VV:05 | 6+5 set, 3 clear | `$00` | 4MCG |
| VV:05 | 6+5 set, 3 set | `$02` | 4MCG |

These scan **optional** font sources (external module and 4MCG). The
resident 4C ROM (1MCG) at `F002=$40-$4F` is always available. The
secondary metrics read at `1CF2h` uses `F002=$4F` (4C page 15,
offset `$1E000`). The primary font directory at `F002=$40` (4C page 0,
offset `$00000`) has header `$4D`.

### Gate-Array Chip Select

Service-manual Figures 2-7, 2-8, and Section 2.2.4 define the `$8000`
window chip select from F002 BANK bits 7:6:

| BANK 7:6 | F002 range | Chip | Size |
| --- | --- | --- | --- |
| 00 | `$00-$3F` | 4MCG (5C) | 512K |
| 01 | `$40-$7F` | 1MCG (4C) | 128K |
| 10 | `$80-$BF` | External CG (CN3) | varies |
| 11 | `$C0-$FF` | PSRAM (2C) | 32K |

For the 4C ROM: BANK bits 3:0 provide `A16:A13`, CPU bus provides
`A12:A0`. ROM offset = `(F002 & $0F) × $2000`. `1774h` mirrors the same
VV:04/VV:05 logic for runtime bank selection.

### Per-Pitch Font Data

The CG ROM contains separate glyph bitmaps for each pitch/quality
combination at native resolution. The `164Bh` font configuration builder
encodes pitch and quality into `VV:A6` (bit 2 = Draft when clear, plus
pitch/condensed/italic bits), and font commands trigger `14C6h` (CALT
`$0092`) to rescan the font directory via `1677h`/`154Eh`. The scan matches
(`VV:A5`, `VV:A6`) against the directory records to find the right glyph
data for the current font family + pitch + quality.

### Print Effect Pipeline

The `43DDh-4C36h` region is a **sequential print-effect pipeline**, not a
single expansion engine. The dispatch at `1ABFh-1B18h` conditionally calls
each effect function based on `VV:27`/`VV:28`/`VV:29`/`VV:2A` flags.
Multiple effects can be applied in sequence to the same glyph data.

| Order | Condition | Address | Effect | Data operation |
| --- | --- | --- | --- | --- |
| 1 | VV:28.4 set | `$4AA8` | Super/subscript (2→3 column conversion) | Converts 2-byte source columns to 3-byte with zero-fill. `$1DFE` sets HL = source (from EE88), EA = work buffer. VV:28.3 selects alignment: SET (superscript) → [data, data, 0] upper 16 pins; CLEAR (subscript) → [0, data, data] lower 16 pins. Fires for **both Draft and LQ** super/subscript characters in the $20-$AF range. The gate at `$1ABBh` checks VV:27 bit 2, which reflects the classifier path (clear for $20-$AF via `$4124`, set for $B0+ via `$409D`), not the user's Draft/LQ quality selection. |
| 2 | VV:27.7 set | `$49C5` | Condensed-Draft mode | Clears work buffer, then merges pairs of source columns via OR and writes with adjacent-dot restriction (XRI/ANA against previous output). Halves width/start/advance. Half-res path clears VV:29.7 and applies restriction only (no merge, no metrics change). |
| 3 | VV:29.4 set | `$47CB` | Emphasized | Copies glyph to work buffer with 3 blank-column padding, then ORs original data at +1 column offset (bold shift). Half-res path uses +2 column offset with adjacent-dot restriction via `$1F50`. Width += 1 (or 2 for half-res), advance -= same. |
| 4 | VV:29.7 set | `$4C16` | Half-res expansion | Clears VV:29.7, calls `$1E52` to double width/start/advance back to full values, then copies each 3-byte column followed by 3 zero bytes — inserting blank columns to restore the full-width sparse dot pattern |
| 5 | VV:29 bits 0+1 set | `$4830` | Double-wide | Calls `$1E52` to double metrics, clears dest buffer, then duplicates columns. Half-res: literal duplication via `STAX (DE+)`+`STAX (DE+$02)`. Normal LQ: ORs adjacent source columns (`LDAX (HL+$03); ORAX (HL+)`), which is a no-op for interleaved blanks → effective duplication. Super/subscript path at `$4879` applies adjacent-dot restriction while doubling. |
| 6 | VV:27 bits 4+3 set | `$4ACE` | Italic shear | Splits each byte into 4-pin nibbles, routes low nibble to current column and high nibble to next column (+3 bytes). Successive bytes within a column write to progressively earlier destination columns (DCX DE × 5 per byte), creating a rightward shear from bottom to top. Normal: 5-column spread across 24 pins (~6° slant), width += 5. Double-wide: 2-bit pairs across 4 columns, 11-column spread, width += 11. |
| 7 | VV:2A bits 5+6 = 11 | `$44C4` | Outline+shadow | Combines outline and shadow: `$457E` smear, second smear, shift-left-1 + shift-right-1 at +1 col (outline border), shift-right-1 at +3 cols + shift-right-2 at +5 cols (shadow), single `$463F` XOR at +1 col (hollow). `$4664`(B=5) → width += 10. Mutually exclusive with 8/9. ESC q 3. |
| 8 | VV:2A.6 set | `$43DD` | Outline | `$457E` smear, second smear, shift-left-1 (`$45B1`) + shift-right-1 (`$45F8`) at +1 col, `$463F` XOR at +1 col (VV:D1=0, pin 1+24 masked). `$4664`(B=1) → width += 2. See "Outline Detail." ESC q 1. |
| 9 | VV:2A.5 set | `$444A` | Shadow | `$457E` smear, copy to buffer2, shift-right-1 at +1/+3 cols + shift-right-2 at +5 cols, `$463F` XOR (VV:D1=1). `$4664`(B=5) → width += 10. See "Shadow Detail." ESC q 2. |
| 10 | VV:2A.7 set | `$4900` | Double-height | If double-wide active, calls `$47CB` (emphasized) first. Then `$1DFE` for work buffer, selects one of four vertical slices via VV:89 bits 0-2, expands each 4-bit nibble → 8 bits via `$49AD` (each dot → 2-dot pair). VV:89 selects which 12-pin slice of the 24-pin source fills the full 24-pin output. |

VV:27-VV:2A correspond to VV:22-VV:25 via the BLOCK copy at `185Ch`.
Confirmed VV bit assignments from ESC ! Master Select (`0F42h`) and
individual command handlers, verified against `lq500_u1.pdf` page 6-4:

| VV register | Bit | ESC/P effect | Set by |
| --- | --- | --- | --- |
| VV:22 | 2 | Classifier path flag: set at `$409D` for $B0+/$F0+ characters, clear for $20-$AF (from VV:2E). Copied to VV:27 bit 2 to gate `$4AA8`. | `$4038` classifier |
| VV:22 | 3 | Not-italic (per classifier, inverse of VV:24.3) | `4038h` classifier |
| VV:22 | 4 | Italic fallback (italic requested but not in font) | `154Eh` font scan |
| VV:22 | 5 | Condensed | SI/DC2, ESC ! bit 2 |
| VV:22 | 7 | Condensed-Draft mode (condensed AND Draft AND not proportional) | `14C6h` reconfig |
| VV:23 | 0 | Underline | ESC -, ESC ! bit 7 |
| VV:23 | 1 | Elite (12 cpi) | ESC M/P, ESC ! bit 0 |
| VV:23 | 3 | Super/subscript vertical align (`1` = superscript, `0` = subscript; meaningful when active) | ESC S 0/1 |
| VV:23 | 4 | Super/subscript active | ESC S 0/1 set, ESC T clear |
| VV:23 | 5 | Proportional | ESC p, ESC ! bit 1 |
| VV:23 | 7 | 15 cpi | ESC g, cleared by ESC P/M |
| VV:24 | 0 | Double-wide one-line (SO, DC4 cancels) | SO/DC4 |
| VV:24 | 0+1 | Double-wide persistent | ESC W, ESC ! bit 5 |
| VV:24 | 3 | Italic | ESC 4/5, ESC ! bit 6 |
| VV:24 | 4 | Emphasized | ESC E/F, ESC ! bit 3 |
| VV:24 | 6 | Double-strike | ESC G/H, ESC ! bit 4 |
| VV:25 | 4 | Extended character ($F0+ range excl $F4/$F5) | `4038h` classifier |
| VV:25 | 5 | Shadow | ESC q 2/3, `$43C3` |
| VV:25 | 6 | Outline | ESC q 1/3, `$43C3` |
| VV:25 | 7 | Double-height | ESC w |

Note: ESC G/H (double-strike) do not trigger font reconfig via CALT
($0092). All other style commands do.

The CG bank set by `1774h` remains active throughout — no F002 writes occur
during the effect chain. Two CG column formats are confirmed:

- **1-byte per column** (`43F4h`): one CG byte ORed into all 3 destination
  planes (bold/overlay effect).
- **2-byte per column** (`4ABAh`/`4AC4h`): two CG bytes provide 16 vertical
  dots, zero-padded to 3 bytes. `VV28` bit 3 selects vertical alignment.

The render entry at `281Dh` calls `1A8Ah` (CG fetch + effect pipeline),
then `2159h` (position/metrics update). When effects fire, the processed
glyph data ends up in the work buffer at `$E983` or `$EBA3` and `EE88`
is updated to point there. When no effects fire (basic LQ with no style
attributes), `EE88` still points into the CG ROM window.

### Normal LQ Render Path (No Effects)

For a plain LQ character ($20-$AF) with no style attributes, VV:27
bit 2 is clear (from the `$4124` classifier path), so the pre-pipeline
flag checks at `1A8Dh`-`1AB8h` do not take the `$1AAB` shortcut via
`$1AA4`.  However, since VV:28 bit 4 (super/subscript) is also clear,
the `$1ABBh` gate at `$1ABCh` (`OFFIW VV:28,$10`) skips `$4AA8`.
The entire effect dispatch at `1ABFh`-`1B18h` is then a no-op: every
remaining gate condition is false, and the pipeline returns without
calling any effect function.

Note: for $B0+ characters, VV:27 bit 2 IS set (forced at `$409D`),
so the `$1AABh` shortcut at `$1AA4h` fires and the effect pipeline
is skipped entirely.

The per-character render loop at `$2948` then calls `$1E7F`, which reads
3 bytes per column directly from the CG source (pointed to by `EE88`)
and ORs them into the image buffer:

```
1E7F: EA = EE66 + 3 × EF97           ; dest = buffer position + 3 × start
1E8E: DE = EE88                       ; source = CG glyph data
1E9A-1EA7: for VV:99 columns:
               LDAX (DE+) → ORAX (HL) → STAX (HL+)   ; byte 0
               LDAX (DE+) → ORAX (HL) → STAX (HL+)   ; byte 1
               LDAX (DE+) → ORAX (HL) → STAX (HL+)   ; byte 2
1EA9: EA = position + 3 × EF9B       ; advance by 3 × advance value
1EB8: SHLD EE66                       ; update buffer position
```

There is **no column duplication or vertical interleave** for normal LQ
characters. Each CG column (3 bytes = 24 vertical dots) maps 1:1 to one
image buffer column. The OR operation allows overlapping characters
(strike-over, accents) to merge.

### 360 DPI Two-Pass Interleave

Full-resolution LQ glyphs are authored at 360 DPI horizontal with the
two-pass interleave baked into the column data. Horizontal strokes
have dots in every other column — for example, a Roman 'I' serif
appears as `#.#.#.#.#.#.#.#.#.#.#` where `.` is a blank (`000000`)
column. Vertical strokes are two dots wide at the same alternating
spacing: `#.#`.

The image buffer stores one 3-byte column per 1/360-inch dot position.
The multi-pass carriage mechanism (VV:6F bit 1 set, EF79 = EF64/2)
fires the image buffer in two passes:

- **Pass 1**: fires all columns at their natural positions (every
  column, including blanks, at 1/360-inch spacing).
- **Pass 2**: fires the same columns offset by one dot position
  (1/360 inch).

The two passes together fill the gaps between the alternating dots,
producing solid strokes at 180 DPI effective density. A 10 CPI
character at 360 DPI occupies 36 columns (start + width + advance =
36 for Roman LQ `M`).

### Half-Resolution Glyphs

Glyph pointer byte 5 bit 7 is a half-resolution flag (not an address
bit). When set, the firmware at `1BC9h` (`OFFI H,$80`) calls `$1E23`:

1. Sets `VV:29` bit 7 (half-res render flag).
2. Halves `VV:99` (active width) → `(width + 1) / 2` stored columns.
3. Halves `EF97` (start) and `EF95` (total advance) via `DSLR`.
4. Recomputes `EF9B`.

Half-resolution glyphs store their column data at 180 DPI — every
column has data, with adjacent dots forming solid strokes. The ROM
contains `(width+1)/2` columns. During the effect pipeline, `VV:29`
bit 7 triggers effect #4 (`$4C16`), which calls `$1E52` to double
the metrics back to full 360 DPI values, then copies each 3-byte
source column followed by 3 zero bytes — spreading the 180 DPI data
into the 360 DPI two-pass interleave format.

Example: Roman `H` is stored as 15 packed columns with solid strokes
(`##`). After `$4C16` expansion to 30 columns, the strokes become
`#.#` — the same alternating pattern as full-resolution glyphs.
Both produce identical printed output after two-pass firing.

Characters with this flag include punctuation that is identical across
font families (`+`, `−`, `.`, `:`, `[`, `]`, `^`, `_`, `|`) and some
letterforms with simple symmetric shapes (`H`, `I`, `L`, `T` in Sans
Serif; `H`, `T`, `l` in Roman).

### Underline Rendering

Underline (`VV:28` bit 0, from `VV:23` bit 0 / ESC `-` / ESC `!`
bit 7) is **not** part of the effect pipeline at `$1ABF`-`$1B18`.
It is rendered separately at `$1EBC`-`$1F22`, after the `$1E7F`
column write loop completes.

At `$1EBC`: `ONIW VV:28,$01` — if underline active, skip the `RET`
and fall through into the underline renderer. The underline is also
invoked from `$2970` (`CALL $1ECC`) in the per-character render loop
for characters that bypass the normal `$1E7F` glyph write.

The underline renderer at `$1ECC`-`$1F22`:

1. Sets `VV:B2 = $01` (underline dot mask = bit 0 of the target column byte).
2. The renderer exits without doing anything if `($2A low nibble & $88 low nibble)` is zero:
   this is the `ONA A,C` gate at `$1ED8`.
3. It also exits if either `$88 bit 5` is set or either `$89 bit 0` or
   `$89 bit 3` is set (`$1EE3` / `$1EE7`).
4. Otherwise, the default remains `VV:B2 = $01`. It is changed to
   `VV:B2 = $04` only when all of these are true:
   - `$89 bit 2` is set,
   - `$89 bit 4` is set,
   - `$2A bit 7` is clear,
   - and the earlier `$88` low-nibble/`$2A` low-nibble overlap gate passed.
5. Reads the **previous** column's byte 2 (`DCX DE; LDAX (DE+)` at
   `$1F06`) to determine the alternation phase — maintaining
   continuity with any preceding underlined character.
6. Walks from old `EE66` to new `EE66` (the full character cell:
   start + width + advance), modifying byte 2 of each 3-byte column:
   - **Even columns**: `ORA A,C` — sets the underline bit.
   - **Odd columns**: `ANA A,C` (with `C = ~mask`) — clears it.
   - `XRI C,$FF` toggles the mask each iteration.

The underline dots follow the 360 DPI two-pass interleave: set in
every other column, matching the glyph data pattern. The two carriage
passes fill the gaps to produce a continuous line.

Using the confirmed pin mapping (`D7..D0 -> H17..H24` for the third
byte in each 3-byte column), `VV:B2 = $01` maps to `H24` and
`VV:B2 = $04` maps to `H22`.

**Written into the image buffer** directly, ORed alongside glyph
column data. The underline is not a separate mechanism — it shares
the same buffer and two-pass print path as the character data.

## Glyph Transform Families

The `43DDh-4C36h` region looks like the resident bitmap expansion engine. It
uses `VV99` as an active width/count and `VV:CF` as a destination stride.
`EE88`/`EE8A` are source/work pointers; `EF95`, `EF97`, and `EF9B` are glyph
metric or edge pointers.

Notable helpers:

| Address | Working label | Evidence |
| --- | --- | --- |
| `45B1h` | `or_shifted_columns_left_into_work_buffer` | Shifts source data left (upward) and ORs into destination. Mirror of `$45F8`. |
| `45F8h` | `shift_right_and_or_into_dest` | DSLR on 16-bit EA pairs shifts pin data downward by VV:D0 bits with cross-byte carry. Last byte carry-sticks via `SK CY; ORI A,$01`. Processes VV:99 columns × VV:CF bytes. |
| `463Fh` | `xor_mask_columns_into_dest` | XORs source into dest per column. First byte: optionally masks pin 1 via `ANI $7F` (gated by VV:D1 bit 0). Last byte: masks pin 24 via `ANI $FE`. Uses DCR skip-on-underflow to count stride bytes. |
| `457Eh` | `smear_and_expand_horizontal` | Calls `$1DDF`, then ORs each source byte into 3 stride-separated dest positions (3-column horizontal thickening). Calls `$4664` with B=1 → width += 2. Used by shadow, outline, and outline+shadow. |
| `1DDFh` | `swap_source_and_allocate_work_buffer` | EE8A = EE88 (save source), EE88 = new zeroed 540-byte buffer. Returns HL = old source, DE = new buffer. |
| `4664h` | `adjust_glyph_width_and_right_edge_metrics` | `VV:99 += 2×B` (two `ADD A,B` at `$4669`/`$466B`). Also decrements `EF97` (start offset) by up to B-1, and adjusts `EF9B` (advance) to keep total cell width constant. |
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
| Printhead | `docs/lq500_3c_printhead.md` | Head-interface registers, three-byte latch burst output, HPW timing, and E05A02LA/CN5/CN6/Figure 5-3 wire placement. |

Keep these domains separate. Print pin firing is a head-output workstream, not
part of carriage movement, even though normal printing couples head timing to
carriage motion.

Current ROM anchors:

- Paper feed command motion enters through `ESC J`/`ESC j`, stores a signed
  distance through the vertical-advance path, sets `VV62=1`, and reaches the
  FE1 paper-feed ISR branch that calls `093Eh` for counted `PB & 18h` phase
  updates. The `540Dh`/`PB mask 04h` path controls the paper-feed drive/hold
  window around those counted steps.
- Carriage movement uses `0908h` as the `PC7`/`TM` phase-step pulse. Startup
  home seek is the `51F7h-5253h` path; runtime movement uses the queued
  scheduler, `72B3h` TM1 sequence records, `7005h` timing/output records, and
  F003 control helpers. One `0908h` pulse is one gate-array phase switch:
  `1/120` inch in 2-2 excitation and `1/240` inch in 1-2 excitation.
- Printhead output is anchored at the E05A02LA `F004h/F005h` interface:
  `5681h` resets the latch counter with `F004=20h`, `08D0h` writes
  direction-dependent `F004=40h`/`C0h`, `0978h` emits exactly three bytes
  through alternate-register `BC=F005h`, and `06D7h-06E9h` updates the
  `EE3Ah` HPW timer addend from the `CR0` voltage-compensation table.

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
  using `4EEAh` panel-action reads and `4FB1h` ADC offset refreshes. VR1 is
  the Draft `n/240` inch correction; VR2 is the LQ `n/720` inch correction.
- `79D4h`, `79F6h`, and `7A00h` are local adjustment display helpers for
  marker output, service strings, and value formatting.
- `7A18h-7A52h` holds the adjustment title, `VR1`/`VR2` labels, plus/minus
  markers, and the out-of-range string.
- `7AB2h-7B51h` maintains shared style/typeface selection state used by service
  and startup flows before `7B52h` reflects the selection on PA/PB outputs.

## State Interactions for Emulation

This section documents how printer attributes interact at parse time and
render time, derived from the firmware trace.  The emulator must reproduce
these rules to match the real printer's output.

### ESC ! Master Select Override

ESC ! (`$0F42`) is a complete override for the attributes it controls.
It first clears all affected bits (ANIW), then sets from the parameter:

| Parameter bit | Clears | Sets | VV register |
| --- | --- | --- | --- |
| 7 (underline) | VV:23.0 | VV:23.0 | VV:23 |
| 6 (italic) | VV:24.3 | VV:24.3 | VV:24 |
| 5 (double-wide) | VV:24.0+1 | VV:24.0+1 | VV:24 |
| 4 (double-strike) | VV:24.6 | VV:24.6 | VV:24 |
| 3 (emphasized) | VV:24.4 | VV:24.4 | VV:24 |
| 2 (condensed) | VV:22.5 | VV:22.5 | VV:22 |
| 1 (proportional) | VV:23.5 | VV:23.5 | VV:23 |
| 0 (elite) | VV:23.1 | VV:23.1 | VV:23 |

ESC ! also always clears VV:23 bit 7 (15 cpi).  It does NOT affect
super/subscript (VV:23 bits 3-4) or double-height (VV:25 bit 7).
After setting bits, it calls CALT ($0092) to trigger font reconfig.

Individual attribute commands (ESC E/F, ESC G/H, etc.) set or clear
their single bit without touching other flags, then also trigger
font reconfig.

### Pitch Precedence

The VV:A6 config byte builder (`$164B`) determines which CG font to
request.  When multiple pitch modes are set simultaneously, the
priority order is:

1. **Proportional** (VV:23.5): sets VV:A6 bits 1+0=$02, skips all
   other pitch checks
2. **15 cpi** (VV:23.7): sets VV:A6 bits 1+0=$03 (maps to the
   elite+proportional font slot)
3. **Elite / 12 cpi** (VV:23.1): sets VV:A6 bit 0=$01
4. **10 cpi** (default): VV:A6 bits 1:0 = $00

Super/subscript active (VV:23 bit 4 via `$166B`) and italic (VV:24.3
via `$1666`) add their bits independently (VV:A6 bit 4 and bit 6).
LQ quality (VV:87 bit 2 via `$1643`) sets VV:A6 bit 2.

Note: VV:A6 bit 4 is the super/subscript font selection bit.  The 4C
font directory entries with config bit 4 set are labelled "Condensed"
in the CG ROM's internal naming, but the firmware maps super/subscript
active (VV:23 bit 4) — not SI/DC2 condensed (VV:22 bit 5) — to this
bit.  These directory entries have `dim1 = $10` (16 vertical dots)
instead of the normal `$18` (24), and their glyph data uses **2 bytes
per column** (16 vertical dots) rather than 3 (verified by glyph
pointer spacing in the ROM).  This applies to both Draft and LQ
condensed fonts — they are the super/subscript glyph sets.

### Condensed-Draft Composite Flag

The reconfig at `$14C6` computes a composite "condensed-Draft" flag
(VV:22 bit 7) that gates effect function #2 (`$49C5`).  It is set only
when ALL of:

- Condensed is active (VV:22 bit 5 set)
- Proportional is NOT active (VV:23 bit 5 clear)
- 15 cpi is NOT active (VV:23 bit 7 clear)
- VV:23 bit 2 is clear (LQ quality context)

When the condensed-Draft flag fires, the effect function halves the
column count by merging adjacent columns, producing the characteristic
compressed output.

### Font Fallback Chain

The fallback scan at `$154E` tries progressively less specific font
matches when the CG directory scan at `$1677` fails:

1. **Exact match**: current VV:A6 (pitch + quality + italic + condensed)
2. **Drop italic**: if VV:A6 bit 6 was set, clear it and add condensed,
   retry
3. **Try alternate pitch** (`$156A`): with condensed cleared, cycles
   through pitch alternatives:
   - From 10 cpi ($00): try elite ($01), then proportional ($02)
   - From proportional ($02): try 10 cpi ($00), then elite ($01)
   - From elite ($01): try 10 cpi ($00), then proportional ($02)
   Similar fallbacks with condensed set at `$15ED`
4. **Try Roman family**: sets VV:A5=$FF and rescans from step 1
5. **Fail**: jumps to `$53DF` (no output for this character)

### International Character Substitution

The substitution at `$1464` is always active, even for USA (country 0).
For the 12 substitutable positions (`#$@[\]^`{|}~`), the firmware
indexes into `$689C + country × 12` to get the CG character code.
Country 0 (USA) reads the base codes themselves, producing an identity
mapping.  Other countries map to non-ASCII CG positions ($80+) where
the national character glyphs are stored.

The emulator must apply this table for ALL countries, including USA,
because the replacement codes ARE the CG ROM character codes.

### Render-Time Effect Interactions

The print effect pipeline at `$1ABF-$1B18` applies effects sequentially.
Each effect operates on the output of the previous one.  Key
interactions:

- **Super/subscript + anything** (Draft only): effect #1 runs first,
  converting 2-byte CG columns to 3-byte format.  All subsequent
  effects see 3-byte columns regardless.  For LQ mode, effect #1 is
  skipped — LQ CG glyphs are already 3-byte columns.
- **Condensed-Draft + emphasized**: both can fire.  Condensed halves
  the column count first, then emphasized adds bold offset columns
  to the condensed result.
- **Double-wide + condensed**: condensed halves, then double-wide
  doubles.  Net effect: original width but with condensed glyph shape.
- **Italic shear**: runs after emphasized and double-wide, so the
  shear applies to the already-widened data.
- **Half-res expansion**: (formerly "double-strike prep") see
  "Half-Resolution Glyphs" above.
- **Double-height**: runs last (effect #10).  Each nibble expands to
  a byte, doubling vertical resolution.

Effects 7-9 are gated by `VV:2A` bits 5+6 (from `VV:25` bits 5+6),
set by ESC q n at `$43C3`:

- n=0: `ANIW VV:25,$9F` — clear both bits (normal).
- n=1: `ORIW VV:25,$40` — set bit 6 (outline, effect 8).
- n=2: `ORIW VV:25,$20` — set bit 5 (shadow, effect 9).
- n=3: `ORIW VV:25,$60` — set both bits (outline+shadow, effect 7).

Values n ≥ 4 are rejected (`LTI A,$04; RET`).

### Shadow Detail (`$444A`)

`$444A` (ESC q 2, `VV:2A` bit 5) creates a hollow character with a
drop shadow extending to the lower-right.

#### Shared Helpers

The shadow, outline, and outline+shadow effects share these helpers:

**`$1DDF`** — buffer swap and allocate:
1. `EE8A = EE88` (save current source as work pointer).
2. Allocates a new buffer via `$1DFE` → `EE88` = new zeroed buffer.
3. Clears 540 bytes (`$049C`).
4. Returns HL = EE8A (old source), DE = EE88 (new buffer).

**`$457E`** — horizontal smear (called from all three effects):
1. Calls `$1DDF` to set up buffers.
2. For each source byte: ORs it into dest at 3 stride-separated
   positions (pos, pos+stride, pos+2×stride). This replicates each
   column into 3 consecutive dest columns with OR overlap, creating
   a horizontally thickened version of the glyph.
3. Calls `$4664` with B=1 → width += 1.

**`$45F8`** — vertical shift-right and OR:
1. `VV:D0` = shift amount (A-1 on entry).
2. For each column (B = VV:99 iterations), for each byte within
   the column (C = VV:CF stride):
   - Loads source byte pair into 16-bit EA (cross-byte carry).
   - DSLR × VV:D0 shifts EA right (pin data moves downward).
   - ORs EAL into dest byte.
3. Last byte: `SK CY; ORI A,$01` — carry-in from DSLR sets bit 0,
   preventing dots from vanishing past pin 24 (carry-stick).

**`$463F`** — XOR/mask to hollow interior:
1. `VV:D1` = A on entry (controls bit 7 masking).
2. For each column (B = VV:99), for each byte (C = VV:CF stride):
   - First byte: `ONIW VV:D1,$01` → if VV:D1 bit 0 set, skip
     `ANI A,$7F` (include pin 1 in XOR). Otherwise mask pin 1 out.
   - Middle bytes: plain XOR with dest.
   - Last byte: `ANI A,$FE` (exclude pin 24 from XOR).
   - XOR source into dest: `XRAX (DE); STAX (DE+)`.
3. DCR is a **skip-on-underflow** instruction on the uPD7810: it
   skips the next instruction when the register was 0 before
   decrement (wraps to 255). Used here to count through stride bytes.

#### Shadow Sequence

1. `$46C4`: sets `VV:CF=3`. If double-height active (`VV:2A` bit 7),
   also performs double-height expansion and sets `VV:CF=4`.

2. `$457E`: calls `$1DDF` (EE8A = source, EE88 = buffer1), then
   smears source into buffer1 (3-column OR thickening). Calls
   `$4664` with B=1 → width += 2 (matching the smear's 2-column
   extension).

3. `$1DDF` again at `$4455`: EE8A = buffer1 (smeared), EE88 =
   buffer2 (zeroed). Returns HL = buffer1, DE = buffer2.

4. `$4458`-`$4466`: copies buffer1 (smeared) to buffer2.

5. Three `$45F8` calls — shift buffer1 (EE8A) downward and OR into
   buffer2 (EE88) at column offsets:
   - `$4477`: offset +1 column, shift down 1 pin.
   - `$448E`: offset +3 columns, shift down 1 pin.
   - `$44A9`: offset +5 columns, shift down 2 pins.

6. `$463F` at `$44B6`: XOR buffer1 (smeared) into buffer2 column by
   column (VV:D1=1 → all bits of byte 0 included, byte 2 bit 0
   excluded). This removes the smeared original from the composite,
   hollowing the character body and leaving only the shadow portions
   visible outside the original footprint.

7. `$4664` at `$44BB`: width += 10 (B=5, `$4664` adds 2×B).

The result is the character rendered as a hollow outline with a solid
shadow stepping rightward and downward in 3 stages. The shadow
becomes visible where it extends beyond the character body.

### Outline Detail (`$43DD`)

`$43DD` (ESC q 1, `VV:2A` bit 6) creates a hollow double-border
outline of the character.

1. `$46C4`: sets `VV:CF=3` (or 4 for double-height).

2. `$457E` at `$43E5`: smear + `$4664`(B=1) → width += 2.
   EE8A = source, EE88 = buffer1 (smeared).

3. `$1DDF` at `$43E8`: EE8A = buffer1, EE88 = buffer2 (zeroed).

4. `$43EB`-`$4414`: smear buffer1 into buffer2 (same 3-column OR
   loop as `$457E` but no `$4664` call — width stays the same).
   This creates a double-smeared version: each original column is
   spread across ~5 dest columns via two cascaded 3-column ORs.

5. At dest offset +1 column (DE = buffer2 + stride):
   - `$4427`: `CALL $45B1` — shift buffer1 LEFT (upward) 1 pin,
     OR into dest at +1 column.
   - `$4432`: `CALL $45F8` — shift buffer1 RIGHT (downward) 1 pin,
     OR into dest at +1 column.
   - `$443C`: `CALL $463F` — XOR buffer1 into dest at +1 column
     (VV:D1=0 → pin 1 masked via `ANI $7F`, pin 24 masked via
     `ANI $FE`).

6. `$4664` at `$4441`: width += 2 (B=1).

The left+right shifts expand the character vertically by 1 pin in
each direction at column offset +1. The XOR then removes the filled
interior from the overlap region, leaving a double-bordered outline.
The pin 1/24 masking in `$463F` prevents the XOR from creating
artifacts at the top and bottom edges.

### Outline+Shadow Detail (`$44C4`)

`$44C4` (ESC q 3, `VV:2A` bits 5+6 both set) is a **separate code
path**, not effects #8 and #9 run in sequence. The dispatch at
`$1AFE` tests both bits together and routes to `$44C4`, which
combines the outline and shadow operations with shared setup and a
single XOR pass.

1. `$46C4` at `$44C9`: sets `VV:CF=3` (or 4 for double-height).

2. `$457E` at `$44CC`: smear + `$4664`(B=1) → width += 2.
   EE8A = source, EE88 = buffer1 (smeared).

3. `$1DDF` at `$44CF`: EE8A = buffer1, EE88 = buffer2 (zeroed).

4. `$44D2`-`$44FB`: smear buffer1 into buffer2 (inline 3-column
   OR loop, no width increment).

5. Outline shifts at +1 column:
   - `$450E`: `$45B1` shift LEFT 1, OR.
   - `$4518`: `$45F8` shift RIGHT 1, OR.

6. Shadow shifts:
   - `$452B`: `$45F8` shift RIGHT 1, OR at +1 column (redundant
     with step 5b — OR is idempotent).
   - `$4542`: `$45F8` shift RIGHT 1, OR at +3 columns.
   - `$455D`: `$45F8` shift RIGHT 2, OR at +5 columns.

7. `$463F` at `$4570`: XOR buffer1 into buffer2 at +1 column
   (VV:D1=0 → pin 1 masked via `ANI $7F`, pin 24 excluded via
   `ANI $FE`). Single XOR pass hollows the interior for both
   outline and shadow simultaneously.

8. `$4664` at `$4575`: width += 10 (B=5).

The key difference from running outline then shadow separately:
the double-smear and XOR happen once (not twice), and the outline
border shifts and shadow offset shifts are applied to the same
buffer before a single hollow pass. This produces cleaner output
at the overlap region than two sequential effects would.

### Super/Subscript Detail (`$4AA8`)

`$4AA8` (ESC S, `VV:28` bit 4) converts 2-byte-per-column CG data
to the standard 3-byte format with vertical alignment selection.
This is not a geometric rescale of a 24-dot source. It maps a source that is
already authored as 16-dot data into a 24-dot destination slot and zero-fills
the unused half.

**`$1ABBh` gate**: `OFFIW VV:27,$04; JR $1AC2` skips effect #1 when
VV:27 bit 2 is set.  VV:27 bit 2 reflects the classifier path, not
the user's Draft/LQ quality setting:

- **$20-$AF characters** → classifier path `$4124`: VV:22 =
  `(VV:22 & $08) | VV:2E`.  VV:2E comes from the 3rd font search
  (with super/subscript in VV:A6), and its bit 2 is always clear
  (cleared at `$14C9`, never re-added by font search).  So VV:27
  bit 2 = clear → `$4AA8` is eligible.

- **$B0+ characters** → classifier path `$4081`: `$409D: ORIW
  VV:22,$04` always sets bit 2.  So VV:27 bit 2 = set → `$4AA8`
  is blocked.

Both LQ and Draft super/subscript fonts use 2 bytes per column
(verified by glyph pointer spacing; dim1=$10 in the font directory).
`$4AA8` fires for both modes in the $20-$AF range, providing the
2→3 byte conversion and vertical alignment zero-fill.

The pre-pipeline flag logic at `$1A8D`-`$1AA8` conditionally sets
`VV:28` bit 4 for Draft characters when `VV:28` bit 7 (15 cpi) is
set and other conditions pass. When `VV:28` bit 4 is already set
(from ESC S), the pre-pipeline jumps to `$1AAB` without modification.

1. `$1DFE` → HL = EE88 (CG source), EA = work buffer.
2. DE = work buffer, EE88 updated to work buffer.
3. `VV:28` bit 3 selects alignment (this comes from `VV:23` bit 3):

   - **Superscript** (bit 3 SET, `$4ABA`): for each column, reads
     2 source bytes via `LDAX (HL+)`, writes them to dest bytes 0-1,
     then writes `$00` to dest byte 2. Output per column:
     `[data, data, 0x00]` — glyph occupies the upper 16 of 24 pins.

   - **Subscript** (bit 3 CLEAR, `$4AC4`): for each column, writes
     `$00` to dest byte 0, then reads 2 source bytes and writes them
     to dest bytes 1-2. Output per column:
     `[0x00, data, data]` — glyph occupies the lower 16 of 24 pins.

4. Loops for B = width columns. This is the vertical-size change for draft:
   only 16 vertical dots carry glyph shape instead of the full 24-dot column,
   which is a source-format selection (`2-byte` -> `3-byte`) with zero-fill.

5. No metrics modification in `$4AA8`; width/advance adjustments for
   super/subscript come from the secondary metrics path at `$1CF2`.
   The vertical size reduction comes from the CG ROM storing
   super/subscript glyphs as 2 bytes per column (16 dots); `$4AA8`
   expands to 3 bytes with zero-fill for vertical placement.

All subsequent effects (#2-#10) see standard 3-byte columns regardless
of the original CG column format.

### Condensed-Draft Detail (`$49C5`)

`$49C5` is implemented in firmware, not as a font-table swap.

The extracted CG directory has no separate plain-LQ condensed family entry
(`0x04`/`0x05`/`0x06` are Roman 15 cpi / 10 cpi Elite / 12 cpi
proportional and `0x17` is elite proportional condensed; no equivalent
plain-LQ condensed). In this path, condensed is implemented by the transform
below, not by selecting a separate font record.

`$49C5` (SI/DC2 + Draft mode, `VV:27` bit 7) halves the glyph width
by merging adjacent column pairs:

1. Calls `$1DFE` for a work buffer. Clears 3 × width bytes to zero.
2. Updates `EE88` to the work buffer. Sets DE = original source,
   HL = work_buffer − 3 (write-ahead offset for restriction).

Two paths based on `VV:29` bit 7 (half-res):

- **Half-res** (`$49E7`): clears `VV:29` bit 7 (preventing `$4C16`
  from running later). Applies a simple `XRI $FF; ANAX` adjacent-dot
  restriction loop over the compact data bytes. Does **not** merge
  column pairs or halve metrics — the half-res data stays at its
  compact width. Returns before the metrics-halving code.

- **Normal** (`$49F9`): main loop at `$4A06` processes column pairs.
  For each pair (columns N and N+1):
  - `LDAX (DE+$03); ORAX (DE+)` — merges both columns via OR
  - `LDAX (HL+); XRI $FF; ANA` — restricts the merged result
    against the inverted previous output column (adjacent-dot
    restriction: suppresses dots that would create adjacent pin
    firings at the condensed spacing)
  - `STAX (HL+$02)` — writes to the output at a +2 byte offset
  - Repeats for all 3 bytes of the column, then DE advances by 6
    (past both merged source columns)

  After the loop: `VV:99 = width / 2` (+ 1 for odd width),
  `EF95 /= 2`, `EF97 /= 2`, `EF9B` recomputed. All metrics halved.

The write-ahead offset (`HL` reads at position P, writes at P+2)
means each merged output column is restricted against its left
neighbor — the firmware ensures no two adjacent output columns have
dots in the same pin position.

Note: effect #2 runs **before** effect #4 (`$4C16`) in the pipeline.
When both condensed and half-res are active, the half-res path here
clears `VV:29` bit 7, so `$4C16` never runs. The condensed output
stays at the compact half-res column spacing.

### Emphasized Detail (`$47CB`)

`$47CB` (ESC E, ESC ! bit 3, `VV:29` bit 4) produces bold text by
ORing each glyph column one position to the right of itself:

1. Calls `$1DFE` to select a work buffer.
2. Three `BLOCK` operations copy the full glyph (width × 3 bytes)
   from the current source (EE88) to the work buffer.
3. Writes 9 zero bytes (3 blank columns) as padding after the data.
4. Updates `EE88` to point to the work buffer.
5. Sets `DE = work_buffer + 3` (one column offset) for normal glyphs,
   or `work_buffer + 6` (two columns) for half-res.
6. ORs the original glyph data into the offset position:

   - **Normal path** (`$480E`): three calls to `$1F62`, which
     performs a straight `LDAX (HL+); ORAX (DE); STAX (DE+)` loop.
     Each original column's data is ORed into the next column's
     position. Result: each dot is widened by one 360 DPI column
     to the right.
   - **Half-res path** (`$47FB`): three calls to `$1F4D`/`$1F50`.
     `$1F50` reads adjacent column data, ORs to find which pin
     positions would conflict, inverts to create a restriction mask,
     and ANDs the bold data through it — suppressing any dot that
     would create an adjacent-dot pair (which the printhead cannot
     fire). The offset is 2 columns (one 180 DPI column pair).

7. Width grows by 1 (normal) or 2 (half-res). `EF9B` (advance)
   shrinks by the same amount to keep the total cell width constant.

The bold offset is always rightward: the original data stays at its
position, and a copy is ORed one column to the right.

### Italic Shear Detail (`$4ACE`)

`$4ACE` (ESC 4, ESC ! bit 6, `VV:27` bits 4+3) applies a rightward
shear by distributing each column's vertical pin data across multiple
destination columns based on vertical position:

1. Calls `$1DDF` (full expansion setup: clears work buffer, returns
   HL = source, DE = dest).

2. Flag cascade at `$4AD9`-`$4AF3` selects between normal, double-wide
   (`$4B3E`), and double-wide+double-height (`$4BD8`) paths.

**Normal path** (`$4AF5`):

- Destination offset: `EA += 12` (4 columns into the cleared buffer).
- For each source column (3 bytes, 24 pins), each byte is split into
  two 4-pin nibbles. The low nibble (`ANI A,$0F`) is ORed into the
  current destination column; the high nibble (`ANI C,$F0`) is ORed
  into the next column (`STAX (DE+$03)`). After each byte, DE backs
  up by 5 positions (`DCX DE × 5`).

  For source column N, the mapping is:

  | Source byte | Pins | Low nibble → | High nibble → |
  | --- | --- | --- | --- |
  | byte 0 (top) | 1-8 | dest col N+4, byte 0 | dest col N+5, byte 0 |
  | byte 1 (mid) | 9-16 | dest col N+2, byte 1 | dest col N+3, byte 1 |
  | byte 2 (bot) | 17-24 | dest col N+0, byte 2 | dest col N+1, byte 2 |

  The bottom pins land at the leftmost column, the top pins at the
  rightmost — a 5-column rightward shear across 24 vertical pins.
  At 360 DPI horizontal / 180 DPI vertical this is approximately 6°.

- Metrics: width += 5, EF9B -= 5.

**Double-wide path** (`$4B3E`):

- Destination offset: `EA += 24` (8 columns).
- Each source byte is split into four 2-bit pairs (masks `$03`,
  `$0C`, `$30`, `$C0`), each ORed into a separate destination column
  at DE, DE+3, DE+6, DE+9. Then DE backs up by 11 positions.
  This spreads 24 pins across 11 destination columns — double the
  normal shear to match the doubled character width.
- Metrics: width += 11, EF9B -= 11.

### Double-Wide Detail (`$4830`)

`$4830` (ESC W, SO, ESC ! bit 5, `VV:29` bits 0+1) doubles each
glyph column horizontally:

1. Calls `$1E52` to double width/start/advance/EF95 (returns original
   width in A). If original width is 0, returns immediately.
2. Computes destination buffer size = (width + 2) × 6 bytes, then
   clears the entire buffer with zeros via `$1DFE`.
3. Updates `EE88` to the work buffer.

Three paths depending on flags:

- **Half-res** (`$4861`, `VV:29` bit 7 set): literal column
  duplication. Each 3-byte source column is written to two consecutive
  destination columns via `STAX (DE+)` plus `STAX (DE+$02)` for all
  3 bytes, then `INX DE × 3` skips past the second copy. Stride: 6
  destination bytes per source column.

- **Normal LQ** (`$48BB`, `VV:28` bit 2 clear): the first and last
  source columns are straight-copied to the destination with a 3-byte
  blank skip (via `$48EA`). The main loop at `$48D6` reads each source
  column ORed with its right neighbor: `LDAX (HL+$03); ORAX (HL+)`.
  For standard 360 DPI interleaved data (alternating data/blank
  columns), ORing with a blank neighbor is a no-op, so this
  effectively duplicates each data column while preserving the
  interleave pattern. `VV:99` gets +1 padding column; `EF9B` gets −1.

- **Super/subscript** (`$4879`, `VV:28` bit 2 set): doubles with
  adjacent-dot restriction. Uses `XRI $FF; ANAX` masking to suppress
  dots that would create adjacent-pin conflicts when the doubled
  column is placed next to the original.

### Double-Height Detail (`$4900`)

`$4900` (ESC w, `VV:2A` bit 7) is not a geometric Y-scale primitive; it is
an explicit vertical-expansion transform executed on packed nibble columns.
It doubles vertical output by expanding each selected source nibble into a
2-dot pair using `$49AD` (`bit7->C0`, `bit6->30`, `bit5->0C`, `bit4->03`):

1. If double-wide is active (`VV:29` bits 0+1 set), calls `$47CB`
   (emphasized) first at `$4908`.
2. Calls `$1DFE` for work buffer. DE = destination, HL = source.
   Updates `EE88` to work buffer.

3. `VV:89` selects which source-pin slice gets doubled. The dispatch
   at `$4915` tests bits 0, 1, 2 in priority order:

   | VV:89 | Path | Source pins | Output pins | Operation |
   | --- | --- | --- | --- | --- |
   | $01 (bit 0) | `$4925` | 1-10 | 1-20 (21-24=0) | byte0 high nibble → expand → d0; byte0 low nibble SLL×4 → expand → d1; byte1 ANI $C0 → expand → d2 (2 pins only). |
   | $02 (bit 1) | `$4945` | 11-22 | 1-24 (full) | byte1 SLL×2 ANI $F0 → expand → d0; byte1 RLR×3 ANI $C0 OR byte2 SLR×2 ANI $30 → expand → d1; byte2 SLL×2 ANI $F0 → expand → d2. |
   | $04 (bit 2) | `$4977` | 23-24 | 19-22 only | d0=0, d1=0; byte2 SLL×5 ANI $60 → expand → d2 (2 pins only). |
   | $00 (none) | `$4991` | 19-24 | 13-24 (1-12=0) | d0=0; byte2 ANI $30 → expand → d1 (2 pins); byte2 SLL×4 → expand → d2. |

   Note: `RLR` is rotate RIGHT through carry on the uPD7810 (MAME:
   `A = (A >> 1) | (carry << 7)`) despite the NEC "Rotate Left
   Register" mnemonic.

4. The expander at `$49AD` converts the high nibble of A to doubled
   bits: bit 7 → `$C0`, bit 6 → `$30`, bit 5 → `$0C`, bit 4 → `$03`.
   Four input bits become 8 output bits — each dot doubled vertically.

### Double-Height Pass Scheduling

#### Mode Table Structure

The mode table at `$67F0` contains 8 two-byte pointers. Each pointer
leads to a record chain: the first 3 bytes are `[VV:88, VV:89, byte2]`,
followed by additional byte2 values for successive passes.

The table index is computed at `$2642`-`$264F`:

```
A = (VV:AA bit 0 ? $08 : $00)    (double-height gate, MVI L1 at $263F)
  + (VV:A9 bit 6 ? $04 : $00)    (render class, $2646)
  + (VV:A9 bit 5 ? $02 : $00)    (double-strike, $2652)
EA = $67F0 + A                    (pointer to record chain)
```

`VV:AA` bit 0 is the double-height gate, set at `$190A` from `VV:25`
bit 7 (ESC w).  When set, A starts at 8, selecting mode table entries
8-14 which all have initial VV:89=$01. Normal rendering uses entries
0-6 with VV:89=$00 (the `$4900` effect is skipped entirely when
`VV:2A` bit 7 is clear).

`VV:A9` bits 5-6 are set in the printable-char path at `$18E4`-`$1904`:
bit 5 from `VV:24` bit 6 (double-strike), bit 6 from `VV:22` bit 1
(character-classifier flag).

#### Inner Loop: Record Chain, VV:89 Shift, and Per-Iteration Paper Advance

The loader at `$264F` reads the initial 3-byte record and sets
`VV:88`/`VV:89`. Then the inner loop at `$2663`-`$26EF` processes
chained byte2 values. Each iteration:

1. Loads `EE7A` from the paper advance table at `$682E`, indexed by
   byte2 bits 2-0 (`$269D`-`$26AA`).
2. Renders characters into the image buffer (`$2750` at `$26C2`),
   applying effect #10 (`$4900`) with the current VV:89 slice.
3. Calls `$2864` at `$26C5` — prints the image buffer at the
   current head position, then advances paper by `EE7A` pins.
4. Clears `EE7A` to zero at `$26CB`.
5. Shifts VV:89 left at `$26E5`-`$26E9`: `$01 → $02 → $04`.

Each iteration fires the mechanism at a **different head position**
— the paper advances between slices, not after all slices
accumulate. The advance distance comes from the table at `$682E`:

| Index | Value | Distance |
| --- | --- | --- |
| 0 | $00 | 0/180" (no advance) |
| 1 | $04 | 4/180" |
| 2 | $06 | 6/180" |
| 3 | $0A | 10/180" |
| 4 | $14 | 20/180" |
| 5 | $18 | 24/180" |
| 6 | $80 | 128/180" |
| 7 | $57 | 87/180" |

`EE7A` feeds into `EF40` at `$287E` within `$2864`, driving the
`$5676` mechanism scheduler. `EF40` is in **1/180-inch units** (one
unit = one stepper phase = one pin pitch).

#### Line Spacing Halving (`$50EB`)

The LF handler at `$2014` loads `EF8B` (line spacing) into HL, then
calls `$50EB` which halves it:

```
50EB: DMOV EA,HL          ; EA = line spacing
50EC: DSLR EA             ; EA >>= 1 (divide by 2)
50EE: DMOV HL,EA          ; HL = spacing / 2
50EF: SK   CY             ; if original was odd:
50F2: LDAW VV:93           ;   load rounding state
50F4: INR  A               ;   toggle
50F5: ANI  A,$01           ;   keep bit 0
50F7: STAW VV:93           ;   save
50F9: SK   Z               ;   if toggled to 0:
50FC: INX  HL              ;     round up (spacing/2 + 1)
```

The halved value is stored to `EE7A` at `$2586`. `VV:93` tracks
the alternating half-unit for odd spacings, ensuring that two
consecutive half-line advances sum to the exact original spacing.

**Loop termination** at `$26D3`-`$26D7`: `MVI A,$10; OFFAX (HL)`
tests bit 4 of the next byte in the record chain. If bit 4 is
**set**, `JRE $26FB` exits the loop. If **clear**, the loop
continues.

#### Record Chains and Tiling

For the base double-height chain at `$6811` (3 iterations):

| Iter | byte2 | Table idx | Advance | VV:89 | Head position | Source pins |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | $04 | 4 | 20/180" | $01 | 0 → 20 | 1-10 → out 1-20 |
| 1 | $22 | 2 | 6/180" | $02 | 20 → 26 | 11-22 → out 1-24 |
| 2 | $30 | 0 | 0 (TERM) | $04 | 26 | 23-24 → out 19-22 |

The print-then-advance sequence places each slice at a different
vertical position. With the 24-pin head:

- Iter 0: prints at position 0, covers rows 0-23, advances to 20
- Iter 1: prints at position 20, covers rows 20-43, advances to 26
- Iter 2: prints at position 26, covers rows 26-49

The overlapping regions receive data at different output pin
positions from different source-pin slices, tiling without
corruption.

For double-height + VV:22.1 (4 iterations, `$681E`):

| Iter | byte2 | Advance | VV:89 | Source pins |
| --- | --- | --- | --- | --- |
| 0 | $04 | 20 | $01 | 1-10 |
| 1 | $22 | 6 | $02 | 11-22 |
| 2 | $23 | 10 | $04 | 23-24 |
| 3 | $30 | 0 (TERM) | $08 | 19-24 (default path) |

For double-height + double-strike (6 iterations, `$6816`):

| Iter | byte2 | Advance | VV:89 | Notes |
| --- | --- | --- | --- | --- |
| 0 | $40 | 0 | $01 | print, no advance |
| 1 | $A4 | 20 | $02 | advance 20, print |
| 2 | $60 | 0 | $04 | print at same pos (double-strike) |
| 3 | $A2 | 6 | $08 | advance 6, print |
| 4 | $60 | 0 | $10 | print (double-strike) |
| 5 | $B0 | 0 (TERM) | $20 | exit |

Double-strike pairs (iters 0+1, 2+3, 4+5) print each band twice
at the same position for bolder output.

#### `$49AD` Expansion: Naive Doubling

The expander at `$49AD` maps each source bit to a **pair of
adjacent output bits** — naive doubling, not interleaved:

```
bit 7 → $C0 (output bits 7+6)
bit 6 → $30 (output bits 5+4)
bit 5 → $0C (output bits 3+2)
bit 4 → $03 (output bits 1+0)
```

This means the staggered Draft horizontal-bar pattern (`.#.#.#.#` /
`#.#.#.#.`) becomes two identical row pairs rather than an
interleaved alternation:

```
source pin 18: .#.#.#.# → row 36: .#.#.#.#
                           row 37: .#.#.#.#  (identical)
source pin 19: #.#.#.#. → row 38: #.#.#.#.
                           row 39: #.#.#.#.  (identical)
```

The physical dot overlap at 180 DPI may mask this banding artifact
on paper, but the firmware does not compensate for the Draft
stagger pattern in double-height mode.

### `VV:88` / `VV:89` / `VV:2A` helper-bit mapping

These three bytes are loaded from the mode table at `67F0h` (via
`264F`-`2676`) and then consumed by normal render, double-strike, and
underline paths. They are not user-visible attributes the way `VV:22`–`VV:25`
are; they are runtime render-mode selectors and compatibility gates.

`VV:2A` bits:

- `0x20` and `0x40`: effect bits for shadow/outline (`ESC q2/1`, and both for
  `ESC q3`), consumed by the effect dispatch at `$1ABF`-`$1B18`.
- `0x80`: global render-state bit set by ESC w (`VV:2A bit 7`) for
  double-height path (`$4900`) and consulted in render/underline gating.
- Low nibble (`0x0F`): participates in overlap-class checks:
  - `VV:2A.low & VV:88.low` gate at `$27D9` and `$1ED6` (`OFFA`/`ONA`).
  - no separate per-bit semantics proven beyond this compatibility role.

`VV:88` bits:

- `0x80`: dispatch/underline override bit:
  - if clear, render can continue without the `VV:29.6` check in
    `$27E2`/`$1EDB`.
  - if set, `VV:29.6` becomes part of the gating path and can force early return.
  - treat as "double-strike/render override flag" (inferred from trace behavior).
- `0x20`: participates with `VV:89.08` in the early render-class branch at
  `$1D28`/`$1D2B` and with `VV:89.08` at `$27FF`/`$2802` for the sibling
  render branch.
- `0x08`: initialized/sanitized via table load (`$2666`/`$266F`) and not used
  as an independent branch predicate elsewhere in current traces.
- Low nibble (`0x0F`): compatibility mask used with `VV:2A` low nibble.

`VV:89` bits:

- `0x01`, `0x02`, `0x04`: double-height source-slice selectors used by
  `$4900` (`bit`-based interleave path choice is also shown in
  “Double-Height Detail”).
- `0x08`: used with `VV:88.20` in mode-branching (`$1D2B`, `$2802`) and as
  an explicit disable in underline setup (`$1EE7` checks `$09`, so either bit
  `0x01` or `0x08` set forces an early return).
- `0x20`: newline-style guard for underline; it must be clear for the alternate
  `VV:B2=$04` mask path.
- `0x02` + `0x04` + `VV:2A.80==0`: together with the `VV:88` low-nibble
  overlap gate, enable the alternate underline mask (`VV:B2=$04`).

Bits in this trio are currently only known through trace behavior; where this
is not provable as a direct documented mode flag, the table marks them as
inferred from control-flow coupling.

### Double-Strike (`VV:29` bit 6)

Double-strike (ESC G/H, `VV:24` bit 6 → `VV:29` bit 6 at runtime)
is **not** part of the effect pipeline at `$1ABF`-`$1B18`. It does
not modify glyph column data.

It operates at two levels:

1. **Render dispatch** (`$27D1`-`$281D`): `VV:29` bit 6 is checked
   at `$27E5` alongside `VV:88` bit 7. The flag cascade selects
   between `CALL $1A8A` at `$281D` (render with position update) and
   `JMP $1A8A` at `$281A` (render without position update). This
   allows the character to be rendered into the image buffer without
   advancing the position, then rendered again with the advance.

2. **Line output** (`$2871`-`$28C3`): the mechanism firing loop
   calls `$5676` multiple times. `$288A` fires the first carriage
   pass; `$28AA` fires a second pass after mechanism completion and
   carriage repositioning via `$28CE`. The same image buffer data
   is printed at two slightly different carriage positions, producing
   a denser/darker impression.

Note: ESC G/H do not trigger font reconfig via CALT (`$0092`), unlike
most other style commands.

### Draft vs LQ Rendering Differences

| Aspect | Draft | LQ |
| --- | --- | --- |
| Image buffer column stride | 4 bytes | 3 bytes |
| CG column format | 3 bytes per column (24 dots) | 3 bytes per column (24 dots) |
| CG font column resolution | Lower (fewer columns per glyph) | Higher (more columns) |
| Condensed-Draft effect | Active (merges adjacent columns) | Not active in plain LQ condensed path |
| Render geometry table mode | Modes 0-4 | Modes 5-7 |
| Bidirectional adjustment | VR1 at n/240 inch | VR2 at n/720 inch |
| Half-resolution glyphs | Not observed | Present (byte 5 bit 7 flag) |

### Image Buffer Structure

The image buffer uses 3 bytes per column for LQ (4 for Draft). Each
3-byte column represents 24 vertical pins at one 1/360-inch horizontal
position. The buffer is at 360 DPI — a 10 CPI character occupies 36
column positions (e.g., Roman LQ `M`: start 3 + width 29 + advance 4).

The `$1E7F` column write loop ORs glyph data directly into the buffer
with no intermediate "develop" step. Start and advance values from the
per-character metrics record are multiplied by the column stride (3 for
LQ) to get byte offsets. The OR operation allows overlapping characters
(strike-over, accents) to merge.

Full-resolution LQ glyphs have the two-pass interleave baked in:
data columns alternate with blank (`000000`) columns. The multi-pass
carriage mechanism fires all columns on each pass, offset by one dot
position, filling the gaps to produce solid 180 DPI output. See
"360 DPI Two-Pass Interleave" above.

The render geometry tables at `$7307`-`$739A` control per-mode
addressing parameters (base offsets, clipping bounds, column stride)
used by `$217C` to compute the buffer destination for each character.

### CG Font Coverage from Extracted Directory

| Index | Family | Config | Quality | Pitch |
| --- | --- | --- | --- | --- |
| 0 | Roman | $00 | Draft | 10 cpi |
| 1 | Roman | $01 | Draft | Elite (12 cpi) |
| 2 | Roman | $13 | Draft | Elite+Proportional+Condensed |
| 3 | Roman | $04 | LQ | 10 cpi |
| 4 | Roman | $05 | LQ | Elite |
| 5 | Roman | $17 | LQ | Elite+Proportional+Condensed |
| 6 | Roman | $06 | LQ | Proportional |
| 7 | Block | $84 | LQ | (default) |
| 8 | Block | $00 | Draft | (default) |
| 9 | Sans Serif | $04 | LQ | 10 cpi |
| 10 | Sans Serif | $05 | LQ | Elite |
| 11 | Sans Serif | $17 | LQ | Elite+Proportional+Condensed |
| 12 | Sans Serif | $06 | LQ | Proportional |

Notable gaps: Sans Serif has no Draft fonts (fallback to Roman Draft).
There is no dedicated 15 cpi font; 15 cpi maps to config $03 via
`$164B`, which has no directory match and falls back through the pitch
alternatives.

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
