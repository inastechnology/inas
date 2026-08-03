# FGT ESP32-C6 Solar Controller

Status: **development CAD only — not fabricated and not used by the current
FGT hardware**.

This directory contains an in-progress candidate design for a future dedicated
controller PCB. A physical board based on this design does not currently exist,
has not been assembled or electrically validated, and must not be treated as
the current FGT wiring or firmware pin contract. Generated ERC/DRC, Gerber,
BOM, CPL, and enclosure outputs show CAD consistency only; they are not evidence
of a manufactured or working device.

The current FGT firmware bring-up uses the direct-wired XIAO ESP32-C6 pin
contract in
[`../../docs/jp/minimal_wiring.md`](../../docs/jp/minimal_wiring.md).

## Design documents

- [BOM index](BOM_DRAFT.md)
- [Rev A 試作発注・組立ガイド](ORDERING.md)
- [主要部品の選定結果](PART_SELECTION.md) — 採用MPN、LCSC番号、定格根拠、
  ヒューズとコネクタの組み合わせ、発注前確認条件
- [部品仕様調査](COMPONENT_SPECIFICATIONS.md) — メーカー一次資料に基づく
  採用部品ごとの電気仕様、pinout、回路上の使用条件
- [Rev A 電気設計DR](ELECTRICAL_DESIGN_REVIEW.md) — 仕様照合結果、回路計算、
  今回の修正、試作後に必要な安全・熱・負荷試験
- [Electrical BOM](ELECTRICAL_BOM.md) — PCB実装部品、電源、RS485、
  MOSFET出力回路、基板上コネクタ
- [Electrical procurement worksheet](ELECTRICAL_PROCUREMENT.csv) —
  主要電子部品の仕様、メーカー型番、LCSC番号、一次資料、実装区分
- [Enclosure and assembly BOM](ENCLOSURE_BOM.md) — 防水筐体、外部コネクタ、
  ハーネス、取付金具、ラベル、シール材
- [Hydraulic and field BOM](HYDRAULIC_AND_FIELD_BOM.md) — 液肥タンク、
  ポンプ、配管、液面・漏水検知、水中コネクタの適用条件
- [Hydraulic procurement worksheet](HYDRAULIC_AND_FIELD_PROCUREMENT.csv) —
  メーカー、型番、購入先URL、単価、発注数の記入用CSV

## KiCad development design

Open [esp32c6-solar-controller.kicad_pro](esp32c6-solar-controller.kicad_pro)
with KiCad 10. The project contains the Rev A single-sheet A1 schematic and routed
`180 x 115 mm` four-layer PCB:

- 20 A shared 12 V input path with LM74610-Q1 reverse-polarity control;
- XIAO ESP32-C6 direct-GPIO control section;
- one board-mounted THVD1410DR RS485 interface with termination and TVS;
- PTC-protected 12 V field power and three generic parallel RS485 connectors;
- normally-closed leak and emergency-stop safety inputs;
- reset-safe hardware gate permission; and
- five individually fused low-side MOSFET output channels.

Related project files:

- [KiCad schematic](esp32c6-solar-controller.kicad_sch)
- [Local symbol library](INA.kicad_sym)
- [XIAO 24-pad SMD footprint](INA_ESP32C6.pretty/XIAO_ESP32C6_SMD_24P.kicad_mod)
- [Schematic PDF](exports/esp32c6-solar-controller.pdf)
- [Schematic layout preview](exports/review/schematic-a1-layout.png)
- [PCB top render](exports/review/pcb-top.png)
- [PCB isometric render](exports/review/pcb-isometric.png)
- [JLCPCB Gerber ZIP](exports/esp32c6-solar-controller-rev-a-gerbers.zip)
- [JLCPCB SMT BOM](exports/assembly/jlcpcb-smt-bom.csv)
- [JLCPCB SMT CPL](exports/assembly/jlcpcb-smt-cpl.csv)
- [Post-assembly BOM](exports/assembly/post-assembly-bom.csv)
- [Board-only STEP](exports/mechanical/controller-board-only-rev-a.step)
- [Final ERC](exports/erc-final.json)
- [Final DRC](exports/drc-final.json)
- [Connectivity netlist](exports/esp32c6-solar-controller.net.xml)

