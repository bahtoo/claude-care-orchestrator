"""
Deterministic PHI Detector — regex-based safety net.

This module runs BEFORE the LLM as a first-pass guarantee. Even if Claude
misses a PHI element, these deterministic patterns will catch it.

Supported PHI types:
- SSN (Social Security Numbers)
- Phone numbers (US formats)
- Dates of birth (multiple date formats)
- Email addresses
- Medical Record Numbers (MRN)
- US street addresses

Note: Name detection is intentionally conservative to minimize false positives.
The LLM pass handles name detection with contextual understanding.
"""

import re
from typing import ClassVar

from care_orchestrator.logging_config import logger
from care_orchestrator.models import PHIDetectionResult, PHIEntity, PHIType


class PHIDetector:
    """Deterministic PHI detection engine using compiled regex patterns."""

    # Compiled regex patterns for each PHI type
    # Using ClassVar to indicate these are shared across all instances
    PATTERNS: ClassVar[list[tuple[PHIType, re.Pattern[str]]]] = [
        # SSN: 123-45-6789, 123 45 6789, 123456789
        (
            PHIType.SSN,
            re.compile(
                r"\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b"
            ),
        ),
        # Phone: (123) 456-7890, 123-456-7890, 123.456.7890, 1234567890, +1-123-456-7890
        (
            PHIType.PHONE,
            re.compile(
                r"(?:\+?1[-.\s]?)?"
                r"(?:\(?\d{3}\)?[-.\s]?)"
                r"\d{3}[-.\s]?\d{4}\b"
            ),
        ),
        # DOB: Various date formats — MM/DD/YYYY, MM-DD-YYYY, Month DD YYYY, etc.
        # Contextual: looks for date-like patterns near DOB indicators
        (
            PHIType.DOB,
            re.compile(
                r"(?:DOB|Date\s*of\s*Birth|Born|Birth\s*Date|D\.O\.B\.?)"
                r"[\s:]*"
                r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
                re.IGNORECASE,
            ),
        ),
        # Standalone dates (more aggressive — catches dates even without DOB context)
        (
            PHIType.DOB,
            re.compile(
                r"\b(?:January|February|March|April|May|June|July|August|September|"
                r"October|November|December)\s+\d{1,2},?\s+\d{4}\b",
                re.IGNORECASE,
            ),
        ),
        # Email
        (
            PHIType.EMAIL,
            re.compile(
                r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
            ),
        ),
        # MRN: Common formats like MRN: 12345678, MRN#12345678
        (
            PHIType.MRN,
            re.compile(
                r"(?:MRN|Medical\s*Record\s*(?:Number|No\.?|#))"
                r"[\s:#]*(\d{4,12})",
                re.IGNORECASE,
            ),
        ),
        # US Street Addresses (simplified — catches common patterns)
        (
            PHIType.ADDRESS,
            re.compile(
                r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s*){1,3}"
                r"(?:Street|St\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Drive|Dr\.?|"
                r"Road|Rd\.?|Lane|Ln\.?|Court|Ct\.?|Place|Pl\.?|Way)\b",
                re.IGNORECASE,
            ),
        ),
    ]

    # Redaction token mapping
    REDACTION_TOKENS: ClassVar[dict[PHIType, str]] = {
        PHIType.SSN: "[REDACTED_SSN]",
        PHIType.PHONE: "[REDACTED_PHONE]",
        PHIType.DOB: "[REDACTED_DOB]",
        PHIType.EMAIL: "[REDACTED_EMAIL]",
        PHIType.NAME: "[REDACTED_NAME]",
        PHIType.MRN: "[REDACTED_MRN]",
        PHIType.ADDRESS: "[REDACTED_ADDRESS]",
    }

    def detect(self, text: str) -> PHIDetectionResult:
        """
        Scan text for PHI using deterministic regex patterns.

        Args:
            text: Raw clinical text to scan.

        Returns:
            PHIDetectionResult with detected entities and redacted text.
        """
        entities: list[PHIEntity] = []

        for phi_type, pattern in self.PATTERNS:
            for match in pattern.finditer(text):
                # Use the first captured group if it exists, otherwise the full match
                if match.groups():
                    value = match.group(1)
                    start = match.start(1)
                    end = match.end(1)
                else:
                    value = match.group(0)
                    start = match.start(0)
                    end = match.end(0)

                entities.append(
                    PHIEntity(
                        value=value,
                        phi_type=phi_type,
                        start=start,
                        end=end,
                    )
                )

        # Sort entities by position (reverse) to redact from end to start
        # This preserves character positions during replacement
        entities_sorted = sorted(entities, key=lambda e: e.start, reverse=True)

        redacted_text = text
        for entity in entities_sorted:
            token = self.REDACTION_TOKENS.get(entity.phi_type, "[REDACTED]")
            redacted_text = (
                redacted_text[: entity.start] + token + redacted_text[entity.end :]
            )

        # Re-sort entities by position (forward) for output
        entities = sorted(entities, key=lambda e: e.start)

        is_clean = len(entities) == 0

        if not is_clean:
            logger.info(
                f"PHI detected: {len(entities)} entities found "
                f"(types: {', '.join(set(e.phi_type.value for e in entities))})"
            )
        else:
            logger.info("PHI scan complete: text is CLEAN")

        return PHIDetectionResult(
            is_clean=is_clean,
            entities=entities,
            redacted_text=redacted_text,
            entity_count=len(entities),
        )


# Module-level convenience instance
phi_detector = PHIDetector()
