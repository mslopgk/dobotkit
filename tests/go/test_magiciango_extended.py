"""Offline wire-format tests for the 49 extended ``MagicianGO`` methods.

Data provenance: the 2026-07-04 RPC coverage audit plus the wire-signature
mining pass that cross-checked three sources — (1) the DobotEDU python
wrapper embedded in the DobotLab asar, (2) the official DobotLinkHelp_EN.CHM
parameter tables, and (3) the DobotLink C++ plugin protocol string table /
renderer JS call sites. Every assertion below pins the mined wire method
name and parameter shape; nothing here touches hardware.

Key mined findings encoded as tests:

- ``SetMovePos`` is a *queued action* command (DobotLink defaults
  isQueued/isWaitForFinish to true) -> exposed as ``unsafe_move_pos`` and
  must carry the three ``_WAIT`` keys, exactly like ``unsafe_rotate``.
- ``SetMoveSpeedTime`` and ``SetOriginPoint`` are NOT queued action
  commands -> plain ``move_speed_time`` / ``set_origin_point`` with no
  queue flags on the wire.
- ``GetTraceAngle`` and ``SetRunningState`` are unconfirmed on the wire ->
  ``firmware_trace_angle`` / ``set_running_state`` are ``**params``
  pass-throughs, asserted as such.
- StopPoint RPCs live in the ``MagicBox`` namespace; GetMagicBoxMode/Num
  and SetRunningState, despite their names, are ``MagicianGO``.
- ``GetQueuedCmdCurrentIndex`` is the real wire name (the CHM's
  GetCmdQueueCurrentIndex is a stale alias).

Uses the same ``FakeClient`` double as ``test_magiciango.py`` — every test
asserts the exact ``(method, params)`` tuple recorded for the call.
"""
from __future__ import annotations

from typing import Any

from dobotkit.go.magiciango import MagicianGO

from .conftest import FakeClient


def make_go(result: Any = None, results: Any = None,
            port_name: str = "COM5") -> tuple[MagicianGO, FakeClient]:
    fc = FakeClient(result=result, results=results)
    return MagicianGO(fc, port_name=port_name), fc


# Queue flags carried by queued action commands (same trio as unsafe_rotate).
_WAIT_KEYS = {"isQueued": True, "isWaitForFinish": True, "timeout": 604800000}


# ---- diagnostics / state getters (MagicianGO, portName only) ----------------

def test_get_alarm_info():
    go, fc = make_go(results={"MagicianGO.GetAlarmInfo": {"warning": []}})
    assert go.get_alarm_info() == {"warning": []}
    assert fc.calls[0] == ("MagicianGO.GetAlarmInfo", {"portName": "COM5"})


def test_clean_alarm_info():
    go, fc = make_go()
    go.clean_alarm_info()
    assert fc.calls[0] == ("MagicianGO.CleanAlarmInfo", {"portName": "COM5"})


def test_running_state():
    go, fc = make_go(results={"MagicianGO.GetRunningState": {"runningState": 1}})
    assert go.running_state() == {"runningState": 1}
    assert fc.calls[0] == ("MagicianGO.GetRunningState", {"portName": "COM5"})


def test_stall_protection():
    go, fc = make_go(results={"MagicianGO.GetStallProtection": {"isHappened": 0}})
    assert go.stall_protection() == {"isHappened": 0}
    assert fc.calls[0] == ("MagicianGO.GetStallProtection", {"portName": "COM5"})


def test_off_ground():
    go, fc = make_go(results={"MagicianGO.GetOffGround": {"isHappened": 1}})
    assert go.off_ground() == {"isHappened": 1}
    assert fc.calls[0] == ("MagicianGO.GetOffGround", {"portName": "COM5"})


def test_get_move_speed():
    go, fc = make_go(results={"MagicianGO.GetMoveSpeed": {"x": 10.0, "y": 0.0, "r": 5.0}})
    assert go.get_move_speed() == {"x": 10.0, "y": 0.0, "r": 5.0}
    assert fc.calls[0] == ("MagicianGO.GetMoveSpeed", {"portName": "COM5"})


def test_get_running_mode():
    go, fc = make_go(results={"MagicianGO.GetRunningMode": {"runningMode": 0}})
    assert go.get_running_mode() == {"runningMode": 0}
    assert fc.calls[0] == ("MagicianGO.GetRunningMode", {"portName": "COM5"})


