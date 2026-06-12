# LQ-500 ROM Dump Handoff

This note is for resuming the LQ-500 ROM/font extraction work when the physical
printer and chip dumps arrive. It was recreated from retained chat context after
the workspace loss.

## Current State

- Target printer: Epson LQ-500.
- `3C` program PROM has been dumped successfully:
  - canonical file: `roms/lq500_3c_m25a10pa_internal_prom.bin`
  - size: 32768 bytes
  - CRC32: `cf3ba9da`
  - SHA1: `7275ef3547ad1bbb12210d626c796a827f308bb6`
  - SHA256: `44cef05debd14852daefdc07dceaec0180e6efebdaea3bb9588966dbd0dab9a0`
  - two `27C256@DIP28` reads matched byte-for-byte.
  - note: the initial inferred orientation read as all `0xff`; reversing the
    DIP28 chip produced plausible data. `minipro` still reported chip ID
    mismatch/`0x0000`, so reads used `-y`.
- `3C` program ROM disassembly/labeling has started:
  - first-pass code map: `docs/lq500_3c_program_rom_map.md`
  - first-pass labels: `data/lq500_3c_program_labels.tsv`
  - parsed command dispatch tables: `data/lq500_3c_command_dispatch_tables.tsv`
  - audited command behavior table: `data/lq500_3c_command_behaviors.tsv`
  - recursive vector trace roots: `data/lq500_3c_trace_roots.tsv`
  - recursive vector trace output: `data/lq500_3c_vector_trace.md`
  - disassembly source: `roms/lq500_3c_m25a10pa_internal_prom.asm`
  - high-confidence labels now cover reset/init, interrupt stubs, F000-F005
    gate-array access anchors, string/output helpers, self-test/data-dump mode,
    and bidirectional adjustment mode.
  - previous naming focus covered control-panel, DIP-switch, and host-input
    code:
    - `0582h` is now labeled `isr_gate_f000_input_capture_buffer`, a candidate
      parallel-port/gate-array host data interrupt path into the shared `EE20h`
      input buffer.
    - `05E2h` is labeled `isr_rxb_host_receive_buffer`, the CPU `RXB` path
      into that same input buffer.
    - `4EEAh` is labeled `read_panel_buttons_debounced`; manual self-test
      paths identify return bits `01h` = LINE FEED/AUTO LOAD, `02h` =
      FORM FEED, and `04h` = ON LINE. Startup dispatch uses `VV0C=01h` for
      Draft self-test, `02h` for LQ self-test, `03h` for data dump, and remaps
      raw `07h` to `08h` for bidirectional adjustment.
    - `4F37h`/`4F54h` are labeled as startup DIP/panel reads using compact
      ADC switch tables plus direct PA bits, so the switches are not just one
      direct CPU port bank.
    - `4FB1h` samples/clamps ADC-derived VR adjustment offsets and is called
      both at startup and from bidirectional adjustment.
  - host input now traces to the command processor:
    - `0A0Bh` is the `CALT ($0080)` shared input-byte consumer using `EE22h`
      as read pointer and `EE1Eh` as pending-byte count.
    - `400Bh` is the top-level read/classify loop.
    - `4038h` classifies printable bytes; printable bytes skip the command
      dispatcher and continue through the `4012h` output path.
    - `6944h` scans count-prefixed dispatch tables at `696Eh` for primary
      controls and `699Ch` for ESC commands.
    - FX-80 comparison: `ESC j n` is a real compatibility reverse-feed handler
      at `2568h`; it pairs with `ESC J` by building `HL=80nn` instead of
      `HL=00nn`. `ESC s n` is an FX-80 half-speed compatibility candidate
      whose LQ-500 table entry consumes one byte only. `ESC r n` and `ESC h n`
      were not found in the checked FX-80 notes and currently look like
      one-byte compatibility/no-op consumers.
  - current naming focus is mechanical outputs, in priority order:
    paper advance/retard, carriage movement, and pin firing. Cut-sheet feeder
    and other option mechanisms are lower priority unless they share these
    output paths.
    - paper-feed hardware anchor from service manual Figure 2-47: the paper
      feed motor is a 4-phase, 48-step motor using 2-2 phase excitation. One
      phase switch advances paper `1/180` inch. `PB2` is active-low drive:
      low turns Q27 on and supplies `+24 V`; when not driven, `+5 V` is
      supplied through `R36`/`D11` for hold. `PB3` is phase A/B and `PB4` is
      phase C/D.
    - firmware match for Figure 2-47: `540Dh` has a `VV62!=0` branch at
      `5498h`/`549Ch` that sets/clears `PB mask 04h`, matching `PB2` if bit
      numbering is zero-based. `549Ch` clears `PB & 04h` low for +24 V drive;
      `5498h` sets it high for hold. `093Eh`/`0953h`/`095Fh`/`096Ah` rotate
      `VV16` and map `VV16 & 18h` directly to `PB & 18h`, matching
      `PB3`/`PB4`. Here `18h` and `04h` are bit masks on the 8-bit `PB` port,
      not pin names. The old "carriage PB mask 18h" label should be treated as
      stale; carriage is now anchored separately through the `VV62==0` FE1 path
      at `0908h`, which pulses CPU `PC7` / gate-array `TM`.
    - pin-firing/head anchor: `08D0h` writes `F004=0C0h`, presets alternate
      `BC=F005h`, and arms timer state; vector `0978h` writes three bytes
      through that `F005h` pointer. `563Ch` prepares `EF75h`/`EF77h`/`EF79h`
      and `5681h` writes `F004=20h`.
    - paper-feed candidate: `ESC J` at `2530h` and FX-80-compatible `ESC j` at
      `2568h` converge at `2534h`, then run through `1FEAh`, `2048h`, and the
      signed vertical-advance setup at `256Eh`. Nonzero pending distance can
      reach `2864h`, which stores the magnitude in `EF40h`, sets `VV38.3`, and
      calls the timed output scheduler at `5676h`. The copied `VV6D.3` path at
      `569Ah-56C5h` sets `VV62=1`, `VV63=0`, and `EF64` from the feed-distance
      state before reaching `558Dh`/`55B1h` and `540Dh`. Correlate this with
      `PB mask 04h` low drive windows and `PB mask 18h` phase switches.
      The command-feed short-move gate is at `55D8h-55E8h`: counts below
      `000Bh` set `VV36 & 04h`, load `EF51` from `725Fh`, and leave `EF64` as
      the command count. These `n=1..10` short moves do not walk the lead/tail
      timing lists; FE1 counts `EF64=n` directly, producing exactly `n`
      `093Eh` phase updates. Counts `>=000Bh` fall through `55EEh-560Eh`,
      where the `708Eh` record subtracts five lead and five tail steps so
      `EF64=count-10`. Long moves therefore produce `5 + (n-10) + 5 = n`
      `PB3`/`PB4` phase changes. `n=0` does not schedule timed paper motion at
      `2864h`.
      The same record seeds `EF4F=725Fh` and `EF57=7269h`; FE1 walks those at
      `0772h` and `0799h`. First five lead words from `725Fh`: `1086h`,
      `0DC6h`, `0CB8h`, `0C24h`, `0C00h`; first five tail words from `7269h`:
      `0C24h`, `0C24h`, `0CB8h`, `0DC6h`, `0FFCh`. The command-feed first
      lead word is about `3.44 ms`, so it appears to be a ROM-revised first
      movement interval relative to the manual's `3.33 ms` `tc1`. `ESC J`
      selects the `0953h` forward phase order; `ESC j` selects the `095Fh`
      reverse phase order. The initial `VV37=1` gate enables active-low `PB2`
      drive before the first counted phase change. The final `PB2` release is
      now traced: after the tail steps, `VV37=10h` selects `EF5B=01` and keeps
      drive low for the `EF59` delay; the next FE1 pass changes to
      `VV37=20h`, whose `540Dh` selector falls through to `EF60=00`, taking
      `5498h` and setting `PB & 04h` high for hold before the later
      `EF5C`/`EF5E` delays and final FE1 masking. `EF60` is copied by
      `55CBh` because uPD7810 `BLOCK` copies `C+1` bytes; for the selected
      `708Eh` command-feed record, the copied `EF60` value is `00`.
      Separately, startup calls the carriage home-seek path at `51F7h-5253h`.
      It branches on and samples the `PA bit 20h` HOME candidate, walks
      carriage timing tables around `7287h`/`72AFh`, pulses `0908h`/`PC7`/`TM`,
      and selects four carriage-current states at `546Ah`, `5474h`, `547Eh`,
      and `5488h`. The current-control shape matches the service manual's
      `PB5`/`PB6 SPDM`/`PB1 SPDH` table, with `SPDM`/`SPDH` likely meaning
      speed medium/high current-select inputs. Schematic review shows `PB1` is
      `AFXT` to CNI/parallel `AUTOFEED`, while `PA1` goes through a transistor
      to STK69818 pins 9/11, so the table's `PB1` label is treated as a manual
      typo and firmware `PA1`/`PA & 02h` is the `SPDH` selector.
    - `data/lq500_3c_paper_advance_path.tsv` tracks the paper-feed staging
      model. The command-distance-to-phase mapping is now resolved for
      immediate feed: nonzero `ESC J`/`ESC j` counts produce one `PB mask 18h`
      phase change per command unit, so each unit is one `1/180` inch phase
      switch on the service-manual model.
