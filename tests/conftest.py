"""
Shared test fixtures for care-orchestrator test suite.

Provides sample clinical notes, mock Anthropic clients, and reusable test data.
"""

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Sample Clinical Notes
# ---------------------------------------------------------------------------

CLEAN_NOTE = """
The patient presented with chronic knee pain. Examination reveals
limited range of motion in the right knee. Recommended imaging
to assess structural damage. Follow-up in 2 weeks.
"""

PHI_LADEN_NOTE = """
Patient John Doe (DOB 05/12/1980) visited for a follow-up.
He requires a Knee MRI (CPT 73221) due to chronic ACL pain (ICD-10 M23.5).
Contact: john.doe@email.com, Phone: (555) 123-4567
SSN: 123-45-6789
Address: 123 Main Street, Springfield
MRN: 78901234
"""

MULTI_CODE_NOTE = """
Patient presents with Type 2 diabetes (ICD-10 E11.9) and hypertension (ICD-10 I10).
Office visit level 4 (CPT 99214). Low back pain noted (ICD-10 M54.5).
Lumbar MRI ordered (CPT 72148).
"""

PRIOR_AUTH_NOTE = """
Prior Authorization Request:
Patient requires total knee replacement (CPT 27447) due to primary
osteoarthritis of the right knee (ICD-10 M17.11). Conservative treatment
has failed after 6 months of physical therapy.
"""


@pytest.fixture
def clean_note():
    """A clinical note with no PHI."""
    return CLEAN_NOTE


@pytest.fixture
def phi_note():
    """A clinical note containing various PHI elements."""
    return PHI_LADEN_NOTE


@pytest.fixture
def multi_code_note():
    """A clinical note with multiple CPT and ICD-10 codes."""
    return MULTI_CODE_NOTE


@pytest.fixture
def prior_auth_note():
    """A clinical note for a Prior Authorization scenario."""
    return PRIOR_AUTH_NOTE


@pytest.fixture
def mock_anthropic_response():
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text="""
<audit_report>
    <phi_status>REDACTED</phi_status>
    <missed_phi_count>0</missed_phi_count>
    <admin_metadata>
        <cpt_codes>73221</cpt_codes>
        <icd10_codes>M23.5</icd10_codes>
        <workflow_type>prior_auth</workflow_type>
    </admin_metadata>
</audit_report>
"""
        )
    ]
    return mock_response


@pytest.fixture
def mock_anthropic_client(mock_anthropic_response):
    """Create a mock Anthropic client that returns the mock response."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_anthropic_response
    return mock_client