# ---- trace -------------------------------------------------------------------
# GetTraceAngle is UNCONFIRMED on the wire (absent from the plugin method
# table and the JS SDK; the CHM page content is actually GetImuAngle), so
# firmware_trace_angle is a **params pass-through. Note it is a *different*
# method from the existing trace_angle (= GetCarCameraAngle, which is what
# DobotEDU's get_trace_angle really calls).

def test_firmware_trace_angle_no_args_sends_only_portname():
    go, fc = make_go()
    go.firmware_trace_angle()
    assert fc.calls[0] == ("MagicianGO.GetTraceAngle", {"portName": "COM5"})


def test_firmware_trace_angle_passes_kwargs_through():
    # Unconfirmed wire params -> whatever the caller supplies must land on the
    # wire verbatim (pass-through contract).
    go, fc = make_go()
    go.firmware_trace_angle(index=1, anything="x")
    method, params = fc.calls[0]
    assert method == "MagicianGO.GetTraceAngle"
    assert params["index"] == 1
    assert params["anything"] == "x"
    assert params["portName"] == "COM5"


def test_firmware_trace_angle_is_distinct_from_trace_angle():
    # trace_angle == GetCarCameraAngle (camera line angle, proven on hardware);
    # firmware_trace_angle == GetTraceAngle (unconfirmed firmware method).
    # They must hit different wire methods.
    go, fc = make_go(results={"MagicianGO.GetCarCameraAngle": {"angle": 5, "count": 1}})
    go.trace_angle()
    go.firmware_trace_angle()
    assert fc.calls[0][0] == "MagicianGO.GetCarCameraAngle"
    assert fc.calls[1][0] == "MagicianGO.GetTraceAngle"


def test_set_trace_line_info():
    go, fc = make_go()
    go.set_trace_line_info(lineInfo=1)
    assert fc.calls[0] == ("MagicianGO.SetTraceLineInfo",
                           {"lineInfo": 1, "portName": "COM5"})


# ---- absolute drive ----------------------------------------------------------
# SetMovePos is a mined *queued action* command (DobotLink defaults the queue
# flags to true; DobotEDU sends them explicitly) -> unsafe_ prefix + _WAIT trio.
# SetMoveSpeedTime / SetOriginPoint are NOT in the queued-action list and are
# sent without queue flags -> plain names, no _WAIT keys.

def test_unsafe_move_pos_includes_queue_flags():
    go, fc = make_go()
    go.unsafe_move_pos(x=50, y=20, s=30)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetMovePos"
    assert (params["x"], params["y"], params["s"]) == (50, 20, 30)
    for k, v in _WAIT_KEYS.items():
        assert params[k] == v
    assert params["portName"] == "COM5"


def test_move_speed_time_has_no_queue_flags():
    go, fc = make_go()
    go.move_speed_time(time=1, x=10, y=0, r=0)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetMoveSpeedTime"
    assert (params["time"], params["x"], params["y"], params["r"]) == (1, 10, 0, 0)
    assert params["portName"] == "COM5"
    # Not a queued action command: none of the _WAIT trio may appear.
    for k in _WAIT_KEYS:
        assert k not in params


def test_move_speed_time_clamps_duration_and_speeds():
    # The drive runs firmware-side and outlives a crashed script, so `time`
    # is clamped to 0..5 s (mirroring drive_for) and x/y/r to +/-SPEED_CAP.
    go, fc = make_go()
    go.move_speed_time(time=600, x=100, y=-100, r=45)
    _, params = fc.calls[0]
    assert params["time"] == 5.0
    assert (params["x"], params["y"], params["r"]) == (30.0, -30.0, 30.0)

    go2, fc2 = make_go()
    go2.move_speed_time(time=-1, x=10)
    assert fc2.calls[0][1]["time"] == 0.0


def test_set_origin_point_has_no_queue_flags():
    go, fc = make_go()
    go.set_origin_point(enable=1)
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetOriginPoint"
    assert params["enable"] == 1
    assert params["portName"] == "COM5"
    for k in _WAIT_KEYS:
        assert k not in params


# ---- car camera --------------------------------------------------------------

def test_car_camera_color():
    canned = {"count": 1, "color_obj": [{"x": 1, "y": 2, "w": 3, "h": 4, "id": 0}]}
    go, fc = make_go(results={"MagicianGO.GetCarCameraColor": canned})
    assert go.car_camera_color() == canned
    assert fc.calls[0] == ("MagicianGO.GetCarCameraColor", {"portName": "COM5"})