- `4C` resident CG/font ROM candidate has been dumped successfully:
  - chip markings: `EPSON (C) 1997 / JAPAN 871 / M10A10LA EDH`
  - board marking under chip: `IM/256 Kbit MASK` and `?256PROM`
  - original `27C256@DIP28` file: `roms/lq500_4c_m10a10la_cg_candidate.bin`
  - original `27C256@DIP28` size: 32768 bytes
  - CRC32: `a9b738e0`
  - SHA1: `58c089c14cfa2320008781367578b45f60436880`
  - SHA256: `ef2af1dfc61d5884e86ccf8f6be7782b0683583806fe7ae9b801079413db65fc`
  - two `27C256@DIP28` reads matched byte-for-byte.
  - a repeated `27C512@DIP28` test read produced a stable 65536-byte two-bank
    image:
    `roms/lq500_4c_m10a10la_cg_candidate_27c512_test.bin`
    - CRC32: `5989d780`
    - SHA1: `6a4245be7e86fccd2501d908f164439592ac2d8f`
    - upper 32768 bytes match the canonical 27256 dump exactly.
    - upper/pin-1-high split file:
      `roms/lq500_4c_m10a10la_pin1_high_bank.bin`
      - CRC32: `a9b738e0`
      - SHA1: `58c089c14cfa2320008781367578b45f60436880`
    - lower/pin-1-low split file:
      `roms/lq500_4c_m10a10la_pin1_low_bank.bin`
      - CRC32: `3d0bfaa2`
      - SHA1: `56b80fcc01b60313fc6754ef1e2072d273d2e25b`
    - continuity finding: 3C pin 1 has continuity to 3C pin 28/VCC, but 4C
      pin 1 does not. 4C pin 28 does have continuity to 3C pin 1 and pin 28.
    - schematic cross-check: the 4C schematic reportedly identifies pin 1 as
      `A15`, confirming that the `27C512@DIP28` pin-1-low/high halves are real
      low/high `A15` halves. The schematic/jumper trace now points to a banked
      1 Mbit arrangement: `J5` ties pin 1 / `A15` to `BK2` on `6C` E01A05KA,
      `J6` wires pin 20 `/CE`, and the hard-to-read `A16/OE` label appears to
      be `A16` wired to `BK3`, not `/OE`.
    - manual cross-check: the technical manual memory map labels the resident
      CG select as `1M CG` in the 4C/2C area, and the address decoder uses
      gate-array bank lines for CG windows. That is evidence for more than a
      simple hard-wired 256 Kbit ROM, despite the board text mentioning
      `256 Kbit`.
  - note: the dump has bitmap-like two-byte patterns and embedded strings
    including `Draft` and `Roman`, so it is very likely resident CG/font data.
    The A15-low half has `Draft` strings; the A15-high/canonical half has
    `Draft` and `Roman` strings. The pin-22-high/A16-high bank includes
    `Sans Serif` strings at full-image offsets `164CBh`, `18E13h`, `1A570h`,
    and `1C5D3h`.
  - `AT27C011@DIP28` and `D27C011@DIP28` test reads on the T48 completed even
    though `minipro -d` reports those profiles as T56-only. Both produced the
    same 131072-byte file:
    `roms/lq500_4c_m10a10la_cg_candidate_27c011_test.bin`
    - CRC32: `7e1e80b2`
    - POSIX cksum: `2115964658 131072`
    - SHA1: `5a0b345da366aa4c18cbd022cb60093902425731`
    - SHA256: `dd8543e4a5713a76193a6e329cbca364bc8eb21d511ef9ab6726e87af775dddc`
    - result: the 128 KiB image is exactly the 64 KiB `27C512` capture
      repeated twice. As 32 KiB quarters it is A15-low, A15-high, A15-low,
      A15-high. This does not expose distinct `BK3`/`A16` data.
  - patched minipro custom PROM reads captured the missing pin-22/A16 state:
    - `LQ500_4C_PIN22_HIGH@DIP28` reads 65536 bytes with pin 20 low and pin 22
      held high. Two reads matched byte-for-byte.
    - pin-22-high file:
      `roms/lq500_4c_m10a10la_pin22_high_custom_prom.bin`
      - CRC32: `d9caaca8`
      - POSIX cksum: `2305131511 65536`
      - SHA1: `d5d70c8591043ea9fa325e11687e2b30d4611394`
      - SHA256: `f707ccb88aeca8cc0993fedae725ef8be2bd946ff2b21e981b1b3fe9b0e7bb61`
    - `LQ500_4C_A16_PIN22@DIP28` treats pin 22 as `A16` and reads 131072
      bytes. Its first 65536 bytes match the stable `27C512@DIP28` capture,
      and its second 65536 bytes match the repeated pin-22-high read.
    - full 128 KiB file:
      `roms/lq500_4c_m10a10la_cg_128k_custom_prom.bin`
      - CRC32: `a482d81c`
      - POSIX cksum: `3600394045 131072`
      - SHA1: `7c85fdca1fa388e2a0f21795bd239a9daf04f4f6`
      - SHA256: `67b2fecb5e90c410dc17562fd344ffe793aefd6bd563ff4d89b89322a8fac303`
