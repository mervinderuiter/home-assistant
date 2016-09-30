"""
Component to interface with various remote controls.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/remote/
"""
import hashlib
import logging
import os
import requests

import voluptuous as vol

from homeassistant.config import load_yaml_config_file
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA  # noqa
from homeassistant.components.http import HomeAssistantView
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    STATE_OFF, STATE_UNKNOWN, STATE_PLAYING, STATE_IDLE,
    ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON,
    SERVICE_VOLUME_UP, SERVICE_VOLUME_DOWN, SERVICE_VOLUME_SET,
    SERVICE_VOLUME_MUTE, SERVICE_TOGGLE, SERVICE_MEDIA_STOP,
    SERVICE_MEDIA_PLAY_PAUSE, SERVICE_MEDIA_PLAY, SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_NEXT_TRACK, SERVICE_MEDIA_PREVIOUS_TRACK, SERVICE_MEDIA_SEEK)

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'remote'
DEPENDENCIES = ['http']
SCAN_INTERVAL = 10

ENTITY_ID_FORMAT = DOMAIN + '.{}'

ENTITY_IMAGE_URL = '/api/remote_proxy/{0}?token={1}&cache={2}'

SERVICE_SELECT_SOURCE = 'select_source'

ATTR_APP_ID = 'app_id'
ATTR_APP_NAME = 'app_name'
ATTR_SUPPORTED_MEDIA_COMMANDS = 'supported_media_commands'
ATTR_INPUT_SOURCE = 'source'
ATTR_INPUT_SOURCE_LIST = 'source_list'
ATTR_MEDIA_ENQUEUE = 'enqueue'

MEDIA_TYPE_MUSIC = 'music'
MEDIA_TYPE_TVSHOW = 'tvshow'
MEDIA_TYPE_VIDEO = 'movie'
MEDIA_TYPE_EPISODE = 'episode'
MEDIA_TYPE_CHANNEL = 'channel'
MEDIA_TYPE_PLAYLIST = 'playlist'

SUPPORT_PAUSE = 1
SUPPORT_STOP = 2
SUPPORT_PLAY_PAUSE = 4
SUPPORT_VOLUME_MUTE = 8
SUPPORT_PREVIOUS_TRACK = 16
SUPPORT_NEXT_TRACK = 32

SUPPORT_NUMERIC = 64
SUPPORT_TURN_ON = 128
SUPPORT_TURN_OFF = 256
SUPPORT_VOLUME_STEP = 1024
SUPPORT_SELECT_SOURCE = 2048


# simple services that only take entity_id(s) as optional argument
SERVICE_TO_METHOD = {
    SERVICE_TURN_ON: 'turn_on',
    SERVICE_TURN_OFF: 'turn_off',
    SERVICE_TOGGLE: 'toggle',
    SERVICE_VOLUME_UP: 'volume_up',
    SERVICE_VOLUME_DOWN: 'volume_down',
    SERVICE_MEDIA_PLAY_PAUSE: 'media_play_pause',
    SERVICE_MEDIA_PLAY: 'media_play',
    SERVICE_MEDIA_PAUSE: 'media_pause',
    SERVICE_MEDIA_STOP: 'media_stop',
    SERVICE_MEDIA_NEXT_TRACK: 'media_next_track',
    SERVICE_MEDIA_PREVIOUS_TRACK: 'media_previous_track'

}

ATTR_TO_PROPERTY = [
    ATTR_APP_ID,
    ATTR_APP_NAME,
    ATTR_SUPPORTED_MEDIA_COMMANDS,
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST
]

# Service call validation schemas
REMOTE_SCHEMA = vol.Schema({
    ATTR_ENTITY_ID: cv.entity_ids,
})


REMOTE_SELECT_SOURCE_SCHEMA = REMOTE_SCHEMA.extend({
    vol.Required(ATTR_INPUT_SOURCE): cv.string,
})


