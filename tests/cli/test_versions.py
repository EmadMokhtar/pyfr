"""Template versions: the vX.Y.Z tags, compared as numbers."""

from __future__ import annotations

import pytest

from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version, parse_ls_remote, resolve_target

LS_REMOTE = """\
aaaa\trefs/tags/v0.10.0
bbbb\trefs/tags/v0.9.0
cccc\trefs/tags/v1.0.0-rc1
dddd\trefs/tags/latest
eeee\trefs/tags/v0.11.0
eeee\trefs/tags/v0.11.0^{}
ffff\trefs/tags/1.2.3
"""
AVAILABLE = [Version(0, 9, 0), Version(0, 10, 0), Version(0, 11, 0)]


def test_parse_accepts_the_v_and_its_absence() -> None:
    assert Version.parse("v1.2.3") == Version.parse("1.2.3") == Version(1, 2, 3)
    assert Version.parse(" v0.12.0\n") == Version(0, 12, 0)


@pytest.mark.parametrize("bad", ["1.2", "v1.2.3.4", "latest", "v1.0.0-rc1", ""])
def test_parse_rejects_other_shapes(bad: str) -> None:
    with pytest.raises(ValueError, match="not a version"):
        Version.parse(bad)


def test_str_carries_the_v_and_bare_does_not() -> None:
    version = Version(0, 12, 0)
    assert str(version) == "v0.12.0"
    assert version.bare == "0.12.0"


def test_versions_compare_as_numbers_not_text() -> None:
    assert Version(0, 9, 0) < Version(0, 10, 0) < Version(1, 0, 0)


def test_parse_ls_remote_keeps_release_tags_only_oldest_first() -> None:
    # v1.0.0-rc1, `latest` and a v-less 1.2.3 are not release tags; the
    # ^{} line of an annotated tag does not count twice.
    assert parse_ls_remote(LS_REMOTE) == AVAILABLE


def test_resolve_target_defaults_to_the_newest() -> None:
    assert resolve_target(None, AVAILABLE) == Version(0, 11, 0)


@pytest.mark.parametrize("requested", ["v0.10.0", "0.10.0"])
def test_resolve_target_accepts_to_with_or_without_the_v(requested: str) -> None:
    assert resolve_target(requested, AVAILABLE) == Version(0, 10, 0)


def test_resolve_target_refuses_an_unknown_tag_and_names_the_newest() -> None:
    with pytest.raises(UpdateError) as stop:
        resolve_target("v0.12.0", AVAILABLE)
    assert "no tag v0.12.0" in stop.value.cause
    assert "v0.11.0" in stop.value.fix


def test_resolve_target_refuses_garbage() -> None:
    with pytest.raises(UpdateError) as stop:
        resolve_target("latest", AVAILABLE)
    assert "not a version" in stop.value.cause
