"""A guided tour of the Dobot Magician (Lite) arm API surface.

This script exercises the breadth of :class:`dobotkit.Magician` -- from the
ergonomic high-level helpers down to the complete 1:1 :class:`LowLevelArm`
escape hatch -- so you can see, in one place, how the library is layered:

    Magician  (intent-revealing helpers + .io / .sensors / .effector groups)
        |
        +-- LowLevelArm  (every SDK function, 1:1, via Magician.lowlevel)
                |
                +-- SerialTransport  (pure-Python serial framing)

It is organised as small, self-contained sections; comment out any you don't
want to run on real hardware. Coordinates are illustrative -- tune them to your
own workspace first.

Run it::

    python examples/arm_full_api_tour.py            # auto-detect the serial port
    python examples/arm_full_api_tour.py COM3        # or name the port explicitly
"""
from __future__ import annotations

import sys

import dobotkit
from dobotkit import GPIOType, PTPMode
from dobotkit.arm.alarms import decode_alarms


def show_device_info(arm: "dobotkit.Magician") -> None:
    """Read identity / version info through the low-level API."""
    ll = arm.lowlevel
    print("device name:   ", ll.get_device_name())
    print("serial number: ", ll.get_device_sn())
    version = ll.get_device_version()
    print(
        "firmware:      "
        f"{version.fw_major}.{version.fw_minor}.{version.fw_revision}"
    )


def basic_motion(arm: "dobotkit.Magician") -> None:
    """Home, set speed, and do a few absolute / relative moves."""
    arm.home(wait=True)
    arm.set_speed(velocity=100, acceleration=100)

    # Absolute straight-line (MOVL) move, waited on until it completes.
    arm.move_to(220, 0, 40, 0, mode=PTPMode.MOVL_XYZ, wait=True)

    # Relative offset move (adds to the current pose).
    arm.move_relative(dx=-20, dz=10, wait=True)

    # ``check_alarms=True`` reads the alarm bitmap first and raises
    # DobotAlarmError instead of driving into a faulted state.
    arm.move_to(200, 30, 40, 0, wait=True, check_alarms=True)

    pose = arm.get_pose()
    print(f"pose after motion: x={pose.x:.1f} y={pose.y:.1f} z={pose.z:.1f} r={pose.r:.1f}")


def effector_demo(arm: "dobotkit.Magician") -> None:
    """Exercise the end-effector group (suction cup + gripper)."""
    arm.effector.suck(True)   # vacuum on (queued so it sequences with motion)
    arm.effector.suck(False)  # release
    arm.effector.grip(True)   # close gripper
    arm.effector.grip(False)  # open gripper

    # pydobot-compatible aliases on the Magician itself behave identically.
    arm.suck(True)
    arm.suck(False)


def io_demo(arm: "dobotkit.Magician") -> None:
    """Exercise the IO group: multiplexing, digital out, digital in, ADC."""
    io = arm.io
    # Configure pin 1 as a digital output, drive it high, read it back.
    io.set_multiplexing(address=1, multiplex=int(GPIOType.DO))
    io.set_do(address=1, level=1)
    print("DO[1] level:", io.get_do(1))

    # Read a digital input and an ADC channel.
    print("DI[2] level:", io.get_di(2))
    print("ADC[3] value:", io.get_adc(3))

    # PWM output: 1 kHz at 50% duty on pin 4.
    io.set_pwm(address=4, frequency=1000.0, duty_cycle=50.0)


def continuous_path_demo(arm: "dobotkit.Magician") -> None:
    """Drop to the low-level API for CP (continuous-path) and ARC moves.

    The high-level Magician focuses on PTP moves; CP/ARC live on
    :class:`LowLevelArm`, reachable through ``arm.lowlevel``.
    """
    ll = arm.lowlevel
    # Continuous-path: set params, then stream a relative segment.
    ll.set_cp_params(plan_acc=100.0, junction_vel=50.0, acc=100.0, real_time_track=0)
    ll.set_cp_cmd(cp_mode=1, x=20.0, y=0.0, z=0.0, velocity=50.0, queued=True)

    # Arc through a middle ("circle") point to an end point. Each point is
    # (x, y, z, rHead).
    ll.set_arc_cmd(
        cir_point=(240.0, 20.0, 40.0, 0.0),
        to_point=(220.0, 40.0, 40.0, 0.0),
        queued=True,
    )
    ll.queue.start()
    ll.queue.wait_for(ll.get_queued_cmd_current_index())


def alarm_check(arm: "dobotkit.Magician") -> None:
    """Read and clear any active alarms."""
    codes = decode_alarms(arm.lowlevel.get_alarms_state())
    if codes:
        print("active alarms:", [c.name for c in codes])
        arm.lowlevel.clear_all_alarms_state()
        print("alarms cleared")
    else:
        print("no active alarms")


def main(port: str = "auto") -> None:
    with dobotkit.Magician(port=port) as arm:
        show_device_info(arm)
        basic_motion(arm)
        effector_demo(arm)
        io_demo(arm)
        continuous_path_demo(arm)
        alarm_check(arm)
        print("tour complete")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "auto")