The schematic, local libraries, and release outputs are reproducible with:

```bash
python3 tools/generate_schematic.py
tools/export_release.sh
```

Running the generator overwrites the generated KiCad schematic, project,
symbol library, and XIAO footprint. Do not make GUI-only schematic edits and
then rerun the generator without first carrying those changes back into the
generator.

Validation status:

- opened and exported with KiCad CLI 10.0.5;
- ERC: zero errors and zero warnings;
- PCB DRC: zero violations and zero unconnected items;
- 121 schematic components and 72 named nets;
- 125 PCB footprints including four mounting holes and 72 PCB nets;
- 90 JLCPCB top-side SMT placements, 23 post-assembly parts, and 8 explicit
  DNP parts;
- every populated SMT part has MPN, footprint, and LCSC number; and
- PDF, Gerber, drill, BOM/CPL, assembly, DXF, SVG, and STEP exports generated.

The project-local symbols currently use passive electrical pin types. ERC
therefore verifies file integrity, grid placement, named connectivity,
unconnected-pin declarations, and library consistency, but it does not replace
an electrical review of driver direction, power-source conflicts, current
ratings, or fail-safe behavior.

Major active parts, power semiconductors, fuses, connector families, and
manufacturer land patterns are fixed in [PART_SELECTION.md](PART_SELECTION.md).
JLCPCB/LCSC stock, placement rotation, and package data are still checked in the
order preview. Charger voltage, actual motor inrush, enclosure temperature, and
field wiring are commissioning limits rather than reasons to leave the PCB
undefined.

## Product boundary

This CAD is a candidate future `FGT` hardware profile for a solar-powered
fertilizer mixing and irrigation controller. It is not the current prototype
hardware profile. If developed further, it is intended to keep the existing
FGT state machine, Runtime Config, status contract, and safety invariants while
using a directly soldered Seeed Studio XIAO ESP32-C6.
The module uses the official 24-pad SMD land pattern so its four underside GPIO
pads are available. The XIAO is consequently a reflow/hot-air service part
rather than a socket-replaceable module.

The physical board exposes five generic MOSFET outputs, one RS485 bus on three
parallel terminals, one flow-pulse input, and four contact inputs. The current
FGT Runtime Config maps those generic resources to:

- clean-water inlet valve or transfer pump;
- A concentrate dosing pump;
- B concentrate dosing pump;
- mixing/circulation pump;
- irrigation pump;
- inlet flow pulse;
- tank-empty and tank-full switches;
- leak and emergency-stop inputs; and
- RS485 devices selected for each installation.

No soil, PAR, or other sensor type is fixed in the PCB, connector name, or
electrical BOM. Device model, Modbus address, register map, and meaning belong
to deployment configuration and firmware/device-definition data.

The solar charger, battery BMS, main fuse, and battery disconnect are external
assemblies. The first enclosure may hold the off-board solar controller and
provide separate two-pin panel connectors for the solar panel and battery. The
controller PCB receives power only from the solar controller's protected load
output. This PCB does not charge an unknown battery chemistry.

## Prototype architecture

```text
solar panel -- 2-pin panel connector --+
                                        |
                                off-board solar controller
                                        |
battery ----- 2-pin panel connector ----+
                                        |
                                 protected LOAD output
                                        |
    +-- protected board input -----------------------------+
    |                                                      |
    +-- 12 V actuator distribution (optional 5V_ACT)       |
                                                           |
                              +----------------------------+
                              |
                     reverse-polarity protection
                              |
                +-------------+-------------------+
                |                                 |
           5 V logic buck                 PTC-protected 12 V field rail
                |                                 |
        XIAO ESP32-C6 direct GPIO         generic RS485 ports 1 / 2 / 3
                |
        safety-gated driver enables
                |
       five replaceable actuator drivers
```

The controller board repeats one safety-gated MOSFET channel per actuator.
Power-SMT MOSFETs, gate drivers, fuses, suppression devices, and connectors are
selected only after the real load voltage, running current, stall current, and
inrush measurements are approved. Revision 1 keeps each power channel
independently fused and testable instead of hiding it in a sealed power module.

## XIAO ESP32-C6 pin contract

