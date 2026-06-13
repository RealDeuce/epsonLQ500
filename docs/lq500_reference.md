# Epson LQ-500 Extracted Reference

This is a reconstructed extraction from the manuals and chat notes after a
workspace loss. The earlier local file `lq500_techdoc.pdf` appears to correspond
to the recovered `epsonlq-500servicemanual.pdf`, commonly titled
`LQ-500 / L-1000 Technical Manual` or `Epson LQ-500 / L-1000 Service Manual`.

Primary local sources:

- `lq500_u1.pdf` - LQ-500 user manual.
- `epsonlq-500servicemanual.pdf` - LQ-500/L-1000 technical/service manual.
- `lq500_sl.pdf` - product specification sheet.
- `l1000_pg.pdf` - LQ-500/L-1000 product information guide.
- `lq500_ps.pdf` - product support bulletins.

PDF text extraction has OCR artifacts. Known corrections:

- `ESC O` is capital letter O, hex `4F`, for cancel skip-over-perforation.
- `ESC 0` is digit zero, hex `30`, for 1/8-inch line spacing.
- `ESC l` for left margin is lowercase letter `l`, hex `6C`.
- `0F` was sometimes rendered as `OF` in the extracted text for `SI`.
- Manuals include font samples and matrix diagrams, but not resident per-glyph
  ROM bytes.

## Printer Profile

- Model: Epson LQ-500.
- Language: Epson ESC/P.
- Print method: 24-pin serial impact dot matrix.
- Interface: parallel interface built in; optional interface boards supported.
- Text direction: bidirectional logic-seeking.
- Dot graphics and character graphics: unidirectional by default; graphics
  direction can be affected by DIP switch 2-6 and `ESC U`.
- Line spacing: 1/6 inch default; programmable in 1/180-inch increments.
- Input buffer: 1 KB or 8 KB, DIP-switch selectable.
- Download buffer: 6 KB. The technical manual says downloading is ignored when
  DIP SW2-5 selects the 8 KB input buffer.
- Ribbon: black cartridge `#7753`.

## Speed And Columns

| Pitch | Quality | Speed |
| --- | --- | --- |
| 10 cpi | Draft | 150 cps/line |
| 10 cpi | Letter Quality | 50 cps/line |
| 12 cpi | Draft | 180 cps/line |
| 12 cpi | Letter Quality | 60 cps/line |

| Pitch/style | Maximum columns |
| --- | ---: |
| 10 cpi | 80 |
| 10 cpi double-wide | 40 |
| 10 cpi condensed | 137 |
| 12 cpi | 96 |
| 12 cpi double-wide | 48 |
| 12 cpi condensed | 160 |
| 15 cpi | 120 |
| 15 cpi double-wide | 60 |
| Proportional | 68 maximum-width chars, 160 minimum-width chars |

## Font Set

Built-in fonts:

| Font | Available pitches | Notes |
| --- | --- | --- |
| Epson Draft | 10, 12, 15 cpi | High-speed draft. |
| Epson Roman | 10, 12, 15 cpi, proportional | Letter Quality. `ESC k 0`. |
| Epson Sans Serif | 10, 12, 15 cpi, proportional | Letter Quality. `ESC k 1`. |

Optional Multi-Font Module `#7407` adds:

| Font | Available pitches | `ESC k n` |
| --- | --- | ---: |
| Courier | 10, 12, 15 cpi | 2 |
| Prestige | 10, 12, 15 cpi | 3 |
| Script | 10, 12, 15 cpi | 4 |
| OCR-B | 10 cpi | 5 |
| OCR-A | 10 cpi | 6 |
| Orator | 10 cpi | 7 |
| Orator-S | 10 cpi | 8 |

Other compatible individual font modules identified in the technical manual:

| Catalog no. | Font |
| ---: | --- |
| 7400 | Courier |
| 7401 | Prestige |
| 7402 | Script |
| 7403 | OCR-B |

Font selection methods:

- SelecType cycles Draft, Roman, Sans Serif, and Slot. Slot is skipped if no
  optional module is installed.
