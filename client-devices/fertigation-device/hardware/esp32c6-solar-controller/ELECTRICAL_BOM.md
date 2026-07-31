# Electrical BOM

Status: released Rev A prototype electrical BOM for the KiCad schematic and
PCB. Exact MPN, LCSC code, and selection reasoning are recorded in
[PART_SELECTION.md](PART_SELECTION.md). Optional `5V_ACT` entries remain DNP;
the released Rev A assembly is 12 V output only.
This document covers parts mounted on the controller PCB or directly wired as
part of its electrical assembly. Enclosure, panel connectors, mounting
hardware, and cable glands are listed separately in
[ENCLOSURE_BOM.md](ENCLOSURE_BOM.md).

## JLCPCB PCBA policy

Revision 1 is designed for JLCPCB mixed-technology assembly:

- use SMT parts for logic, RS485, gate drivers, protection, and passive parts;
- place SMT parts on the top side where practical;
- use THT only for high-current pluggable terminals, replaceable fuse holders,
  the XIAO sockets, and parts whose thermal/service requirements justify it;
- allow JLCPCB wave/manual assembly for selected THT catalog parts;
- verify every manufacturer part number and JLCPCB/LCSC part number again
  immediately before ordering because stock and assembly classification change;
- keep `Comment`, `Designator`, `Footprint`, manufacturer part number, and
  JLCPCB/LCSC part number consistent between the KiCad schematic, BOM, and CPL;
  and
- mark every optional part explicitly as `DNP` instead of relying on an empty
  value.

The release package includes JLCPCB-formatted BOM and CPL CSV files plus a
separate post-assembly BOM. The human-readable tables below explain the
engineering intent; `exports/assembly/procurement-bom.csv` is the order list.

Point-to-point prototype procurement:
[ELECTRICAL_PROCUREMENT.csv](ELECTRICAL_PROCUREMENT.csv).
PCB assembly procurement:
[`exports/assembly/procurement-bom.csv`](exports/assembly/procurement-bom.csv).

## Minimum point-to-point wiring

```text
POWER IN 3 pin
  pin 1 +12 V ───────────────────────────────────────── +12 V bus
  pin 2 GND  ────────────────────────────────────────── GND bus
  pin 3 NC

+12 V bus ──┬── DCDC IN+
            ├── LOAD 1+ ... LOAD 5+
            ├── TTL-RS485 VCC
            └── RS485 connector pin 1 (+12 V), all ports

GND bus  ───┬── DCDC IN-
            ├── MOSFET Source 1 ... 5
            ├── TTL-RS485 GND
            └── RS485 connector pin 3 (GND), all ports

DCDC OUT+ 5 V ───────────────────────────────────── XIAO 5V
DCDC OUT- GND ───────────────────────────────────── XIAO GND

Per MOSFET output:
  XIAO GPIO ── 100 ohm ── Gate
                             |
                           47 kohm
                             |
  GND ───────────────────── Source
  LOAD- ─────────────────── Drain

  1N4001: K=LOAD+ / A=Drain

RS485:
  XIAO TX ────────── TTL-RS485 RXD
  XIAO RX ────────── TTL-RS485 TXD
  TTL-RS485 A ────── RS485 connector pin 2, short internal parallel wiring
  TTL-RS485 B ────── RS485 connector pin 4, short internal parallel wiring
```

## 1. Controller

| Designator/group | Qty | Part or requirement | Mounting | Status |
|---|---:|---|---|---|
| `U1` | 1 | Seeed Studio XIAO ESP32-C6 | Socketed module | Selected |
| `J_U1A`, `J_U1B` | 2 | 1x7, 2.54 mm female socket header | THT | Selected format |
| `U2` | 1 | Microchip `MCP23017T-E/SO`, LCSC `C629440`, 16-bit I/O expander | SOIC-28, SMT | Selected |
| `R_I2C1`, `R_I2C2` | 2 | 4.7 kohm I2C pull-up | 0603 or 0805, SMT | Initial value |
| `C_U2` | 1 | 100 nF X7R MCP23017 decoupling | 0603 or 0805, SMT | Selected value |
| `C_3V3_BULK` | 1 | 10 uF 3.3 V rail bulk capacitor | 0805/1206, SMT | Initial value |
| `R_INT` | 1 | MCP23017 interrupt pull-up, 10 kohm | 0603, SMT | Selected initial value |
| `TP_*` | 12+ | SMD test pads plus selected loop test points | SMT/THT mixed | Selected format |

