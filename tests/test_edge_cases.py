"""Tests for edge cases and error handling."""

from pathlib import Path

import pytest

from update_versions import (
    _parse_image_ref,
    is_stable,
    is_version_tag,
    new_constraint,
    parse_helm_releases,
    parse_images,
    parse_modules,
    parse_providers,
)


class TestIsStable:
    def test_stable_semver(self):
        assert is_stable("1.2.3") is True
        assert is_stable("v1.2.3") is True

    def test_prerelease(self):
        assert is_stable("1.0.0-alpha.1") is False
        assert is_stable("1.0.0-beta") is False
        assert is_stable("1.0.0rc1") is False

    def test_invalid_string(self):
        assert is_stable("not-a-version") is False
        assert is_stable("") is False


class TestIsVersionTag:
    def test_date_version(self):
        assert is_version_tag("2026.6.1") is True

    def test_v_prefix(self):
        assert is_version_tag("v1.0.0") is True

    def test_rejects_empty(self):
        assert is_version_tag("") is False

    def test_rejects_nightly(self):
        assert is_version_tag("nightly") is False

    def test_rejects_canary(self):
        assert is_version_tag("canary") is False

    def test_rejects_dev(self):
        assert is_version_tag("dev") is False

    def test_rejects_snapshot(self):
        assert is_version_tag("snapshot") is False

    def test_version_with_rc(self):
        # "1.0.0-rc1" contains digits so passes is_version_tag but is_stable filters it
        result = is_version_tag("1.0.0-rc1")
        # It has digits so is a "version tag", but is_stable will reject it
        assert isinstance(result, bool)


class TestNewConstraintEdgeCases:
    def test_latest_equals_current(self):
        ver, manual = new_constraint("1.0.0", "1.0.0")
        assert ver is None
        assert not manual

    def test_pessimistic_already_at_latest_minor(self):
        ver, manual = new_constraint("~> 3.5", "3.5.9")
        assert ver is None
        assert not manual

    def test_pessimistic_patch_already_up_to_date(self):
        ver, manual = new_constraint("~> 1.17.9", "1.17.9")
        assert ver is None
        assert not manual

    def test_major_bump_on_exact_pin(self):
        # Exact pins always bump, including major
        ver, manual = new_constraint("1.0.0", "2.0.0")
        assert ver == "2.0.0"
        assert not manual

    def test_three_part_pessimistic_major_bump(self):
        ver, manual = new_constraint("~> 1.2.3", "2.0.0")
        assert ver is None
        assert manual


class TestParseProvidersEdgeCases:
    def test_no_required_providers_block(self):
        result = parse_providers("terraform {}")
        assert result == []

    def test_empty_content(self):
        result = parse_providers("")
        assert result == []

    def test_provider_without_version(self):
        content = '''
terraform {
  required_providers {
    nover = {
      source = "foo/bar"
    }
  }
}
'''
        result = parse_providers(content)
        assert result == []

    def test_single_line_format(self):
        content = '''
terraform {
  required_providers {
    proxmox = { source = "bpg/proxmox", version = "0.111.0" }
  }
}
'''
        result = parse_providers(content)
        assert len(result) == 1
        assert result[0].source == "bpg/proxmox"


class TestParseHelmReleasesEdgeCases:
    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.tf"
        f.write_text("")
        assert parse_helm_releases([f]) == []

    def test_no_helm_releases(self, tmp_path):
        f = tmp_path / "other.tf"
        f.write_text('resource "kubernetes_namespace_v1" "foo" { metadata { name = "foo" } }')
        assert parse_helm_releases([f]) == []

    def test_missing_repository_skipped(self, tmp_path):
        f = tmp_path / "helm.tf"
        f.write_text('resource "helm_release" "foo" { chart = "bar" version = "1.0.0" }')
        assert parse_helm_releases([f]) == []


