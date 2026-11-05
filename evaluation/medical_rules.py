"""CLI wrapper for shared deterministic source-governance rules."""
from medivector.quality_rules import (  # noqa: F401
    LIMITATIONS, NO_EVIDENCE_ANSWERS, evaluate_case, evaluate_suite, markdown, timestamp, main,
)

if __name__ == '__main__':
    main()