The XIAO USB-C connector, BOOT button, RESET button, and antenna end remain
accessible after assembly.

## 2. Generic RS485 field terminals

One transceiver serves one RS485 bus exposed at three parallel connection
points. No soil, PAR, or other device type is assigned in hardware. Do not
populate one transceiver per connected device. The plug-in converter module is
replaced by a board-mounted 3.3 V transceiver.

| Designator/group | Qty | Part or requirement | Mounting | Status |
|---|---:|---|---|---|
| `U3` | 1 | TI `THVD1410DR`, LCSC `C2671345`, 3.3 V, 500 kbps half-duplex RS485 transceiver | SOIC-8, SMT | Selected |
| `C_U3` | 1 | 100 nF X7R local decoupling | 0603 or 0805, SMT | Selected value |
| `R_TX`, `R_RX` | 2 | UART series resistor footprints | 0603, SMT | 0 ohm initial |
| `R_DE_PD` | 1 | `DE`/`/RE` direction-control pull-down | 0603, SMT | 47 kohm initial |
| `J2` | 1 | `RS485 PORT 1`: Phoenix `1757268`; plug `1757035`; `12V_FIELD`, `GND`, `A`, `B` | 4-pin pluggable THT terminal | Selected |
| `J3` | 1 | `RS485 PORT 2`: Phoenix `1757268`; plug `1757035`; same pin order | 4-pin pluggable THT terminal | Selected |
| `J4` | 0 or 1 | `RS485 PORT 3`: Phoenix `1757268`; plug `1757035`; same pin order | 4-pin pluggable THT terminal | Optional/DNP |
| `R_TERM` | 1 | 120 ohm, 1% RS485 termination | 0805 or 1206, SMT | Selected value |
| `JP_TERM` | 1 | Termination enable header and shunt | 1x2, 2.54 mm THT | Selected |
| `R_BIAS_A`, `R_BIAS_B` | 2 | 680 ohm, 1% RS485 fail-safe bias resistor footprints | 0805, SMT | DNP initial |
| `R_AB1`, `R_AB2` | 2 | 10 ohm pulse-proof series resistors | 0603, SMT | TI surge-protection starting point |
| `D_RS485` | 1 | Bourns `CDSOT23-SM712`, LCSC `C404012`, bidirectional RS485 TVS | SOT-23, SMT | Selected |
| `F_FIELD` | 1 | Bourns `MF-MSMF075/24-2`, LCSC `C208467`, 0.75 A hold / 1.5 A trip | 1812, SMT | Shared protection for `12V_FIELD`; not software switched |
| `C_RS485_BULK` | 1 | Nichicon `UHE1E470MDD`, LCSC `C134230`, 47 uF 25 V | THT D5 x 11 | Selected |

Connect XIAO `D6/TX` to `D`, `D7/RX` to `R`, and tie `DE` and active-low
`/RE` to `D8`. The external pull-down makes reset default to receive mode with
the driver disabled. XIAO `D1` and `D9` are unassigned in revision 1.

Revision 1 is non-isolated RS485 and carries a common `GND` with `A` and `B`.
Cable length, grounding, and surge environment must be reviewed before release.
If connected devices can sit at a materially different ground potential, replace this
section with an isolated transceiver and isolated field-side power rather than
silently fitting an unisolated substitute.

## 3. PCB power input and rails

The external solar controller handles panel and battery charging. The PCB takes
power from its protected `LOAD` output.