def is_on(hass, entity_id=None):
    """
    Return true if specified media player entity_id is on.

    Check all media player if no entity_id specified.
    """
    entity_ids = [entity_id] if entity_id else hass.states.entity_ids(DOMAIN)
    return any(not hass.states.is_state(entity_id, STATE_OFF)
               for entity_id in entity_ids)


def turn_on(hass, entity_id=None):
    """Turn on specified media player or all."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_TURN_ON, data)


def turn_off(hass, entity_id=None):
    """Turn off specified media player or all."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_TURN_OFF, data)


def toggle(hass, entity_id=None):
    """Toggle specified media player or all."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_TOGGLE, data)


def volume_up(hass, entity_id=None):
    """Send the media player the command for volume up."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_VOLUME_UP, data)


def volume_down(hass, entity_id=None):
    """Send the media player the command for volume down."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_VOLUME_DOWN, data)


def mute_volume(hass, mute, entity_id=None):
    """Send the media player the command for muting the volume."""
    
    if entity_id:
        data[ATTR_ENTITY_ID] = entity_id

    hass.services.call(DOMAIN, SERVICE_VOLUME_MUTE, data)


def set_volume_level(hass, volume, entity_id=None):
    """Send the media player the command for setting the volume."""
    

    if entity_id:
        data[ATTR_ENTITY_ID] = entity_id

    hass.services.call(DOMAIN, SERVICE_VOLUME_SET, data)


def media_play_pause(hass, entity_id=None):
    """Send the media player the command for play/pause."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_MEDIA_PLAY_PAUSE, data)


def media_play(hass, entity_id=None):
    """Send the media player the command for play/pause."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_MEDIA_PLAY, data)


def media_pause(hass, entity_id=None):
    """Send the media player the command for pause."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_MEDIA_PAUSE, data)


def media_stop(hass, entity_id=None):
    """Send the media player the stop command."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_MEDIA_STOP, data)


def media_next_track(hass, entity_id=None):
    """Send the media player the command for next track."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_MEDIA_NEXT_TRACK, data)


def media_previous_track(hass, entity_id=None):
    """Send the media player the command for prev track."""
    data = {ATTR_ENTITY_ID: entity_id} if entity_id else {}
    hass.services.call(DOMAIN, SERVICE_MEDIA_PREVIOUS_TRACK, data)

def select_source(hass, source, entity_id=None):
    """Send the media player the command to select input source."""
    data = {ATTR_INPUT_SOURCE: source}

    if entity_id:
        data[ATTR_ENTITY_ID] = entity_id

    hass.services.call(DOMAIN, SERVICE_SELECT_SOURCE, data)

def setup(hass, config):
    """Track states and offer events for remotes."""
    component = EntityComponent(
        logging.getLogger(__name__), DOMAIN, hass, SCAN_INTERVAL)

    component.setup(config)

    descriptions = load_yaml_config_file(
        os.path.join(os.path.dirname(__file__), 'services.yaml'))

    def remote_service_handler(service):
        """Map services to methods on MediaPlayerDevice."""
        method = SERVICE_TO_METHOD[service.service]

        for player in component.extract_from_service(service):
            getattr(player, method)()

            if player.should_poll:
                player.update_ha_state(True)

    for service in SERVICE_TO_METHOD:
        hass.services.register(DOMAIN, service, remote_service_handler,
                               descriptions.get(service),
                               schema=REMOTE_SCHEMA)

                           
    def select_source_service(service):
        """Change input to selected source."""
        input_source = service.data.get(ATTR_INPUT_SOURCE)

        for player in component.extract_from_service(service):
            player.select_source(input_source)

            if player.should_poll:
                player.update_ha_state(True)

    hass.services.register(DOMAIN, SERVICE_SELECT_SOURCE,
                           select_source_service,
                           descriptions.get(SERVICE_SELECT_SOURCE),
                           schema=REMOTE_SELECT_SOURCE_SCHEMA)


