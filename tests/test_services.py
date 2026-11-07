"""Tests for the services (services.py): both are admin-only, like the
WebSocket API, but an automation or script (no user) may still call them.

Runs without Home Assistant installed — the service registry, users and
exceptions are small stand-ins.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
import types
import unittest

import stubs


class _Unauthorized(Exception):
    def __init__(self, context=None) -> None:
        super().__init__()
        self.context = context


class _UnknownUser(_Unauthorized):
    pass


class _Hass:
    def __init__(self, users: dict) -> None:
        self.registered: dict = {}
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

    stubs.stub("homeassistant")
    stubs.stub(
        "homeassistant.core",
        HomeAssistant=object,
        ServiceCall=object,
        SupportsResponse=types.SimpleNamespace(ONLY="only"),
    )
    stubs.stub(
        "homeassistant.exceptions",
        Unauthorized=_Unauthorized,
        UnknownUser=_UnknownUser,
    )
    stubs.new_package("sc_services_test")
    stubs.stub("sc_services_test.const", DOMAIN="spatial_context")
    stubs.stub("sc_services_test.export", async_get_map_data=get_map)
    stubs.stub("sc_services_test.zigbee_mesh", async_get_network_map=network_map)
    services = stubs.load("sc_services_test", "services")

    hass = _Hass(
        {
            "admin": types.SimpleNamespace(is_admin=True),
            "user": types.SimpleNamespace(is_admin=False),
        }
    )
    asyncio.run(services.async_setup_services(hass))
    return hass, calls


def _call(user_id: str | None) -> types.SimpleNamespace:
    return types.SimpleNamespace(context=types.SimpleNamespace(user_id=user_id))


class AdminOnlyServicesTest(unittest.TestCase):
    def test_both_services_are_registered(self) -> None:
        hass, _ = _setup()
        self.assertEqual(set(hass.registered), {"get_map", "refresh_zigbee_mesh"})

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
        for service in ("get_map", "refresh_zigbee_mesh"):
            with self.assertRaises(_Unauthorized):
                asyncio.run(hass.registered[service](_call("user")))
        self.assertEqual(calls, [])

    def test_an_unknown_user_is_refused(self) -> None:
        hass, calls = _setup()
        with self.assertRaises(_UnknownUser):
            asyncio.run(hass.registered["get_map"](_call("deleted")))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
