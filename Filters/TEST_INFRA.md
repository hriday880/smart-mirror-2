# E2E Test Infra: Smart Mirror Hand Gesture Photo Capture

## Test Philosophy
- Opaque-box, requirement-driven. Derives from `ORIGINAL_REQUEST.md` and user-facing specifications without dependence on implementation internals.
- Strict isolation: All tests run against test duplicate modules and test launcher, asserting original source files remain 100% unaltered.
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing.

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Scenario) |
|---|---------|---------------------|:-----------------:|:-----------------:|:-----------------:|:-----------------:|
| F1 | Test Environment Isolation | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| F2 | macOS `test.command` Launcher | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| F3 | Peace Sign (✌️) Detection Engine | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| F4 | Hold Confirmation (0.7s) & Progress HUD | Survey 2 | 5 | 5 | ✓ | ✓ |
| F5 | Animated 3-2-1 Countdown & Sound | Survey 2 | 5 | 5 | ✓ | ✓ |
| F6 | Shutter Flash Animation & Sound | Survey 2 | 5 | 5 | ✓ | ✓ |
| F7 | Pristine Layer-Separated Disk Saver | Survey 2, Survey 3 | 5 | 5 | ✓ | ✓ |
| F8 | Background LAN HTTP Delivery Server | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| F9 | OpenCV QR Code Encoding & HUD Card | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| F10 | Auto-Dismiss (6s), Cooldown (2s) & Reset | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Headless Test Runner**: `pytest` or `python -m unittest` with synthetic landmark generators and `MockVideoCapture`.
- **Directory Layout**:
  ```
  tests/
  ├── conftest.py                   # Pytest fixtures, mock landmarks, mock camera
  ├── test_tier1_features.py        # Tier 1: 50+ unit tests for isolated features F1-F10
  ├── test_tier2_boundaries.py      # Tier 2: 50+ boundary/edge cases (jitter, scale, timeouts)
  ├── test_tier3_combinations.py    # Tier 3: Pairwise interactions (portal + peace sign, etc.)
  ├── test_tier4_scenarios.py       # Tier 4: Real-world fair booth scenarios
  └── test_runner.py                # Standalone unified runner that publishes TEST_READY.md
  ```
- **Pass/Fail Semantics**: 100% test pass rate with exit code 0. Zero regressions and zero modifications to original files.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| S1 | Solo Fairgoer Souvenir Selfie | F3, F4, F5, F6, F7, F8, F9, F10 | Medium |
| S2 | Two-Person Portal Filter Selection followed by Peace Sign Photo | F1, F3, F4, F5, F6, F7, F8, F9, F10 | High |
| S3 | Rapid Consecutive Fairgoers (Debounce & Queue Lifecycle) | F4, F7, F8, F9, F10 | High |
| S4 | Mobile Phone Wi-Fi Scan & Instant Photo Download Simulation | F8, F9, F10 | High |
| S5 | Launcher Cold-Start & Clean Termination via `test.command` | F1, F2, F8 | Medium |

## Coverage Thresholds
- Tier 1: ≥50 test cases (≥5 per feature across F1–F10)
- Tier 2: ≥50 boundary and corner cases
- Tier 3: ≥10 pairwise interaction test cases
- Tier 4: ≥5 realistic fair booth end-to-end scenarios
- **Total Suite Minimum: ≥115 automated test cases**
