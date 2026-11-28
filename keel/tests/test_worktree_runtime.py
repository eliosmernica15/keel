"""Adversarial acceptance tests for the real worktree/staging runtimes.

Every git repository and project tree below lives under pytest's ``tmp_path``.
No test shells out through a shell, touches the main Keel checkout, or deletes
anything outside its own temporary directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# This repo is commonly installed editable against a different worktree. Make
# these tests exercise the runtime in THIS worktree even when that install is
# active. (The exact pytest command is unchanged; no files outside tmp_path
# are touched.)
_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
for _name in tuple(sys.modules):
    if _name == "keel" or _name.startswith("keel."):
        del sys.modules[_name]

from keel import worktree_runtime as wt  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        check=True,
        shell=False,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "tester@example.test")
    _git(root, "config", "user.name", "Tester")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "a.txt").write_text("original-a\n", encoding="utf-8")
    (root / "b.txt").write_text("original-b\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "initial")
    return root


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.txt").write_text("original-a\n", encoding="utf-8")
    (root / "b.txt").write_text("original-b\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "c.txt").write_text("original-c\n", encoding="utf-8")
    (root / "unclaimed.txt").write_text("do not touch\n", encoding="utf-8")
    return root


def _link_or_skip(target: Path, link: Path) -> None:
    """Create a symlink, falling back to a Windows junction (no privilege).

    Junctions are not reported by ``Path.is_symlink()`` but are resolved by
    ``os.path.realpath``, so they still exercise the containment check.
    """
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
        return
    except (OSError, NotImplementedError) as exc:
        if os.name != "nt":
            pytest.skip(f"symlinks are unavailable here: {exc}")
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        pytest.skip(f"neither symlink nor junction is available: {proc.stderr.strip()}")


# ---------------------------------------------------------------------------
# Git worktree runtime
# ---------------------------------------------------------------------------


def test_git_worktree_roundtrip_and_file_isolation(repo: Path) -> None:
    info = wt.create_worktree(repo, "session/One")
    assert info.branch == wt.branch_name("session/One")
    assert info.branch.startswith("keel/session-one-")
    assert Path(info.path).is_dir()
    assert (Path(info.path) / "a.txt").read_text(encoding="utf-8") == "original-a\n"
    assert wt.is_dirty(repo) is False  # managed area lives under .git, not the checkout

    (Path(info.path) / "a.txt").write_text("worktree edit\n", encoding="utf-8")
    assert (repo / "a.txt").read_text(encoding="utf-8") == "original-a\n"
    branches = [entry.branch for entry in wt.list_worktrees(repo)]
    assert info.branch in branches

    with pytest.raises(wt.WorktreeError) as refused:
        wt.remove_worktree(repo, "session/One")  # remove by session id
    assert refused.value.code == "dirty_worktree"
    wt.remove_worktree(repo, "session/One", force=True)
    assert not Path(info.path).exists()
    assert (repo / "a.txt").read_text(encoding="utf-8") == "original-a\n"


def test_git_dirty_checkout_is_detected_before_create(repo: Path) -> None:
    (repo / "a.txt").write_text("uncommitted\n", encoding="utf-8")
    assert wt.is_dirty(repo) is True
    with pytest.raises(wt.WorktreeError) as refused:
        wt.create_worktree(repo, "dirty-session")
    assert refused.value.code == "dirty_checkout"
    info = wt.create_worktree(repo, "dirty-session", allow_dirty=True)
    # A worktree is built from the committed base ref, not from uncommitted
    # source edits; those edits stay in the original checkout.
    assert (Path(info.path) / "a.txt").read_text(encoding="utf-8") == "original-a\n"
    assert (repo / "a.txt").read_text(encoding="utf-8") == "uncommitted\n"


def test_git_branch_collision_rejected_then_suffixed(repo: Path) -> None:
    taken = wt.branch_name("duplicate")
    _git(repo, "branch", taken)
    with pytest.raises(wt.WorktreeError) as refused:
        wt.create_worktree(repo, "duplicate")
    assert refused.value.code == "branch_collision"

    info = wt.create_worktree(repo, "duplicate", collision="suffix")
    assert info.branch == f"{taken}-2"
    second = wt.create_worktree(repo, "duplicate", collision="suffix")
    assert second.branch == f"{taken}-3"


def test_git_symlink_escape_is_rejected(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret\n", encoding="utf-8")
    _link_or_skip(outside, repo / "escape")
    with pytest.raises(wt.WorktreeError) as refused:
        wt.create_worktree(repo, "escaping", worktree_dir="escape/wt",
                           allow_dirty=True)
    assert refused.value.code in {"symlink_path", "path_escape"}
    assert not (outside / "wt").exists()


def test_git_path_traversal_and_absolute_escape_rejected(repo: Path, tmp_path: Path) -> None:
    with pytest.raises(wt.WorktreeError) as refused:
        wt.create_worktree(repo, "traversal", worktree_dir="../outside-wt")
    assert refused.value.code == "path_traversal"

    outside = tmp_path / "absolute-wt"
    with pytest.raises(wt.WorktreeError) as refused:
        wt.create_worktree(repo, "absolute", worktree_dir=outside)
    assert refused.value.code == "path_escape"
    assert not outside.exists()


def test_git_ref_validation(repo: Path) -> None:
    with pytest.raises(wt.WorktreeError) as refused:
        wt.create_worktree(repo, "bad-ref", base_ref="no-such-ref")
    assert refused.value.code == "unknown_ref"
    with pytest.raises(wt.WorktreeError) as refused:
        wt.create_worktree(repo, "bad-ref", base_ref="--upload-pack=evil")
    assert refused.value.code == "invalid_ref"


def test_git_unknown_worktree_and_prune(repo: Path) -> None:
    with pytest.raises(wt.WorktreeError) as refused:
        wt.remove_worktree(repo, "never-created")
    assert refused.value.code == "unknown_worktree"
    wt.prune_worktrees(repo)  # no-op on a healthy repo


def test_git_delete_branch_opt_in(repo: Path) -> None:
    info = wt.create_worktree(repo, "branch-cleanup")
    assert wt._branch_exists(wt.repo_root(repo), info.branch)
    wt.remove_worktree(repo, info.path, delete_branch=True)
    assert not wt._branch_exists(wt.repo_root(repo), info.branch)


def test_git_never_uses_a_shell() -> None:
    source = Path(wt.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "shell=False" in source


# ---------------------------------------------------------------------------
# Non-Git exact-file staging runtime
# ---------------------------------------------------------------------------


def test_staging_copies_only_claimed_files(project: Path, tmp_path: Path) -> None:
    area = wt.stage_exact_files(
        project, ["a.txt", "sub/c.txt"], stage_root=tmp_path / "stages"
    )
    staged = sorted(p.relative_to(area.stage_dir).as_posix() for p in area.stage_dir.rglob("*")
                    if p.is_file())
    assert staged == ["a.txt", "sub/c.txt"]
    assert set(area.files) == {"a.txt", "sub/c.txt"}
    assert (project / "a.txt").read_text(encoding="utf-8") == "original-a\n"
    assert (project / "unclaimed.txt").read_text(encoding="utf-8") == "do not touch\n"
    assert area.state == "staged"
    assert area.journal_path.is_file()


def test_staging_empty_claim_rejected_for_write_but_allowed_for_read(
    project: Path, tmp_path: Path
) -> None:
    with pytest.raises(wt.WorktreeError) as refused:
        wt.stage_exact_files(project, [], stage_root=tmp_path / "stages")
    assert refused.value.code == "empty_claim"
    read_area = wt.stage_exact_files(
        project, [], stage_root=tmp_path / "stages", task="read"
    )
    assert read_area.files == {}


def test_staging_windows_style_and_traversal_claims(project: Path, tmp_path: Path) -> None:
    with pytest.raises(wt.WorktreeError) as refused:
        wt.stage_exact_files(project, [r"..\outside.txt"], stage_root=tmp_path / "stages")
    assert refused.value.code == "path_traversal"
    with pytest.raises(wt.WorktreeError) as refused:
        wt.stage_exact_files(project, [r"C:\temp\evil.txt"], stage_root=tmp_path / "stages")
    assert refused.value.code == "absolute_path"
    with pytest.raises(wt.WorktreeError) as refused:
        wt.stage_exact_files(project, [r"\\server\share\evil.txt"],
                             stage_root=tmp_path / "stages")
    assert refused.value.code == "absolute_path"

    area = wt.stage_exact_files(project, [r"sub\c.txt"], stage_root=tmp_path / "stages")
    assert "sub/c.txt" in area.files
    with pytest.raises(wt.WorktreeError) as refused:
        wt.stage_exact_files(project, ["a.txt", "a.txt"], stage_root=tmp_path / "stages")
    assert refused.value.code == "duplicate_claim"
    with pytest.raises(wt.WorktreeError) as refused:
        wt.stage_exact_files(project, ["sub", "sub/c.txt"], stage_root=tmp_path / "stages")
    assert refused.value.code == "overlapping_claim"


def test_staging_symlink_escape_rejected(project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret\n", encoding="utf-8")
    _link_or_skip(outside, project / "link")
    with pytest.raises(wt.WorktreeError) as refused:
        wt.stage_exact_files(project, ["link/secret.txt"], stage_root=tmp_path / "stages")
    assert refused.value.code in {"symlink_path", "path_escape"}


def test_staging_out_of_scope_change_rejected(project: Path, tmp_path: Path) -> None:
    area = wt.stage_exact_files(project, ["a.txt"], stage_root=tmp_path / "stages")
    (area.stage_dir / "extra.txt").write_text("sneaky\n", encoding="utf-8")
    with pytest.raises(wt.WorktreeError) as refused:
        area.apply()
    assert refused.value.code == "out_of_scope"
    assert (project / "a.txt").read_text(encoding="utf-8") == "original-a\n"
    assert not (project / "extra.txt").exists()


def test_staging_out_of_scope_directory_rejected(project: Path, tmp_path: Path) -> None:
    area = wt.stage_exact_files(project, ["a.txt"], stage_root=tmp_path / "stages")
    (area.stage_dir / "extras").mkdir()
    with pytest.raises(wt.WorktreeError) as refused:
        area.apply()
    assert refused.value.code == "out_of_scope"


def test_staging_baseline_mismatch_refuses_apply(project: Path, tmp_path: Path) -> None:
    area = wt.stage_exact_files(project, ["a.txt"], stage_root=tmp_path / "stages")
    (area.stage_dir / "a.txt").write_text("staged edit\n", encoding="utf-8")
    (project / "a.txt").write_text("later user edit\n", encoding="utf-8")
    with pytest.raises(wt.WorktreeError) as refused:
        area.apply()
    assert refused.value.code == "baseline_mismatch"
    assert (project / "a.txt").read_text(encoding="utf-8") == "later user edit\n"


def test_staging_apply_and_backup_restore(project: Path, tmp_path: Path) -> None:
    area = wt.stage_exact_files(project, ["a.txt"], stage_root=tmp_path / "stages")
    (area.stage_dir / "a.txt").write_text("staged-a\n", encoding="utf-8")
    report = area.apply()
    assert report.applied == ("a.txt",)
    assert (project / "a.txt").read_text(encoding="utf-8") == "staged-a\n"
    assert (project / "unclaimed.txt").read_text(encoding="utf-8") == "do not touch\n"

    restored = area.restore_backups()
    assert restored == ("a.txt",)
    assert (project / "a.txt").read_text(encoding="utf-8") == "original-a\n"


def test_staging_new_file_claim_and_restore(project: Path, tmp_path: Path) -> None:
    area = wt.stage_exact_files(project, ["new.txt"], stage_root=tmp_path / "stages")
    (area.stage_dir / "new.txt").write_text("created\n", encoding="utf-8")
    report = area.apply()
    assert report.created == ("new.txt",)
    assert (project / "new.txt").read_text(encoding="utf-8") == "created\n"
    area.restore_backups()
    assert not (project / "new.txt").exists()


def test_staging_seal_detects_post_review_change(project: Path, tmp_path: Path) -> None:
    area = wt.stage_exact_files(project, ["a.txt"], stage_root=tmp_path / "stages")
    (area.stage_dir / "a.txt").write_text("reviewed\n", encoding="utf-8")
    area.seal()
    (area.stage_dir / "a.txt").write_text("changed-after-review\n", encoding="utf-8")
    with pytest.raises(wt.WorktreeError) as refused:
        area.apply()
    assert refused.value.code == "staged_modified"
    assert (project / "a.txt").read_text(encoding="utf-8") == "original-a\n"


def test_staging_advisory_lock_is_cooperative(project: Path, tmp_path: Path) -> None:
    area = wt.stage_exact_files(project, ["a.txt"], stage_root=tmp_path / "stages")
    area.acquire_lock("another-worker")
    with pytest.raises(wt.WorktreeError) as refused:
        area.apply()
    assert refused.value.code == "lock_held"
    area.release_lock()
    (area.stage_dir / "a.txt").write_text("applied-after-lock\n", encoding="utf-8")
    area.apply()
    assert (project / "a.txt").read_text(encoding="utf-8") == "applied-after-lock\n"


def test_staging_rollback_on_ordinary_failure(project: Path, tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    area = wt.stage_exact_files(project, ["a.txt", "b.txt"], stage_root=tmp_path / "stages")
    (area.stage_dir / "a.txt").write_text("staged-a\n", encoding="utf-8")
    (area.stage_dir / "b.txt").write_text("staged-b\n", encoding="utf-8")
    real = wt._install_one
    calls: list[str] = []

    def failing(staging: wt.ExactFileStaging, rel: str) -> None:
        calls.append(rel)
        if len(calls) == 2:
            raise RuntimeError("ordinary failure")
        real(staging, rel)

    monkeypatch.setattr(wt, "_install_one", failing)
    with pytest.raises(wt.WorktreeError) as refused:
        area.apply()
    assert refused.value.code == "apply_failed"
    assert (project / "a.txt").read_text(encoding="utf-8") == "original-a\n"
    assert (project / "b.txt").read_text(encoding="utf-8") == "original-b\n"
    assert area.state == "rolled_back"


def test_interrupted_apply_recovery_restores_original(project: Path, tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    area = _interrupt_after_first_file(project, tmp_path, monkeypatch)
    assert area.state == "applying"
    assert (project / "a.txt").read_text(encoding="utf-8") == "staged-a\n"
    assert (project / "b.txt").read_text(encoding="utf-8") == "original-b\n"

    report = area.recover()
    assert report.restored == ("a.txt",)
    assert report.state == "recovered"
    assert (project / "a.txt").read_text(encoding="utf-8") == "original-a\n"
    assert (project / "b.txt").read_text(encoding="utf-8") == "original-b\n"


def test_interrupted_apply_recovery_preserves_later_user_change(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    area = _interrupt_after_first_file(project, tmp_path, monkeypatch)
    (project / "a.txt").write_text("user edit after interruption\n", encoding="utf-8")
    report = area.recover()
    assert report.preserved == ("a.txt",)
    assert report.restored == ()
    assert (project / "a.txt").read_text(encoding="utf-8") == "user edit after interruption\n"
    assert (project / "b.txt").read_text(encoding="utf-8") == "original-b\n"


def test_interrupted_apply_recovery_from_journal(project: Path, tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    area = _interrupt_after_first_file(project, tmp_path, monkeypatch)
    report = wt.recover_interrupted_apply(area.control_dir)
    assert report.restored == ("a.txt",)
    assert (project / "a.txt").read_text(encoding="utf-8") == "original-a\n"
    assert (project / "b.txt").read_text(encoding="utf-8") == "original-b\n"


def _interrupt_after_first_file(project: Path, tmp_path: Path,
                                monkeypatch: pytest.MonkeyPatch) -> wt.ExactFileStaging:
    area = wt.stage_exact_files(project, ["a.txt", "b.txt"], stage_root=tmp_path / "stages")
    (area.stage_dir / "a.txt").write_text("staged-a\n", encoding="utf-8")
    (area.stage_dir / "b.txt").write_text("staged-b\n", encoding="utf-8")
    real = wt._install_one
    calls: list[str] = []

    def hard_stop(staging: wt.ExactFileStaging, rel: str) -> None:
        calls.append(rel)
        if len(calls) == 2:
            # KeyboardInterrupt is a BaseException: apply() deliberately does
            # not roll back, leaving the journal in the "applying" state.
            raise KeyboardInterrupt("simulated process interruption")
        real(staging, rel)

    monkeypatch.setattr(wt, "_install_one", hard_stop)
    with pytest.raises(KeyboardInterrupt):
        area.apply()
    return area