- Recovered technical/service manual: `epsonlq-500servicemanual.pdf`.
- CPU from the technical manual: NEC uPD7810HG at board location `4B`.
- Disassembler available locally: `../mame/unidasm`.
- Correct MAME disassembler architecture: `upd7810`.
- Main reference files:
  - `docs/lq500_reference.md`
  - `data/lq500_commands.json`
  - `data/lq500_fonts_and_memory.json`
  - `data/rom_dump_manifest.template.json`
  - `epsonlq-500servicemanual.pdf`
  - `lq500_u1.pdf`
  - `lq500_sl.pdf`

Manual extraction is complete enough for command and font naming work. Program
ROM and the populated `4C` resident CG/font ROM are now dumped. The complete
`4C` image is the 128 KiB custom PROM read
`roms/lq500_4c_m10a10la_cg_128k_custom_prom.bin`; native T48 `27C011`-style
reads are known to mirror only the A16-low 64 KiB bank.

## Expected Chips And Regions

From the LQ-500 technical manual memory map:

| Region | Expected size | Board location | Notes |
| --- | ---: | --- | --- |
| Internal PROM | 32 KB | `3C` | Program PROM in CPU lower address range. This is not CPU-on-chip ROM. |
| External PROM | unknown | external/optional | Selectable by firmware when correct PROM is mounted. |
| 4M CG | Manual label, likely 4 Mbit if populated | `5C` | Character generator select, banked into `8000h-A000h`; confirm actual chip size from markings. |
| 1M CG | Manual label, likely 1 Mbit if populated | `4C` in figure; text also says `2C`, conflicting with PSRAM | Character generator select, banked into `8000h-A000h`; confirm whether a stock chip is actually installed. |
| External CG | unknown | external/optional | Character generator data from external/font module path. |
| PSRAM | not ROM | `2C` | Buffer RAM, not expected to be dumped as font source. |