| Function | XIAO pad | ESP32-C6 GPIO | Reset/safety rule |
|---|---|---:|---|
| Battery voltage ADC | `D0` / pad 1 | `GPIO0` | High-impedance divider; never exceed 3.3 V |
| Output command 1 | `D1` / pad 2 | `GPIO1` | External 47 kohm pull-down; boot default OFF |
| Inlet flow pulse | `D2` / pad 3 | `GPIO2` | Filtered input with defined pull state |
| Actuator master enable | `D3` / pad 4 | `GPIO21` | External pull-down; LOW disables all outputs |
| Output command 2 | `D4` / pad 5 | `GPIO22` | External 47 kohm pull-down; boot default OFF |
| Output command 3 | `D5` / pad 6 | `GPIO23` | External 47 kohm pull-down; boot default OFF |
| RS485 TX | `D6` / pad 7 | `GPIO16` | Direct 3.3 V UART connection |
| RS485 RX | `D7` / pad 8 | `GPIO17` | 3.3 V logic only |
| RS485 DE/RE | `D8` / pad 9 | `GPIO19` | External pull-down selects receive mode |
| Tank empty | `D9` / pad 10 | `GPIO20` | Filtered active-low input |
| Tank full | `D10` / pad 11 | `GPIO18` | Filtered active-low input |
| Output command 4 | `MTDI` / pad 15 | `GPIO5` | Strap pin held LOW by 47 kohm output pull-down |
| Leak status | `MTDO` / pad 16 | `GPIO7` | Filtered status input; hardware also removes permission |
| Output command 5 | `MTMS` / pad 19 | `GPIO4` | Strap pin held LOW by 47 kohm output pull-down |
| Emergency-stop status | `MTCK` / pad 20 | `GPIO6` | Filtered status input; hardware also removes permission |

The XIAO USB-C connector, BOOT button, and RESET button remain accessible after
installation. The XIAO antenna end must be located at a board and enclosure
edge, with no copper, battery, pump, cable bundle, or metal hardware in its
antenna keep-out region.

`GPIO4` and `GPIO5` are ESP32-C6 strapping pins sampled during reset. They are
used only for output commands because each one has a physical 47 kohm
pull-down, producing the required OFF/LOW boot state. They must never receive
an external pull-up. Production validation must include cold boot, reset, USB
download, and OTA restart tests with all five gates verified OFF.

The five direct commands retain the FGT default order: clean-water inlet,
A concentrate, B concentrate, mixer, and irrigation. They reach the gate
drivers only when the independent master-enable safety chain is valid.

Leak and emergency stop must also remove actuator permission in hardware. The
firmware reads and reports the same signals directly, but a crashed MCU or
incorrect output command cannot override the hardware disable.

This PCB requires a direct-GPIO firmware hardware profile matching the table
above.

## Implemented electrical sections

1. **Power input**
   - keyed battery connector;
   - replaceable board fuse;
   - reverse-polarity protection;
   - input TVS selected after the maximum charger voltage is known;
   - service power switch connector;
   - battery voltage divider with ADC protection;
   - 5 V buck sized for XIAO, RS485, control logic, and margin.
2. **Controller**
   - directly soldered XIAO ESP32-C6 using the official 24-pad SMD pattern;
   - accessible USB-C, BOOT, and RESET;
   - reset-safe pull-downs.
3. **Safety and I/O**
   - direct MCU GPIO for five commands and four contact inputs;
   - filtered dry-contact inputs;
   - hardware master-enable chain;
   - five fused generic 12 V low-side MOSFET outputs;
   - flow pulse input.
4. **RS485 field bus**
   - one board-mounted TI THVD1410DR 3.3 V, 500 kbps half-duplex transceiver
     for the complete bus;
   - SOIC-8 package for JLCPCB SMT assembly and prototype rework;
   - bus TVS and connector-side protection;
   - selectable 120 ohm termination;
   - optional bias footprints;
   - PTC-protected, non-switched 12 V field supply;
   - three parallel, numbered connectors carrying `A`, `B`, `GND`, and `12V`.
5. **Connectors and mechanical**
   - terminal labels identical to Hub output inventory;
   - mounting holes and keep-outs;
   - enclosure and cable-gland datum locations.

## Proposed external connectors

