"""Unit tests for Win32 AMD64 Workspace ABI structures and validation gate."""

import ctypes
from orbit.adapters.workspace.abi import (
    ABE_BOTTOM,
    ABE_LEFT,
    ABE_RIGHT,
    ABE_TOP,
    ABM_NEW,
    ABM_QUERYPOS,
    ABM_REMOVE,
    ABM_SETPOS,
    APPBARDATA,
    MONITORINFOEXW,
    RECT,
    SPI_GETWORKAREA,
    SPI_SETWORKAREA,
    WS_EX_TOPMOST,
    WS_POPUP,
    validate_workspace_abi,
)


def test_rect_size_and_fields():
    # Win32 RECT must be 16 bytes (4 x 32-bit LONG)
    assert ctypes.sizeof(RECT) == 16
    rc = RECT(left=100, top=200, right=500, bottom=600)
    assert rc.left == 100
    assert rc.top == 200
    assert rc.right == 500
    assert rc.bottom == 600
    assert rc.width == 400
    assert rc.height == 400
    assert rc.to_tuple() == (100, 200, 500, 600)


def test_rect_to_dict_and_bounding_box():
    rc = RECT(left=0, top=0, right=1920, bottom=1080)
    d = rc.to_dict()
    assert d == {"left": 0, "top": 0, "right": 1920, "bottom": 1080, "width": 1920, "height": 1080}

    bbox = rc.to_bounding_box()
    assert bbox.left == 0
    assert bbox.top == 0
    assert bbox.width == 1920
    assert bbox.height == 1080


def test_appbardata_size_and_field_offsets():
    # APPBARDATA on 64-bit AMD64:
    # cbSize (4) + padding (4) + hWnd (8) + uCallbackMessage (4) + uEdge (4) + rc (16) + lParam (8) = 48 bytes
    assert ctypes.sizeof(APPBARDATA) == 48
    assert APPBARDATA.cbSize.offset == 0
    assert APPBARDATA.hWnd.offset == 8
    assert APPBARDATA.uCallbackMessage.offset == 16
    assert APPBARDATA.uEdge.offset == 20
    assert APPBARDATA.rc.offset == 24
    assert APPBARDATA.lParam.offset == 40


def test_monitorinfoexw_size_and_field_offsets():
    # MONITORINFOEXW on 64-bit AMD64:
    # cbSize (4) + rcMonitor (16) + rcWork (16) + dwFlags (4) + szDevice (64 = 32 x 2) = 104 bytes
    assert ctypes.sizeof(MONITORINFOEXW) == 104
    assert MONITORINFOEXW.cbSize.offset == 0
    assert MONITORINFOEXW.rcMonitor.offset == 4
    assert MONITORINFOEXW.rcWork.offset == 20
    assert MONITORINFOEXW.dwFlags.offset == 36
    assert MONITORINFOEXW.szDevice.offset == 40


def test_validate_workspace_abi_gate():
    report = validate_workspace_abi()
    assert isinstance(report, dict)
    assert report["is_valid"] is True
    assert report["rect_size_bytes"] == 16
    assert report["appbardata_size_bytes"] == 48
    assert report["monitorinfoexw_size_bytes"] == 104
    assert report["pointer_size_bytes"] == 8


def test_constants_alignment():
    assert ABM_NEW == 0
    assert ABM_REMOVE == 1
    assert ABM_QUERYPOS == 2
    assert ABM_SETPOS == 3

    assert ABE_LEFT == 0
    assert ABE_TOP == 1
    assert ABE_RIGHT == 2
    assert ABE_BOTTOM == 3

    assert SPI_GETWORKAREA == 0x0030
    assert SPI_SETWORKAREA == 0x002F
    assert WS_POPUP == 0x80000000
    assert WS_EX_TOPMOST == 0x00000008
