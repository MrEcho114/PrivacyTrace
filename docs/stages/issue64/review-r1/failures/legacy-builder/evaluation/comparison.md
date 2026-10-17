# Controlled comparison

Suite: pt907; truth SHA256: `0beb0e990c27668658c24341978f871082dc53952affcff1b444d7eb864baeb3`.

One target per source scenario; failures and abstentions remain in the denominator.
Shared scanner evidence, scheme-referenced API locators and status agreement are separate. Scheme API locators are N/A when the frozen target has no invoke.

| Scheme | Total | Status agreement | Failures | Abstentions | Shared scanner | Scheme API locators (applicable) | API N/A | Shared policy spans | Complete DEX | Truncated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| permission_keyword | 12 | 0 | 12 | 0 | 0 | 0/11 | 1 | 0 | 0 | 0 |
| api_flat | 12 | 0 | 12 | 0 | 0 | 0/11 | 1 | 0 | 0 | 0 |
| privacytrace | 12 | 0 | 12 | 0 | 0 | 0/11 | 1 | 0 | 0 | 0 |

| Scenario | Scheme | Expected | Actual | Agreement | Errors |
| --- | --- | --- | --- | --- | --- |
| C01 | permission_keyword | INSUFFICIENT_EVIDENCE | NO_PREDICTION | False | BUILD_A_FAILED |
| C01 | api_flat | INSUFFICIENT_EVIDENCE | NO_PREDICTION | False | BUILD_A_FAILED |
| C01 | privacytrace | INSUFFICIENT_EVIDENCE | NO_PREDICTION | False | BUILD_A_FAILED |
| C02 | permission_keyword | EXACT_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C02 | api_flat | EXACT_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C02 | privacytrace | EXACT_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C03 | permission_keyword | CATEGORY_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C03 | api_flat | CATEGORY_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C03 | privacytrace | CATEGORY_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C04 | permission_keyword | NOT_DECLARED | NO_PREDICTION | False | BUILD_A_FAILED |
| C04 | api_flat | NOT_DECLARED | NO_PREDICTION | False | BUILD_A_FAILED |
| C04 | privacytrace | NOT_DECLARED | NO_PREDICTION | False | BUILD_A_FAILED |
| C05 | permission_keyword | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C05 | api_flat | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C05 | privacytrace | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C06 | permission_keyword | INSUFFICIENT_EVIDENCE | NO_PREDICTION | False | BUILD_A_FAILED |
| C06 | api_flat | INSUFFICIENT_EVIDENCE | NO_PREDICTION | False | BUILD_A_FAILED |
| C06 | privacytrace | INSUFFICIENT_EVIDENCE | NO_PREDICTION | False | BUILD_A_FAILED |
| C07 | permission_keyword | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C07 | api_flat | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C07 | privacytrace | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C08 | permission_keyword | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C08 | api_flat | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C08 | privacytrace | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C09 | permission_keyword | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C09 | api_flat | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C09 | privacytrace | AMBIGUOUS_DISCLOSURE | NO_PREDICTION | False | BUILD_A_FAILED |
| C10 | permission_keyword | INSUFFICIENT_EVIDENCE | NO_PREDICTION | False | BUILD_A_FAILED |
| C10 | api_flat | INSUFFICIENT_EVIDENCE | NO_PREDICTION | False | BUILD_A_FAILED |
| C10 | privacytrace | INSUFFICIENT_EVIDENCE | NO_PREDICTION | False | BUILD_A_FAILED |
| C11 | permission_keyword | EXACT_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C11 | api_flat | EXACT_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C11 | privacytrace | EXACT_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C12 | permission_keyword | EXACT_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C12 | api_flat | EXACT_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |
| C12 | privacytrace | EXACT_MATCH | NO_PREDICTION | False | BUILD_A_FAILED |

P/R/F1: N/A (no binary runtime collection/legality target). CPU, peak memory and human preparation cost: not measured.

The legacy failures column includes missing target predictions; diagnostics separately count execution failures and successful runs with no target output.

Complete DEX processing does not prove complete behavior coverage. Prediction files retain non-target findings and coverage limitations.
