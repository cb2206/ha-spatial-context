"""The fork's spatial tools (spatial_tools.py) on the Spatial Context LLM API
(llm_tools.py), with homeassistant.helpers.llm and probatio stubbed: the API
offers GetSpatialMap plus the five tools, names are prefixed and tagged, a
non-admin user is refused, lookup errors come back as tool errors, and a
broken spatial module never takes GetSpatialMap down.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
import types
import unittest

import stubs

PKG = "sc_llm_test"


class _Invalid(Exception):
    pass


class _Required:
    def __init__(self, name, description=None):
        self.name = name


class _Optional:
    def __init__(self, name, description=None):
        self.name = name


class _Schema:
    def __init__(self, schema):
        self.schema = schema

    def __call__(self, data):
        for key in self.schema:
            if isinstance(key, _Required) and key.name not in data:
                raise _Invalid(f"required key not provided @ data['{key.name}']")
        return dict(data)


@dataclasses.dataclass
class _ToolResult:
    data: dict
    error: bool = False


class _Tool:
    name: str
    title = None
    description = None
    integration = None


class _API:
    def __init__(self, hass, id, name):
        self.hass, self.id, self.name = hass, id, name


@dataclasses.dataclass
class _APIInstance:
    api: object
    api_prompt: str
    llm_context: object
    tools: list


class _User:
    def __init__(self, is_admin):
        self.is_admin = is_admin


class _Auth:
    async def async_get_user(self, user_id):
        return {"admin": _User(True), "user": _User(False)}.get(user_id)


def _context(user_id=None):
    return types.SimpleNamespace(context=types.SimpleNamespace(user_id=user_id))


def _load(run_tool=None, break_spatial=False):
    for name in [m for m in sys.modules if m.startswith(PKG)] + ["probatio", "homeassistant.helpers.llm"]:
        sys.modules.pop(name, None)
    stubs.stub_ha_core()
    stubs.stub("homeassistant.helpers")
    stubs.stub("probatio", Schema=_Schema, Required=_Required, Optional=_Optional, In=lambda v: v, Invalid=_Invalid)
    stubs.stub(
        "homeassistant.helpers.llm",
        Tool=_Tool,
        API=_API,
        APIInstance=_APIInstance,
        LLMContext=object,
        ToolInput=object,
        ToolResult=_ToolResult,
        ToolAnnotations=lambda **kw: types.SimpleNamespace(**kw),
        async_register_api=lambda hass, api: (lambda: None),
    )
    stubs.new_package(PKG)
    stubs.stub(f"{PKG}.const", DOMAIN="spatial_context")

    class MapFilterError(ValueError):
        pass

    async def get_map(hass):
        return {"floors": []}

    stubs.stub(
        f"{PKG}.export",
        MapFilterError=MapFilterError,
        async_get_map_data=get_map,
        filter_map_data=lambda data, floor, room: data,
    )
    stubs.new_package(f"{PKG}.spatial")

    class NotFound(LookupError):
        pass

    async def default_run(hass, tool, args):
        return {"tool": tool, "args": args}

    if break_spatial:
        stubs.stub(f"{PKG}.spatial.ai")  # no NotFound / async_run_tool: the import fails
    else:
        stubs.stub(f"{PKG}.spatial.ai", NotFound=NotFound, async_run_tool=run_tool or default_run)
    stubs.load(PKG, "spatial_tools") if not break_spatial else None
    llm_tools = stubs.load(PKG, "llm_tools")
    return llm_tools, NotFound


def _instance(llm_tools):
    hass = types.SimpleNamespace(auth=_Auth())
    api = llm_tools.SpatialContextAPI(hass)
    return hass, asyncio.run(api.async_get_api_instance(_context()))


class SpatialToolsOnTheAPITest(unittest.TestCase):
    def test_the_api_offers_the_map_and_the_spatial_tools(self) -> None:
        llm_tools, _ = _load()
        _, instance = _instance(llm_tools)
        names = [tool.name for tool in instance.tools]
        self.assertEqual(
            names,
            [
                "GetSpatialMap",
                "spatial_context__summary",
                "spatial_context__device_context",
                "spatial_context__path",
                "spatial_context__weak_links",
                "spatial_context__room",
            ],
        )
        for tool in instance.tools[1:]:
            self.assertEqual(tool.integration, "spatial_context")
            self.assertTrue(tool.annotations.read_only)
            self.assertFalse(tool.annotations.open_world)
            self.assertTrue(tool.description)
        # The map tool's own prompt stays first; ours steers to summary.
        self.assertTrue(instance.api_prompt.startswith(llm_tools._API_PROMPT))
        self.assertIn("summary tool", instance.api_prompt)
        self.assertIn("ordinal", instance.api_prompt)

    def test_a_call_runs_the_tool_and_reports_errors(self) -> None:
        calls = []

        async def run(hass, tool, args):
            calls.append((tool, args))
            if args.get("device") == "missing":
                raise not_found("No device matches 'missing'")
            return {"ok": True}

        llm_tools, not_found = _load(run)
        hass, instance = _instance(llm_tools)
        tool = {t.name: t for t in instance.tools}["spatial_context__device_context"]

        def call(args, user_id=None):
            return asyncio.run(tool.async_call(hass, types.SimpleNamespace(tool_args=args), _context(user_id)))

        self.assertEqual(call({"device": "d1"}).data, {"ok": True})
        self.assertEqual(call({"device": "d1"}, "admin").data, {"ok": True})
        bad = call({"device": "missing"})
        self.assertTrue(bad.error)
        self.assertIn("missing", bad.data["error"])
        no_arg = call({})
        self.assertTrue(no_arg.error)
        self.assertIn("device", no_arg.data["error"])
        self.assertEqual(calls, [("device_context", {"device": "d1"}), ("device_context", {"device": "d1"}), ("device_context", {"device": "missing"})])

    def test_an_unexpected_failure_is_a_tool_error(self) -> None:
        async def run(hass, tool, args):
            raise KeyError("rooms")

        llm_tools, _ = _load(run)
        hass, instance = _instance(llm_tools)
        tool = {t.name: t for t in instance.tools}["spatial_context__summary"]
        import logging

        with self.assertLogs(logging.getLogger(f"{PKG}.spatial_tools"), "ERROR"):
            result = asyncio.run(tool.async_call(hass, types.SimpleNamespace(tool_args={}), _context()))
        self.assertTrue(result.error)
        self.assertIn("log", result.data["error"])

    def test_a_non_admin_user_is_refused(self) -> None:
        calls = []

        async def run(hass, tool, args):
            calls.append(tool)
            return {}

        llm_tools, _ = _load(run)
        hass, instance = _instance(llm_tools)
        tool = {t.name: t for t in instance.tools}["spatial_context__summary"]
        refused = asyncio.run(tool.async_call(hass, types.SimpleNamespace(tool_args={}), _context("user")))
        self.assertTrue(refused.error)
        self.assertIn("administrators", refused.data["error"])
        self.assertEqual(calls, [])

    def test_a_broken_spatial_module_leaves_the_map_tool(self) -> None:
        llm_tools, _ = _load(break_spatial=True)
        with self.assertLogs(llm_tools._LOGGER, "WARNING"):
            _, instance = _instance(llm_tools)
        self.assertEqual([tool.name for tool in instance.tools], ["GetSpatialMap"])
        self.assertEqual(instance.api_prompt, llm_tools._API_PROMPT)


if __name__ == "__main__":
    unittest.main()