class RemoteControlDevice(Entity):
    """ABC for remote controls."""

    # pylint: disable=too-many-public-methods,no-self-use

    # Implement these for your media player

    @property
    def state(self):
        """State of the player."""
        return STATE_UNKNOWN

    @property
    def access_token(self):
        """Access token for this media player."""
        return str(id(self))

    @property
    def app_id(self):
        """ID of the current running app."""
        return None

    @property
    def app_name(self):
        """Name of the current running app."""
        return None

    @property
    def source(self):
        """Name of the current input source."""
        return None

    @property
    def source_list(self):
        """List of available input sources."""
        return None

    @property
    def supported_media_commands(self):
        """Flag media commands that are supported."""
        return 0

    def turn_on(self):
        """Turn the media player on."""
        raise NotImplementedError()

    def turn_off(self):
        """Turn the media player off."""
        raise NotImplementedError()

    def mute_volume(self, mute):
        """Mute the volume."""
        raise NotImplementedError()

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        raise NotImplementedError()

    def media_play(self):
        """Send play commmand."""
        raise NotImplementedError()

    def media_pause(self):
        """Send pause command."""
        raise NotImplementedError()

    def media_stop(self):
        """Send stop command."""
        raise NotImplementedError()

    def media_previous_track(self):
        """Send previous track command."""
        raise NotImplementedError()

    def media_next_track(self):
        """Send next track command."""
        raise NotImplementedError()

    def play_media(self, media_type, media_id):
        """Play a piece of media."""
        raise NotImplementedError()

    def select_source(self, source):
        """Select input source."""
        raise NotImplementedError()

    def clear_playlist(self):
        """Clear players playlist."""
        raise NotImplementedError()

    # No need to overwrite these.
    @property
    def support_pause(self):
        """Boolean if pause is supported."""
        return bool(self.supported_media_commands & SUPPORT_PAUSE)

    @property
    def support_stop(self):
        """Boolean if stop is supported."""
        return bool(self.supported_media_commands & SUPPORT_STOP)

    @property
    def support_volume_set(self):
        """Boolean if setting volume is supported."""
        return bool(self.supported_media_commands & SUPPORT_VOLUME_SET)

    @property
    def support_volume_mute(self):
        """Boolean if muting volume is supported."""
        return bool(self.supported_media_commands & SUPPORT_VOLUME_MUTE)

    @property
    def support_previous_track(self):
        """Boolean if previous track command supported."""
        return bool(self.supported_media_commands & SUPPORT_PREVIOUS_TRACK)

    @property
    def support_next_track(self):
        """Boolean if next track command supported."""
        return bool(self.supported_media_commands & SUPPORT_NEXT_TRACK)

    @property
    def support_select_source(self):
        """Boolean if select source command supported."""
        return bool(self.supported_media_commands & SUPPORT_SELECT_SOURCE)

    def toggle(self):
        """Toggle the power on the media player."""
        if self.state in [STATE_OFF, STATE_IDLE]:
            self.turn_on()
        else:
            self.turn_off()

    def volume_up(self):
        """Turn volume up for media player."""
        if self.volume_level < 1:
            self.set_volume_level(min(1, self.volume_level + .1))

    def volume_down(self):
        """Turn volume down for media player."""
        if self.volume_level > 0:
            self.set_volume_level(max(0, self.volume_level - .1))

    def media_play_pause(self):
        """Play or pause the media player."""
        if self.state == STATE_PLAYING:
            self.media_pause()
        else:
            self.media_play()

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self.state == STATE_OFF:
            state_attr = {
                ATTR_SUPPORTED_MEDIA_COMMANDS: self.supported_media_commands,
            }
        else:
            state_attr = {
                attr: getattr(self, attr) for attr
                in ATTR_TO_PROPERTY if getattr(self, attr) is not None
            }

        return state_attr
