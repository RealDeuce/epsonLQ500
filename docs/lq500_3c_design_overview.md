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

### Second CG Read

After the initial metrics, when `VV27` bit 2 is clear the code reaches
`1CEDh` → `1CF2h`, which performs a second CG read:

- Sets `F002=$4F` (a fixed bank, distinct from the font-selected bank).
- Reads a 6-byte record at (`$8000` or `$8600`) + `VV:A0` × 6.
- `VV28` bit 4 selects the base: `$8000` when set, `$8600` when clear.
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
| 1 | VV:28.4 set | `$4AA8` | Super/subscript active | Copies 2-byte CG columns → 3-byte with zero-fill; VV:28.3 selects upper/lower 16-pin alignment |
| 2 | VV:27.7 set | `$49C5` | Condensed-Draft mode | Clears destination, XOR-inverts and ANDs adjacent columns to merge/halve column count |
| 3 | VV:29.4 set | `$47CB` | Emphasized | Copies glyph to work buffer with 3 blank-column padding, then ORs original data at +1 column offset (bold shift). Half-res path uses +2 column offset with adjacent-dot restriction via `$1F50`. Width += 1 (or 2 for half-res), advance -= same. |
| 4 | VV:29.7 set | `$4C16` | Half-res expansion | Clears VV:29.7, calls `$1E52` to double width/start/advance back to full values, then copies each 3-byte column followed by 3 zero bytes — inserting blank columns to restore the full-width sparse dot pattern |
| 5 | VV:29 bits 0+1 set | `$4830` | Double-wide | Calls `$1E52` to double metrics, clears dest buffer, then duplicates columns. Half-res: literal duplication via `STAX (DE+)`+`STAX (DE+$02)`. Normal LQ: ORs adjacent source columns (`LDAX (HL+$03); ORAX (HL+)`), which is a no-op for interleaved blanks → effective duplication. Super/subscript path at `$4879` applies adjacent-dot restriction while doubling. |
| 6 | VV:27 bits 4+3 set | `$4ACE` | Italic shear | Splits each byte into nibbles, ORs upper nibble at current position and lower nibble at stride-offset position to create rightward slant |
| 7 | VV:2A bits 5+6 = 11 | `$44C4` | Unused on LQ-500 | — |
| 8 | VV:2A.6 set | `$43DD` | Unused on LQ-500 | — |
| 9 | VV:2A.5 set | `$444A` | Unused on LQ-500 | — |
| 10 | VV:2A.7 set | `$4900` | Double-height | Expands each 4-bit nibble → 8 bits (each dot becomes 2-dot pair) via `$49AD`; VV:89 bits select extraction mode |

VV:27-VV:2A correspond to VV:22-VV:25 via the BLOCK copy at `185Ch`.
Confirmed VV bit assignments from ESC ! Master Select (`0F42h`) and
individual command handlers, verified against `lq500_u1.pdf` page 6-4:

| VV register | Bit | ESC/P effect | Set by |
| --- | --- | --- | --- |
| VV:22 | 3 | Not-italic (per classifier, inverse of VV:24.3) | `4038h` classifier |
| VV:22 | 4 | Italic fallback (italic requested but not in font) | `154Eh` font scan |
| VV:22 | 5 | Condensed | SI/DC2, ESC ! bit 2 |
| VV:22 | 7 | Condensed-Draft mode (condensed AND Draft AND not proportional) | `14C6h` reconfig |
| VV:23 | 0 | Underline | ESC -, ESC ! bit 7 |
| VV:23 | 1 | Elite (12 cpi) | ESC M/P, ESC ! bit 0 |
| VV:23 | 3 | Superscript (vs subscript when bit 4 set) | ESC S 0 |
| VV:23 | 4 | Super/subscript active | ESC S 0/1, ESC T |
| VV:23 | 5 | Proportional | ESC p, ESC ! bit 1 |
| VV:23 | 7 | 15 cpi | ESC g, cleared by ESC P/M |
| VV:24 | 0 | Double-wide one-line (SO, DC4 cancels) | SO/DC4 |
| VV:24 | 0+1 | Double-wide persistent | ESC W, ESC ! bit 5 |
| VV:24 | 3 | Italic | ESC 4/5, ESC ! bit 6 |
| VV:24 | 4 | Emphasized | ESC E/F, ESC ! bit 3 |
| VV:24 | 6 | Double-strike | ESC G/H, ESC ! bit 4 |
| VV:25 | 4 | Extended character ($F0+ range excl $F4/$F5) | `4038h` classifier |
| VV:25 | 5-6 | Unused on LQ-500 (ESC q not supported) | — |
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

For a plain LQ character with no style attributes, the pre-pipeline flag
checks at `1A8Dh`-`1AB8h` route through `VV:27` bit 2 (LQ flag, set),
which causes `JR $1AAB` at `1AA4h`. The entire effect dispatch at
`1ABFh`-`1B18h` is then a no-op: every gate condition is false, and
the pipeline returns without calling any effect function.

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

1. Sets `VV:B2 = $01` (underline dot mask = bit 0 of byte 2).
   Condition checks at `$1ECF`-`$1F00` may change this to `$04`
   (bit 2 of byte 2) for double-height characters.
2. Reads the **previous** column's byte 2 (`DCX DE; LDAX (DE+)` at
   `$1F06`) to determine the alternation phase — maintaining
   continuity with any preceding underlined character.
3. Walks from old `EE66` to new `EE66` (the full character cell:
   start + width + advance), modifying byte 2 of each 3-byte column:
   - **Even columns**: `ORA A,C` — sets the underline bit.
   - **Odd columns**: `ANA A,C` (with `C = ~mask`) — clears it.
   - `XRI C,$FF` toggles the mask each iteration.

The underline dots follow the 360 DPI two-pass interleave: set in
every other column, matching the glyph data pattern. The two carriage
passes fill the gaps to produce a continuous line.

**Vertical position**: `VV:B2 = $01` → bit 0 of byte 2 → wire 17
(H17, vertical position 16/180 inch below pin 1). This corresponds
to the 24-pin head's underline strike position. For double-height:
`VV:B2 = $04` → bit 2 of byte 2 → wire 19 (H19, position 18/180).

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

Condensed (VV:23 bit 4 via `$166B`) and italic (VV:24.3 via `$1666`)
add their bits independently (VV:A6 bit 4 and bit 6).  LQ quality
(VV:87 bit 2 via `$1643`) sets VV:A6 bit 2.

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

- **Super/subscript + anything**: effect #1 runs first, converting
  2-byte CG columns to 3-byte format.  All subsequent effects see
  3-byte columns regardless.
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

Effects that are unused on the LQ-500 (effects 7-9, gated by VV:2A
bits 5+6) are skipped.

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

### Draft vs LQ Rendering Differences

| Aspect | Draft | LQ |
| --- | --- | --- |
| Image buffer column stride | 4 bytes | 3 bytes |
| CG column format | 3 bytes per column (24 dots) | 3 bytes per column (24 dots) |
| CG font column resolution | Lower (fewer columns per glyph) | Higher (more columns) |
| Condensed-Draft effect | Active (merges adjacent columns) | Not active (different font used) |
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
