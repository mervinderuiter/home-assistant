"""
Support for interface with a Sony Bravia TV.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.braviatv/
"""
import logging
import os
import json
import re
import sleekxmpp
import requests
import pprint
import time
from homeassistant.loader import get_component
from homeassistant.helpers import event
from sleekxmpp.xmlstream import ET

from homeassistant.components.remote import (
    SUPPORT_NEXT_TRACK, SUPPORT_PAUSE, SUPPORT_PREVIOUS_TRACK,
    SUPPORT_TURN_OFF, SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_STEP,
    SUPPORT_SELECT_SOURCE, RemoteControlDevice,
    SUPPORT_STOP, SUPPORT_PLAY_PAUSE, MEDIA_TYPE_CHANNEL)

from homeassistant.const import (
    STATE_OFF, STATE_ON, STATE_UNKNOWN, STATE_IDLE, SERVICE_TURN_ON, SERVICE_TURN_OFF, SERVICE_TOGGLE, SERVICE_MEDIA_PLAY)    

DEPENDENCIES = []

DOMAIN = "harmony"

LOGGER = logging.getLogger(__name__)

SUPPORT_HARMONY = SUPPORT_VOLUME_STEP | \
                 SUPPORT_VOLUME_MUTE | SUPPORT_STOP | SUPPORT_PAUSE |\
                 SUPPORT_PLAY_PAUSE | SUPPORT_PREVIOUS_TRACK | SUPPORT_NEXT_TRACK | \
                 SUPPORT_TURN_OFF | SUPPORT_SELECT_SOURCE | SUPPORT_STOP
                 
def setup_platform(hass, config, add_devices_callback, discovery_info=None):
    
    ip = config['ip']
    email = config['email']
    password = config['password']

    harmony = Harmony(email, password, ip, hass, event, add_devices_callback)
    harmony.initialize()
        
    return
                 