Address decoding is handled by gate array `E01A05KA` at `6C`. It selects
internal PROM, external PROM, `4MCG`, `1MCG`, external CG, RAM, and the head
gate array using `AB12`-`AB15` plus bank lines 7 and 6.

Important: `4M CG` and `1M CG` are service-manual memory-map labels. They may
mean megabits/capacity-class address decoding, not a promise that every normal
LQ-500 has a 512 KB plus 128 KB CG ROM set installed. The appendix clearly
identifies PSRAM at `2C`, but does not clearly list the CG ROM chip part
numbers. Trust the physical board and chip markings when the printer arrives.

Board-photo observation: the socketed chip at `6C` is marked `E01A05LC`, which
appears to be the same address-decoder gate-array family as the service-manual
`E01A05KA` reference, not a ROM dump target. Boards found online also appear to
have a socketed ROM-like device at `4C` and a partially obscured socket that is
almost certainly `3C`, because a separate RAM chip is clearly marked `2C`. The
`5C` footprint appears unpopulated and labeled `4M/2M/1M/256kbit MASK IMPROM`.
Treat `5C` as a likely alternate/optional mask-ROM footprint until proven
otherwise.

The two ROM markings visible in board photos are `M25A10PA` and `M10A10LA`.
Working hypothesis:

- `M25A10PA` is the `3C` program PROM. The `25` marking plausibly corresponds
  to a 256 kbit / 32 KB mask PROM, matching the manual's internal PROM size.
- `M10A10LA` is the `4C` resident CG ROM. The patched minipro custom PROM read
  captured it as 128 KiB. The schematic reportedly confirms `4C` pin 1 is
  `A15`, so each 64 KiB A16 bank has valid low/high `A15` halves. The
  schematic/jumper trace also shows `J5` tying pin 1 / `A15` to `BK2`, `J6`
  wiring pin 20 `/CE`, and the hard-to-read `A16/OE` label appears to be
  `A16` wired to `BK3`.

Treat this as a hypothesis until the actual board location and dump sizes
confirm it.

## Dump Naming

Use names that preserve physical origin before we understand the contents:

```text
lq500_3c_m25a10pa_internal_prom.bin
lq500_4c_m10a10la_cg_candidate.bin
lq500_5c_4m_cg_<chipmark>.bin
lq500_external_cg_or_font_module_<label>.bin
```

For each dump, record:

- Board location.
- Chip markings.
- Package/pin count.
- Programmer device type used.
- File size.
- CRC32, SHA1, SHA256.
- Whether multiple reads matched byte-for-byte.
- Any adapter or byte-lane handling used by the programmer.

Use `data/rom_dump_manifest.template.json` as the starting manifest.

## First Commands

After placing dumps in a `roms/` subdirectory, run:

```sh
ls -l roms
cksum roms/*.bin
sha1 roms/*.bin
sha256 roms/*.bin
file roms/*.bin
```

Likely `minipro` read profiles for the two main ROMs:

```sh
minipro -p '27C256@DIP28' -r roms/lq500_3c_m25a10pa_internal_prom.bin
minipro -p '27C512@DIP28' -r roms/lq500_4c_m10a10la_try_27c512.bin
```

The markings look like Epson/custom mask ROM names, not generic JEDEC EPROM
part numbers, so these are compatible read-profile guesses:

- `M25A10PA`: try `27C256@DIP28` first. Cross-check with `M27C256B@DIP28`,
  `AT27C256@DIP28`, or `TC57256D@DIP28` if needed.
