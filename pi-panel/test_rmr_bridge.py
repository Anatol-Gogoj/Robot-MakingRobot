"""Unit tests for the operator panel button rules in rmr_bridge.py (issue #218).

Runs without a Pi, pyserial or websockets: both modules are stubbed before the import.
    python -m unittest pi-panel/test_rmr_bridge.py      (from the repo root)
"""

import asyncio
import json
import os
import sys
import types
import unittest

for _name in ("serial", "websockets"):
    if _name not in sys.modules:
        sys.modules[_name] = types.ModuleType(_name)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rmr_bridge as bridge  # noqa: E402


class FakeClient:
    def __init__(self, addr):
        self.remote_address = (addr, 50000)
        self.sent = []

    async def send(self, msg):
        self.sent.append(json.loads(msg))


class ButtonSpec(unittest.TestCase):
    def test_cmd_only(self):
        self.assertEqual(bridge.button_spec({"pin": 22, "cmd": "G28"}), ("G28", None))

    def test_action_only(self):
        self.assertEqual(bridge.button_spec({"pin": 16, "action": "start"}), (None, "start"))

    def test_cmd_and_action(self):
        self.assertEqual(bridge.button_spec({"pin": 25, "cmd": "M410", "action": "stop"}), ("M410", "stop"))

    def test_neither_is_refused(self):
        with self.assertRaises(ValueError):
            bridge.button_spec({"pin": 16})

    def test_unknown_action_is_refused(self):
        with self.assertRaises(ValueError):
            bridge.button_spec({"pin": 16, "action": "pause"})


class Loopback(unittest.TestCase):
    def test_addresses(self):
        for addr, want in (("127.0.0.1", True), ("::1", True), ("::ffff:127.0.0.1", True),
                           ("192.168.1.20", False), ("10.20.30.4", False), ("fe80::1%eth0", False),
                           ("?", False), ("", False)):
            self.assertEqual(bridge.is_loopback(FakeClient(addr)), want, addr)

    def test_no_remote_address(self):
        self.assertFalse(bridge.is_loopback(object()))


class Targets(unittest.TestCase):
    def setUp(self):
        self.panel = FakeClient("127.0.0.1")
        self.phone = FakeClient("192.168.1.20")

    def test_stop_goes_to_everyone(self):
        actors, err = bridge.button_targets("stop", [self.panel, self.phone])
        self.assertEqual(set(actors), {self.panel, self.phone})
        self.assertIsNone(err)

    def test_start_goes_to_the_panel_only(self):
        actors, err = bridge.button_targets("start", [self.panel, self.phone])
        self.assertEqual(actors, [self.panel])
        self.assertIsNone(err)

    def test_start_without_a_panel_page_is_refused(self):
        actors, err = bridge.button_targets("start", [self.phone])
        self.assertEqual(actors, [])
        self.assertIn("no panel page", err)

    def test_start_with_two_panel_pages_is_refused(self):
        actors, err = bridge.button_targets("start", [self.panel, FakeClient("::1"), self.phone])
        self.assertEqual(actors, [])
        self.assertIn("2 pages", err)

    def test_no_action(self):
        self.assertEqual(bridge.button_targets(None, [self.panel]), ([], None))

    def test_start_refused_while_another_page_is_busy(self):
        actors, err = bridge.button_targets("start", [self.panel, self.phone], lambda ws: ws is self.phone)
        self.assertEqual(actors, [])
        self.assertIn("another screen (192.168.1.20)", err)

    def test_busy_panel_itself_still_gets_start(self):
        # its own hold is the panel page's to resume
        actors, err = bridge.button_targets("start", [self.panel, self.phone], lambda ws: ws is self.panel)
        self.assertEqual(actors, [self.panel])
        self.assertIsNone(err)

    def test_stop_ignores_busy(self):
        actors, _ = bridge.button_targets("stop", [self.panel, self.phone], lambda ws: True)
        self.assertEqual(set(actors), {self.panel, self.phone})


class ClientMessages(unittest.TestCase):
    def tearDown(self):
        bridge.client_busy.clear()

    def test_state_is_recorded_and_not_gcode(self):
        ws = FakeClient("192.168.1.20")
        self.assertTrue(bridge.note_client_message(ws, '{"_rmr":"state","busy":true}'))
        self.assertTrue(bridge.client_busy[ws])
        self.assertTrue(bridge.note_client_message(ws, '{"_rmr":"state","busy":false}'))
        self.assertFalse(bridge.client_busy[ws])

    def test_other_brace_lines_never_reach_marlin(self):
        ws = FakeClient("192.168.1.20")
        self.assertTrue(bridge.note_client_message(ws, '{not json'))
        self.assertTrue(bridge.note_client_message(ws, '{"_rmr":"other"}'))
        self.assertNotIn(ws, bridge.client_busy)

    def test_gcode_passes(self):
        for line in ("G28", "M118 RMR:HOMED_ALL", "  M410"):
            self.assertFalse(bridge.note_client_message(FakeClient("::1"), line))


class WriteOrder(unittest.TestCase):
    """A button's pages hear of it after the command's echo and before its bytes leave."""

    def test_echo_dispatch_write(self):
        order = []

        class FakeSerial:
            is_open = True

            def write(self, data):
                order.append("write " + data.decode().strip())

        saved = (bridge.ser, bridge.schedule_broadcast)
        bridge.ser = FakeSerial()
        bridge.schedule_broadcast = lambda msg: order.append("broadcast " + json.loads(msg)["_rmr"])
        try:
            bridge.write_serial("M410", source="button:stop", before_write=lambda: order.append("dispatch"))
        finally:
            bridge.ser, bridge.schedule_broadcast = saved
        self.assertEqual(order, ["broadcast tx", "dispatch", "write M410"])


class Dispatch(unittest.TestCase):
    def run_dispatch(self, conns, name, cmd, action):
        async def go():
            bridge.clients.clear()
            bridge.clients.update(conns)
            bridge._dispatch_button(name, cmd, action)
            for _ in range(3):
                await asyncio.sleep(0)
        try:
            asyncio.run(go())
        finally:
            bridge.clients.clear()

    def test_start_asks_the_panel_and_informs_the_rest(self):
        panel, phone = FakeClient("127.0.0.1"), FakeClient("192.168.1.20")
        self.run_dispatch([panel, phone], "start", None, "start")
        self.assertEqual(panel.sent, [{"_rmr": "button", "name": "start", "cmd": None, "action": "start"}])
        self.assertEqual(phone.sent, [{"_rmr": "button", "name": "start", "cmd": None}])

    def test_refused_start_reports_to_everyone(self):
        phone = FakeClient("192.168.1.20")
        self.run_dispatch([phone], "start", None, "start")
        self.assertEqual(phone.sent[0], {"_rmr": "button", "name": "start", "cmd": None})
        self.assertEqual(phone.sent[1]["_rmr"], "error")
        self.assertNotIn("action", phone.sent[0])

    def test_stop_asks_everyone(self):
        panel, phone = FakeClient("127.0.0.1"), FakeClient("192.168.1.20")
        self.run_dispatch([panel, phone], "stop", "M410", "stop")
        for c in (panel, phone):
            self.assertEqual(c.sent, [{"_rmr": "button", "name": "stop", "cmd": "M410", "action": "stop"}])

    def test_plain_button_is_unchanged(self):
        panel = FakeClient("127.0.0.1")
        self.run_dispatch([panel], "home_all", "G28", None)
        self.assertEqual(panel.sent, [{"_rmr": "button", "name": "home_all", "cmd": "G28"}])


if __name__ == "__main__":
    unittest.main()