class Harmony():

    def __init__(self, email, password, ip, hass, event, add_devices_callback):
        
        self.email = email
        self.password = password
        self.ip = ip   
        self.hass = hass        
        self.port = 5222
        self.poweroff_id = "-1"
        self.event = event
        self.add_devices_callback = add_devices_callback
        
        self.logitech_auth_url = ('https://svcs.myharmony.com/CompositeSecurityServices/Security.svc/json/GetUserAuthToken')
        
        self.hass.services.register("harmony_activities", SERVICE_TURN_ON, self.turn_on)
        self.hass.services.register("harmony_activities", SERVICE_TURN_OFF, self.turn_off)        
        
        # Update the activity status every 30 seconds
        #self.event.track_time_change(self.hass, self.initialize, second=[0,30])
        
        # Automatically retrieve a new token every hour. Lifetime is not known yet. 
        self.event.track_time_change(self.hass, self.get_token, minute=0, second=0)

        self.token = None
        self.session_token = None
    
    def connect(self):
        
        if self.session_token == None:
            #try again with new token
            self.get_token()
                                        
        try:
            self.create_client()
        except:
            LOGGER.error('Could not connect to Harmony. Retry with new token.')
            self.get_token()
            self.create_client()

    def create_client(self):
    
        self.client = HarmonyClient(self.session_token)
        
        self.client.connect(address=(self.ip, self.port),
                       use_tls=False, use_ssl=False)
        self.client.process(block=False)

        while not self.client.sessionstarted:
            time.sleep(0.1)
    
    def disconnect(self):
        self.client.disconnect(send_close=False)
            
    def get_token(self, event=None):
        
        # Auth token obtained from the harmony server. This needs to be exchanged for a session token on the hub. 
        # Dont know how long this token is valid. Need to experiment. 
        
        headers = {'content-type': 'application/json; charset=utf-8'}
        data = {'email': self.email, 'password': self.password}
        data = json.dumps(data)
        resp = requests.post(self.logitech_auth_url, headers=headers, data=data)
        if resp.status_code != 200:
            LOGGER.error('Received response code %d from Logitech.',
                         resp.status_code)
            LOGGER.error('Data: \n%s\n', resp.text)
            return

        result = resp.json().get('GetUserAuthTokenResult', None)
        if not result:
            LOGGER.error('Malformed JSON (GetUserAuthTokenResult): %s', resp.json())
            return
        token = result.get('UserAuthToken', None)
        if not token:
            LOGGER.error('Malformed JSON (UserAuthToken): %s', resp.json())
            return
                
        self.token = token        
        self.session_token = self.get_session_token()
        
    def get_session_token(self):
        login_client = SwapAuthToken(self.token)
        login_client.connect(address=(self.ip, self.port),
                             use_tls=False, use_ssl=False)
        
        login_client.process(block=True)    
        return login_client.uuid

    def initialize(self, event=None):
                        
        LOGGER.info('Updating Harmony entities')
        self.connect()        

        # Get the current activity so we can set the state
        active_activity = str(self.client.get_current())[7:]
                
        # Get the configuration from the hub
        data = self.client.get_config()
        
        self.activities = []
        for activity in data['activity']:
            if not activity['id'] == self.poweroff_id:
                activity_dict = {}
                activity_dict['harmony_name'] = activity['label']
                activity_dict['harmony_id'] = activity['id']
                activity_dict['entity_id'] = activity['label'].replace (" ", "_").lower()
            
                if activity_dict['harmony_id'] == str(active_activity):
                    state = STATE_ON
                else:
                    state = STATE_OFF
                    
                

                #self.hass.states.set('harmony_activities.' + activity_dict['entity_id'], state)
                #self.activities.append(activity_dict)

        for device in data['device']:
        
            
            self.add_devices_callback([HarmonyDevice(device, self)])
            
            
            
            
        
        #    device['label'] = device['label'].replace (" ", "_").replace ("-", "_").lower()
        
        #    self.hass.services.register("harmony_remote_" + device['label'], SERVICE_TOGGLE, self.toggle)
        #    self.hass.services.register("harmony_remote_" + device['label'], SERVICE_MEDIA_PLAY, self.toggle)             
         #   self.hass.states.set('harmony_remote_' + device['label'] + '.mervin_test', STATE_OFF)
        
        #self.client.hold_action('29611288', 'Mute', 'press')
        #time.sleep(0.1)
        #self.client.hold_action('29611288', 'Pause', 'release')        
        self.disconnect()

    def send_command(self, command):
        
        self.connect()   
        self.client.hold_action(command['action'])
        self.disconnect()            
    
    def get_activity_by_entity(self, entity_id):
        entity = entity_id.split('.')
        for activity in self.activities:
            if activity['entity_id'] == entity[1]:
                return activity
        return False
        
    def turn_off(self, service):
        
        entity_id = service.data['entity_id']
        if type(entity_id) == list:
            entity_id = entity_id[0]
        
        self.connect()
        self.client.start_activity(self.poweroff_id)
        self.disconnect()
        
        self.hass.states.set(entity_id, STATE_OFF)        

    def turn_on(self, service):
        
        entity_id = service.data['entity_id']
        if type(entity_id) == list:
            entity_id = entity_id[0]

        activity = self.get_activity_by_entity(entity_id)
        
        self.connect()
        self.client.start_activity(activity['harmony_id'])
        self.disconnect()
        
        self.hass.states.set(entity_id, STATE_ON)
        
    def toggle(self, service):
        
        entity_id = service.data['entity_id']
        if type(entity_id) == list:
            entity_id = entity_id[0]

        activity = self.get_activity_by_entity(entity_id)
        
        self.connect()
        self.client.start_activity(activity['harmony_id'])
        self.disconnect()
        
        self.hass.states.set(entity_id, STATE_ON)
        