| Designator/group | Qty | Part or requirement | Mounting | Status |
|---|---:|---|---|---|
| `J1` | 1 | Phoenix `PC 5/2-G-7,62` (`1720466`), plug `1718481`, 32 A nominal | THT/wave assembly | Selected; custom 6-solder-pin footprint |
| `F_IN` | 1 | Littelfuse `178.6165.0001` PCB ATO holder + `0257020.PXPV` 20 A fuse | THT/manual | Selected initial value; final coordination from inrush and wire protection |
| `Q_RPOL` | 1 | TI `CSD18540Q5B`, LCSC `C86513`, 60 V N-MOSFET | DNK 5 x 6 mm power SMT | Selected; thermal land pattern review required |
| `U_RPOL` | 1 | TI `LM74610QDGKRQ1`, LCSC `C2649431`, ideal-diode/reverse-polarity controller | DGK VSSOP-8, 3 x 5 mm, SMT | Selected; manufacturer land pattern implemented |
| `C_RPOL` | 1 | Samsung `CL21B225KOFNNNE`, LCSC `C28234`, 2.2 uF 16 V X7R charge-pump capacitor | 0805, SMT | Selected |
| `C_RPOL_FILTER` | 1 | Samsung `CL10C101JB8NNNC`, LCSC `C14858`, 100 pF 50 V C0G | 0603, SMT | Selected |
| `D_TVS_IN` | 1 | Littelfuse `SMBJ18A`, LCSC `C151256` | SMB power SMT | Selected if charger LOAD steady maximum is <=16 V |
| `C_IN_BULK` | 1 | Nichicon `UHE1V471MPD`, LCSC `C116237`, 470 uF 35 V | THT D10 x 20 | Selected |
| `C_IN_HF` | 1 | 100 nF input high-frequency bypass | 0603 or 0805, SMT | Selected value |
| `U4` | 1 | Diodes Inc. `AP63205WU-7`, LCSC `C2071056`, fixed 5 V / 2 A buck | TSOT23-6, SMT | Selected |
| `L1` | 1 | Bourns `SRP5030TA-4R7M`, LCSC `C2047088`, 4.7 uH | Shielded 5 x 5 mm SMT | Selected |
| `C_BUCK_IN` | 1 | Samsung `CL31B106KBHNNNE`, LCSC `C89632`, 10 uF 50 V X7R | 1206, SMT | Selected |
| `C_BUCK_OUT` | 2 | Samsung `CL31B226KPHNNNE`, LCSC `C87996`, 22 uF 10 V X7R | 1206, SMT | Selected |
| `C_BOOT` | 1 | 100 nF 16 V X7R | 0603, SMT | Selected value |
| `F_5V_LOGIC` | 1 | Bourns `MF-NSMF075-2`, LCSC `C89653`, 0.75 A hold PTC | 1206, SMT | Selected |
| `C_5V_BULK` | 1 | Samsung `CL31B226KPHNNNE`, 22 uF 10 V X7R | 1206, SMT | Selected |
| `R_BAT_TOP`, `R_BAT_BOTTOM` | 2 | 150 kohm / 27 kohm, 1%, battery ADC divider | 0603, SMT | Selected initial values; 18 V -> approx. 2.75 V |
| `R_BAT_SER` | 1 | 1 kohm ADC series protection resistor | 0603, SMT | Selected |
| `C_BAT_ADC` | 1 | 100 nF X7R ADC RC filter capacitor | 0603, SMT | Selected |
| `D_BAT_CLAMP` | 1 | Nexperia `BAT54S,215`, LCSC `C47546`, dual Schottky ADC clamp | SOT-23, SMT | Selected |
| `LED_12V`, `LED_5V` | 0 or 2 | Rail indicators with resistors | SMT | DNP for low-power build |

`5V_LOGIC` supplies only XIAO ESP32-C6, MCP23017, RS485 logic, and low-current
control circuits. It must not supply a pump.

## 4. Optional future 5 V actuator rail

The first prototype uses 12 V for all five actuators. These parts are not
populated unless a future hardware profile includes a 5 V actuator.