def test_car_camera_tag():
    canned = {"count": 1,
              "aptag_obj": [{"x": 1, "y": 2, "w": 3, "h": 4, "id": 7, "rot": 0.5}]}
    go, fc = make_go(results={"MagicianGO.GetCarCameraTag": canned})
    assert go.car_camera_tag() == canned
    assert fc.calls[0] == ("MagicianGO.GetCarCameraTag", {"portName": "COM5"})


def test_get_car_camera_model():
    go, fc = make_go(results={"MagicianGO.GetCarCameraRunModel": {"runModelIndex": 2}})
    assert go.get_car_camera_model() == {"runModelIndex": 2}
    assert fc.calls[0] == ("MagicianGO.GetCarCameraRunModel", {"portName": "COM5"})


def test_set_car_camera_model():
    go, fc = make_go()
    go.set_car_camera_model(runModelIndex=3)
    assert fc.calls[0] == ("MagicianGO.SetCarCameraRunModel",
                           {"runModelIndex": 3, "portName": "COM5"})


def test_get_car_camera_calibration_mode():
    go, fc = make_go(results={"MagicianGO.GetCarCameraCalibrationMode":
                              {"isEnableCali": 0}})
    assert go.get_car_camera_calibration_mode() == {"isEnableCali": 0}
    # NOTE: the CHM example misprints the method as GetCameraCalibrationMode;
    # the plugin string table has the full 'Car' name — that is the wire truth.
    assert fc.calls[0] == ("MagicianGO.GetCarCameraCalibrationMode",
                           {"portName": "COM5"})


def test_set_car_camera_calibration_mode():
    go, fc = make_go()
    go.set_car_camera_calibration_mode(isEnableCali=1)
    assert fc.calls[0] == ("MagicianGO.SetCarCameraCalibrationMode",
                           {"isEnableCali": 1, "portName": "COM5"})


def test_camera_calibration_data_requires_point_lists():
    # A "Get" that takes inputs: DobotLink feeds both 9-point JSON strings to
    # its fit_homography helper.
    april = "[[0,0],[1,0],[2,0],[0,1],[1,1],[2,1],[0,2],[1,2],[2,2]]"
    device = "[[10,10],[20,10],[30,10],[10,20],[20,20],[30,20],[10,30],[20,30],[30,30]]"
    go, fc = make_go(results={"MagicianGO.GetCameraCalibrationData":
                              {"data": "max_x_err:0.44,max_y_err:0.6"}})
    res = go.camera_calibration_data(april_list=april, device_list=device)
    assert res == {"data": "max_x_err:0.44,max_y_err:0.6"}
    assert fc.calls[0] == ("MagicianGO.GetCameraCalibrationData",
                           {"april_list": april, "device_list": device,
                            "portName": "COM5"})


# ---- arm camera ----------------------------------------------------------------

def test_arm_camera_color():
    canned = {"count": 0}
    go, fc = make_go(results={"MagicianGO.GetArmCameraColor": canned})
    assert go.arm_camera_color() == canned
    assert fc.calls[0] == ("MagicianGO.GetArmCameraColor", {"portName": "COM5"})


def test_arm_camera_angle():
    go, fc = make_go(results={"MagicianGO.GetArmCameraAngle": {"angle": 45}})
    assert go.arm_camera_angle() == {"angle": 45}
    assert fc.calls[0] == ("MagicianGO.GetArmCameraAngle", {"portName": "COM5"})


def test_get_arm_camera_model():
    go, fc = make_go(results={"MagicianGO.GetArmCameraRunModel": {"runModelIndex": 1}})
    assert go.get_arm_camera_model() == {"runModelIndex": 1}
    assert fc.calls[0] == ("MagicianGO.GetArmCameraRunModel", {"portName": "COM5"})


def test_set_arm_camera_model():
    go, fc = make_go()
    go.set_arm_camera_model(runModelIndex=0)
    assert fc.calls[0] == ("MagicianGO.SetArmCameraRunModel",
                           {"runModelIndex": 0, "portName": "COM5"})


def test_get_arm_camera_calibration_mode():
    go, fc = make_go(results={"MagicianGO.GetArmCameraCalibrationMode":
                              {"isEnableCali": 1}})
    assert go.get_arm_camera_calibration_mode() == {"isEnableCali": 1}
    assert fc.calls[0] == ("MagicianGO.GetArmCameraCalibrationMode",
                           {"portName": "COM5"})


def test_set_arm_camera_calibration_mode():
    go, fc = make_go()
    go.set_arm_camera_calibration_mode(isEnableCali=0)
    assert fc.calls[0] == ("MagicianGO.SetArmCameraCalibrationMode",
                           {"isEnableCali": 0, "portName": "COM5"})


