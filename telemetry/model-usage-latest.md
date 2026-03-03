# Model Usage Report

- Calls: 3
- Prompt tokens: 10200
- Completion tokens: 2920
- Total tokens: 13120
- Errors: 0
- Fallbacks: 1
- Estimated cost (USD): 0.5000

## By Lane
| Lane | Calls | Tokens | Errors | Fallbacks | Avg Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| L1_low_cost | 1 | 1520 | 0 | 0 | 1900 |
| L2_balanced | 1 | 3300 | 0 | 1 | 2400 |
| L3_heavy | 1 | 8300 | 0 | 0 | 5200 |

## By Model
| Model | Calls | Tokens | Errors | Fallbacks |
| --- | ---: | ---: | ---: | ---: |
| balanced_paid_model | 1 | 3300 | 0 | 1 |
| codex_or_gemini_advanced | 1 | 8300 | 0 | 0 |
| gemini_free_tier | 1 | 1520 | 0 | 0 |

## Fallback Reasons
- google_rate_limit: 1
