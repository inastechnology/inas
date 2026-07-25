import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "deployment"


class AppliancePolicyTest(unittest.TestCase):
    def test_device_ap_is_isolated_and_never_uses_shared_nat_mode(self):
        connection = (DEPLOYMENT / "networkmanager" / "inas-device-ap.nmconnection").read_text(encoding="utf-8")
        self.assertIn("mode=ap", connection)
        self.assertIn("ap-isolation=1", connection)
        self.assertIn("method=manual", connection)
        self.assertNotIn("method=shared", connection)
        self.assertIn("never-default=true", connection)

    def test_firewall_denies_device_forwarding_without_masquerade(self):
        rules = (DEPLOYMENT / "nftables" / "inas-edge-gateway.nft").read_text(encoding="utf-8")
        self.assertIn('iifname "wlan0" drop', rules)
        self.assertIn('oifname "wlan0" drop', rules)
        self.assertNotIn("masquerade", rules)
        self.assertNotIn("dnat", rules)

    def test_mosquitto_requires_credentials_and_scopes_device_topics(self):
        config = (DEPLOYMENT / "mosquitto" / "inas-edge-gateway.conf").read_text(encoding="utf-8")
        acl = (DEPLOYMENT / "mosquitto" / "acl").read_text(encoding="utf-8")
        self.assertIn("listener 1883 192.168.50.1", config)
        self.assertIn("allow_anonymous false", config)
        self.assertIn("password_file ", config)
        self.assertIn("acl_file ", config)
        self.assertIn("user ina-edge-gateway", acl)
        self.assertIn("topic read $SYS/broker/log/#", acl)
        self.assertIn("pattern write /%u/kinds/config/request", acl)
        self.assertNotIn("pattern read #", acl)

    def test_systemd_unit_uses_persistent_state_watchdog_and_hardening(self):
        unit = (DEPLOYMENT / "systemd" / "inas-edge-gateway.service").read_text(encoding="utf-8")
        for directive in (
            "Type=notify",
            "WatchdogSec=60",
            "StateDirectory=inas",
            "UMask=0077",
            "NoNewPrivileges=true",
            "ProtectSystem=strict",
            "ProtectKernelModules=true",
            "CapabilityBoundingSet=",
            "ReadWritePaths=/var/lib/inas",
        ):
            self.assertIn(directive, unit)

    def test_host_forwarding_is_disabled(self):
        sysctl = (DEPLOYMENT / "sysctl" / "90-inas-edge-gateway.conf").read_text(encoding="utf-8")
        self.assertIn("net.ipv4.ip_forward=0", sysctl)
        self.assertIn("net.ipv6.conf.all.forwarding=0", sysctl)


if __name__ == "__main__":
    unittest.main()
