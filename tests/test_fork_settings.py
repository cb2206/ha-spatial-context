"""Fork settings in storage.py: the spatial-engine defaults, and the old
`llm_tools_enabled` switch turning on the Spatial Context LLM API
(`llm_api_enabled`) until the next save drops it.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
import unittest

import stubs


class FakeStore:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, version, key) -> None:
        self.hass, self.key = hass, key

    async def async_load(self):
        return self.hass.stored.get(self.key)

    async def async_save(self, data) -> None:
        self.hass.stored[self.key] = data


stubs.new_package("sc_fork_settings_test")
stubs.stub("homeassistant")
stubs.stub("homeassistant.core", HomeAssistant=object)
stubs.stub("homeassistant.helpers")
stubs.stub("homeassistant.helpers.storage", Store=FakeStore)
stubs.load("sc_fork_settings_test", "const")
stubs.load("sc_fork_settings_test", "backup")
storage = stubs.load("sc_fork_settings_test", "storage")

KEY = "spatial_context.layout"


def _hass(settings):
    hass = stubs.FakeHass()
    hass.stored[KEY] = {"floors": {}, "settings": settings}
    return hass


class ForkSettingsTest(unittest.TestCase):
    def test_spatial_engine_defaults(self) -> None:
        settings = asyncio.run(storage.async_get_settings(_hass({})))
        self.assertEqual(settings["floor_height_m"], 3.0)
        self.assertEqual(settings["rf_path_loss_exponent"], 2.0)
        self.assertEqual(settings["rf_slab_loss_db"], 13)
        self.assertFalse(settings["llm_api_enabled"])
        self.assertNotIn("llm_tools_enabled", settings)

    def test_the_old_switch_turns_the_api_on(self) -> None:
        hass = _hass({"llm_tools_enabled": True, "floor_height_m": 2.7})
        settings = asyncio.run(storage.async_get_settings(hass))
        self.assertTrue(settings["llm_api_enabled"])
        self.assertNotIn("llm_tools_enabled", settings)
        self.assertEqual(settings["floor_height_m"], 2.7)
        # A save of what was read drops the old key from storage.
        asyncio.run(storage.async_save_settings(hass, settings))
        self.assertNotIn("llm_tools_enabled", hass.stored[KEY]["settings"])
        self.assertTrue(hass.stored[KEY]["settings"]["llm_api_enabled"])

    def test_the_old_switch_off_never_turns_the_api_off(self) -> None:
        on = asyncio.run(storage.async_get_settings(_hass({"llm_tools_enabled": False, "llm_api_enabled": True})))
        self.assertTrue(on["llm_api_enabled"])
        off = asyncio.run(storage.async_get_settings(_hass({"llm_tools_enabled": False})))
        self.assertFalse(off["llm_api_enabled"])


if __name__ == "__main__":
    unittest.main()