# ---- command queue control -----------------------------------------------------

def test_clean_cmd_queue():
    go, fc = make_go()
    go.clean_cmd_queue()
    assert fc.calls[0] == ("MagicianGO.CleanCmdQueue", {"portName": "COM5"})


def test_cmd_queue_start():
    go, fc = make_go()
    go.cmd_queue_start()
    assert fc.calls[0] == ("MagicianGO.SetCmdQueueStart", {"portName": "COM5"})


def test_cmd_queue_stop():
    go, fc = make_go()
    go.cmd_queue_stop()
    assert fc.calls[0] == ("MagicianGO.SetCmdQueueStop", {"portName": "COM5"})


def test_cmd_queue_force_stop():
    # Wire name really is "Forcely" (sic) — do not "fix" the spelling.
    go, fc = make_go()
    go.cmd_queue_force_stop()
    assert fc.calls[0] == ("MagicianGO.SetCmdQueueForcelyStop", {"portName": "COM5"})


def test_queued_cmd_current_index_uses_js_sdk_wire_name():
    # Wire name per JS SDK + plugin table: GetQueuedCmdCurrentIndex.
    # (The CHM documents a stale alias, GetCmdQueueCurrentIndex.)
    # Result field is spelled queueCmdCurrentIndex ('queue', not 'Queued').
    go, fc = make_go(results={"MagicianGO.GetQueuedCmdCurrentIndex":
                              {"queueCmdCurrentIndex": 7}})
    assert go.queued_cmd_current_index() == {"queueCmdCurrentIndex": 7}
    assert fc.calls[0] == ("MagicianGO.GetQueuedCmdCurrentIndex",
                           {"portName": "COM5"})


def test_cmd_queue_available_space():
    go, fc = make_go(results={"MagicianGO.GetCmdQueueAvailableSpace": {"space": 32}})
    assert go.cmd_queue_available_space() == {"space": 32}
    assert fc.calls[0] == ("MagicianGO.GetCmdQueueAvailableSpace",
                           {"portName": "COM5"})


# ---- MagicBox / stop point -----------------------------------------------------
# Namespace split (mined): only the StopPoint trio (+GetImgToArmXY) live in
# "MagicBox.*"; GetMagicBoxMode / GetMagicBoxNum / SetRunningState are
# "MagicianGO.*" despite their names.

def test_magic_box_mode_is_magiciango_namespace():
    go, fc = make_go(results={"MagicianGO.GetMagicBoxMode": {"mode": 1}})
    assert go.magic_box_mode() == {"mode": 1}
    assert fc.calls[0] == ("MagicianGO.GetMagicBoxMode", {"portName": "COM5"})


def test_magic_box_num_is_magiciango_namespace():
    go, fc = make_go(results={"MagicianGO.GetMagicBoxNum": {"num": 4}})
    assert go.magic_box_num() == {"num": 4}
    assert fc.calls[0] == ("MagicianGO.GetMagicBoxNum", {"portName": "COM5"})


def test_stop_point_state_is_magicbox_namespace():
    go, fc = make_go(results={"MagicBox.GetStopPointState": {"result": True}})
    assert go.stop_point_state() == {"result": True}
    assert fc.calls[0] == ("MagicBox.GetStopPointState", {"portName": "COM5"})


def test_set_stop_point_param_is_magicbox_namespace():
    go, fc = make_go()
    go.set_stop_point_param(scopeErr=40, stopErr=2)
    assert fc.calls[0] == ("MagicBox.SetStopPointParam",
                           {"scopeErr": 40, "stopErr": 2, "portName": "COM5"})


def test_set_stop_point_server_capital_p_params():
    # Wire params are PointX / PointY — capital P, mined from DobotEDU py and
    # stop_point_test.py. Lowercase would be silently ignored by the firmware.
    go, fc = make_go()
    go.set_stop_point_server(PointX=100, PointY=50)
    assert fc.calls[0] == ("MagicBox.SetStopPointServer",
                           {"PointX": 100, "PointY": 50, "portName": "COM5"})


def test_set_running_state_passes_kwargs_through():
    # SetRunningState is effectively unconfirmed (plugin string-table adjacency
    # only) -> **params pass-through contract, MagicianGO namespace.
    go, fc = make_go()
    go.set_running_state(runningState=1)
    assert fc.calls[0] == ("MagicianGO.SetRunningState",
                           {"runningState": 1, "portName": "COM5"})


