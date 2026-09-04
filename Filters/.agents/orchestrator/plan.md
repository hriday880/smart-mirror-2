# Master Project Plan: Smart Mirror Hand Gesture Photo Capture

## Objective
Develop and verify a robust hand-gesture-triggered photo capture and fair-ready delivery workflow for the Smart Mirror application in macOS, strictly isolated from production files.

## Work Breakdown Structure

### Phase 0: Survey & Scope Mapping (Parallel Explorers)
- **Explorer 1**: Codebase Architecture, MediaPipe Hand Tracking pipeline, video feed loops, UI rendering mechanisms.
- **Explorer 2**: Hand gesture recognition options (Peace sign, Open Palm, etc.), debounce/hold-time dynamics, countdown overlay & flash animation UX.
- **Explorer 3**: Fair delivery workflow (instant photo save, local web server / QR code generation, frictionless transfer, preview dismissal) and test isolation strategy (`main_test.py`, `test.command`).

### Phase 1: Global Synthesis & Project Blueprint
- Synthesize findings into `PROJECT.md` (Architecture, Feature Inventory, Milestones, Interface Contracts, Code Layout).
- Formulate `TEST_INFRA.md` (4-tier test architecture, mock media/gesture pipeline, verification scripts).

### Phase 2: Dual Track Dispatch
- **Track 1: Implementation Track**
  - M1: Test Environment Isolation & `test.command` macOS Launcher Setup.
  - M2: Robust MediaPipe Gesture Recognition Engine (with smoothing/hold-time/debounce).
  - M3: Visual Capture Pipeline (Countdown timer, visual feedback/flash, capture high-res frame with active filter).
  - M4: Fair-Ready Delivery Hub (Save to gallery, local HTTP server / QR code display on mirror UI, auto-dismiss / resume).
- **Track 2: E2E Testing Track**
  - Harness creation: Headless mock camera/gesture injector, simulated UI event runner.
  - Test suites: Tier 1 (Feature coverage), Tier 2 (Boundaries/Edge cases), Tier 3 (Cross-feature interactions), Tier 4 (Realistic fair scenarios).
  - Publication of `TEST_READY.md`.

### Phase 3: Integration & Final Milestone
- Sub-orchestrator execution: Pass 100% E2E tests (Tiers 1-4).
- Adversarial hardening: Tier 5 white-box stress testing with Challengers & Reviewers.
- Forensic Integrity Audit (`teamwork_preview_auditor`).

### Phase 4: Signoff & Reporting
- Final validation of macOS launcher `test.command` and isolated test files.
- Human report generation and victory message to Sentinel parent.
