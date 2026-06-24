"""Tests for async network fetchers using mocked HTTP responses."""

import re
from pathlib import Path

import aiohttp
import pytest
import yaml
from aioresponses import aioresponses

from update_versions import (
    ImageRef,
    _list_tags_oci,
    fetch_latest_chart,
    fetch_latest_image,
    fetch_latest_module,
    fetch_latest_provider,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_DUMMY = Path("dummy.tf")


def _dockerhub_ref(tag: str = "2026.6.1") -> ImageRef:
    return ImageRef(
        file=_DUMMY,
        original=f"cloudflare/cloudflared:{tag}",
        registry="dockerhub",
        namespace="cloudflare",
        name="cloudflared",
        tag=tag,
    )


def _ghcr_ref(tag: str = "v1.0.0") -> ImageRef:
    return ImageRef(
        file=_DUMMY,
        original=f"ghcr.io/myorg/myapp:{tag}",
        registry="ghcr",
        namespace="myorg",
        name="myapp",
        tag=tag,
    )


# ── Provider fetcher ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_latest_provider_returns_highest_stable():
    with aioresponses() as m:
        m.get(
            "https://registry.opentofu.org/v1/providers/bpg/proxmox/versions",
            payload={"versions": [{"version": "0.111.0"}, {"version": "0.112.0"}]},
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_provider(session, "bpg/proxmox")
    assert result == "0.112.0"


@pytest.mark.asyncio
async def test_fetch_latest_provider_filters_prerelease():
    with aioresponses() as m:
        m.get(
            "https://registry.opentofu.org/v1/providers/bpg/proxmox/versions",
            payload={"versions": [{"version": "0.112.0"}, {"version": "0.113.0-beta1"}]},
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_provider(session, "bpg/proxmox")
    assert result == "0.112.0"


@pytest.mark.asyncio
async def test_fetch_latest_provider_all_prerelease_returns_none():
    with aioresponses() as m:
        m.get(
            "https://registry.opentofu.org/v1/providers/bpg/proxmox/versions",
            payload={"versions": [{"version": "1.0.0-alpha"}, {"version": "1.0.0-rc1"}]},
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_provider(session, "bpg/proxmox")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_latest_provider_empty_versions_returns_none():
    with aioresponses() as m:
        m.get(
            "https://registry.opentofu.org/v1/providers/bpg/proxmox/versions",
            payload={"versions": []},
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_provider(session, "bpg/proxmox")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_latest_provider_http_error_returns_none():
    with aioresponses() as m:
        m.get(
            "https://registry.opentofu.org/v1/providers/bpg/proxmox/versions",
            status=404,
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_provider(session, "bpg/proxmox")
    assert result is None


# ── Helm chart fetcher ────────────────────────────────────────────────────────


def _helm_index(chart: str, versions: list[str]) -> str:
    return yaml.dump({"entries": {chart: [{"version": v} for v in versions]}})


@pytest.mark.asyncio
async def test_fetch_latest_chart_returns_highest_stable():
    repo = "https://helm.cilium.io"
    with aioresponses() as m:
        m.get(f"{repo}/index.yaml", body=_helm_index("cilium", ["1.17.4", "1.17.9", "1.18.0"]))
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_chart(session, repo, "cilium")
    assert result == "1.18.0"


@pytest.mark.asyncio
async def test_fetch_latest_chart_filters_prerelease():
    repo = "https://helm.cilium.io"
    with aioresponses() as m:
        m.get(f"{repo}/index.yaml", body=_helm_index("cilium", ["1.17.4", "1.18.0-rc1"]))
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_chart(session, repo, "cilium")
    assert result == "1.17.4"


@pytest.mark.asyncio
async def test_fetch_latest_chart_missing_chart_returns_none():
    repo = "https://helm.cilium.io"
    with aioresponses() as m:
        m.get(f"{repo}/index.yaml", body=yaml.dump({"entries": {}}))
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_chart(session, repo, "cilium")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_latest_chart_http_error_returns_none():
    repo = "https://helm.cilium.io"
    with aioresponses() as m:
        m.get(f"{repo}/index.yaml", status=503)
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_chart(session, repo, "cilium")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_latest_chart_strips_trailing_slash():
    repo = "https://helm.cilium.io/"
    with aioresponses() as m:
        m.get("https://helm.cilium.io/index.yaml", body=_helm_index("cilium", ["1.18.0"]))
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_chart(session, repo, "cilium")
    assert result == "1.18.0"


# ── Module fetcher ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_latest_module_opentofu_registry():
    source = "terraform-aws-modules/vpc/aws"
    with aioresponses() as m:
        m.get(
            f"https://registry.opentofu.org/v1/modules/{source}/versions",
            payload={"modules": [{"versions": [{"version": "5.1.2"}, {"version": "5.2.0"}]}]},
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_module(session, source, "opentofu")
    assert result == "5.2.0"


@pytest.mark.asyncio
async def test_fetch_latest_module_terraform_registry():
    source = "terraform-aws-modules/eks/aws"
    with aioresponses() as m:
        m.get(
            f"https://registry.terraform.io/v1/modules/{source}/versions",
            payload={"modules": [{"versions": [{"version": "20.0.0"}, {"version": "20.1.0"}]}]},
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_module(session, source, "terraform")
    assert result == "20.1.0"


@pytest.mark.asyncio
async def test_fetch_latest_module_filters_prerelease():
    source = "terraform-aws-modules/vpc/aws"
    with aioresponses() as m:
        m.get(
            f"https://registry.opentofu.org/v1/modules/{source}/versions",
            payload={"modules": [{"versions": [{"version": "5.2.0"}, {"version": "5.3.0-beta"}]}]},
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_module(session, source, "opentofu")
    assert result == "5.2.0"


@pytest.mark.asyncio
async def test_fetch_latest_module_empty_returns_none():
    source = "terraform-aws-modules/vpc/aws"
    with aioresponses() as m:
        m.get(
            f"https://registry.opentofu.org/v1/modules/{source}/versions",
            payload={"modules": []},
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_module(session, source, "opentofu")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_latest_module_http_error_returns_none():
    source = "terraform-aws-modules/vpc/aws"
    with aioresponses() as m:
        m.get(
            f"https://registry.opentofu.org/v1/modules/{source}/versions",
            status=404,
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_module(session, source, "opentofu")
    assert result is None


# ── OCI tag listing ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tags_oci_single_page():
    with aioresponses() as m:
        m.get(
            "https://registry-1.docker.io/v2/cloudflare/cloudflared/tags/list",
            payload={"tags": ["2026.6.1", "2026.7.0"]},
        )
        async with aiohttp.ClientSession() as session:
            tags = await _list_tags_oci(session, "registry-1.docker.io", "cloudflare/cloudflared", "token123")
    assert set(tags) == {"2026.6.1", "2026.7.0"}


@pytest.mark.asyncio
async def test_list_tags_oci_pagination():
    page2_url = "https://registry-1.docker.io/v2/cloudflare/cloudflared/tags/list?last=2026.6.1"
    with aioresponses() as m:
        m.get(
            "https://registry-1.docker.io/v2/cloudflare/cloudflared/tags/list",
            payload={"tags": ["2026.6.1"]},
            headers={"Link": f'<{page2_url}>; rel="next"'},
        )
        m.get(
            page2_url,
            payload={"tags": ["2026.7.0"]},
        )
        async with aiohttp.ClientSession() as session:
            tags = await _list_tags_oci(session, "registry-1.docker.io", "cloudflare/cloudflared", "token123")
    assert set(tags) == {"2026.6.1", "2026.7.0"}


@pytest.mark.asyncio
async def test_list_tags_oci_non_200_returns_empty():
    with aioresponses() as m:
        m.get(
            "https://registry-1.docker.io/v2/cloudflare/cloudflared/tags/list",
            status=401,
        )
        async with aiohttp.ClientSession() as session:
            tags = await _list_tags_oci(session, "registry-1.docker.io", "cloudflare/cloudflared", "")
    assert tags == []


# ── Image fetcher ─────────────────────────────────────────────────────────────

_TOKEN_URL = re.compile(r"https://auth\.docker\.io/token.*")
_TAGS_URL_CF = "https://registry-1.docker.io/v2/cloudflare/cloudflared/tags/list"
_GHCR_TOKEN_URL = re.compile(r"https://ghcr\.io/token.*")
_GHCR_TAGS_URL = "https://ghcr.io/v2/myorg/myapp/tags/list"


@pytest.mark.asyncio
async def test_fetch_latest_image_dockerhub_returns_newer():
    ref = _dockerhub_ref("2026.6.1")
    with aioresponses() as m:
        m.get(_TOKEN_URL, payload={"token": "fake-token"})
        m.get(_TAGS_URL_CF, payload={"tags": ["2026.6.1", "2026.7.0", "latest", "main"]})
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_image(session, ref)
    assert result == "2026.7.0"


@pytest.mark.asyncio
async def test_fetch_latest_image_dockerhub_no_newer_returns_none():
    ref = _dockerhub_ref("2026.7.0")
    with aioresponses() as m:
        m.get(_TOKEN_URL, payload={"token": "fake-token"})
        m.get(_TAGS_URL_CF, payload={"tags": ["2026.6.1", "2026.7.0"]})
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_image(session, ref)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_latest_image_filters_unstable_tags():
    ref = _dockerhub_ref("2026.6.1")
    with aioresponses() as m:
        m.get(_TOKEN_URL, payload={"token": "fake-token"})
        m.get(_TAGS_URL_CF, payload={"tags": ["2026.6.1", "latest", "main", "rc1", "2026.7.0-rc1"]})
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_image(session, ref)
    # No stable tag newer than current
    assert result is None


@pytest.mark.asyncio
async def test_fetch_latest_image_dockerhub_no_stable_tags_returns_none():
    ref = _dockerhub_ref("2026.6.1")
    with aioresponses() as m:
        m.get(_TOKEN_URL, payload={"token": "fake-token"})
        m.get(_TAGS_URL_CF, payload={"tags": ["latest", "main", "edge"]})
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_image(session, ref)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_latest_image_ghcr_returns_newer():
    ref = _ghcr_ref("v1.0.0")
    with aioresponses() as m:
        m.get(_GHCR_TOKEN_URL, payload={"token": "ghcr-token"})
        m.get(_GHCR_TAGS_URL, payload={"tags": ["v1.0.0", "v1.1.0", "v2.0.0-rc1", "latest"]})
        async with aiohttp.ClientSession() as session:
            result = await fetch_latest_image(session, ref)
    assert result == "v1.1.0"


@pytest.mark.asyncio
async def test_fetch_latest_image_unknown_registry_returns_none():
    ref = ImageRef(
        file=_DUMMY,
        original="gcr.io/proj/img:v1",
        registry="unknown",
        namespace="proj",
        name="img",
        tag="v1",
    )
    async with aiohttp.ClientSession() as session:
        result = await fetch_latest_image(session, ref)
    assert result is None
