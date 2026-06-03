"""Named constants for the InvForge defensive security layer (PR-08)."""

from __future__ import annotations

# IsolationForest parameters
RANDOM_STATE = 42
ANOMALY_CONTAMINATION = 0.05
ANOMALY_N_ESTIMATORS = 100
MIN_SAMPLES_FOR_ANOMALY = 20

# Operational hours (UTC) for after-hours review signals
OPS_HOURS_START = 8
OPS_HOURS_END = 20

# Risk scoring rule weights (documented; final score capped at 1.0)
RULE_QUANTITY_SPIKE_WEIGHT = 0.35
SPIKE_MULTIPLIER = 3.0

RULE_EXTREME_NEGATIVE_WEIGHT = 0.25
NEGATIVE_THRESHOLD = 10.0

RULE_REPEATED_REVERSAL_WEIGHT = 0.20
REVERSAL_WINDOW = 3

RULE_UNKNOWN_REFERENCE_WEIGHT = 0.10

RULE_DATA_QUALITY_WEIGHT = 0.10

# Risk level thresholds
RISK_LEVEL_LOW_MAX = 0.3
RISK_LEVEL_MEDIUM_MAX = 0.6
RISK_LEVEL_HIGH_MAX = 0.85

# Security posture thresholds
POSTURE_CLEAN_ANOMALY_RATE_MAX = 0.03
POSTURE_HIGH_RISK_ANOMALY_RATE_MIN = 0.08

# Valid movement types and reference patterns
VALID_MOVEMENT_TYPES = frozenset({"in", "out", "adjustment"})
REFERENCE_PATTERNS = (
    "PO-",
    "SO-",
    "CYCLE-COUNT",
    "INIT-RECEIPT",
)

# Movement type label encoding for anomaly features
MOVEMENT_TYPE_ENCODING = {
    "in": 0,
    "out": 1,
    "adjustment": 2,
    "unknown": 3,
}

ANOMALY_FEATURES = [
    "quantity",
    "movement_type_encoded",
    "day_of_week",
    "is_weekend",
    "quantity_zscore_per_part",
]

FEATURES_USED_STRING = "|".join(ANOMALY_FEATURES)

# Audit log constraints
AUDIT_DESCRIPTION_MAX_LEN = 200

# Secret-like substrings that must not appear in generated artifacts
FORBIDDEN_ARTIFACT_SUBSTRINGS = (
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
    "bearer ",
    "aws_secret",
    "private_key",
)
