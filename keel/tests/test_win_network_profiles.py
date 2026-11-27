from __future__ import annotations

import concurrent.futures
import ctypes
import threading
import time

import pytest

from keel import win_network


class _FakeUserenv:
    def __init__(self, create_results):
        self.create_results = iter(create_results)
        self.create_calls = 0
        self.derive_calls = 0
        self.active_creates = 0
        self.max_active_creates = 0
        self.guard = threading.Lock()

    def CreateAppContainerProfile(
        self, _name, _display_name, _description, _capabilities, _count, output
    ):
        with self.guard:
            self.create_calls += 1
            self.active_creates += 1
            self.max_active_creates = max(
                self.max_active_creates, self.active_creates
            )
        try:
            time.sleep(0.01)
            result = next(self.create_results)
            if result == 0:
                ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = (
                    ctypes.c_void_p(0x1234)
                )
            return result
        finally:
            with self.guard:
                self.active_creates -= 1

    def DeriveAppContainerSidFromAppContainerName(self, _name, output):
        self.derive_calls += 1
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = (
            ctypes.c_void_p(0x1234)
        )
        return 0


@pytest.fixture
def fake_userenv(monkeypatch):
    monkeypatch.setattr(win_network, "_APPCONTAINER_PROFILE_LOCK",
                        threading.Lock())
    userenv = _FakeUserenv([0, *([win_network.HRESULT_ALREADY_EXISTS] * 7)])
    monkeypatch.setattr(
        win_network, "_apis", lambda: (userenv, object(), object())
    )
    return userenv


def test_concurrent_profile_requests_reuse_one_stable_sid(fake_userenv):
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        sids = list(pool.map(lambda _index: win_network.appcontainer_sid(),
                             range(8)))

    assert all(sid.value == 0x1234 for sid in sids)
    assert fake_userenv.create_calls == 8
    assert fake_userenv.derive_calls == 7
    assert fake_userenv.max_active_creates == 1


def test_unexpected_hresult_can_recover_existing_profile_sid(monkeypatch):
    userenv = _FakeUserenv([win_network.HRESULT_UNEXPECTED])
    monkeypatch.setattr(win_network, "_APPCONTAINER_PROFILE_LOCK",
                        threading.Lock())
    monkeypatch.setattr(
        win_network, "_apis", lambda: (userenv, object(), object())
    )

    sid = win_network.appcontainer_sid()

    assert sid.value == 0x1234
    assert userenv.derive_calls == 1


def test_unexpected_hresult_fails_closed_when_profile_cannot_be_derived(
    monkeypatch,
):
    userenv = _FakeUserenv([win_network.HRESULT_UNEXPECTED])

    def missing_profile(_name, output):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = (
            ctypes.c_void_p()
        )
        return win_network.HRESULT_ALREADY_EXISTS

    userenv.DeriveAppContainerSidFromAppContainerName = missing_profile
    monkeypatch.setattr(win_network, "_APPCONTAINER_PROFILE_LOCK",
                        threading.Lock())
    monkeypatch.setattr(
        win_network, "_apis", lambda: (userenv, object(), object())
    )

    with pytest.raises(win_network.NetworkIsolationUnavailable,
                       match="CreateAppContainerProfile returned"):
        win_network.appcontainer_sid()
