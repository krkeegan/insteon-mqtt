#===========================================================================
#
# Network and serial link management
#
#===========================================================================
import logging
import paho.mqtt.client as paho
from .Link import Link
from .. import Signal


class Mqtt (Link):
    def __init__(self, host, port=1883, id=None, reconnect_dt=10):
        super().__init__()
        self.host = host
        self.port = port
        self.connected = False

        self.signal_connected = Signal.Signal()  # (MqttLink, bool connected)
        self.signal_message = Signal.Signal()    # (MqttLink, Message msg)

        self._reconnect_dt = reconnect_dt
        self._fd = None

        self.client = paho.Client(client_id=id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self.log = logging.getLogger(__name__)

    #-----------------------------------------------------------------------
    def load_config(self, config):
        assert(not self.connected)

        self.host = config['broker']
        self.port = config['port']

        username =  config.get('username', None)
        if username is not None:
            password = config.get('password', None)
            self.client.username_pw_set(username, password)

    #-----------------------------------------------------------------------
    def publish(self, topic, payload, qos=0, retain=False):
        self.client.publish(topic, payload, qos, retain)
        self.signal_needs_write.emit(self, True)

        self.log.debug("MQTT publish %s %s qos=%s ret=%s", topic, payload,
                       qos, retain)

    #-----------------------------------------------------------------------
    def subscribe(self, topic, qos=0):
        self.client.subscribe(topic, qos)
        self.signal_needs_write.emit(self, True)

        self.log.debug("MQTT subscribe %s qos=%s", topic, qos)

    #-----------------------------------------------------------------------
    def unsubscribe(self, topic):
        self.client.unsubscribe(topic)
        self.signal_needs_write.emit(self, True)

        self.log.debug("MQTT unsubscribe %s", topic)

    #-----------------------------------------------------------------------
    def fileno(self):
        assert(self._fd)
        return self._fd

    #-----------------------------------------------------------------------
    def retry_connect_dt(self):
        return self._reconnect_dt

    #-----------------------------------------------------------------------
    def connect(self):
        try:
            self.client.connect(self.host, self.port)
            self._fd = self.client.socket().fileno()

            self.log.info("MQTT device opened %s %s", self.host, self.port)
            return True
        except:
            self.log.exception("MQTT connection error to %s %s", self.host,
                               self.port)
            return False

    #-----------------------------------------------------------------------
    def read_from_link(self):
        rtn = self.client.loop_read()

        self.log.debug("MQTT reading status %s", rtn)
        if rtn == 0:
            return 1
        else:
            return -1

    #-----------------------------------------------------------------------
    def write_to_link(self):
        self.client.loop_write()

        self.log.debug("MQTT writing")

        if not self.client.want_write():
            self.signal_needs_write.emit(self, False)

    #-----------------------------------------------------------------------
    def close(self):
        self.log.info("MQTT device closing %s %s", self.host, self.port)

        self.client.disconnect()
        self.signal_needs_write.emit(self, True)

    #-----------------------------------------------------------------------
    def _on_connect(self, client, data, flags, result):
        if result == 0:
            self.connected = True
            self.signal_connected.emit(self, True)
        else:
            self.log.error("MQTT connection refused %s %s %s", self.host,
                           self.port, result)

    #-----------------------------------------------------------------------
    def _on_disconnect(self, client, data, result):
        self.log.info("MQTT disconnection %s %s", self.host, self.port)

        self.connected = False
        self.signal_closing.emit(self)
        self.signal_connected.emit(self, False)

    #-----------------------------------------------------------------------
    def _on_message(self, client, data, message):
        self.log.info("MQTT message %s %s", message.topic, message.payload)
        self.signal_message.emit(self, message)

    #-----------------------------------------------------------------------
    def __str__(self):
        return "MQTT %s:%d" % (self.host, self.port)
    
    #-----------------------------------------------------------------------
