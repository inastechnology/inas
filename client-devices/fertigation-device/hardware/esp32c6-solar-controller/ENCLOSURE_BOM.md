# Enclosure and Harness BOM

Status: minimum Rev A enclosure, panel-connector, and harness baseline.
Prices, purchase URLs, model numbers, and scaling quantities are maintained in
[ENCLOSURE_PROCUREMENT.csv](ENCLOSURE_PROCUREMENT.csv). System-level electrical
modules are listed in
[ELECTRICAL_PROCUREMENT.csv](ELECTRICAL_PROCUREMENT.csv). PCB design details
are outside this minimum procurement view.

## 1. Controller enclosure

| Item | Qty/controller | Selection |
|---|---:|---|
| Enclosure | 1 | Takachi `BCPR304012S`, IP65 polycarbonate, 300 x 400 x 120 mm |
| Internal mounting plate | 1 | Takachi `BMP3040Z`, 265 x 365 x 1.6 mm |
| External mounting feet | 1 set | Takachi `BFL-2S` |
| Controller-module mounting hardware | 1 set | M3 standoffs, screws, washers, locking parts, and optional DIN-rail adapters selected after receiving the modules |

Mechanical release files:

- [Mounting plate DXF](enclosure/bmp3040z-mounting-plate-rev-a.dxf)
- [Connector cutout coupons](enclosure/connector-cutout-coupons-rev-a.dxf)
- [Five-output panel reference](enclosure/output-panel-cutouts-rev-a.dxf)
- [Mechanical dimensions](enclosure/mechanical-dimensions.csv)
- [Mounting layout preview](exports/mechanical/bmp3040z-mounting-plate-rev-a.svg)

Drill the received enclosure only after checking the wall taper, moulded ribs,
lid gasket, connector nut clearance, and cable bend radius. Test each connector
family on a cutout coupon before making the final panel.

## 2. Power input and MOSFET outputs

Use Amphenol LTW X-Lok Middle C, 3-pin, 20 A connectors. Only two contacts carry
power; pin 3 is reserved and must remain unconnected. Opposite panel-contact
genders distinguish the controller power input from switched outputs.

| Connection | Controller panel | Cable connector | Optional device panel | Optional device cable end | Pin assignment |
|---|---|---|---|---|---|
| `POWER IN` | `CC-03RMMS-QC800P` | `CC-03BFFB-QL8LPP` | - | - | 1=`+12V IN`, 2=`GND`, 3=`NC` |
| `MOSFET OUT 1..5` | `CC-03RMFS-QC800P` | `CC-03BFMB-QL8LPP` | `CC-03RMMS-QC800P` | `CC-03BFFB-QL8LPP` | 1=`+12V`, 2=`SW_RETURN`, 3=`NC` |

`SW_RETURN` is the MOSFET-switched low-side return. It is not an always-on
ground and must not be bonded to enclosure GND outside the controller PCB.

The optional device-panel pair is used only when a pump or other load can be
safely modified. If the equipment has a moulded lead that should remain intact,
connect the two-core output cable to that lead using an appropriately rated
sealed method and omit the device-panel connector pair.

Use the matching `CAP-WACMQMA1` cap on each normally disconnected X-Lok panel
receptacle.

## 3. RS485 ports

Use M12 A-coded 4-pin connectors. The controller provides two physical ports
on one shared, non-isolated RS485 bus.

| Position | Qty/controller | Selection |
|---|---:|---|
| Controller panel socket with 0.5 m flying leads | 2 | Phoenix Contact `1237436` |
| Controller-side cable plug | 2 | Phoenix Contact `1413993` |
| Device-side cable socket | Up to 2 | Phoenix Contact `1413994`; omit for a terminal-block device |
| Optional device panel inlet | Up to 2 | Phoenix Contact `1239274`; only for a self-built device |
| Unused controller-port cap | 2 | Phoenix Contact `1560251` |

All four connectors use the same assignment:

| Pin | Signal |
|---:|---|
| 1 | `+12V_FIELD` |
| 2 | `A` |
| 3 | `GND` |
| 4 | `B` |

The panel cutout is approximately 16.2 mm for the M16 x 1.5 rear-mount body;
confirm it against the received connector and coupon before drilling.

## 4. Cables and internal wiring

| Harness | Minimum specification | Wiring rule |
|---|---|---|
| External `POWER IN` and MOSFET load cable | Fuji `2PNCT`, 2-core x 2.0 mm2, outside diameter about 11 mm | One core is positive; the other is `GND` or `SW_RETURN` according to the circuit |
| Internal power wiring | Flexible KIV-equivalent 2.0 mm2, red and black | Red is positive. Black from a MOSFET output is `SW_RETURN`, not enclosure GND |
| RS485 external cable | Belden `3107A`, 120 ohm, two twisted pairs, shielded, 22 AWG | Put `A/B` on the same pair and `+12V_FIELD/GND` on the other pair |

RS485 must use a twisted pair for `A/B`. Do not use one conductor from each
pair. The cable shield/drain is not signal GND. Insulate it at the field-device
end and bond it at the controller end only after the enclosure functional-earth
strategy is defined.

Crimp or terminate stranded conductors with the connector manufacturer's
specified process. Mark both cable ends with the circuit name and pin number;
colour alone is not sufficient to distinguish `GND` from `SW_RETURN`.

## 5. Adding one MOSFET output

For one additional MOSFET output, the enclosure and harness increment is:

- one `CC-03RMFS-QC800P` controller panel receptacle;
- one `CC-03BFMB-QL8LPP` controller-side cable plug;
- one additional two-core load cable run;
- one red/black internal wire pair;
- one `CAP-WACMQMA1` panel cap; and
- if the load itself receives a panel inlet, one `CC-03RMMS-QC800P` plus one
  `CC-03BFFB-QL8LPP`.

These quantities appear directly in the `add_one_mosfet_quantity` column of
[ENCLOSURE_PROCUREMENT.csv](ENCLOSURE_PROCUREMENT.csv). A sixth cutout also
requires a panel-layout and clearance review; it is not automatically covered
by the five-output DXF.