- DIP switches 1-4 and 1-5 choose the default font.
- `ESC k n` selects the typestyle family.
- `ESC x n` selects Draft (`0`) or Letter Quality (`1`).

Default DIP font selection:

| Font | SW1-4 | SW1-5 |
| --- | --- | --- |
| Roman | OFF | OFF |
| Sans Serif | ON | OFF |
| Slot | OFF | ON |
| Draft | ON | ON |

Pitch DIP selection:

| Pitch | SW2-7 | SW2-8 |
| --- | --- | --- |
| 10 cpi | OFF | OFF |
| 12 cpi | ON | OFF |
| 15 cpi | OFF | ON |
| Proportional | ON | ON |

## Character Matrix And Cell Geometry

The product specification sheet summarizes resident matrix sizes as `9 x 23` in
Draft and `29 x 23` in Letter Quality. The technical manual provides the fuller
table:

| Printing mode | Face matrix | HDD | Character size H x V (mm) | Unit `ESC SP` |
| --- | --- | ---: | --- | ---: |
| Draft, 10 pitch | 9 x 23 | 120 | 1.9 x 3.2 | 120 |
| Draft, 12 pitch | 9 x 23 | 120 | 1.9 x 3.2 | 120 |
| Draft, 15 pitch | 9 x 16 | 120 | 1.0 x 2.3 | 120 |
| Draft, 10 pitch condensed | Reshaped | 240 | Reshaped | 120 |
| Draft, 12 pitch condensed | Reshaped | 240 | Reshaped | 120 |
| LQ, 10 pitch | 29 x 23 | 360 | 2.0 x 3.2 | 180 |
| LQ, 12 pitch | 29 x 23 | 360 | 2.0 x 3.2 | 180 |
| LQ, 15 pitch | 15 x 16 | 360 | 1.0 x 2.3 | 180 |
| LQ, 10 pitch condensed | Reshaped | 360 | Reshaped | 180 |
| LQ, 12 pitch condensed | Reshaped | 360 | Reshaped | 180 |
| LQ, proportional | Max 39 x 23, min 18 x 23 | 360 | Max 2.6 x 3.2, min 1.0 x 3.2 | 180 |
| LQ, proportional condensed | Reshaped | 360 | Reshaped | 180 |
| LQ, proportional super/subscript | Max 28 x 16, min 12 x 16 | 360 | Max 1.8 x 2.3, min 0.7 x 2.3 | 180 |
| LQ, proportional super/subscript condensed | Reshaped | 360 | Reshaped | 180 |

Notes:

- HDD means horizontal dot density in dots per inch.
- Face matrix and character size are maximum-character values.
- `ESC SP` units are minimum right-side spacing units.
- Condensed matrices are reshaped by firmware.

Character-cell geometry from the technical manual:

| Mode | Face width | Character width by pitch |
| --- | --- | --- |
| Draft normal | 9 dots | 12 dots at 10 pitch/120 dpi; 15 dots at 12 pitch/180 dpi; 16 dots at 15 pitch/240 dpi; 14 dots at condensed 10 pitch/240 dpi; 12 dots at condensed 12 pitch/240 dpi |
| LQ normal | 29 dots, except 15-dot firmware-reshaped 15 pitch/condensed LQ | 36 dots at 10 pitch/360 dpi; 30 dots at 12 pitch/360 dpi; 24 dots at 15 pitch/360 dpi; 21 dots at condensed 10 pitch/360 dpi; 18 dots at condensed 12 pitch/360 dpi |

The manual labels left space `a0`, face width `a1`, right space `a2`, and
character width `cw`. This describes glyph cell layout, not ROM contents.

## ROM And CG Memory Map

The technical manual says `CG = character generator` and describes these regions
in the 64 KB uPD7810HG CPU address space:

| Region | Location/size from manual | Notes |
| --- | --- | --- |
| Internal PROM | 32 KB, board location `3C` | Program PROM in lower address range. |
| External PROM | Selectable external PROM region | If correct external PROM is mounted, firmware can select it by writing bit 7 low at `F001h`. |
| 4M CG | Board location `5C`; label likely means 4 Mbit capacity class if populated | Character generator region banked into `8000h-A000h`; board photos suggest `5C` may be unpopulated. |
| 1M CG | Figure appears to show `4C`; text also refers to `2C`, conflicting with PSRAM | Character generator region banked into `8000h-A000h`; Figure 2-8 appears to assign populated `4C` to bank-selector values `40h..79h`. Treat board markings as authoritative. |
| External CG | External character-generator region | Used for cartridge/module CG data. |
| PSRAM | Board location `2C` | Used for buffers, including input/line/image/queue/download. |

The address decoder is in gate array `E01A05KA` at `6C`. Board photos show a
socketed `E01A05LC` at `6C`, likely the same gate-array family and not a ROM
dump target. It selects internal PROM, external PROM, `4MCG`, `1MCG`, external
CG, RAM, and the head gate array using `AB12`-`AB15` plus bank lines 7 and 6.

Board-photo notes from the chat:

- `2C` is clearly RAM.
- The partially obscured socket is almost certainly `3C`.
- The two visible ROM markings are `M25A10PA` and `M10A10LA`.
- Working hypothesis: `M25A10PA` is the `3C` 256 kbit / 32 KB program PROM.
- Working hypothesis: `M10A10LA` is the `4C` CG/font ROM candidate. The
  schematic reportedly identifies `4C` pin 1 as `A15`, so the stable
  `27C512@DIP28` read should be treated as a 64 KiB A16-low bank with valid
  low/high A15 halves rather than an invalid low-half artifact. The
  schematic/jumper trace shows `J5` tying pin 1 / `A15` to `BK2` on `6C`
  E01A05KA, `J6` wiring pin 20 `/CE`, and the hard-to-read `A16/OE` label now
  appears to be `A16` wired to `BK3`. Figure 2-8 appears to place `4C` in the
  CPU `8000h-A000h` window for bank-selector values `40h..79h`; this is a
  range, not two discrete `40h`/`80h` banks. Native T48 `AT27C011@DIP28` and
  `D27C011@DIP28` reads mirrored the A16-low bank, but patched custom PROM
  reads captured a distinct pin-22-high/A16-high bank and a full 128 KiB image.
- `5C` is an unpopulated footprint labeled `4M/2M/1M/256kbit MASK IMPROM`.

For the planned hardware dumps, see [`rom_dump_handoff.md`](rom_dump_handoff.md)
and [`../data/rom_dump_manifest.template.json`](../data/rom_dump_manifest.template.json).

## Character Sets And Tables

Character support:

- 96 standard ASCII characters.
- `ESC R` exposes USA plus 13 international variants, and Legal.
- Italic table or Epson Extended Graphics table for codes 128-255.
- Epson Extended Graphics contains accented characters, Greek characters,
  mathematical symbols, and line/box/shaded graphics.

International sets available through `ESC R n`:

| n | Set |
| ---: | --- |
| 0 | USA |
| 1 | France |
| 2 | Germany |
| 3 | United Kingdom |
| 4 | Denmark I |
| 5 | Sweden |
| 6 | Italy |
| 7 | Spain I |
| 8 | Japan |
| 9 | Norway |
| 10 | Denmark II |
| 11 | Spain II |
| 12 | Latin America |
| 13 | Korea |
| 64 | Legal |

First eight international sets by DIP switches:

| Set | SW1-1 | SW1-2 | SW1-3 |
| --- | --- | --- | --- |
| USA | ON | ON | ON |
| France | ON | ON | OFF |
| Germany | ON | OFF | ON |
| United Kingdom | ON | OFF | OFF |
| Denmark I | OFF | ON | ON |
| Sweden | OFF | ON | OFF |
| Italy | OFF | OFF | ON |
| Spain I | OFF | OFF | OFF |

Character table selection:

| Method | Values |
| --- | --- |
| DIP SW1-7 | ON = Epson Extended Graphics, OFF = Italic |
| `ESC t n` | `0` Italic, `1` Extended Graphics, `2` remap download chars 0-127 to 128-255 |

