"""How the bundled card reaches the browser (#44).

@elmr91 loses the card on about one hard reload in three. Measured, and each
measurement removed a suspect: it is not the cache, not the `?v=` mechanism, not
his Nginx (reproduced over direct HTTP), and not the card throwing on a half-loaded
Home Assistant. What is left is the loader. Registered by hand as a Lovelace
resource it works every time; handed to the frontend shell with
`add_extra_js_url` it does not.

The difference is structural: Lovelace loads its own resources and waits for them
before rendering a card, and nothing waits for an extra module URL. So the
integration now registers the card the way HACS registers a plugin, and keeps the
old path only where a resource cannot exist.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_YAML
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.rf_fan import CARD_URL
from tests.ha_helpers import full_entry
from tests.ha_helpers import setup_full as _setup_full


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


def _resources(hass: HomeAssistant) -> list[dict]:
    return list(hass.data[LOVELACE_DATA].resources.async_items())


async def test_the_card_is_registered_as_a_lovelace_resource(
    hass: HomeAssistant,
) -> None:
    """Lovelace waits for its own resources; nothing waits for an extra module URL."""
    assert await async_setup_component(hass, "lovelace", {})
    await _setup_full(hass)

    urls = [item["url"] for item in _resources(hass)]

    assert [url for url in urls if url.startswith(CARD_URL)], (
        f"the card was not registered as a resource: {urls}"
    )
    # `res_type` is the create-time field name; storage keeps it as `type`.
    assert all(item["type"] == "module" for item in _resources(hass))


async def test_it_is_registered_once_however_often_the_entry_reloads(
    hass: HomeAssistant,
) -> None:
    """A resource is persistent, so a second registration would be a second copy.

    Two copies of the same card race to define the element, and the loser cannot
    replace it -- which is how a stale build kept rendering for @elmr91 through
    three releases (#29).
    """
    assert await async_setup_component(hass, "lovelace", {})
    entry, _calls = await _setup_full(hass)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    ours = [item for item in _resources(hass) if item["url"].startswith(CARD_URL)]
    assert len(ours) == 1


async def test_an_existing_registration_is_moved_to_the_current_version(
    hass: HomeAssistant,
) -> None:
    """Including one added by hand: that is the copy that froze for a month (#29).

    Matching on the path rather than the whole URL is what lets a hand-registered
    entry be adopted instead of duplicated.
    """
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_create_item({"res_type": "module", "url": f"{CARD_URL}?v=1.0.0"})

    await _setup_full(hass)

    ours = [item for item in _resources(hass) if item["url"].startswith(CARD_URL)]
    assert len(ours) == 1, "the hand-registered copy was duplicated rather than adopted"
    assert ours[0]["url"] != f"{CARD_URL}?v=1.0.0", "the stale version was left in place"


async def test_yaml_mode_leaves_the_resource_list_alone(hass: HomeAssistant) -> None:
    """In YAML mode the resource list is the user's file, not ours to write to.

    So the integration falls back to the frontend module list there — the path it
    used for everyone until now, and the one `test_setup` covers. It cannot be
    exercised here: the built frontend (`hass_frontend`) is not installed in the
    test environment, which is also why that other test asserts an absent frontend
    is not an error.
    """
    assert await async_setup_component(
        hass, "lovelace", {"lovelace": {"mode": MODE_YAML}}
    )
    await _setup_full(hass)

    ours = [item for item in _resources(hass) if str(item.get("url", "")).startswith(CARD_URL)]

    assert ours == [], "the integration wrote into a YAML-managed resource list"


async def test_removing_the_last_fan_takes_the_resource_with_it(
    hass: HomeAssistant,
) -> None:
    """A resource outlives the integration that made it, and then it 404s.

    Left behind, it points at a file nothing serves any more — and Home Assistant
    reports that on every dashboard, to a user who has just uninstalled the thing
    responsible and has no way to connect the two.
    """
    assert await async_setup_component(hass, "lovelace", {})
    entry, _calls = await _setup_full(hass)
    assert [item for item in _resources(hass) if item["url"].startswith(CARD_URL)]

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    ours = [item for item in _resources(hass) if item["url"].startswith(CARD_URL)]
    assert ours == [], "the card resource outlived the integration"


async def test_the_resource_stays_while_another_fan_needs_it(
    hass: HomeAssistant,
) -> None:
    """One registration serves every fan, so the last one out turns off the light."""
    assert await async_setup_component(hass, "lovelace", {})
    first, _calls = await _setup_full(hass)
    second = full_entry(hass)
    await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_remove(first.entry_id)
    await hass.async_block_till_done()

    ours = [item for item in _resources(hass) if item["url"].startswith(CARD_URL)]
    assert len(ours) == 1, "the card stopped loading for a fan that still exists"


async def test_a_store_not_yet_read_is_not_mistaken_for_an_empty_one(
    hass: HomeAssistant, hass_storage
) -> None:
    """The duplicate @elmr91 woke up to, twice in one day (#44).

    `async_items()` does not read the store; only `async_create_item()` does. So on
    a start where Lovelace has not yet loaded its resources, the collection answers
    "empty", the registration believes nothing is there, and the create — which
    loads first — appends a second copy of what was already registered. One more
    per restart, all identical, and the card then races itself.

    Seeded through the store rather than the collection, because that is the whole
    point: on disk, and not yet in memory.
    """
    hass_storage["lovelace_resources"] = {
        "version": 1,
        "key": "lovelace_resources",
        "data": {
            "items": [
                {"id": "seeded", "type": "module", "url": f"{CARD_URL}?v=1.8.1b1"}
            ]
        },
    }
    assert await async_setup_component(hass, "lovelace", {})

    await _setup_full(hass)

    ours = [item for item in _resources(hass) if item["url"].startswith(CARD_URL)]
    assert len(ours) == 1, f"the store was read as empty and duplicated: {ours}"


async def test_copies_that_already_exist_are_cleaned_up(hass: HomeAssistant) -> None:
    """Anyone who restarted twice on 1.8.1b1 has two, and cannot know why.

    Fixing the cause leaves them there, so the registration removes the extras it
    finds rather than making them somebody's manual chore.
    """
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    for _ in range(3):
        await resources.async_create_item(
            {"res_type": "module", "url": f"{CARD_URL}?v=1.8.1b1"}
        )

    await _setup_full(hass)

    ours = [item for item in _resources(hass) if item["url"].startswith(CARD_URL)]
    assert len(ours) == 1, f"the extra copies were left behind: {ours}"
