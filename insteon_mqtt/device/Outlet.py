#===========================================================================
#
# Insteon on/off outlet
#
#===========================================================================
import functools
from .Base import Base
from . import functions
from ..CommandSeq import CommandSeq
from .. import handler
from .. import log
from .. import message as Msg
from .. import on_off
from ..Signal import Signal
from .. import util

LOG = log.get_logger()


class Outlet(functions.Set, Base):
    """Insteon on/off outlet device.

    This is used for in-wall on/off outlets.  Each outlet (top and bottom) is
    an independent switch and is controlled via group 1 (top) and group2
    (bottom) inputs.

    State changes are communicated by emitting signals.  Other classes can
    connect to these signals to perform an action when a change is made to
    the device (like sending MQTT messages).  Supported signals are:

    - signal_state( Device, int group, bool is_on, on_off.Mode mode, str
                     reason ): Sent whenever the switch is turned on or off.
                     Group will be 1 for the top outlet and 2 for the bottom
                     outlet.
    """

    def __init__(self, protocol, modem, address, name=None):
        """Constructor

        Args:
          protocol (Protocol):  The Protocol object used to communicate
                   with the Insteon network.  This is needed to allow the
                   device to send messages to the PLM modem.
          modem (Modem):  The Insteon modem used to find other devices.
          address (Address):  The address of the device.
          name (str):  Nice alias name to use for the device.
        """
        super().__init__(protocol, modem, address, name)

        self._is_on = [False, False]  # top outlet, bottom outlet

        # Support on/off style signals.
        # API: func(Device, int group, bool is_on, on_off.Mode mode,
        #           str reason)
        self.signal_state = Signal()

        # Remote (mqtt) commands mapped to methods calls.  Add to the
        # base class defined commands.
        self.cmd_map.update({
            'on' : self.on,
            'off' : self.off,
            'set_flags' : self.set_flags,
            })

        # NOTE: the outlet does NOT include the group in the ACK of an on/off
        # command.  So there is no way to tell which outlet is being ACK'ed
        # if we send multiple messages to it.  Each time on or off is called,
        # it pushes the outlet to this list so that when the ACK/NAK arrives,
        # we can pop it off and know which outlet was being commanded.
        self._which_outlet = []

        # Update the group map with the groups to be paired and the handler
        # for broadcast messages from this group
        # Can the outlet really act as a controller?
        self.group_map.update({0x01: self.handle_on_off,
                               0x02: self.handle_on_off})

    #-----------------------------------------------------------------------
    def refresh(self, force=False, on_done=None):
        """Refresh the current device state and database if needed.

        This sends a ping to the device.  The reply has the current device
        state (on/off, level, etc) and the current db delta value which is
        checked against the current db value.  If the current db is out of
        date, it will trigger a download of the database.

        This will send out an updated signal for the current device status
        whenever possible (like dimmer levels).

        Args:
          force (bool):  If true, will force a refresh of the device database
                even if the delta value matches as well as a re-query of the
                device model information even if it is already known.
          on_done: Finished callback.  This is called when the command has
                   completed.  Signature is: on_done(success, msg, data)
        """
        LOG.info("Outlet %s cmd: status refresh", self.label)

        seq = CommandSeq(self, "Device refreshed", on_done, name="DevRefresh")

        # This sends a refresh ping which will respond w/ the current
        # database delta field.  The handler checks that against the current
        # value.  If it's different, it will send a database download command
        # to the device to update the database.  Code 0x19 also allows us to
        # get the state of both outlets in a single field.
        msg = Msg.OutStandard.direct(self.addr, 0x19, 0x01)
        msg_handler = handler.DeviceRefresh(self, self.handle_refresh, force,
                                            on_done, num_retry=3)
        seq.add_msg(msg, msg_handler)

        # If model number is not known, or force true, run get_model
        self.addRefreshData(seq, force)

        # Run all the commands.
        seq.run()

    #-----------------------------------------------------------------------
    def on(self, group=0x01, level=None, mode=on_off.Mode.NORMAL,
           reason="", transition=None, on_done=None):
        """Turn the device on.

        This will send the command to the device to update it's state.  When
        we get an ACK of the result, we'll change our internal state and emit
        the state changed signals.

        Args:
          group (int):  The group to send the command to.  The top outlet is
                group 1, the bottom outlet is group 2.
          level (int):  If non zero, turn the device on.  Should be in the
                range 0 to 255.  Only dimmers use the intermediate values, all
                other devices look at level=0 or level>0.
          mode (on_off.Mode): The type of command to send (normal, fast, etc).
          reason (str):  This is optional and is used to identify why the
                 command was sent. It is passed through to the output signal
                 when the state changes - nothing else is done with it.
          on_done: Finished callback.  This is called when the command has
                   completed.  Signature is: on_done(success, msg, data)
        """
        LOG.info("Outlet %s grp: %s cmd: on", group, self.addr)
        assert 1 <= group <= 2
        assert isinstance(mode, on_off.Mode)

        if transition or mode == on_off.Mode.RAMP:
            LOG.error("Device %s does not support transition.", self.addr)
            mode = on_off.Mode.NORMAL if mode == on_off.Mode.RAMP else mode

        # Send the requested on code value.
        cmd1 = on_off.Mode.encode(True, mode)

        # Top outlet uses a standard message
        if group == 1:
            msg = Msg.OutStandard.direct(self.addr, cmd1, 0xff)

        # Bottom outlet uses an extended message
        else:
            data = bytes([0x02] + [0x00] * 13)
            msg = Msg.OutExtended.direct(self.addr, cmd1, 0xff, data)

        # Use the standard command handler which will notify us when
        # the command is ACK'ed.
        callback = functools.partial(self.handle_ack, reason=reason)
        msg_handler = handler.StandardCmd(msg, callback, on_done)

        # See __init__ code comments for what this is for.
        self._which_outlet.append(group)

        # Send the message to the PLM modem for protocol.
        self.send(msg, msg_handler)

    #-----------------------------------------------------------------------
    def off(self, group=0x01, mode=on_off.Mode.NORMAL, reason="",
            transition=None, on_done=None):
        """Turn the device off.

        This will send the command to the device to update it's state.  When
        we get an ACK of the result, we'll change our internal state and emit
        the state changed signals.

        Args:
          group (int):  The group to send the command to.  The top outlet is
                group 1, the bottom outlet is group 2.
          mode (on_off.Mode): The type of command to send (normal, fast, etc).
          reason (str):  This is optional and is used to identify why the
                 command was sent. It is passed through to the output signal
                 when the state changes - nothing else is done with it.
          on_done: Finished callback.  This is called when the command has
                   completed.  Signature is: on_done(success, msg, data)
        """
        LOG.info("Outlet %s cmd: off", self.addr)
        assert 1 <= group <= 2
        assert isinstance(mode, on_off.Mode)

        if transition or mode == on_off.Mode.RAMP:
            LOG.error("Device %s does not support transition.", self.addr)
            mode = on_off.Mode.NORMAL if mode == on_off.Mode.RAMP else mode

        # Send the correct off code.
        cmd1 = on_off.Mode.encode(False, mode)

        # Top outlet uses a standard message
        if group == 1:
            msg = Msg.OutStandard.direct(self.addr, cmd1, 0x00)

        # Bottom outlet uses an extended message
        else:
            data = bytes([0x02] + [0x00] * 13)
            msg = Msg.OutExtended.direct(self.addr, cmd1, 0x00, data)

        # Use the standard command handler which will notify us when the
        # command is ACK'ed.
        callback = functools.partial(self.handle_ack, reason=reason)
        msg_handler = handler.StandardCmd(msg, callback, on_done)

        # See __init__ code comments for what this is for.
        self._which_outlet.append(group)

        # Send the message to the PLM modem for protocol.
        self.send(msg, msg_handler)

    #-----------------------------------------------------------------------
    def set_backlight(self, level, on_done=None):
        """Set the device backlight level.

        This changes the level of the LED back light that is used by the
        device status LED's (dimmer levels, KeypadLinc buttons, etc).

        The default factory level is 0x1f.

        Per page 157 of insteon dev guide range is between 0x11 and 0x7F,
        however in practice backlight can be incremented from 0x00 to at least
        0x7f.

        Args:
          level (int):  The backlight level in the range [0,255]
          on_done: Finished callback.  This is called when the command has
                   completed.  Signature is: on_done(success, msg, data)
        """
        seq = CommandSeq(self, "Outlet set backlight complete", on_done,
                         name="SetBacklight")

        # First set the backlight on or off depending on level value
        is_on = level > 0
        LOG.info("Outlet %s setting backlight to %s", self.label, is_on)
        cmd = 0x09 if is_on else 0x08
        msg = Msg.OutExtended.direct(self.addr, 0x20, cmd, bytes([0x00] * 14))
        msg_handler = handler.StandardCmd(msg, self.handle_backlight, on_done)
        seq.add_msg(msg, msg_handler)

        if is_on:
            # Second set the level only if on
            LOG.info("Outlet %s setting backlight to %s", self.label, level)

            # Extended message data - see Insteon dev guide p156.
            data = bytes([
                0x01,   # D1 must be group 0x01
                0x07,   # D2 set global led brightness
                level,  # D3 brightness level
                ] + [0x00] * 11)

            msg = Msg.OutExtended.direct(self.addr, 0x2e, 0x00, data)
            msg_handler = handler.StandardCmd(msg, self.handle_backlight,
                                              on_done)
            seq.add_msg(msg, msg_handler)

        seq.run()

    #-----------------------------------------------------------------------
    def set_flags(self, on_done, **kwargs):
        """Set internal device flags.

        This command is used to change internal device flags and states.
        Valid inputs are:

        - backlight=level:  Change the backlight LED level (0-255).  See
          set_backlight() for details.

        Args:
          kwargs: Key=value pairs of the flags to change.
          on_done: Finished callback.  This is called when the command has
                   completed.  Signature is: on_done(success, msg, data)
        """
        LOG.info("Outlet %s cmd: set flags", self.label)

        # Check the input flags to make sure only ones we can understand were
        # passed in.
        FLAG_BACKLIGHT = "backlight"
        flags = set([FLAG_BACKLIGHT])
        unknown = set(kwargs.keys()).difference(flags)
        if unknown:
            LOG.error("Unknown Outlet flags input: %s.\n Valid flags "
                      "are: %s", unknown, flags)

        # Start a command sequence so we can call the flag methods in series.
        seq = CommandSeq(self, "Outlet set_flags complete", on_done,
                         name="DevSetFlags")

        if FLAG_BACKLIGHT in kwargs:
            backlight = util.input_byte(kwargs, FLAG_BACKLIGHT)
            seq.add(self.set_backlight, backlight)

        seq.run()

    #-----------------------------------------------------------------------
    def handle_backlight(self, msg, on_done):
        """Callback for handling set_backlight() responses.

        This is called when we get a response to the set_backlight() command.
        We don't need to do anything - just call the on_done callback with
        the status.

        Args:
          msg (InpStandard):  The response message from the command.
          on_done: Finished callback.  This is called when the command has
                   completed.  Signature is: on_done(success, msg, data)
        """
        on_done(True, "Backlight level updated", None)

    #-----------------------------------------------------------------------
    def handle_on_off(self, msg):
        """Handle broadcast on_off messages from this device.

        This is called via the handle_broadcast and the mapping in group_map.

        Args:
          msg (InpStandard):  Broadcast message from the device.
        """
        reason = on_off.REASON_DEVICE
        if msg.cmd1 == Msg.CmdType.LINK_CLEANUP_REPORT:
            LOG.info("Outlet %s broadcast ACK grp: %s", self.addr, msg.group)

        # On/off command codes.
        elif on_off.Mode.is_valid(msg.cmd1):
            is_on, mode = on_off.Mode.decode(msg.cmd1)
            LOG.info("Outlet %s broadcast grp: %s on: %s mode: %s", self.addr,
                     msg.group, is_on, mode)

            self._set_is_on(msg.group, is_on, mode, reason)

            self.update_linked_devices(msg)

    #-----------------------------------------------------------------------
    def handle_refresh(self, msg):
        """Callback for handling refresh() responses.

        This is called when we get a response to the refresh() command.  The
        refresh command reply will contain the current device state in cmd2
        and this updates the device with that value.  It is called by
        handler.DeviceRefresh when we can an ACK for the refresh command.

        Args:
          msg (message.InpStandard):  The refresh message reply.  The current
              device state is in the msg.cmd2 field.
        """
        # From outlet developers guide - refresh must be 0x19 0x01 to enable
        # these codes which allows us to get the state of both outlets with
        # one call.
        response = {
            0x00: [False, False],
            0x01: [True, False],
            0x02: [False, True],
            0x03: [True, True]
            }

        is_on = response.get(msg.cmd2, None)
        if is_on is not None:
            LOG.ui(" %s refresh top=%s bottom=%s", self.label, is_on[0],
                   is_on[1])

            # Set the state for each outlet.
            self._set_is_on(1, is_on[0], reason=on_off.REASON_REFRESH)
            self._set_is_on(2, is_on[1], reason=on_off.REASON_REFRESH)

        else:
            LOG.error("Outlet %s unknown refresh response %s", self.label,
                      msg.cmd2)

    #-----------------------------------------------------------------------
    def handle_ack(self, msg, on_done, reason=""):
        """Callback for standard commanded messages.

        This callback is run when we get a reply back from one of our
        commands to the device.  If the command was ACK'ed, we know it worked
        so we'll update the internal state of the device and emit the signals
        to notify others of the state change.

        Args:
          msg (message.InpStandard):  The reply message from the device.
              The on/off level will be in the cmd2 field.
          on_done: Finished callback.  This is called when the command has
                   completed.  Signature is: on_done(success, msg, data)
          reason (str):  This is optional and is used to identify why the
                 command was sent. It is passed through to the output signal
                 when the state changes - nothing else is done with it.
        """
        # Get the last outlet we were commanding.  The message doesn't tell
        # us which outlet it was so we have to track it here.  See __init__
        # code comments for more info.
        if not self._which_outlet:
            LOG.error("Outlet %s ACK error.  No outlet ID's were saved",
                      self.addr)
            on_done(False, "Outlet update failed - no ID's saved", None)
            return

        group = self._which_outlet.pop(0)

        # If this it the ACK we're expecting, update the internal
        # state and emit our signals.
        LOG.debug("Outlet %s grp: %s ACK: %s", self.addr, group, msg)

        is_on, mode = on_off.Mode.decode(msg.cmd1)
        reason = reason if reason else on_off.REASON_COMMAND
        self._set_is_on(group, is_on, mode, reason)
        on_done(True, "Outlet state updated to on=%s" % self._is_on,
                self._is_on)

    #-----------------------------------------------------------------------
    def handle_group_cmd(self, addr, msg):
        """Respond to a group command for this device.

        This is called when this device is a responder to a scene.  The
        device that received the broadcast message (handle_broadcast) will
        call this method for every device that is linked to it.  The device
        should look up the responder entry for the group in it's all link
        database and update it's state accordingly.

        Args:
          addr (Address):  The device that sent the message.  This is the
               controller in the scene.
          msg (InpStandard):  Broadcast message from the device.  Use
              msg.group to find the group and msg.cmd1 for the command.
        """
        # Make sure we're really a responder to this message.  This shouldn't
        # ever occur.
        entry = self.db.find(addr, msg.group, is_controller=False)
        if not entry:
            LOG.error("Outlet %s has no group %s entry from %s", self.addr,
                      msg.group, addr)
            return

        # The local button being modified is stored in the db entry.
        localGroup = entry.data[2]

        # Handle on/off commands codes.
        if on_off.Mode.is_valid(msg.cmd1):
            is_on, mode = on_off.Mode.decode(msg.cmd1)
            self._set_is_on(localGroup, is_on, mode, on_off.REASON_SCENE)

        # Note: I don't believe the on/off switch can participate in manual
        # mode stopping commands since it changes state when the button is
        # held, not when it's released.
        else:
            LOG.warning("Outlet %s unknown group cmd %#04x", self.addr,
                        msg.cmd1)

    #-----------------------------------------------------------------------
    def _set_is_on(self, group, is_on, mode=on_off.Mode.NORMAL, reason=""):
        """Update the device on/off state.

        This will change the internal state and emit the state changed
        signals.  It is called by whenever we're informed that the device has
        changed state.

        Args:
          group (int):  The group to update (1 for upper outlet, 2 for lower).
          is_on (bool):  True if the switch is on, False if it isn't.
          mode (on_off.Mode): The type of on/off that was triggered (normal,
               fast, etc).
          reason (str):  This is optional and is used to identify why the
                 command was sent. It is passed through to the output signal
                 when the state changes - nothing else is done with it.
        """
        is_on = bool(is_on)

        LOG.info("Setting device %s grp: %s on %s %s %s", self.label, group,
                 is_on, mode, reason)
        self._is_on[group - 1] = is_on

        # Notify others that the outlet state has changed.
        self.signal_state.emit(self, button=group, is_on=is_on, mode=mode,
                               reason=reason)

    #-----------------------------------------------------------------------