| Ref | Label | Signals |
|---|---|---|
| `J1` | `POWER FROM CHARGER LOAD` | `LOAD+`, `LOAD-` |
| `J2` | `RS485 PORT 1` | `12V_FIELD`, `GND`, `A`, `B` |
| `J3` | `RS485 PORT 2` | `12V_FIELD`, `GND`, `A`, `B` |
| `J4` | `RS485 PORT 3` | `12V_FIELD`, `GND`, `A`, `B` |
| `J5` | `FLOW` | sensor supply, `FLOW_PULSE`, `GND` |
| `J6` | `TANK EMPTY` | contact, common |
| `J7` | `TANK FULL` | contact, common |
| `J8` | `LEAK` | contact, common |
| `J9` | `EMERGENCY STOP` | normally-closed safety loop |
| `J10` | `MOSFET OUT 1` | `12V_ACT`, switched return |
| `J11` | `MOSFET OUT 2` | `12V_ACT`, switched return |
| `J12` | `MOSFET OUT 3` | `12V_ACT`, switched return |
| `J13` | `MOSFET OUT 4` | `12V_ACT`, switched return |
| `J14` | `MOSFET OUT 5` | `12V_ACT`, switched return |

The three RS485 connectors share one UART, one transceiver, and one A/B trunk;
they are connection points on one bus, not three independent interfaces.
Connected devices must use non-conflicting addresses and compatible serial
settings. Only the two physical ends of the trunk are terminated; a 120 ohm
resistor is not fitted at every connector. Keep stubs short and prefer a
daisy-chain cable layout for long field wiring.

`12V_FIELD` is protected by a shared 0.75 A hold PTC but is not switched or
assigned to a particular sensor. A device that requires power cycling can be
wired through one of the generic MOSFET outputs, subject to its voltage,
polarity, flyback, and current requirements.

Each MOSFET connector carries 12 V positive and a low-side switched return.
The PCB has no pump or valve function printed into these five channels. Each
direct DC load must be below 100 W, corresponding to less than 8.33 A running
current at 12 V. The channel design target is 10 A continuous after thermal
derating; startup and locked-rotor current remain separate verification items.

The candidate PCB mapping is:

| Physical output | Runtime role |
|---|---|
| `MOSFET OUT 1` | Clean-water inlet |
| `MOSFET OUT 2` | A concentrate pump |
| `MOSFET OUT 3` | B concentrate pump |
| `MOSFET OUT 4` | Mixer |
| `MOSFET OUT 5` | Irrigation pump |

Normal operation energizes one 12 V MOSFET channel. The absolute interlock
limit is two channels, so the maximum steady load is below 200 W or about
16.7 A at 12 V. The shared input path targets 20 A continuous after thermal
derating, and its Phoenix PC 5 connector is rated 32 A nominal.

The initial two-channel exceptions are `A PUMP + MIXER` and
`B PUMP + MIXER`. `A PUMP + B PUMP` is always forbidden. Two motors are never
started simultaneously; the second channel may start only after the first
channel's inrush interval. Any other pair requires an explicitly reviewed
sequence. A request for a third active channel is rejected and treated as a
fault.

The footprint may support a future `5V_ACT` rail, but it is separate from
`5V_LOGIC`. Each channel uses a high-current through-hole assembly link between
`OUTx+` and either `12V_ACT` or optional `5V_ACT`. The link is soldered during
assembly, is not accessible from outside the enclosure, and its voltage is
printed on the terminal label. Do not pass pump current through a 2.54 mm
configuration jumper, and never connect a pump to the XIAO logic supply.

## PCB and enclosure baseline

- Four-layer PCB: signal / solid ground / power / signal.
- JLCPCB mixed-technology PCBA is the manufacturing baseline.
- Logic, RS485, protection, gate drivers, and power MOSFETs use top-side SMT
  where practical; high-current terminals and serviceable fuses may use
  JLCPCB-supported THT/wave assembly.
- KiCad properties retain manufacturer and JLCPCB/LCSC part numbers, and the
  release package includes matching JLCPCB BOM and CPL files.