def test_set_running_state_passthrough_is_verbatim():
    go, fc = make_go()
    go.set_running_state(whatever=3, extra="y")
    method, params = fc.calls[0]
    assert method == "MagicianGO.SetRunningState"
    assert params["whatever"] == 3
    assert params["extra"] == "y"
    assert params["portName"] == "COM5"


# ---- output --------------------------------------------------------------------

def test_set_light_prompt():
    go, fc = make_go()
    go.set_light_prompt(index=2)
    assert fc.calls[0] == ("MagicianGO.SetLightPrompt",
                           {"index": 2, "portName": "COM5"})


# ---- device info / identity ------------------------------------------------------

def test_product_name():
    go, fc = make_go(results={"MagicianGO.GetProductName":
                              {"productName": "MagicianGo"}})
    assert go.product_name() == {"productName": "MagicianGo"}
    assert fc.calls[0] == ("MagicianGO.GetProductName", {"portName": "COM5"})


def test_device_fw_software_version():
    canned = {"majorVersionNum": 1, "secondVersionNum": 2,
              "revisionVersionNum": 3, "previousVersionNum": 4}
    go, fc = make_go(results={"MagicianGO.GetDeviceFwSoftwareVersion": canned})
    assert go.device_fw_software_version() == canned
    assert fc.calls[0] == ("MagicianGO.GetDeviceFwSoftwareVersion",
                           {"portName": "COM5"})


def test_device_fw_hardware_version():
    go, fc = make_go(results={"MagicianGO.GetDeviceFwHardwareVersion":
                              {"majorVersionNum": 3}})
    assert go.device_fw_hardware_version() == {"majorVersionNum": 3}
    assert fc.calls[0] == ("MagicianGO.GetDeviceFwHardwareVersion",
                           {"portName": "COM5"})


def test_device_id():
    go, fc = make_go(results={"MagicianGO.GetDeviceID": {"deviceID": [1, 2, 3]}})
    assert go.device_id() == {"deviceID": [1, 2, 3]}
    # CHM example misprints the namespace as MagicBox; the plugin table places
    # GetDeviceID under the MagicianGO device family.
    assert fc.calls[0] == ("MagicianGO.GetDeviceID", {"portName": "COM5"})


def test_get_device_name():
    go, fc = make_go(results={"MagicianGO.GetDeviceName": {"deviceName": "MgoNO.1"}})
    assert go.get_device_name() == {"deviceName": "MgoNO.1"}
    assert fc.calls[0] == ("MagicianGO.GetDeviceName", {"portName": "COM5"})


def test_set_device_name():
    go, fc = make_go()
    go.set_device_name(deviceName="MgoNO.1")
    assert fc.calls[0] == ("MagicianGO.SetDeviceName",
                           {"deviceName": "MgoNO.1", "portName": "COM5"})


def test_get_device_sn():
    go, fc = make_go(results={"MagicianGO.GetDeviceSN":
                              {"deviceSN": "SNMGO20200821000061"}})
    assert go.get_device_sn() == {"deviceSN": "SNMGO20200821000061"}
    assert fc.calls[0] == ("MagicianGO.GetDeviceSN", {"portName": "COM5"})


def test_set_device_sn():
    go, fc = make_go()
    go.set_device_sn(deviceSN="SNMGO20200821000061")
    assert fc.calls[0] == ("MagicianGO.SetDeviceSN",
                           {"deviceSN": "SNMGO20200821000061", "portName": "COM5"})


def test_device_time():
    canned = {"gSystick": 123456, "passtime": "01:02:03.4"}
    go, fc = make_go(results={"MagicianGO.GetDeviceTime": canned})
    assert go.device_time() == canned
    assert fc.calls[0] == ("MagicianGO.GetDeviceTime", {"portName": "COM5"})


def test_device_reboot():
    go, fc = make_go(result=True)
    assert go.device_reboot() is True  # returns Any, no normalisation
    assert fc.calls[0] == ("MagicianGO.DeviceReboot", {"portName": "COM5"})


def test_heartbeat():
    go, fc = make_go(result=True)
    assert go.heartbeat() is True
    assert fc.calls[0] == ("MagicianGO.HeartBeat", {"portName": "COM5"})


# ---- cross-cutting: custom port name propagates to every new family -------------

def test_new_methods_use_configured_port_name():
    go, fc = make_go(port_name="COM7")
    go.get_alarm_info()
    go.set_light_prompt(index=1)
    go.stop_point_state()
    go.heartbeat()
    for _, params in fc.calls:
        assert params["portName"] == "COM7"
