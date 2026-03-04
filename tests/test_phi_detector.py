"""
Tests for the deterministic PHI detector.

Validates regex-based detection of SSN, phone, DOB, email, MRN, and addresses.
"""

import pytest

from care_orchestrator.models import PHIType
from care_orchestrator.phi_detector import PHIDetector


@pytest.fixture
def detector():
    """Fresh PHIDetector instance for each test."""
    return PHIDetector()


# ---------------------------------------------------------------------------
# SSN Detection
# ---------------------------------------------------------------------------


class TestSSNDetection:
    """Tests for Social Security Number detection."""

    def test_ssn_with_dashes(self, detector):
        result = detector.detect("SSN: 123-45-6789")
        assert not result.is_clean
        ssn_entities = [e for e in result.entities if e.phi_type == PHIType.SSN]
        assert len(ssn_entities) >= 1
        assert "[REDACTED_SSN]" in result.redacted_text

    def test_ssn_with_spaces(self, detector):
        result = detector.detect("SSN: 123 45 6789")
        assert not result.is_clean
        ssn_entities = [e for e in result.entities if e.phi_type == PHIType.SSN]
        assert len(ssn_entities) >= 1

    def test_ssn_no_separators(self, detector):
        result = detector.detect("SSN: 123456789")
        assert not result.is_clean
        ssn_entities = [e for e in result.entities if e.phi_type == PHIType.SSN]
        assert len(ssn_entities) >= 1

    def test_invalid_ssn_000_prefix(self, detector):
        """SSNs starting with 000 are invalid and should not match."""
        result = detector.detect("Number: 000-12-3456")
        ssn_entities = [e for e in result.entities if e.phi_type == PHIType.SSN]
        assert len(ssn_entities) == 0


# ---------------------------------------------------------------------------
# Phone Detection
# ---------------------------------------------------------------------------


class TestPhoneDetection:
    """Tests for phone number detection."""

    def test_phone_with_parens(self, detector):
        result = detector.detect("Call (555) 123-4567")
        assert not result.is_clean
        phone_entities = [e for e in result.entities if e.phi_type == PHIType.PHONE]
        assert len(phone_entities) >= 1
        assert "[REDACTED_PHONE]" in result.redacted_text

    def test_phone_with_dashes(self, detector):
        result = detector.detect("Phone: 555-123-4567")
        assert not result.is_clean
        phone_entities = [e for e in result.entities if e.phi_type == PHIType.PHONE]
        assert len(phone_entities) >= 1

    def test_phone_with_dots(self, detector):
        result = detector.detect("Phone: 555.123.4567")
        assert not result.is_clean
        phone_entities = [e for e in result.entities if e.phi_type == PHIType.PHONE]
        assert len(phone_entities) >= 1

    def test_phone_with_country_code(self, detector):
        result = detector.detect("Phone: +1-555-123-4567")
        assert not result.is_clean
        phone_entities = [e for e in result.entities if e.phi_type == PHIType.PHONE]
        assert len(phone_entities) >= 1


# ---------------------------------------------------------------------------
# DOB Detection
# ---------------------------------------------------------------------------


class TestDOBDetection:
    """Tests for date of birth detection."""

    def test_dob_with_label(self, detector):
        result = detector.detect("DOB 05/12/1980")
        assert not result.is_clean
        dob_entities = [e for e in result.entities if e.phi_type == PHIType.DOB]
        assert len(dob_entities) >= 1
        assert "[REDACTED_DOB]" in result.redacted_text

    def test_dob_with_colon(self, detector):
        result = detector.detect("Date of Birth: 12-25-1990")
        assert not result.is_clean
        dob_entities = [e for e in result.entities if e.phi_type == PHIType.DOB]
        assert len(dob_entities) >= 1

    def test_dob_spelled_month(self, detector):
        result = detector.detect("Born on January 15, 1985")
        assert not result.is_clean
        dob_entities = [e for e in result.entities if e.phi_type == PHIType.DOB]
        assert len(dob_entities) >= 1


