# 02: Verify latency improvement

**Status:** resolved
**Blocked by:** 01-persistent-indicator

## What to build

Run the startup timing harness before and after the persistent indicator change to confirm the latency improvement. Document the results.

## Acceptance criteria

- [ ] Run `_debug/startup_timing_v3.py` before change, capture baseline
- [ ] Run `_debug/startup_timing_v3.py` after change, capture new numbers
- [ ] Confirm `indicator.show("recording")` <5ms (was ~250ms)
- [ ] Confirm end-to-end (keypress → arecord capturing) ~130ms (was ~250ms)
- [ ] Document results in ticket comments

## Comments

Baseline (already captured):
```
Indicator cold start: 315 ms
Indicator warm start: 218 ms  
Python imports: 257 ms
arecord startup: ~130 ms
```
