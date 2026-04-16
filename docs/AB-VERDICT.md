# SOMA A/B Benchmark — Verdict

> **Model:** claude-haiku-4-5-20251001 | **Tasks:** 2 | **Runs:** 3 per task | **Cost:** $0.00  
> **Generated:** 2026-04-16T16:39:51.189446+00:00

## 🟡 VERDICT: NO SIGNIFICANT DIFFERENCE

No metrics to evaluate.

**Recommendation:** kill  
**Confidence:** low  

## Statistical Results

| Metric | SOMA (mean±std) | Baseline (mean±std) | Δ | p-value | Effect | 95% CI (SOMA) | Sig? |
|--------|-----------------|--------------------|----|---------|--------|---------------|------|

### Effect Direction Summary


## Per-Task Breakdown

### Task: linked_list_with_bugs
_Build linked list, inject bugs via fake error feedback, force retries_

| Run | Mode | Tokens | Retries | Duration | Pass | Reflex Blocks |
|-----|------|--------|---------|----------|------|---------------|
| 1 | Baseline | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 2 | Baseline | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 3 | Baseline | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 4 | SOMA | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 5 | SOMA | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 6 | SOMA | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 7 | Reflex | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 8 | Reflex | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 9 | Reflex | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |

### Task: debug_failing_test
_Given buggy code, debug through misleading errors to find real issues_

| Run | Mode | Tokens | Retries | Duration | Pass | Reflex Blocks |
|-----|------|--------|---------|----------|------|---------------|
| 1 | Baseline | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 2 | Baseline | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 3 | Baseline | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 4 | SOMA | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 5 | SOMA | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 6 | SOMA | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 7 | Reflex | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 8 | Reflex | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |
| 9 | Reflex | ERROR: Error code: 400 - {'type': 'error', 'err | - | - | - | - |

## Raw Data

<details>
<summary>Click to expand JSON (for reproducibility)</summary>

```json
{
  "tasks": [
    {
      "task_name": "linked_list_with_bugs",
      "description": "Build linked list, inject bugs via fake error feedback, force retries",
      "baseline_runs": [
        {
          "task_name": "linked_list_with_bugs",
          "soma_enabled": false,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nE9oj3F3SPy6FU4iJa'}"
        },
        {
          "task_name": "linked_list_with_bugs",
          "soma_enabled": false,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEEJbQHMA4wnBJ8GJG'}"
        },
        {
          "task_name": "linked_list_with_bugs",
          "soma_enabled": false,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEJ5oTXjQ6SCmYVrNa'}"
        }
      ],
      "soma_runs": [
        {
          "task_name": "linked_list_with_bugs",
          "soma_enabled": true,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nECAMiLQKY7TXCycDg'}"
        },
        {
          "task_name": "linked_list_with_bugs",
          "soma_enabled": true,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEGfirSV3ViCYQrrNg'}"
        },
        {
          "task_name": "linked_list_with_bugs",
          "soma_enabled": true,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEJkVKzjQpfd1mNsdW'}"
        }
      ],
      "reflex_runs": [
        {
          "task_name": "linked_list_with_bugs",
          "soma_enabled": true,
          "reflex_enabled": true,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nED5g78kmQUxAeE4Bv'}"
        },
        {
          "task_name": "linked_list_with_bugs",
          "soma_enabled": true,
          "reflex_enabled": true,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEHUqTiY3F4kjy6n3K'}"
        },
        {
          "task_name": "linked_list_with_bugs",
          "soma_enabled": true,
          "reflex_enabled": true,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEL2dXn9GPtzVKGXPh'}"
        }
      ]
    },
    {
      "task_name": "debug_failing_test",
      "description": "Given buggy code, debug through misleading errors to find real issues",
      "baseline_runs": [
        {
          "task_name": "debug_failing_test",
          "soma_enabled": false,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nELvThT24QJNnoaRGB'}"
        },
        {
          "task_name": "debug_failing_test",
          "soma_enabled": false,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEPit9wS7zxASrJr2y'}"
        },
        {
          "task_name": "debug_failing_test",
          "soma_enabled": false,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nETJBu4BnABVS7KPoX'}"
        }
      ],
      "soma_runs": [
        {
          "task_name": "debug_failing_test",
          "soma_enabled": true,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEMvjNVMRywufcpdpf'}"
        },
        {
          "task_name": "debug_failing_test",
          "soma_enabled": true,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEQaEWEA68zCpuQ1Et'}"
        },
        {
          "task_name": "debug_failing_test",
          "soma_enabled": true,
          "reflex_enabled": false,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEVE2P9CzBuhui8Mgy'}"
        }
      ],
      "reflex_runs": [
        {
          "task_name": "debug_failing_test",
          "soma_enabled": true,
          "reflex_enabled": true,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nENo5542mdZM39J37n'}"
        },
        {
          "task_name": "debug_failing_test",
          "soma_enabled": true,
          "reflex_enabled": true,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nES3n8uLTsyU9Kbtmf'}"
        },
        {
          "task_name": "debug_failing_test",
          "soma_enabled": true,
          "reflex_enabled": true,
          "steps": [],
          "total_tokens": 0,
          "total_duration": 0.0,
          "final_test_passed": false,
          "total_retries": 0,
          "total_reflex_blocks": 0,
          "error": "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Ca7nEVm2NAY9aTcMLBoKH'}"
        }
      ]
    }
  ],
  "model": "claude-haiku-4-5-20251001",
  "runs_per_task": 3,
  "timestamp": "2026-04-16T16:39:51.189446+00:00",
  "total_cost_estimate": 0.0
}
```

</details>

## Methodology

- Each task ran **3** times with SOMA enabled, **3** times without (baseline)
- Same model, same prompts, same temperature
- Tasks include deliberate error injection to trigger retries
- Pairs with errors on either side excluded from statistical analysis
- **Significance threshold:** α = 0.05 (two-sided)
- **Effect size:** Cohen's d / rank-biserial for continuous; rate difference for binary
- **Confidence intervals:** Bootstrap (5,000 resamples, percentile method)


---

**Kill criteria: FAILED** — no metric shows p < 0.05 improvement. The project approach must be redesigned.

*This report was generated automatically.  SOMA project kill criteria: if no metric shows p < 0.05 improvement, the project approach is considered failed.*