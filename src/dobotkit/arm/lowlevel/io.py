"""IO / EMotor / WAIT / TRIG commands (Task 2.7).

This mixin covers the digital/analog IO surface (multiplexing, DO, PWM, DI,
ADC), the extended stepper motors (``EMotor`` / ``EMotorS``), and the queued
``WAIT`` / ``TRIG`` commands.

Ext / ExtEx routing
-------------------
The SDK exposes three flavours of every IO/EMotor call: the base function, an
``*Ext`` variant, and an ``*ExtEx`` variant. The only behavioural difference is
the slave the frame is routed to: under a MagicBox controller the base function
already auto-routes to the MagicBox slave (slave id ``-1``); the ``Ext`` /
``ExtEx`` variants force that routing explicitly (see research doc s1).

To stay DRY we implement each command **once** and generate the ``_ext`` /
``_ext_ex`` variants as thin wrappers that set ``self._routed_to_magicbox`` for
the duration of the underlying call. The slave id is not part of the wire frame
this layer emits, so the flag is recorded (and reset in a ``finally`` so it
never leaks to a subsequent call) for the transport/controller layer to honour;
the protocol id is shared by all three flavours.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from dobotkit.arm import structures as S
from dobotkit.arm.ids import ProtocolId
from dobotkit.arm.lowlevel._base import _LowLevelProtocol


class IoMixin(_LowLevelProtocol):
    """IO / EMotor / WAIT / TRIG commands."""

    # -- MagicBox routing flag --------------------------------------------- #

    _routed_to_magicbox: bool = False

    @contextmanager
    def _magicbox_routing(self) -> Iterator[None]:
        """Flag the wrapped call as MagicBox-routed (Ext/ExtEx convention).

        Sets :attr:`_routed_to_magicbox` for the duration of the body and always
        resets it afterwards so the flag never leaks to an unrelated call.
        """
        self._routed_to_magicbox = True
        try:
            yield
        finally:
            self._routed_to_magicbox = False

    # -- IO multiplexing --------------------------------------------------- #

    def set_io_multiplexing(
        self, address: int, multiplex: int, *, queued: bool = False
    ) -> Optional[int]:
        """Assign a multiplex function to an IO pin."""
        resp = self._send(
            ProtocolId.SET_GET_IO_MULTIPLEXING,
            S.pack_IOMultiplexing(address, multiplex),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_io_multiplexing(self, address: int) -> S.IOMultiplexing:
        """Read the multiplex function currently assigned to an IO pin."""
        resp = self._send(
            ProtocolId.SET_GET_IO_MULTIPLEXING,
            S.pack_IOMultiplexing(address, 0),
            rw=False,
        )
        return S.unpack_IOMultiplexing(resp.params)

    def set_io_multiplexing_ext(
        self, address: int, multiplex: int, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed :meth:`set_io_multiplexing`."""
        with self._magicbox_routing():
            return self.set_io_multiplexing(address, multiplex, queued=queued)

    def set_io_multiplexing_ext_ex(
        self, address: int, multiplex: int, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed (ExtEx) :meth:`set_io_multiplexing`."""
        with self._magicbox_routing():
            return self.set_io_multiplexing(address, multiplex, queued=queued)

    def get_io_multiplexing_ext(self, address: int) -> S.IOMultiplexing:
        """MagicBox-routed :meth:`get_io_multiplexing`."""
        with self._magicbox_routing():
            return self.get_io_multiplexing(address)

    def get_io_multiplexing_ext_ex(self, address: int) -> S.IOMultiplexing:
        """MagicBox-routed (ExtEx) :meth:`get_io_multiplexing`."""
        with self._magicbox_routing():
            return self.get_io_multiplexing(address)

    # -- IO digital output (DO) -------------------------------------------- #

    def set_io_do(
        self, address: int, level: int, *, queued: bool = False
    ) -> Optional[int]:
        """Set the digital-output level of an IO pin."""
        resp = self._send(
            ProtocolId.SET_GET_IO_DO,
            S.pack_IODO(address, level),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_io_do(self, address: int) -> S.IODO:
        """Read the digital-output level set on an IO pin."""
        resp = self._send(
            ProtocolId.SET_GET_IO_DO,
            S.pack_IODO(address, 0),
            rw=False,
        )
        return S.unpack_IODO(resp.params)

    def set_io_do_ext(
        self, address: int, level: int, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed :meth:`set_io_do`."""
        with self._magicbox_routing():
            return self.set_io_do(address, level, queued=queued)

    def set_io_do_ext_ex(
        self, address: int, level: int, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed (ExtEx) :meth:`set_io_do`."""
        with self._magicbox_routing():
            return self.set_io_do(address, level, queued=queued)

    def get_io_do_ext(self, address: int) -> S.IODO:
        """MagicBox-routed :meth:`get_io_do`."""
        with self._magicbox_routing():
            return self.get_io_do(address)

    def get_io_do_ext_ex(self, address: int) -> S.IODO:
        """MagicBox-routed (ExtEx) :meth:`get_io_do`."""
        with self._magicbox_routing():
            return self.get_io_do(address)

    # -- IO PWM ------------------------------------------------------------ #

    def set_io_pwm(
        self,
        address: int,
        frequency: float,
        duty_cycle: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Configure PWM output (frequency Hz, duty cycle %) on an IO pin."""
        resp = self._send(
            ProtocolId.SET_GET_IO_PWM,
            S.pack_IOPWM(address, frequency, duty_cycle),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def get_io_pwm(self, address: int) -> S.IOPWM:
        """Read the PWM configuration of an IO pin."""
        resp = self._send(
            ProtocolId.SET_GET_IO_PWM,
            S.pack_IOPWM(address, 0.0, 0.0),
            rw=False,
        )
        return S.unpack_IOPWM(resp.params)

    def set_io_pwm_ext(
        self,
        address: int,
        frequency: float,
        duty_cycle: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """MagicBox-routed :meth:`set_io_pwm`."""
        with self._magicbox_routing():
            return self.set_io_pwm(address, frequency, duty_cycle, queued=queued)

    def set_io_pwm_ext_ex(
        self,
        address: int,
        frequency: float,
        duty_cycle: float,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """MagicBox-routed (ExtEx) :meth:`set_io_pwm`."""
        with self._magicbox_routing():
            return self.set_io_pwm(address, frequency, duty_cycle, queued=queued)

    def get_io_pwm_ext(self, address: int) -> S.IOPWM:
        """MagicBox-routed :meth:`get_io_pwm`."""
        with self._magicbox_routing():
            return self.get_io_pwm(address)

    def get_io_pwm_ext_ex(self, address: int) -> S.IOPWM:
        """MagicBox-routed (ExtEx) :meth:`get_io_pwm`."""
        with self._magicbox_routing():
            return self.get_io_pwm(address)

    # -- IO digital input (DI) --------------------------------------------- #

    def get_io_di(self, address: int) -> S.IODI:
        """Read the digital-input level of an IO pin."""
        resp = self._send(
            ProtocolId.GET_IO_DI,
            S.pack_IODI(address),
            rw=False,
        )
        return S.unpack_IODI(resp.params)

    def get_io_di_ext(self, address: int) -> S.IODI:
        """MagicBox-routed :meth:`get_io_di`."""
        with self._magicbox_routing():
            return self.get_io_di(address)

    def get_io_di_ext_ex(self, address: int) -> S.IODI:
        """MagicBox-routed (ExtEx) :meth:`get_io_di`."""
        with self._magicbox_routing():
            return self.get_io_di(address)

    # -- IO ADC ------------------------------------------------------------ #

    def get_io_adc(self, address: int) -> S.IOADC:
        """Read the ADC value of an IO pin."""
        resp = self._send(
            ProtocolId.GET_IO_ADC,
            S.pack_IOADC(address),
            rw=False,
        )
        return S.unpack_IOADC(resp.params)

    def get_io_adc_ext(self, address: int) -> S.IOADC:
        """MagicBox-routed :meth:`get_io_adc`."""
        with self._magicbox_routing():
            return self.get_io_adc(address)

    def get_io_adc_ext_ex(self, address: int) -> S.IOADC:
        """MagicBox-routed (ExtEx) :meth:`get_io_adc`."""
        with self._magicbox_routing():
            return self.get_io_adc(address)

    # -- Extended motors --------------------------------------------------- #

    def set_e_motor(
        self, index: int, is_enabled: int, speed: int, *, queued: bool = False
    ) -> Optional[int]:
        """Drive an extended (conveyor/stepper) motor at a continuous speed."""
        resp = self._send(
            ProtocolId.SET_EMOTOR,
            S.pack_EMotor(index, is_enabled, speed),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def set_e_motor_ext(
        self, index: int, is_enabled: int, speed: int, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed :meth:`set_e_motor`."""
        with self._magicbox_routing():
            return self.set_e_motor(index, is_enabled, speed, queued=queued)

    def set_e_motor_ext_ex(
        self, index: int, is_enabled: int, speed: int, *, queued: bool = False
    ) -> Optional[int]:
        """MagicBox-routed (ExtEx) :meth:`set_e_motor`."""
        with self._magicbox_routing():
            return self.set_e_motor(index, is_enabled, speed, queued=queued)

    def set_e_motors(
        self,
        index: int,
        is_enabled: int,
        speed: int,
        distance: int,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Drive an extended motor a fixed distance at a given speed."""
        resp = self._send(
            ProtocolId.SET_EMOTOR_S,
            S.pack_EMotorS(index, is_enabled, speed, distance),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def set_e_motors_ext(
        self,
        index: int,
        is_enabled: int,
        speed: int,
        distance: int,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """MagicBox-routed :meth:`set_e_motors`."""
        with self._magicbox_routing():
            return self.set_e_motors(
                index, is_enabled, speed, distance, queued=queued
            )

    def set_e_motors_ext_ex(
        self,
        index: int,
        is_enabled: int,
        speed: int,
        distance: int,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """MagicBox-routed (ExtEx) :meth:`set_e_motors`."""
        with self._magicbox_routing():
            return self.set_e_motors(
                index, is_enabled, speed, distance, queued=queued
            )

    # -- WAIT / TRIG ------------------------------------------------------- #

    def set_wait_cmd(
        self, wait_time: int, *, queued: bool = False
    ) -> Optional[int]:
        """Queue a wait command (pauses the queue for ``wait_time`` ms)."""
        resp = self._send(
            ProtocolId.SET_WAIT_CMD,
            S.pack_WAITCmd(wait_time),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None

    def set_trig_cmd(
        self,
        address: int,
        mode: int,
        condition: int,
        threshold: int,
        *,
        queued: bool = False,
    ) -> Optional[int]:
        """Queue a trigger command (block the queue until an IO/ADC condition)."""
        resp = self._send(
            ProtocolId.SET_TRIG_CMD,
            S.pack_TRIGCmd(address, mode, condition, threshold),
            rw=True,
            queued=queued,
        )
        return self._queued_index(resp) if queued else None