- `M10A10LA`: both observed ROMs are DIP28. `minipro -d` reports
  `AT27C011@DIP28`, `D27C011@DIP28`, and `D27011@DIP28` as 131072-byte DIP28
  devices, but also says they are available on T56 only. With a T48, try
  `27C512@DIP28` to test a 64 KB read, but do not assume that proves the full
  capacity if the chip is actually 128 KB.

The native EPROM XML entries do not expose an `OE` polarity knob. To test
whether the `4C` `BK3`/pin-22 state can be captured by holding that pin high,
use [`../patches/minipro-lq500-4c-custom-prom.patch`](../patches/minipro-lq500-4c-custom-prom.patch).
It adds two custom PROM bitbang profiles to the T48/`INFOIC2PLUS` database:

```sh
git -C /usr/ports/sysutils/minipro/work/minipro-f124338492a3937dbf02f9c4bc5219892f10481e apply /usr/home/admin/T400/lq500/patches/minipro-lq500-4c-custom-prom.patch
```

After rebuilding/running that patched minipro, the useful read attempts are:

```sh
minipro -p 'LQ500_4C_PIN22_HIGH@DIP28' -y -r roms/lq500_4c_m10a10la_pin22_high_custom_prom.bin
minipro -p 'LQ500_4C_A16_PIN22@DIP28' -y -r roms/lq500_4c_m10a10la_cg_128k_custom_prom.bin
```

`LQ500_4C_PIN22_HIGH@DIP28` reads 64 KiB with pin 20 low and pin 22 high; this
captured a stable bank distinct from the existing 64 KiB `27C512` capture.
`LQ500_4C_A16_PIN22@DIP28` treats pin 22 as `A16` and captured a single 128 KiB
read ordered as the old `27C512` A16-low bank followed by the pin-22-high
A16-high bank.

Only perform read operations. If two compatible profiles produce byte-identical
files of the expected size, keep the simpler generic profile name in the
manifest notes.

If the 32 KB program PROM is available:

```sh
../mame/unidasm roms/lq500_3c_m25a10pa_internal_prom.bin -arch upd7810 -basepc 0x0000 > roms/lq500_3c_m25a10pa_internal_prom.asm
../mame/unidasm roms/lq500_3c_m25a10pa_internal_prom.bin -arch upd7810 -basepc 0x0000 -norawbytes > roms/lq500_3c_m25a10pa_internal_prom_noraw.asm
```

For small spot checks:

```sh
../mame/unidasm roms/lq500_3c_m25a10pa_internal_prom.bin -arch upd7810 -basepc 0x0000 -count 0x100
../mame/unidasm roms/lq500_3c_m25a10pa_internal_prom.bin -arch upd7810 -basepc 0x0000 -skip 0x1000 -count 0x100
```

Likely base PC for the internal PROM is `0x0000`. Revisit this if reset/vector
behavior from the uPD7810 datasheet contradicts the service manual memory map.

## Recursive Trace Workflow

The current control-flow trace is generated from reset and interrupt/vector
seeds, with uPD7810 skip-producing instructions modeled as two-successor
instructions. `JR` itself is unconditional; loops such as `DCR B; JR back` exit
when `DCR` sets the CPU skip flag and suppresses the following `JR`.

Editable roots live in TSV format:

```text
data/lq500_3c_trace_roots.tsv
```

Rerun the trace with:

```sh
python3 tools/trace_upd7810_unidasm.py \
  --rom roms/lq500_3c_m25a10pa_internal_prom.bin \
  --unidasm ../mame/unidasm \
  --out-prefix data/lq500_3c_vector_trace \
  --roots-file data/lq500_3c_trace_roots.tsv
```

Generated outputs:

- `data/lq500_3c_vector_trace.instructions.tsv`
- `data/lq500_3c_vector_trace.segments.tsv`
- `data/lq500_3c_vector_trace.frontier.tsv`
- `data/lq500_3c_vector_trace.used_roots.tsv`
- `data/lq500_3c_vector_trace.summary.json`
- `data/lq500_3c_vector_trace.decode_cache.json`
- `data/lq500_3c_vector_trace.md`