class HarmonyDevice(RemoteControlDevice):

    def __init__(self, device, harmony):
    
        self._device = device
        self._harmony = harmony
        #self._name = self._device['label'].replace ("-", "_").lower()
        self._name = self._device['label'].lower()
        self._source_list = []
  
        self._commands = []
  
        for control_group in self._device['controlGroup']:
            for function in control_group['function']:
                self._source_list.append(function['label'])
                
                command = {}
                command['name'] = function['name']
                command['label'] = function['label']
                command['action'] = function['action']
                
                self._commands.append(function)
         
        
    @property
    def should_poll(self):
        """No polling needed."""
        return False
        
    @property
    def state(self):
        """Return the state of the player."""
        
        #return STATE_IDLE        
        #return STATE_OFF        
        return STATE_UNKNOWN
    
    @property
    def name(self):
        """Return the name of the device."""
        return self._name
        
    @property
    def supported_media_commands(self):
        """Flag of media commands that are supported."""
        return SUPPORT_HARMONY

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        return None
        
    @property
    def source_list(self):
        """Used to store all IR commands."""
        return self._source_list
        
    @property
    def media_content_type(self):
        """Content type of current playing media."""
        return MEDIA_TYPE_CHANNEL
        
    def turn_on(self):
        """Turn on the device."""
        # TODO
        
    def turn_off(self):
        """Turn off the device."""
        # TODO
    
    def media_stop(self):
        """Send stop command."""
        self.try_send_command("Stop")
        
    def media_play(self):
        """Send play commmand."""
        self.try_send_command("Play")
        
    def media_play_pause(self):
        """Send play/pause commmand."""
        self.try_send_command("Pause")

    def media_pause(self):
        """Send pause command."""
        self.try_send_command("Pause")
        
    def volume_up(self):
        """Volume up."""
        self.try_send_command("VolumeUp")

    def volume_down(self):
        """Volume down."""
        self.try_send_command("VolumeDown")
        
    def select_source(self, source):
        """Set the input source."""
        for command in self._commands:
            if command['label'] == source:
                self.send_command(command)
                
    def try_send_command(self, name):
        command = self.find_command(name)
        if command:
            self.send_command(command)
        else:
            LOGGER.warning('Selected command not supported by this device.')
    
    def find_command(self, name):
        for command in self._commands:
            if command['name'] == name:
                return command
        return False
                
    def send_command(self, command):
        LOGGER.info('Device ' + self._name + ' sending command: ' + command['action'])
        self._harmony.send_command(command)             
    

class SwapAuthToken(sleekxmpp.ClientXMPP):
    """An XMPP client for swapping a Login Token for a Session Token.

    After the client finishes processing, the uuid attribute of the class will
    contain the session token.
    """

    def __init__(self, token):
        """Initializes the client.

        Args:
          token: The base64 string containing the 48-byte Login Token.
        """
        plugin_config = {
            # Enables PLAIN authentication which is off by default.
            'feature_mechanisms': {'unencrypted_plain': True},
        }
        super(SwapAuthToken, self).__init__(
            'guest@connect.logitech.com/gatorade.', 'gatorade.', plugin_config=plugin_config)

        self.token = token
        self.uuid = None
        self.add_event_handler('session_start', self.session_start)

    def session_start(self, _):
        """Called when the XMPP session has been initialized."""
        iq_cmd = self.Iq()
        iq_cmd['type'] = 'get'
        action_cmd = ET.Element('oa')
        action_cmd.attrib['xmlns'] = 'connect.logitech.com'
        action_cmd.attrib['mime'] = 'vnd.logitech.connect/vnd.logitech.pair'
        action_cmd.text = 'token=%s:name=%s' % (self.token,
                                                'foo#iOS6.0.1#iPhone')
        iq_cmd.set_payload(action_cmd)
        result = iq_cmd.send(block=True)
        payload = result.get_payload()
        assert len(payload) == 1
        oa_resp = payload[0]
        assert oa_resp.attrib['errorcode'] == '200'
        match = re.search(r'identity=(?P<uuid>[\w-]+):status', oa_resp.text)
        assert match
        self.uuid = match.group('uuid')
        LOGGER.info('Received UUID from device: %s', self.uuid)
        self.disconnect(send_close=False)


