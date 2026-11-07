"""Tests for the services (services.py): every one is admin-only, like the
WebSocket API, but an automation or script (no user) may still call them.
They are all registered through Home Assistant's async_register_admin_service
(stubbed here with the same check Home Assistant makes).

Runs without Home Assistant installed — the service registry, users and
exceptions are small stand-ins.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
import sys
import types
import unittest

import stubs

try:
    import voluptuous  # noqa: F401  (services.py imports it)
except ModuleNotFoundError:  # pragma: no cover - CI installs it
    voluptuous = None


_Unauthorized = stubs.Unauthorized
_UnknownUser = stubs.UnknownUser


ALL_SERVICES = {"get_map", "refresh_zigbee_mesh", "refresh_links", "query", "update_settings"}


class _Hass:
    def __init__(self, users: dict) -> None:
        self.registered: dict = {}
        self.admin_registered: set = set()
        self.services = types.SimpleNamespace(async_register=self._register)
        self.auth = types.SimpleNamespace(async_get_user=self._get_user)
        self._users = users

    def _register(self, domain, service, handler, *args, **kwargs) -> None:
        self.registered[service] = handler

    async def _get_user(self, user_id):
        return self._users.get(user_id)


def _setup() -> tuple[_Hass, list]:
    calls: list = []

    async def get_map(hass):
        calls.append("get_map")
        return {"floors": []}

    async def network_map(hass, force_refresh=False):
        calls.append("refresh")

    async def run_tool(hass, tool, args):
        calls.append("query")
        return {}

    async def get_settings(hass):
        return {}

    async def save_settings(hass, settings):
        calls.append("update_settings")

    stubs.stub_ha_core()
    stubs.stub_ha_services()
    service_helper = sys.modules["homeassistant.helpers.service"]
    register_admin = service_helper.async_register_admin_service

    def record_admin(hass, domain, service, *args, **kwargs):
        hass.admin_registered.add(service)
        register_admin(hass, domain, service, *args, **kwargs)

    service_helper.async_register_admin_service = record_admin
    pkg = "sc_services_test"
    stubs.new_package(pkg)
    stubs.new_package(f"{pkg}.spatial")
    stubs.stub(f"{pkg}.const", DOMAIN="spatial_context")
    stubs.stub(f"{pkg}.export", async_get_map_data=get_map)
    stubs.stub(f"{pkg}.zigbee_mesh", async_get_network_map=network_map)
    stubs.stub(f"{pkg}.storage", async_get_settings=get_settings, async_save_settings=save_settings)
    stubs.stub(
        f"{pkg}.spatial.ai",
        TOOLS=("summary",),
        NotFound=LookupError,
        async_run_tool=run_tool,
    )
    stubs.stub(f"{pkg}.spatial.map_view", MapFilterError=ValueError, async_get_map_view=None)
    services = stubs.load(pkg, "services")

    hass = _Hass(
        {
            "admin": types.SimpleNamespace(is_admin=True),
            "user": types.SimpleNamespace(is_admin=False),
        }
    )
    asyncio.run(services.async_setup_services(hass))
    return hass, calls


def _call(user_id: str | None, data: dict | None = None) -> types.SimpleNamespace:
    return types.SimpleNamespace(data=data or {}, context=types.SimpleNamespace(user_id=user_id))


@unittest.skipIf(voluptuous is None, "voluptuous is not installed")
class AdminOnlyServicesTest(unittest.TestCase):
    def test_every_service_is_an_admin_service(self) -> None:
        hass, _ = _setup()
        self.assertEqual(set(hass.registered), ALL_SERVICES)
        self.assertEqual(hass.admin_registered, ALL_SERVICES)

    def test_an_admin_can_call_them(self) -> None:
        hass, calls = _setup()
        result = asyncio.run(hass.registered["get_map"](_call("admin")))
        self.assertEqual(result, {"floors": []})
        asyncio.run(hass.registered["refresh_zigbee_mesh"](_call("admin")))
        self.assertEqual(calls, ["get_map", "refresh"])

    def test_an_automation_with_no_user_can_call_them(self) -> None:
        hass, calls = _setup()
        asyncio.run(hass.registered["get_map"](_call(None)))
        asyncio.run(hass.registered["refresh_zigbee_mesh"](_call(None)))
        self.assertEqual(calls, ["get_map", "refresh"])

    def test_a_non_admin_is_refused(self) -> None:
        hass, calls = _setup()
        data = {"query": {"tool": "summary"}}
        for service in sorted(ALL_SERVICES):
            with self.assertRaises(_Unauthorized):
                asyncio.run(hass.registered[service](_call("user", data.get(service))))
        self.assertEqual(calls, [])

    def test_an_unknown_user_is_refused(self) -> None:
        hass, calls = _setup()
        with self.assertRaises(_UnknownUser):
            asyncio.run(hass.registered["get_map"](_call("deleted")))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
