# Resource Agent Logic & Boundary Benchmark Report

**Execution Mode**: `unit`  
**Execution Timestamp**: 2026-11-02 07:22:15Z  
**Total Invariant Tests**: 7  

## Summary Metrics

| Metric | Formula | Value |
|---|---|---|
| **Test Pass Rate** | `Passed Tests / Total Tests × 100` | **100.0%** (7/7) |
| **Tests Passed** | Verified invariant checks | 7 |
| **Tests Failed** | Violated invariants | 0 |

## Invariant Verification Results

| # | Test Name | Category | Status | Runtime (s) | Details |
|---|---|---|---|---|---|
| 1 | `test_proposal_lifecycle_and_single_use_idempotency` | `proposal_lifecycle` | **PASS** | 0.2600 | First consume: ok=True; Second consume: ok=False, msg='Proposal has already been confirmed and processed (duplicate submission blocked).' |
| 2 | `test_proposal_user_session_isolation` | `proposal_lifecycle` | **PASS** | 0.0072 | Attempt by wrong user: ok=False, error='Access denied: Proposal belongs to another user session.' |
| 3 | `test_proposal_ttl_expiry_enforcement` | `proposal_lifecycle` | **PASS** | 0.0064 | Attempt to consume expired proposal: ok=False, error='Proposal has expired. Please check current availability and request again.' |
| 4 | `test_superseded_proposal_invalidation` | `proposal_lifecycle` | **PASS** | 0.0142 | p4a superseded: ok=False, err='Confirmation Blocked: Proposal has been discarded or superseded. Please create a new booking request.'; p4b active: ok=True |
| 5 | `test_natural_language_parameter_extraction` | `nlp_parsing` | **PASS** | 0.0022 | Parsed: date=2026-11-15, start=14:00:00, end=16:00:00, details={'resource_name': 'Seminar Hall A', 'resource_type': 'SEMINAR_HALL', 'resource_id': None, 'min_capacity': 60, 'purpose': None} |
| 6 | `test_temporal_interval_overlap_logic` | `conflict_detection` | **PASS** | 0.0000 | c1_overlap=True, c2_disjoint=False, c3_touching=False, c4_enclosed=True |
| 7 | `test_non_admin_approval_rejection_blocked` | `authorization_guards` | **PASS** | 0.0013 | Student approve: error='Access denied: Only university Administrators possess the authority to approve resource bookings.'; Faculty reject: error='Access denied: Only university Administrators possess the authority to reject resource bookings.' |