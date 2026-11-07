# Changelog

Notes for each release are also on the [releases page](https://github.com/Greminn/ha-spatial-context/releases). This file starts at 1.0.0 and summarises the beta releases before it.

## Fork changes

1.0.1-fork.6: use `DeviceEntry.config_entry_id` instead of the deprecated `config_entries` (stops working in HA 2027.10), and point the manifest's documentation and issue tracker at the fork.

1.0.1-fork.5: the UniFi Wi-Fi layer reads clients from the controller's raw data. aiounifi names the AP `access_point_mac`, so `ap_mac` was always empty and no client links were found (upstream `wifi_mesh.py` has the same problem).

This is the `next` branch of a fork (cb2206/ha-spatial-context): upstream `dev` (1.0.1-beta.4) plus these fixes, each also on its own `fix/*` branch to offer upstream.

- Wi-Fi: a UniFi client's signal fills in the missing dBm on links from enabled trackers (`fix/wifi-unifi-rssi`).
- `get_map`: devices whose room was deleted are exported under Unassigned instead of being dropped (`fix/export-orphan-room-devices`).
- `get_map` and `refresh_zigbee_mesh` are admin-only for user calls; automations and scripts still work (`fix/admin-only-services`).
- Saves refuse malformed points, a bad scale, NaN and infinity, and an oversized hidden device list; malformed stored data is skipped instead of breaking a floor (`fix/layout-validation`).
- ZHA: a PreviousChild neighbour is no longer drawn as a live link; the refresh action's description no longer says Zigbee2MQTT only (`fix/zha-stale-relationships`).
- The panel follows Home Assistant's language (German now shows), and the last hard-coded English strings are translated (`fix/i18n-set-language`).
- Minimum Home Assistant version raised to 2026.9, the first release the device registry code works on (`fix/min-ha-version`).

Phase 2 (1.0.1-fork.2), new features on `feat/*` branches:

- Link store: ZHA neighbour and route tables, Zigbee2MQTT's cached map, Matter/Thread neighbour and route tables (one snapshot per Thread network) and UniFi Wi-Fi associations are read into a persisted store. It refreshes two minutes after start and then every 30 minutes, and never scans. Also available on demand through the new `spatial_context.refresh_links` action and the `spatial_context/get_links` WebSocket command (`feat/link-store`).
- Spatial engine (`spatial/`): metric positions and heights, server-side room from the pin, room adjacency, walls and floor slabs between two devices, an RF path-loss model, and findings (weak links, unplaced infrastructure, isolated routers, far parents, area mismatches, uncalibrated levels). It reads the link store (`feat/spatial-ai`).
- LLM tools (`spatial_context__summary`, `device_context`, `path`, `weak_links`, `room`), each with a bounded token budget. Off by default: they are offered only on the "Home Assistant" LLM API once `llm_tools_enabled` is on (`feat/spatial-ai`).
- `get_map` gains optional `floor`, `room`, `compact` and `include_links` fields. With no fields its output is unchanged (`feat/spatial-ai`).
- New actions `spatial_context.query` (the LLM tools' answers, for ha-mcp, scripts and REST) and `spatial_context.update_settings` (floor height, RF exponent, slab loss, weak-link threshold, LLM tools on/off). Saving settings keeps any setting the sender does not know about (`feat/spatial-ai`).
- Every action is registered through Home Assistant's `async_register_admin_service`, so user calls need an admin and automations still work.

Phase 3 (1.0.1-fork.3), setup automation (`feat/setup-automation`):

- Bulk place: put every unplaced device on a floor (or one area's devices) into the room linked to its HA area, spread out from the room's pole of inaccessibility. Such pins are marked approximate (see-through, dashed rim, an "N approximate" chip and filter) until dragged or confirmed with "Confirm position". A "Keep placing" toggle arms the next unplaced device after each placement.
- Create placeholder rooms for a floor's HA areas that have no room yet (squares sized by device count, linked to the area, laid out over the plan).
- Generate walls from room outlines: shared edges become one interior wall (rooms within 35 cm count as sharing it), outside edges become exterior walls; running it again adds nothing.
- PDF (page 1, pdf.js loaded only on first use) and SVG backgrounds, a background from a camera entity's current image (e.g. a vacuum map), and background rotation with 90° turns and a straighten slider.
- Pins gain an optional `approximate` flag and floors a `background_rotation_deg` (finite, −360..360, default 0). `get_map` adds `"approximate": true` only for such pins, so other output is unchanged. The LLM tools and `spatial_context.query` report `position_confidence` ("approximate"/"confirmed") per placed device, and the summary counts approximate positions. Restart HA after installing: an older backend rejects saves that carry the new fields.

## Unreleased

### Added
- Devices can be hidden from the **Place device** list with the eye button on a row, and brought back from the new **Hidden devices** filter (#43).
- **Clear placed devices** asks how far to go: in the selected area, on this floor, in this building or everywhere, with the number of devices for each (#44).
- **Reset floor** has a checkbox for each thing it can clear: rooms, walls, doors and windows, placed devices and the background image (#45). Choosing everything works as before.
- An **Opening a view** setting: choose **Fit to screen** and every floor and the Property tab open fitted to the screen instead of at their saved view. Saved views are not changed (#48).
- The Home Assistant version is shown under About in Settings, so it is easy to include in a bug report.
- Click and drag to size a new building on the Property tab. Drag from one corner and the outline keeps the building's proportions. A plain click still places it at the default size (#56).
- A **Back to group** arrow on a device's card, when you opened it from a list of devices at the same spot (#62).
- A **Move out of this spot** button on each device in that list, so a stacked device can be moved without deleting it (#47).
- A warning triangle on a Zigbee link that reads much weaker than the walls between its two devices predict. Hover it for the expected and measured signal. It needs the floor's scale set. A **Flag weak links** setting chooses how big the gap must be (25 dB by default, 0 turns it off) (#29).
- A device's card lists its links to devices that are not placed on any floor, marked "not placed on the plan" (#63).

### Changed
- A room linked to an area now follows the area's name: rename the area in Home Assistant and the room follows. Type a name to override it, clear the box (or choose **Use area name**) to follow the area again. Rooms that already carry their area's name start following it (#52).
- The Settings page is titled **Spatial Context Settings**, and its back arrow says **Back to Spatial Context**.

### Fixed
- Going back to a group of devices after scrolling a long link list on a device's card no longer shows a blank card.
- The first click-and-drag to size a new building no longer fails after choosing the building from the list (#56).
- A ZHA coordinator with no enabled entities, such as the ZBT-2 or an SLZB-06 radio, is listed in the Place device list (#60).
- Devices whose only enabled entities are firmware update or event entities, such as IKEA Tradfri repeaters and Styrbar remotes, are listed in the Place device list (#54).
- With only one floor, the Place device list starts on **All floors**, so devices with no area, or an area on no floor, are no longer hidden (#54).
- The OpenThread Border Router app, and Home Assistant Yellow, Green, SkyConnect and ZBT-2 hardware, can now be placed on the plan and chosen under **Settings → Border router** (#42).
- The **Not placed yet** filter in the device list no longer shows devices that are placed on another floor.

## 1.0.0

The first stable release.

### Added
- A full documentation site, with a first floor plan walkthrough and a page for each feature.
- A key for the Connectivity Map that explains solid, dashed and grey lines, shows the weakest and strongest readings on screen, and reads off the value as you move along the bar.
- Zigbee layer support for ZHA, as well as Zigbee2MQTT.
- A Thread border router setting for the Matter layer.
- A placed and not-placed filter in the device list, with buttons to find a placed device on the plan or remove it.
- A **Use area name** button on a room, a **Getting started guide** link in the menu, and menus that close when you click away.
- A copy of the layout is kept for each version, and a version that is older than the one that saved the layout refuses to load it.

### Changed
- The panel and every command are for administrators only.
- Errors shown in the panel are short messages, and the detail goes to the Home Assistant log.
- Saves have size limits, and the debug log masks web and IP addresses.
- Zigbee readings of 0 or 1, which are stale entries in a neighbour table, are ignored. A link with no real reading is drawn grey.
- New buildings on the Property tab are placed at their real-world size.
- The panel code is split into smaller modules, and tests now run in CI.

### Fixed
- The device registry is read the way Home Assistant now expects.

## Before 1.0.0

Releases up to 0.16.0-beta.2 were pre-releases. They built the floor plan editor, the Property tab, the Connectivity Map layers (Zigbee, Wi-Fi, Matter and Bluetooth), the map data and the `get_map` action, English and German translations, and the native Home Assistant look. See the [releases page](https://github.com/Greminn/ha-spatial-context/releases) for each one.
