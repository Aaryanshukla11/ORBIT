"""Unit tests for KeyboardStateManager and key ownership tracking in ORBIT M1.3."""

import pytest
from orbit.adapters.keyboard.state import (
    KeyboardStateManager,
    KeyOwner,
    PressedKey,
)


def test_keyboard_state_manager_initial_state():
    mgr = KeyboardStateManager()
    assert mgr.is_locked is False
    assert mgr.lockout_state == "NORMAL"
    assert mgr.lockout_reason is None
    assert mgr.get_orbit_pressed_keys() == []


def test_keyboard_state_single_key_lifecycle():
    mgr = KeyboardStateManager()
    key = mgr.register_key_down(vk_code=0x41, scan_code=0, is_extended=False, is_unicode=False, owner=KeyOwner.ORBIT_SYNTHETIC)
    assert key.vk_code == 0x41
    assert mgr.is_key_down(0x41) is True
    assert len(mgr.get_orbit_pressed_keys()) == 1

    popped = mgr.register_key_up(vk_code=0x41, scan_code=0, is_extended=False, is_unicode=False, owner=KeyOwner.ORBIT_SYNTHETIC)
    assert popped is not None
    assert popped.vk_code == 0x41
    assert mgr.is_key_down(0x41) is False
    assert len(mgr.get_orbit_pressed_keys()) == 0


def test_keyboard_ownership_isolation():
    mgr = KeyboardStateManager()
    # User physically holds Shift
    mgr.register_key_down(vk_code=0x10, scan_code=0, is_extended=False, is_unicode=False, owner=KeyOwner.USER_PHYSICAL)
    # ORBIT injects 'A'
    mgr.register_key_down(vk_code=0x41, scan_code=0, is_extended=False, is_unicode=False, owner=KeyOwner.ORBIT_SYNTHETIC)

    orbit_keys = mgr.get_orbit_pressed_keys()
    assert len(orbit_keys) == 1
    assert orbit_keys[0].vk_code == 0x41

    released = []
    sanitized = mgr.sanitize_orbit_keys(release_callback=lambda k: released.append(k.vk_code) or True)

    # Only ORBIT-owned key was released!
    assert len(sanitized) == 1
    assert sanitized[0].vk_code == 0x41
    assert released == [0x41]

    # User physical key remains tracked and untouched
    assert mgr.is_key_down(0x10) is True


def test_keyboard_failed_release_locks_state():
    mgr = KeyboardStateManager()
    mgr.register_key_down(vk_code=0x11, scan_code=0, is_extended=False, is_unicode=False, owner=KeyOwner.ORBIT_SYNTHETIC)

    # Release callback returns False (dispatch failure)
    mgr.sanitize_orbit_keys(release_callback=lambda k: False)

    assert mgr.is_locked is True
    assert mgr.lockout_state == "UNRESOLVED_LOCKED"
    assert mgr.lockout_reason is not None

    # Subsequent key down must be rejected
    with pytest.raises(RuntimeError, match="UNRESOLVED_LOCKED"):
        mgr.register_key_down(vk_code=0x42)


def test_keyboard_recovery_token_workflow():
    mgr = KeyboardStateManager()
    token = mgr.lock_state("Simulated hardware bus desynchronization")
    assert mgr.is_locked is True

    # Bad token fails
    assert mgr.recover_locked_state("BAD_TOKEN") is False
    assert mgr.is_locked is True

    # Valid token restores state
    assert mgr.recover_locked_state(token) is True
    assert mgr.is_locked is False
    assert mgr.lockout_state == "NORMAL"
