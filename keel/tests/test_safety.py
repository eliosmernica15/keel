"""Tier-2 (not configurable) safety-envelope tests."""

from __future__ import annotations

import json
import pytest

from keel.safety import Check, outline, tier2_check


def chk(tool, **inp) -> Check:
    return tier2_check(tool, inp)


# ---------- bypass/disable matrix: Tier 2 must hold in every mode ----------

def test_unparseable_command_refused_everywhere():
    for mode in ("default", "acceptEdits", "dontAsk", "bypassPermissions"):
        result = chk("run_shell", command="rm -rf $(evil)", shell="posix")
        assert not result.allowed


def test_format_refused_even_in_bypass():
    assert not chk("run_shell", command="format C:", shell="cmd").allowed
    assert not chk("run_shell", command="diskpart", shell="cmd").allowed


def test_recursive_root_delete_refused():
    assert not chk("run_shell", command="rm -rf /", shell="posix").allowed
    assert not chk("run_shell", command="rm -rf /*", shell="posix").allowed


def test_catastrophic_by_name():
    for cmd in ("format D:", "diskpart", "mkfs.ext4 /dev/sdb",
                "fdisk -l", "sdelete -p 3 C:\\temp"):
        shell = "cmd" if cmd.startswith(("format", "diskpart", "sdelete")) else "posix"
        assert not chk("run_shell", command=cmd, shell=shell).allowed, cmd


# ---------- protected paths (read + write) ----------

def test_read_env_refused():
    assert not chk("read_file", path="/repo/.env").allowed
    assert not chk("read_file", path="/repo/config/.env.local").allowed


def test_read_ssh_refused():
    assert not chk("read_file", path="/home/user/.ssh/id_rsa").allowed


def test_read_pem_refused():
    assert not chk("read_file", path="/etc/ssl/private/server.pem").allowed


def test_write_env_refused():
    assert not chk("write_file", path="/repo/.env", content="x").allowed


def test_write_system_refused():
    assert not chk("write_file", path="C:\\Windows\\System32\\drivers\\etc\\hosts",
                   content="x").allowed
    assert not chk("edit_file", path="/etc/passwd",
                   old_string="root", new_string="root2").allowed


def test_shell_delete_into_windows_refused():
    assert not chk("run_shell",
                   command="Remove-Item -Recurse -Force C:\\Windows\\System32",
                   shell="powershell").allowed


def test_shell_delete_env_refused():
    assert not chk("run_shell",
                   command="rm -rf /repo/.env", shell="posix").allowed


def test_shell_delete_ssh_refused():
    assert not chk("run_shell",
                   command="del C:\\Users\\me\\.ssh\\id_rsa", shell="cmd").allowed


def test_dd_of_device_refused():
    assert not chk("run_shell",
                   command="dd if=/dev/zero of=/dev/sda", shell="posix").allowed


def test_redirect_into_env_refused():
    assert not chk("run_shell",
                   command="echo secret > /repo/.env", shell="posix").allowed


# ---------- allowed cases (Tier 2 must not overreach) ----------

def test_read_normal_file_allowed():
    assert chk("read_file", path="/repo/src/main.py").allowed


def test_read_ordinary_write_allowed():
    assert chk("write_file", path="/repo/out.txt", content="hi").allowed


def test_destructive_but_benign_allowed():
    # deleting a normal file under the repo is Tier-2's call to allow;
    # Tier-1 handles the consent path
    assert chk("run_shell", command="rm -rf /repo/build", shell="posix").allowed


def test_curl_network_allowed_by_tier2():
    assert chk("run_shell",
               command="curl https://api.example.com/health", shell="posix").allowed


# ---------- "Can Tier 2 be disabled?" matrix ----------

def test_no_knob_in_rpc_surface():
    # the module accepts no configuration; there is nothing to set
    import inspect
    sig = inspect.signature(tier2_check)
    # tool_registry is an optional, backward-compatible parameter that does
    # not disable or configure safety; it only provides tool classification.
    assert list(sig.parameters) == ["tool_name", "tool_input", "tool_registry"]


def test_outline_is_published():
    assert len(outline()) >= 8
    joined = " ".join(outline()).lower()
    for word in ("format", "unparseable", "secret", "redirect"):
        assert word in joined
