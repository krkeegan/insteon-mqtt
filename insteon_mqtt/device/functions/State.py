#===========================================================================
#
# State Functions.
#
#===========================================================================
from ..Base import Base
from ...Signal import Signal
from ... import log
from ... import on_off

LOG = log.get_logger()


class State(Base):
    """State Trait Abstract Class

    This is an abstract class that provides support for the State topic.
    """
    def __init__(self, protocol, modem, address, name=None):
        """Constructor

        Args:
          protocol (Protocol): The Protocol object used to communicate
                   with the Insteon network.  This is needed to allow the
                   device to send messages to the PLM modem.
          modem (Modem): The Insteon modem used to find other devices.
          address (Address): The address of the device.
          name (str): Nice alias name to use for the device.
        """
        super().__init__(protocol, modem, address, name)

        self._is_on = False
        self._level = 0x00

        # Support dimmer style signals and motion on/off style signals.
        # API:  func(Device, int level, on_off.Mode mode, str reason)
        self.signal_state = Signal()

    #-----------------------------------------------------------------------
    def _set_state(self, is_on=None, level=None, group=None,
                   mode=on_off.Mode.NORMAL, reason=""):
        """Update the device level or on/off state.

        This will change the internal state and emit the state changed
        signals.  It is called by whenever we're informed that the device has
        changed state.

        Args:
          is_on (bool):  True if the switch is on, False if it isn't.
          level (int): The new device level in the range [0,255].  0 is off.
          group (int): The group to which this applies
          mode (on_off.Mode): The type of on/off that was triggered (normal,
               fast, etc).
          reason (str):  This is optional and is used to identify why the
                 command was sent. It is passed through to the output signal
                 when the state changes - nothing else is done with it.
        """
        LOG.info("Setting device %s on %s level %s %s %s", self.label, is_on,
                 level, mode, reason)
        self._cache_state(group, is_on, level, reason)

        self.signal_state.emit(self, is_on=is_on, level=level, mode=mode,
                               button=group, reason=reason)

    #-----------------------------------------------------------------------
    def _cache_state(self, group, is_on, level, reason):
        """Cache the State of the Device

        Used to help with the unique device functions.

        Args:
          group (int): The group which this applies
          is_on (bool): Whether the device is on.
          level (int): The new device level in the range [0,255].  0 is off.
          reason (str): Reason string to pass around.
        """
        if is_on is not None:
            self._is_on = is_on
        if level is not None:
            self._level = level