"""
Tests for the Payer Policy Engine.

Tests policy loading, PA requirement checks, auto-approve logic,
and edge cases around missing payers/codes.
"""

import json
import tempfile
from pathlib import Path

import pytest

from care_orchestrator.policy_engine import PolicyEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_policy_data():
    return {
        "payer_id": "test_payer",
        "payer_name": "Test Payer",
        "policy_version": "1.0",
        "default_requires_auth": False,
        "prior_auth_rules": [
            {
                "cpt_code": "73221",
                "requires_auth": True,
                "criteria": {
                    "required_diagnoses": ["M23.5", "S83.5"],
                    "required_documentation": [
                        "Clinical exam findings",
                        "Failed initial treatment",
                    ],
                    "age_restrictions": "none",
                    "review_timeline_hours": 48,
                },
                "auto_approve_diagnoses": ["S83.5"],
            },
            {
                "cpt_code": "99213",
                "requires_auth": False,
                "criteria": None,
                "auto_approve_diagnoses": [],
            },
        ],
    }


@pytest.fixture
def sample_default_auth_policy_data():
    return {
        "payer_id": "strict_payer",
        "payer_name": "Strict Payer",
        "policy_version": "1.0",
        "default_requires_auth": True,
        "prior_auth_rules": [],
    }


@pytest.fixture
def policy_dir(sample_policy_data, sample_default_auth_policy_data):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        with open(path / "test_payer.json", "w") as f:
            json.dump(sample_policy_data, f)
        with open(path / "strict_payer.json", "w") as f:
            json.dump(sample_default_auth_policy_data, f)
        yield path


@pytest.fixture
def engine(policy_dir):
    return PolicyEngine(policies_dir=policy_dir)


# ---------------------------------------------------------------------------
# Policy Loading Tests
# ---------------------------------------------------------------------------


class TestPolicyLoading:
    """Tests for loading payer policies from JSON files."""

    def test_loads_policies_from_directory(self, engine):
        assert len(engine.available_payers) == 2

    def test_available_payers_includes_ids(self, engine):
        assert "test_payer" in engine.available_payers
        assert "strict_payer" in engine.available_payers

    def test_get_policy_returns_policy(self, engine):
        policy = engine.get_policy("test_payer")
        assert policy is not None
        assert policy.payer_name == "Test Payer"

    def test_get_policy_unknown_returns_none(self, engine):
        assert engine.get_policy("nonexistent") is None

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            eng = PolicyEngine(policies_dir=tmpdir)
            assert len(eng.available_payers) == 0

    def test_missing_directory(self):
        eng = PolicyEngine(policies_dir="/nonexistent/path")
        assert len(eng.available_payers) == 0


# ---------------------------------------------------------------------------
# PA Requirement Tests
# ---------------------------------------------------------------------------


class TestPARequirements:
    """Tests for checking prior authorization requirements."""

    def test_code_requires_auth(self, engine):
        req = engine.check_requirements("73221", ["M23.5"], "test_payer")
        assert req is not None
        assert req.requires_auth is True

    def test_code_does_not_require_auth(self, engine):
        req = engine.check_requirements("99213", [], "test_payer")
        assert req is not None
        assert req.requires_auth is False

    def test_unknown_code_uses_default(self, engine):
        req = engine.check_requirements("99999", [], "test_payer")
        assert req is not None
        assert req.requires_auth is False  # default is False

    def test_strict_payer_default_requires_auth(self, engine):
        req = engine.check_requirements("99999", [], "strict_payer")
        assert req is not None
        assert req.requires_auth is True  # default is True

    def test_unknown_payer_returns_none(self, engine):
        req = engine.check_requirements("73221", [], "nonexistent")
        assert req is None

    def test_criteria_included_when_auth_required(self, engine):
        req = engine.check_requirements("73221", ["M23.5"], "test_payer")
        assert req.criteria is not None
        assert "M23.5" in req.criteria.required_diagnoses
        assert req.criteria.review_timeline_hours == 48


# ---------------------------------------------------------------------------
# Auto-Approve Tests
# ---------------------------------------------------------------------------


class TestAutoApprove:
    """Tests for automatic approval based on qualifying diagnoses."""

    def test_auto_approve_with_qualifying_diagnosis(self, engine):
        assert engine.check_auto_approve("73221", ["S83.5"], "test_payer") is True

    def test_no_auto_approve_without_qualifying_diagnosis(self, engine):
        assert engine.check_auto_approve("73221", ["M23.5"], "test_payer") is False

    def test_no_auto_approve_for_non_auth_code(self, engine):
        assert engine.check_auto_approve("99213", ["S83.5"], "test_payer") is False

    def test_no_auto_approve_for_unknown_payer(self, engine):
        assert engine.check_auto_approve("73221", ["S83.5"], "nonexistent") is False


# ---------------------------------------------------------------------------
# Real Policy File Tests
# ---------------------------------------------------------------------------


class TestRealPolicies:
    """Tests using the actual shipped policy files."""

    def test_commercial_generic_loads(self):
        eng = PolicyEngine(policies_dir="config/policies")
        assert "commercial_generic" in eng.available_payers

    def test_medicare_loads(self):
        eng = PolicyEngine(policies_dir="config/policies")
        assert "medicare" in eng.available_payers

    def test_medicaid_loads(self):
        eng = PolicyEngine(policies_dir="config/policies")
        assert "medicaid" in eng.available_payers

    def test_commercial_mri_requires_auth(self):
        eng = PolicyEngine(policies_dir="config/policies")
        req = eng.check_requirements("73221", ["M23.5"], "commercial_generic")
        assert req is not None
        assert req.requires_auth is True