## DIP Switches

| Switch | Function | ON | OFF |
| --- | --- | --- | --- |
| 1-1..1-3 | International character set | See table above | See table above |
| 1-4..1-5 | Font selection | See table above | See table above |
| 1-6 | Condensed mode | Condensed | Normal |
| 1-7 | Character table | Graphic | Italic |
| 1-8 | Cut sheet feeder mode | ON | OFF |
| 2-1 | Page length | 12 inches | 11 inches |
| 2-2 | CSF page length | A4, 65 lines | Letter, 61 lines |
| 2-3 | Skip over perforation | ON | OFF |
| 2-4 | Auto line feed | ON | OFF |
| 2-5 | Input buffer capacity | 8 KB | 1 KB |
| 2-6 | Graphics print direction | Bidirectional allowed | Unidirectional |
| 2-7..2-8 | Character pitch | See table above | See table above |

Notes:

- With auto line feed on, each `CR` is accompanied by `LF`.
- Before defining user-defined characters, the manual says to set the input
  buffer to 1 KB.
- If SW2-6 is OFF, graphics printing remains unidirectional even if `ESC U 0`
  is received. If SW2-6 is ON, `ESC U 0` can select bidirectional graphics.

## Initialization Defaults

Initialization methods:

- Power on.
- INIT signal on parallel interface pin 31 goes LOW.
- Software: `ESC @`.

Important difference: `ESC @` resets font to the current SelecType setting.
Hardware initialization resets typestyle according to DIP switch defaults. `ESC
@` does not initialize the mechanism, clear the input buffer, or clear the
user-defined character set.

Default conditions after initialization:

| Item | Reset to |
| --- | --- |
| Top-of-form position | Current paper position |
| Left/right margins | Cancelled |
| Line spacing | 1/6 inch |
| Vertical tabs | Cleared |
| Horizontal tabs | Every eight characters |
| VFU channel | Channel 0 |
| Font selection | Hardware: DIP setting; software: current SelecType setting |
| Character pitch | Current DIP setting |
| Justification | Left |
| Special print effects | Cancelled |
| User-defined character set | Hardware: cleared; software: deselected only |
| Graphics assignment | `ESC K`=`ESC * 0`, `ESC L`=`ESC * 1`, `ESC Y`=`ESC * 2`, `ESC Z`=`ESC * 3` |

Power-on or INIT signal also clears the data buffer.

## Power-On Panel Modes

Manual-described button combinations:

| Held during power-on | Mode |
| --- | --- |
| LINE FEED/AUTO LOAD | Draft self-test |
| FORM FEED | Letter Quality self-test |
| LINE FEED/AUTO LOAD + FORM FEED | Data dump mode |
| ON LINE + FORM FEED + LINE FEED/AUTO LOAD | Bidirectional adjustment mode |

The service manual says the self-test prints the firmware revision first, then
the current DIP switch settings. Firmware tracing shows the selected settings
are printed in emphasized/bold mode, while the unselected alternatives remain in
normal weight.

Carriage motor speed modes from service manual Table 2-7:

| Carriage speed | Drive frequency | Phase-excitation method |
| --- | ---: | --- |
| x3 | 900 PPS | 2-2 phase |
| x2 | 600 PPS | 2-2 phase |
| x1.5 | 900 PPS | 1-2 phase |
| x1 | 600 PPS | 1-2 phase |

Tables 2-8 and 2-9 define the phase drive sequences for 2-2 and 1-2
excitation. Table 2-11 gives constant-speed timing: x3 and x1.5 use `1.11 ms`;
x2 and x1 use `1.66 ms`. Home-position seek is described separately, not as
x3 or x2: after power-on the printer uses the 2-2 excitation system for a
`20` or `30 ms` check interval, regardless of the normal phase-switching
timing.