| Designator/group | Qty | Part or requirement | Mounting | Status |
|---|---:|---|---|---|
| `MOD_5V_ACT` | 0 or 1 | Separately fused high-current 5 V buck | THT module | DNP/TBD |
| `F_5V_ACT` | 0 or 1 | 5 V actuator rail fuse | THT | DNP/TBD |
| `C_5V_ACT` | 0 or 1+ | Actuator rail bulk capacitor | THT | DNP/TBD |

The optional `5V_ACT` rail is electrically distinct from `5V_LOGIC`.

## 5. Five repeated MOSFET output channels

The following parts are repeated for five electrically identical generic
outputs. The PCB labels them `MOSFET OUT 1` through `MOSFET OUT 5`; functional
roles are assigned by Runtime Config and wiring documentation. All five
first-assembly links select 12 V. Each direct DC load must be below 100 W. At
12 V this is below 8.33 A running current per channel; revision 1 targets 10 A
continuous capability per channel after PCB and enclosure thermal derating.
Startup and locked-rotor current are separate limits and still require
measurement.

| Designator pattern | Qty total | Part or requirement | Mounting | Status |
|---|---:|---|---|---|
| `Q_OUT1..5` | 5 | TI `CSD18540Q5B`, LCSC `C86513`, 60 V, max. 3.3 mOhm at 4.5 V gate | DNK 5 x 6 mm power SMT | Selected; thermal rating to validate |
| `U_GATE1..3` | 3 | Microchip `TC4427AEOA`, LCSC `C18690`, dual MOSFET gate driver | SOIC-8, SMT | Selected; one spare channel |
| `R_GATE1..5` | 5 | 22 ohm gate resistor | 0603, SMT | Selected initial value |
| `R_GS1..5` | 5 | 47 kohm gate-source pull-down | 0603, SMT | Selected |
| `F_OUT1..5` | 5 | Littelfuse `178.6165.0001` + ATO `0257010.PXPV` 10 A | THT/manual | Selected initial value; lower fuse allowed per load |
| `D_FLY1..5` | 5 | ST `STPS30SM60SG-TR`, LCSC `C2935135`, 60 V / 30 A Schottky | D2PAK power SMT | Selected; alternate `STPS30M60SG-TR` / `C2970011` |
| `D_TVS1..5` | 5 | Optional output TVS/snubber footprint | SMB power SMT | DNP until cable transient measurement |
| `LED_OUT1..5` | 0 or 5 | Output indicator and resistor | SMT | DNP for low-power build |
| `J10..14` | 5 | Phoenix `1720466`; plug `1718481`; 32 A nominal | High-current THT/wave assembly | Selected; custom footprint |
| `W_12V_1..5` | 5 fitted | High-current 12 V rail wire link | Large plated THT holes | Default fitted |
| `W_5V_1..5` | 5 DNP | Optional high-current 5 V rail wire link | Large plated THT holes | Do not fit in rev 1 |

Each connector carries fixed positive power and a MOSFET-switched negative
return:

| Channel | PCB terminal label | Current FGT default role |
|---|---|---|
| 1 | `MOSFET OUT 1` | Clean-water inlet |
| 2 | `MOSFET OUT 2` | A concentrate pump |
| 3 | `MOSFET OUT 3` | B concentrate pump |
| 4 | `MOSFET OUT 4` | Mixer |
| 5 | `MOSFET OUT 5` | Irrigation pump |

Do not select a MOSFET from its headline current alone. Approval requires
`RDS(on)` at the actual gate voltage, safe operating area, measured inrush,
thermal rise, copper temperature, connector rating, wire rating, and fuse
coordination.

Normal operation permits one energized 12 V MOSFET channel. The absolute limit
is two energized channels, so two loads just below 100 W total less than 200 W,
or about 16.7 A at 12 V. The shared board input and power path target 20 A
continuous after thermal derating. The released Phoenix PC 5 connectors are
32 A nominal, with final acceptance based on enclosure temperature and measured
voltage drop.

Never start two motors at the same instant. When two channels are required,
start the second only after the first load's inrush has decayed. The initial
allowed pairs are `A PUMP + MIXER` and `B PUMP + MIXER`; `A PUMP + B PUMP` is
always forbidden. Other pairs remain prohibited until a reviewed operating
sequence explicitly permits them.

