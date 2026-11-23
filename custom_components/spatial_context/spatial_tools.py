"""Fork: the spatial engine's outputs as tools on the Spatial Context LLM API.

llm_tools.py's `SpatialContextAPI` offers these next to `GetSpatialMap`, so
they share its switch (Settings > AI Assistants, `llm_api_enabled`, #53) and
its rule that a signed-in user must be an administrator.

Like llm_tools.py, this imports Home Assistant's `llm` helper and `probatio`
at module level, so it only loads on Home Assistant 2026.10 or newer, through
llm_tools.py, which llm_api.py imports lazily.
"""

from __future__ import annotations

import logging
from typing import Any

import probatio

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import DOMAIN
from .spatial.ai import NotFound, async_run_tool

PROMPT = (
    "For radio questions (Zigbee, Thread, Wi-Fi coverage, weak links, which "
    "router serves a room) start with the summary tool, then ask about one "
    "device, a path between two devices, a room, or weak links; prefer these "
    "tools to GetSpatialMap without a floor or room, which returns the whole "
    "map. Ids like d12 (device), r3 (room) and l1 (level) are short ids from "
    "these tools; names work too. Distances are metres, signals dBm, losses "
    "dB. predicted_dbm is a rough model from distance, walls and floors; "
    "gap_db is how much weaker the measured signal is than predicted. Zigbee "
    "signal is LQI, which is ordinal and vendor-specific: use it to rank "
    "links, not as a measurement. Unplaced devices and uncalibrated levels "
    "have no geometry."
)

_LOGGER = logging.getLogger(__name__)

_LAYERS = ["zigbee", "thread", "wifi", "bluetooth"]

_ADMIN_ONLY = "Spatial Context is only available to administrators."


async def async_admin_refusal(
    hass: HomeAssistant, llm_context: llm.LLMContext
) -> llm.ToolResult | None:
    """The same rule as GetSpatialMap: a signed-in user must be an admin; a
    call with no user behind it (a voice assistant, an automation) is allowed,
    since the owner switched the API on."""
    user_id = llm_context.context.user_id if llm_context.context else None
    if user_id:
        user = await hass.auth.async_get_user(user_id)
        if user is not None and not user.is_admin:
            return llm.ToolResult(data={"error": _ADMIN_ONLY}, error=True)
    return None


class _SpatialTool(llm.Tool):
    """One spatial engine output. Read-only and local."""

    integration = DOMAIN
    # Read-only, so the MCP Server's stateless mode includes it.
    annotations = llm.ToolAnnotations(
        read_only=True, destructive=False, idempotent=True, open_world=False
    )
    tool: str

    def __init__(self) -> None:
        self.name = f"{DOMAIN}__{self.tool}"

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        refusal = await async_admin_refusal(hass, llm_context)
        if refusal is not None:
            return refusal
        try:
            args = self.parameters(tool_input.tool_args)
            data = await async_run_tool(hass, self.tool, args)
        except (NotFound, ValueError, probatio.Invalid) as err:
            return llm.ToolResult(data={"error": str(err)}, error=True)
        except Exception:  # noqa: BLE001 - odd stored data must not crash the agent's turn
            _LOGGER.exception("Spatial Context tool %s failed", self.name)
            return llm.ToolResult(
                data={"error": "The spatial tool failed; see the Home Assistant log."},
                error=True,
            )
        return llm.ToolResult(data=data)


class SummaryTool(_SpatialTool):
    tool = "summary"
    title = "Home layout summary"
    description = (
        "The home at a glance: levels, rooms with neighbouring rooms, radio "
        "infrastructure (routers, border routers, access points) and where it "
        "is, networks, the top findings, and which data is approximate."
    )
    parameters = probatio.Schema({})


class DeviceContextTool(_SpatialTool):
    tool = "device_context"
    title = "Device location and links"
    description = (
        "Where one device is (level, room, position), its radios, every radio "
        "link with distance, walls, predicted and measured signal, findings, "
        "and the nearest infrastructure."
    )
    parameters = probatio.Schema({probatio.Required("device"): str})


class PathTool(_SpatialTool):
    tool = "path"
    title = "What is between two devices"
    description = (
        "Distance, floors and walls (material, loss) on the straight path "
        "between two devices, the rooms it passes, the predicted signal, and "
        "any measured link between them."
    )
    parameters = probatio.Schema(
        {probatio.Required("a"): str, probatio.Required("b"): str}
    )


class WeakLinksTool(_SpatialTool):
    tool = "weak_links"
    title = "Weak radio links"
    description = (
        "Links whose measured signal is far below what distance, walls and "
        "floors predict, worst first. Optionally one layer or one level."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional("layer"): probatio.In(_LAYERS),
            probatio.Optional("level"): str,
        }
    )


class RoomTool(_SpatialTool):
    tool = "room"
    title = "Room details"
    description = (
        "One room: size, neighbouring rooms, its devices and their radio "
        "roles, links inside and out, and findings."
    )
    parameters = probatio.Schema({probatio.Required("room"): str})


TOOL_CLASSES = (SummaryTool, DeviceContextTool, PathTool, WeakLinksTool, RoomTool)


def spatial_tools() -> list[Any]:
    """One instance of each spatial tool."""
    return [cls() for cls in TOOL_CLASSES]