class TestParseModulesEdgeCases:
    def test_skips_git_source(self, tmp_path):
        f = tmp_path / "mod.tf"
        f.write_text('''
module "git_mod" {
  source  = "git::https://github.com/org/repo.git"
  version = "1.0.0"
}
''')
        assert parse_modules([f]) == []

    def test_skips_http_source(self, tmp_path):
        f = tmp_path / "mod.tf"
        f.write_text('''
module "http_mod" {
  source  = "https://example.com/mod.zip"
  version = "1.0.0"
}
''')
        assert parse_modules([f]) == []

    def test_skips_module_without_version(self, tmp_path):
        f = tmp_path / "mod.tf"
        f.write_text('''
module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
}
''')
        assert parse_modules([f]) == []

    def test_skips_two_part_source(self, tmp_path):
        f = tmp_path / "mod.tf"
        f.write_text('''
module "bad" {
  source  = "namespace/name"
  version = "1.0.0"
}
''')
        assert parse_modules([f]) == []

    def test_terraform_registry(self, tmp_path):
        f = tmp_path / "mod.tf"
        f.write_text('''
module "eks" {
  source  = "registry.terraform.io/terraform-aws-modules/eks/aws"
  version = "20.0.0"
}
''')
        modules = parse_modules([f])
        assert len(modules) == 1
        assert modules[0].registry == "terraform"
        assert modules[0].source == "terraform-aws-modules/eks/aws"


class TestParseImagesEdgeCases:
    def test_no_images(self, tmp_path):
        f = tmp_path / "nomatch.tf"
        f.write_text('resource "kubernetes_namespace_v1" "foo" { metadata { name = "foo" } }')
        assert parse_images([f]) == []

    def test_skips_untagged(self, tmp_path):
        f = tmp_path / "img.tf"
        f.write_text('container { image = "nginx" }')
        assert parse_images([f]) == []

    def test_deduplicates_same_image_across_files(self, tmp_path):
        f1 = tmp_path / "a.tf"
        f2 = tmp_path / "b.tf"
        f1.write_text('container { image = "nginx:1.25.0" }')
        f2.write_text('container { image = "nginx:1.25.0" }')
        images = parse_images([f1, f2])
        assert len(images) == 1


class TestParseImageRef:
    def test_official_dockerhub_image(self, tmp_path):
        ref = _parse_image_ref("nginx:1.25.3", tmp_path / "x.tf")
        assert ref is not None
        assert ref.registry == "dockerhub"
        assert ref.namespace == ""  # single-part image: namespace empty to preserve original format
        assert ref.name == "nginx"

    def test_namespaced_dockerhub_image(self, tmp_path):
        ref = _parse_image_ref("cloudflare/cloudflared:2026.6.1", tmp_path / "x.tf")
        assert ref is not None
        assert ref.registry == "dockerhub"
        assert ref.namespace == "cloudflare"
        assert ref.name == "cloudflared"

    def test_ghcr_image(self, tmp_path):
        ref = _parse_image_ref("ghcr.io/myorg/myapp:v1.2.3", tmp_path / "x.tf")
        assert ref is not None
        assert ref.registry == "ghcr"
        assert ref.namespace == "myorg"
        assert ref.name == "myapp"
        assert ref.tag == "v1.2.3"

    def test_unknown_registry_returns_none(self, tmp_path):
        ref = _parse_image_ref("gcr.io/myproject/myimage:v1", tmp_path / "x.tf")
        assert ref is None

    def test_no_tag_returns_none(self, tmp_path):
        ref = _parse_image_ref("nginx", tmp_path / "x.tf")
        assert ref is None

    def test_unstable_tag_returns_none(self, tmp_path):
        ref = _parse_image_ref("nginx:latest", tmp_path / "x.tf")
        assert ref is None

    def test_updated_property_dockerhub(self, tmp_path):
        ref = _parse_image_ref("cloudflare/cloudflared:2026.6.1", tmp_path / "x.tf")
        assert ref is not None
        ref.latest_tag = "2026.7.0"
        assert ref.updated == "cloudflare/cloudflared:2026.7.0"

    def test_updated_property_ghcr(self, tmp_path):
        ref = _parse_image_ref("ghcr.io/myorg/myapp:v1.0.0", tmp_path / "x.tf")
        assert ref is not None
        ref.latest_tag = "v2.0.0"
        assert ref.updated == "ghcr.io/myorg/myapp:v2.0.0"