Firmware must reject an activation that would exceed two channels and turn all
outputs off on any state-machine or output-register consistency fault. The
hardware master-enable chain still removes permission from every gate driver on
reset, emergency stop, leak, or watchdog failure.

## 6. Flow and safety inputs

| Designator/group | Qty | Part or requirement | Mounting | Status |
|---|---:|---|---|---|
| `J5` | 1 | Phoenix `1757255`; plug `1757022`; flow supply, pulse, GND | 3-pin pluggable THT terminal | Selected; default 12 V sensor supply |
| `U_FLOW` | 1 | TI `TLV7031DBVR`, LCSC `C2869832`, comparator front end | SOT-23-5, SMT | Selected for NPN/open-collector or dry contact |
| `R_FLOW_PULL`, `R_FLOW_SER`, `C_FLOW` | 3 | 10 kohm pull-up, 1 kohm series, 100 nF filter | 0603, SMT | Selected |
| `R_FLOW_REF1`, `R_FLOW_REF2` | 2 | 47 kohm / 47 kohm, 1.65 V comparator reference | 0603, SMT | Selected |
| `J6` | 1 | Phoenix `1757242`; plug `1757019`; tank-empty contact | 2-pin pluggable THT terminal | Selected |
| `J7` | 1 | Phoenix `1757242`; plug `1757019`; tank-full contact | 2-pin pluggable THT terminal | Selected |
| `J8` | 1 | Phoenix `1757242`; plug `1757019`; leak contact/safety loop | 2-pin pluggable THT terminal | Selected connector; NC contact required |
| `J9` | 1 | Phoenix `1757242`; plug `1757019`; normally-closed emergency-stop loop | 2-pin pluggable THT terminal | Selected |
| `R_IN_*` | 4 | 10 kohm pull-up | 0603, SMT | Selected initial value |
| `R_FILTER_*` | 4 | 1 kohm series resistor | 0603, SMT | Selected initial value |
| `C_FILTER_*` | 4 | 100 nF X7R debounce/noise capacitor | 0603, SMT | Selected initial value |
| `D_INPUT_*` | 4 | TI `TPD1E10B06DPYR`, LCSC `C48260`, cable-entry ESD | X1SON-2, SMT | Selected; exact land pattern review required |
| `U_MASTER` | 2 | TI `SN74AHCT08DR`, LCSC `C7480`, master-enable and per-output AND gates | SOIC-14, SMT | Selected |
| `R_MASTER_PD` | 1+ | Master and driver default-OFF pull-downs | 0603 or 0805, SMT | 47-100 kohm |

Emergency stop and leak remove gate-driver permission independently of
firmware. MCP23017 still reports their state to the device application.

## 7. Commissioning inputs after part selection

The major parts, schematic, and PCB are released for Rev A prototype ordering.
Provide or measure these values before energizing field loads:

1. Solar-controller exact model and measured minimum/maximum `LOAD` voltage.
2. Battery chemistry, operating range, maximum charger voltage, BMS current.
3. For each 12 V actuator: model, running current, startup/stall current,
   polarity, and cable length.
4. Flow sensor model, supply voltage, pulse output type, and cable length.
5. Safety switch contact types and cable lengths.
6. RS485 bus length, device count, baud rate, address plan, grounding, and
   cable type. Device models are not fixed by this PCB.
7. RS485 cable grounding, shield strategy, and whether galvanic isolation is
   required.

## 8. Electrical quantity summary

| Category | Quantity |
|---|---:|
| XIAO ESP32-C6 | 1 |
| MCP23017 | 1 |
| SMT RS485 transceiver | 1 |
| MOSFET output channels | 5 |
| Power-SMT MOSFETs | 5 |
| Dual gate-driver ICs | 3 |
| Output fuses | 5 |
| Pump/valve PCB terminals | 5 |
| RS485 PCB terminals | 2 required + 1 optional |
| Flow PCB terminal | 1 |
| Safety PCB terminals | 4 |
| Logic buck converter | 1 |
| Optional actuator 5 V converter | 0 in revision 1 |