Current vector-seeded trace stats:

- decoded instructions: `7010`
- reached code bytes: `14058`
- not-reached bytes: `18710`
- unresolved indirect stops: `JEA` at `02DCh`, `240Ah`, `5468h`, and `761Ch`
- decode-failed frontier points: `008Bh` and `00A2h`

Use `frontier.tsv` for iterative review. Hand-confirmed indirect entry points
should be added to `lq500_3c_trace_roots.tsv`, then the trace should be rerun.
Do not automatically promote every `untraced_gap_start`; many are inline data,
alignment bytes, tables, or skipped-over instruction bytes.

## First Analysis Pass

1. Validate dump sizes against actual chip markings and programmer device type.
2. Check for all-`0x00`, all-`0xff`, repeated halves, stuck bits, or obvious
   byte-lane/address-line swaps.
3. Disassemble the 32 KB program PROM with `upd7810`.
4. Search the program PROM for immediate values and tables related to known
   memory-map registers:
   - `F001h`: external PROM select bit is mentioned in the technical manual.
   - `F000h`-region: gate array/head gate array I/O area.
   - Bank line manipulation for CG ROM windows.
5. Search the CG dumps for plausible glyph packing:
   - Draft face matrices: `9x23`, `9x16`.
   - LQ face matrices: `29x23`, `15x16`, proportional up to `39x23`.
   - User-defined character format uses left/body/right spacing plus two or
     three bytes per column; resident ROM may use a related but not identical
     encoding.
6. Correlate CG bank boundaries against firmware access patterns.
7. Render candidate glyphs and compare against printed samples/manual tables.

## Things We Know Are Not The Answer

- The LQ-500 manuals do not publish per-glyph ROM byte contents.
- IBMulator's printer emulation and the 1541 Ultimate MPS Emulator do not
  contain a Proprinter III ROM dump. They use shared emulator-native MPS
  chargen tables for Epson FX-80/JX-80, IBM Graphics Printer, IBM Proprinter,
  and Commodore MPS modes.
- That MPS data can be a 9-pin/FX-style reference, but it is not direct LQ-500
  24-pin LQ font data.

## Open Questions

- Exact chip markings and locations on the actual received board.
- Confirm whether `M25A10PA` is at `3C` and `M10A10LA` is at `4C`, or whether
  those markings were swapped in the board photo.
- Whether the ordered printer has an optional font module installed.
- Whether there are regional firmware/font variants.
- Whether `4M CG` and `1M CG` are both populated in any LQ-500 variants or are
  partly address-decoder support for options.
- Whether the unpopulated `5C` `MASK IMPROM` footprint is for alternate CG ROM
  capacities, optional ROM, or factory/model variants.
- Whether the resident CG encoding is column-major, row-major, split high/low
  pin-plane, banked by font, banked by character table, or compressed.
- Whether proportional spacing data is stored adjacent to glyph bitmaps or in
  separate firmware tables.

## Useful Manual Facts

- Resident fonts: Draft, Roman, Sans Serif.
- Optional module fonts: Courier, Prestige, Script, OCR-B, and in `#7407`
  also OCR-A, Orator, Orator-S.
- Built-in LQ family numbers for `ESC k`: Roman `0`, Sans Serif `1`.
- Optional `ESC k` values: Courier `2`, Prestige `3`, Script `4`, OCR-B `5`,
  OCR-A `6`, Orator `7`, Orator-S `8`.
- Download buffer: 6 KB. Downloading is ignored when DIP SW2-5 selects the
  8 KB input buffer.
- Character-cell fields in the manual: left space `a0`, face width `a1`,
  right space `a2`, character width `cw`.

## Resume Checklist

When resuming:

1. Put dumps under `roms/`.
2. Fill out `data/rom_dump_manifest.json` from the template.
3. Generate checksums and disassembly for the program PROM.
4. Add a quick dump-integrity note to this file.
5. Start CG structure discovery from the populated socketed ROMs first; do not
   assume `5C` exists unless the actual board has it populated.