- Pluggable terminal blocks at the enclosure cable-entry edge.
- XIAO antenna and USB at the opposite edge.
- Logic and RS485 separated from pump wiring and driver heat.
- Four mounting holes outside the XIAO antenna keep-out.
- Released board outline: 180 mm x 115 mm with four M3 holes on
  172 mm x 107 mm pitch. This is approximately 33% less board area than the
  superseded 220 mm x 140 mm layout while preserving connector service space.
- Baseline enclosure: Takachi `BCPR304012S`, IP65 polycarbonate box with outdoor
  roof, and `BMP3040Z` 265 mm x 365 mm internal mounting plate.
- The reference off-board solar controller image is approximately
  134 mm x 70 mm, with approximately 126 mm x 50 mm mounting-hole spacing.
  If it is mounted inside the same enclosure, reserve a separate mounting area
  and finger clearance for all six screw terminals.
- Enclosure CAD is produced separately from KiCad and references the PCB STEP
  export, terminal heights, USB service clearance, and cable-gland locations.

## Required safety behavior

- All actuator outputs are OFF at boot, reset, OTA, sleep, missing controller,
  and invalid configuration.
- A and B cannot be active together.
- A or B requires mixing to be active.
- Water inlet and irrigation cannot be active together.
- Emergency stop and leak remove driver permission without firmware action.
- The PTC-protected RS485 field rail cannot remove power from the controller.
- A failed or disconnected RS485 device is reported according to its configured
  device definition and cannot silently approve unattended fertilizer dosing.
- Interrupted batches never resume automatically.
- The first fertilizer run follows successful water-only tests and measured
  pump/flow calibration.

## Required measurements before field commissioning

If a future PCB is fabricated from this CAD, it can remain sensor-model
independent because the RS485 and MOSFET ports are generic. The following
values must be measured before that future board is connected to real loads,
fertilizer, or unattended outdoor operation:

1. Battery chemistry and configuration:
   - 4S LiFePO4, 12 V lead-acid, 3S Li-ion, or another pack;
   - normal operating range;
   - maximum charger voltage;
   - BMS continuous and peak current.
2. Solar panel and external charge-controller model.
3. For each of the five actuators:
   - model number;
   - nominal voltage;
   - running current;
   - startup or stall current;
   - whether the input is a dry-contact/logic enable or a direct DC load.
   - all five currently planned pumps are 12 V and below 100 W;
   - confirm measured current, inrush, and polarity before selecting the shared
     12 V power stage;
   - normal operation permits one active channel;
   - the absolute limit is two active channels, initially only
     `A PUMP + MIXER` or `B PUMP + MIXER`;
   - simultaneous motor starts and `A PUMP + B PUMP` are prohibited.
4. Flow sensor model, supply voltage, and pulse output type.
5. Tank-empty, tank-full, leak, and emergency-stop contact types and cable
   lengths.
6. Expected RS485 bus length, device count, baud rate, address plan, and cable
   type. Individual device models remain deployment configuration rather than
   PCB assumptions.
7. Required enclosure rating, mounting method, connector direction, and
   preferred off-the-shelf enclosure.
8. RS485 grounding/shielding strategy and whether field conditions require
   galvanic isolation.

## Official design references

- Seeed Studio XIAO ESP32-C6 pin map and power notes:
  <https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/>
- Seeed Studio official XIAO KiCad footprint archive:
  <https://files.seeedstudio.com/wiki/XIAO-KiCad-Library/New_XIAO_Series_Footprints.zip>
- Espressif ESP32-C6 GPIO and strapping-pin notes:
  <https://docs.espressif.com/projects/esp-idf/en/stable/esp32c6/api-reference/peripherals/gpio.html>
- Espressif ESP32-C6 hardware design guidelines:
  <https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c6/index.html>
- TI THVD1410 product page and datasheet:
  <https://www.ti.com/product/THVD1410>
- JLCPCB KiCad 10 BOM/CPL export guidance:
  <https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad>
- JLCPCB mixed SMT/THT assembly FAQ:
  <https://jlcpcb.com/help/article/pcb-assembly-faqs>
- Existing FGT requirements:
  [../../docs/requirements.md](../../docs/requirements.md)
- Existing FGT hardware and power contract:
  [../../docs/hardware_and_power.md](../../docs/hardware_and_power.md)
- Existing FGT verification plan:
  [../../docs/verification_plan.md](../../docs/verification_plan.md)
