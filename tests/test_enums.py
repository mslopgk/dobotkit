from dobotkit.enums import PTPMode, GPIOType, ContinuousPathMode

def test_ptpmode_values():
    assert PTPMode.JUMP_XYZ == 0
    assert PTPMode.MOVJ_XYZ == 1
    assert PTPMode.MOVL_XYZ == 2
    assert PTPMode.MOVJ_ANGLE == 4
    assert PTPMode.MOVL_XYZ_INC == 7
    assert PTPMode.JUMP_MOVL_XYZ == 9

def test_gpiotype_values():
    assert GPIOType.DUMMY == 0
    assert GPIOType.DO == 1
    assert GPIOType.PWM == 2
    assert GPIOType.DI == 3
    assert GPIOType.ADC == 4
    assert GPIOType.DIPU == 5
    assert GPIOType.DIPD == 6

def test_cp_mode():
    assert ContinuousPathMode.RELATIVE == 0
    assert ContinuousPathMode.ABSOLUTE == 1
