import unittest

from ina_device_hub.device_output_capabilities import (
    device_output_capabilities,
    equipment_type_from_notes,
    equipment_types_for_role,
    infer_equipment_type,
    supported_output_ids,
)


class DeviceOutputCapabilitiesTest(unittest.TestCase):
    def test_watering_device_exposes_only_two_fixed_irrigation_outputs(self):
        outputs = device_output_capabilities("WTR")

        self.assertEqual([item["number"] for item in outputs], [1, 2])
        self.assertEqual([item["channel_mask"] for item in outputs], [1, 2])
        self.assertEqual([item["role"] for item in outputs], ["irrigation", "irrigation"])
        self.assertEqual(supported_output_ids("WTR"), {"irr1", "irr2"})

    def test_integrated_controller_adds_its_fixed_sensor_power_output(self):
        outputs = device_output_capabilities("WRS")

        self.assertEqual([item["number"] for item in outputs], [1, 2, 3])
        self.assertEqual(outputs[2]["role"], "sensor_power")
        self.assertEqual(outputs[2]["channel_mask"], 0)
        self.assertEqual(outputs[2]["terminal"], "SENSOR_12V_SW")

    def test_other_device_kinds_do_not_offer_configurable_outputs(self):
        self.assertEqual(device_output_capabilities("ENV"), [])
        self.assertEqual(supported_output_ids("SOI"), set())

    def test_irrigation_equipment_types_are_presented_as_guided_choices(self):
        choices = equipment_types_for_role("irrigation")

        self.assertEqual([choice["value"] for choice in choices], ["pump", "valve", "drip_line", "sprinkler"])
        self.assertEqual(choices[2]["label"], "点滴チューブ")

    def test_equipment_type_can_be_inferred_from_existing_names(self):
        self.assertEqual(infer_equipment_type("点滴チューブ A", role="irrigation"), "drip_line")
        self.assertEqual(infer_equipment_type("第1電磁弁", role="irrigation"), "valve")
        self.assertEqual(infer_equipment_type("A区画", role="irrigation"), "pump")
        self.assertEqual(infer_equipment_type("土壌ECセンサー", role="sensor_power"), "soil_sensor")

    def test_visual_type_token_is_read_without_disturbing_legacy_notes(self):
        self.assertEqual(equipment_type_from_notes("現地確認済み\nequipment_type=sprinkler"), "sprinkler")
        self.assertEqual(equipment_type_from_notes("現地確認済み"), "")


if __name__ == "__main__":
    unittest.main()