Figure 2-44 gives the carriage distance mapping for normal 60 DPI characters
at 900 PPS: two phase switching times span `1/60` inch, with half-dot positions
at `120 DPI`. Thus one 2-2 carriage phase switch is `1/120` inch. In 1-2
excitation, the drive sequence has twice as many phase states for the same
motor cycle, so one 1-2 phase switch is `1/240` inch. The printing area starts
`22` phase-switching times after the home position; Figure 2-44 labels that
22-step left-side span as the acceleration area. In the 2-2 case shown there,
the acceleration area is `22/120` inch.

Paper-feed motor details from service manual Figure 2-47:

- The paper-feed motor is a 4-phase, 48-step stepper motor.
- Drive voltage is `24 VDC +10%`; coil resistance is `58 ohms +/- 7%` at
  `25 C`.
- Current is `1.1 A` max/rush, `0.30 A` typical while driving, and
  `0.06 A +/- 20 mA` while holding.
- The motor drive frequency is `400 PPS`, matching one phase switch every
  `2.5 ms`.
- It uses 2-2 phase excitation and open-loop CPU control.
- Each phase switch advances paper by `1/180` inch.
- `PB2` is the active-low paper-feed drive signal: low turns Q27 on and
  supplies `+24 V`; when not driven, `+5 V` is supplied through `R36`/`D11` to
  hold the motor.
- `PB3` is phase A/B and `PB4` is phase C/D.

Paper-feed 2-2 excitation sequence:

| Step | `PB3` | `PB4` | A phase | B phase | C phase | D phase |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | H | H | ON | OFF | ON | OFF |
| 1 | H | L | ON | OFF | OFF | ON |
| 2 | L | L | OFF | ON | OFF | ON |
| 3 | L | H | OFF | ON | ON | OFF |

The listed excitation order is clockwise and feeds paper forward.
Counterclockwise rotation feeds paper in reverse.

Paper-feed acceleration/deceleration timing:

| Stage | Set time |
| --- | --- |
| `tc1` | `3.33 ms` |
| `tc2` | `2.87 ms` |
| `tc3` | `2.65 ms` |
| `tc4` | `2.53 ms` |
| `t` | `2.50 ms` |

Deceleration uses the reverse timing order. Timing accuracy is `+200 us` /
`-50 us`. If the move is less than 10 steps, the speed is neither accelerating
nor decelerating.

## Command Set

The full command list is available as machine-readable data in
[`../data/lq500_commands.json`](../data/lq500_commands.json). It contains 77
commands across printer operation, data control, vertical/horizontal motion,
overall style, print width, enhancements, word processing, character tables,
user-defined characters, and graphics.

Graphics modes under `ESC *`:

| Mode | Pins | m | Horizontal dpi | Notes |
| --- | ---: | ---: | ---: | --- |
| Single-density | 8 | 0 | 60 | |
| Double-density | 8 | 1 | 120 | |
| High-speed double-density | 8 | 2 | 120 | Adjacent dots cannot print. |
| Quadruple-density | 8 | 3 | 240 | Adjacent dots cannot print. |
| CRT I | 8 | 4 | 40 | |
| CRT II | 8 | 6 | 90 | |
| Single-density | 24 | 32 | 60 | |
| Double-density | 24 | 33 | 120 | |
| CRT III | 24 | 38 | 90 | |
| Triple-density | 24 | 39 | 180 | |
| Hex-density | 24 | 40 | 360 | Adjacent dots cannot print. |

## External Source Check

IBMulator's printer emulation cites Rene Garcia's MPS Emulator from the 1541
Ultimate project. That source includes Epson FX-80/JX-80, IBM Graphics Printer,
IBM Proprinter, and Commodore MPS interpreters, but the bitmap data is a shared
MPS chargen (`chargen_draft`, `chargen_nlq_low`, `chargen_nlq_high`, and partial
italic tables), not a Proprinter III ROM dump and not direct LQ-500 font data.

## Support Bulletin Notes

LQ-500 group beep codes from support bulletin P-0076:

| Signal | Meaning |
| --- | --- |
| 1 beep | BEL code, 0.5 sec beep |
| 1 beep | Control panel setting accepted |
| 3 beeps | Paper end detected |
| 5 beeps | Abnormal carriage movement |