# ---------------------------------------------------------------------------
# Email Detection
# ---------------------------------------------------------------------------


class TestEmailDetection:
    """Tests for email address detection."""

    def test_standard_email(self, detector):
        result = detector.detect("Email: john.doe@hospital.com")
        assert not result.is_clean
        email_entities = [e for e in result.entities if e.phi_type == PHIType.EMAIL]
        assert len(email_entities) == 1
        assert "[REDACTED_EMAIL]" in result.redacted_text

    def test_email_with_plus(self, detector):
        result = detector.detect("Contact: user+tag@example.org")
        assert not result.is_clean
        email_entities = [e for e in result.entities if e.phi_type == PHIType.EMAIL]
        assert len(email_entities) == 1


# ---------------------------------------------------------------------------
# MRN Detection
# ---------------------------------------------------------------------------


class TestMRNDetection:
    """Tests for Medical Record Number detection."""

    def test_mrn_with_label(self, detector):
        result = detector.detect("MRN: 78901234")
        assert not result.is_clean
        mrn_entities = [e for e in result.entities if e.phi_type == PHIType.MRN]
        assert len(mrn_entities) == 1
        assert "[REDACTED_MRN]" in result.redacted_text

    def test_mrn_with_hash(self, detector):
        result = detector.detect("MRN#12345678")
        assert not result.is_clean
        mrn_entities = [e for e in result.entities if e.phi_type == PHIType.MRN]
        assert len(mrn_entities) == 1


# ---------------------------------------------------------------------------
# Address Detection
# ---------------------------------------------------------------------------


class TestAddressDetection:
    """Tests for street address detection."""

    def test_street_address(self, detector):
        result = detector.detect("Lives at 123 Main Street")
        assert not result.is_clean
        addr_entities = [e for e in result.entities if e.phi_type == PHIType.ADDRESS]
        assert len(addr_entities) >= 1
        assert "[REDACTED_ADDRESS]" in result.redacted_text

    def test_avenue_address(self, detector):
        result = detector.detect("Office at 456 Oak Avenue")
        assert not result.is_clean
        addr_entities = [e for e in result.entities if e.phi_type == PHIType.ADDRESS]
        assert len(addr_entities) >= 1


# ---------------------------------------------------------------------------
# Clean Text (No False Positives)
# ---------------------------------------------------------------------------


class TestCleanText:
    """Ensure no false positives on clean clinical text."""

    def test_clean_clinical_note(self, detector, clean_note):
        result = detector.detect(clean_note)
        assert result.is_clean
        assert result.entity_count == 0
        assert result.redacted_text == clean_note

    def test_medical_codes_not_flagged(self, detector):
        """CPT and ICD-10 codes should NOT be flagged as PHI."""
        text = "Procedure CPT 73221, Diagnosis ICD-10 M23.5"
        result = detector.detect(text)
        # Codes themselves shouldn't be detected as PHI
        assert result.entity_count == 0


# ---------------------------------------------------------------------------
# Mixed PHI
# ---------------------------------------------------------------------------


class TestMixedPHI:
    """Tests with multiple PHI types in a single text."""

    def test_multiple_phi_types(self, detector, phi_note):
        result = detector.detect(phi_note)
        assert not result.is_clean
        assert result.entity_count >= 4  # SSN, phone, email, DOB at minimum

        phi_types_found = {e.phi_type for e in result.entities}
        assert PHIType.SSN in phi_types_found
        assert PHIType.PHONE in phi_types_found
        assert PHIType.EMAIL in phi_types_found

    def test_redaction_preserves_non_phi(self, detector, phi_note):
        """Redaction should not remove clinical content."""
        result = detector.detect(phi_note)
        assert "Knee MRI" in result.redacted_text
        assert "CPT 73221" in result.redacted_text
        assert "ICD-10 M23.5" in result.redacted_text