class HarmonyClient(sleekxmpp.ClientXMPP):
    """An XMPP client for connecting to the Logitech Harmony."""

    def __init__(self, auth_token):
        user = '%s@connect.logitech.com/gatorade' % auth_token
        password = auth_token
        plugin_config = {
            # Enables PLAIN authentication which is off by default.
            'feature_mechanisms': {'unencrypted_plain': True},
        }
        super(HarmonyClient, self).__init__(
            user, password, plugin_config=plugin_config)

    def get_config(self):
        """Retrieves the Harmony device configuration.

        Returns:
          A nested dictionary containing activities, devices, etc.
        """
        iq_cmd = self.Iq()
        iq_cmd['type'] = 'get'
        action_cmd = ET.Element('oa')
        action_cmd.attrib['xmlns'] = 'connect.logitech.com'
        action_cmd.attrib['mime'] = (
            'vnd.logitech.harmony/vnd.logitech.harmony.engine?config')
        iq_cmd.set_payload(action_cmd)
        result = iq_cmd.send(block=True)
        payload = result.get_payload()
        assert len(payload) == 1
        action_cmd = payload[0]
        assert action_cmd.attrib['errorcode'] == '200'
        device_list = action_cmd.text
        print(device_list)
        return json.loads(device_list)

    def get_current(self):
        """Retrieves the Harmony device configuration.

        Returns:
          A nested dictionary containing activities, devices, etc.
        """
        iq_cmd = self.Iq()
        iq_cmd['type'] = 'get'
        action_cmd = ET.Element('oa')
        action_cmd.attrib['xmlns'] = 'connect.logitech.com'
        action_cmd.attrib['mime'] = (
            'vnd.logitech.harmony/vnd.logitech.harmony.engine?getCurrentActivity')
        iq_cmd.set_payload(action_cmd)
        result = iq_cmd.send(block=True)
        payload = result.get_payload()
        assert len(payload) == 1
        action_cmd = payload[0]
        assert action_cmd.attrib['errorcode'] == '200'
        device_list = action_cmd.text
        return device_list

    def start_activity(self, activity_id):
        """Retrieves the Harmony device configuration.

        Returns:
          A nested dictionary containing activities, devices, etc.
        """
        iq_cmd = self.Iq()
        iq_cmd['type'] = 'get'
        action_cmd = ET.Element('oa')
        action_cmd.attrib['xmlns'] = 'connect.logitech.com'
        action_cmd.attrib['mime'] = (
            'vnd.logitech.harmony/vnd.logitech.harmony.engine?startactivity')
        action_cmd.text = 'activityId=' + activity_id + ':timestamp=0'
        iq_cmd.set_payload(action_cmd)
        result = iq_cmd.send(block=True)
        payload = result.get_payload()
        assert len(payload) == 1
        action_cmd = payload[0]
        assert action_cmd.attrib['errorcode'] == '200'
        device_list = action_cmd.text
        return device_list
        
    def hold_action(self, action):
        """Retrieves the Harmony device configuration.

        Returns:
          A nested dictionary containing activities, devices, etc.
        """
        iq_cmd = self.Iq()
        iq_cmd['type'] = 'get'
        action_cmd = ET.Element('oa')
        action_cmd.attrib['xmlns'] = 'connect.logitech.com'
        action_cmd.attrib['mime'] = (
            'vnd.logitech.harmony/vnd.logitech.harmony.engine?holdAction')        
        action_json = json.loads(action)
        action_string = '{"type"::"IRCommand","deviceId"::"' + action_json['deviceId'] + '","command"::"' + action_json['command'] + '"}'
        status = 'status=press'
        timestamp = 'timestamp=0'        
        action_cmd.text = 'action=' + action_string + ':' + status + ':' + timestamp        
        iq_cmd.set_payload(action_cmd)
        result = iq_cmd.send(block=True)
        payload = result.get_payload()
        assert len(payload) == 1
        action_cmd = payload[0]
        assert action_cmd.attrib['errorcode'] == '200'
        device_list = action_cmd.text
        return device_list
           