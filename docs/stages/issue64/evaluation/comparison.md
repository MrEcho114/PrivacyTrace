# Controlled comparison

Suite: pt907; truth SHA256: `0beb0e990c27668658c24341978f871082dc53952affcff1b444d7eb864baeb3`.

One target per source scenario; failures and abstentions remain in the denominator.
Status agreement, API mapping/location and DEX processing coverage are separate.

| Scheme | Total | Status agreement | Failures | Abstentions | Mapping/location | Complete DEX | Truncated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| permission_keyword | 12 | 2 | 1 | 0 | 12 | 12 | 0 |
| api_flat | 12 | 4 | 0 | 1 | 12 | 12 | 0 |
| privacytrace | 12 | 12 | 0 | 3 | 12 | 12 | 0 |

| Scenario | Scheme | Expected | Actual | Agreement | Errors |
| --- | --- | --- | --- | --- | --- |
| C01 | permission_keyword | INSUFFICIENT_EVIDENCE | EXACT_MATCH | False |  |
| C01 | api_flat | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | True |  |
| C01 | privacytrace | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | True |  |
| C02 | permission_keyword | EXACT_MATCH | EXACT_MATCH | True |  |
| C02 | api_flat | EXACT_MATCH | EXACT_MATCH | True |  |
| C02 | privacytrace | EXACT_MATCH | EXACT_MATCH | True |  |
| C03 | permission_keyword | CATEGORY_MATCH | NOT_DECLARED | False |  |
| C03 | api_flat | CATEGORY_MATCH | NOT_DECLARED | False |  |
| C03 | privacytrace | CATEGORY_MATCH | CATEGORY_MATCH | True |  |
| C04 | permission_keyword | NOT_DECLARED | NOT_DECLARED | True |  |
| C04 | api_flat | NOT_DECLARED | NOT_DECLARED | True |  |
| C04 | privacytrace | NOT_DECLARED | NOT_DECLARED | True |  |
| C05 | permission_keyword | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | False |  |
| C05 | api_flat | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | False |  |
| C05 | privacytrace | AMBIGUOUS_DISCLOSURE | AMBIGUOUS_DISCLOSURE | True |  |
| C06 | permission_keyword | INSUFFICIENT_EVIDENCE | NOT_DECLARED | False |  |
| C06 | api_flat | INSUFFICIENT_EVIDENCE | NOT_DECLARED | False |  |
| C06 | privacytrace | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | True |  |
| C07 | permission_keyword | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | False |  |
| C07 | api_flat | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | False |  |
| C07 | privacytrace | AMBIGUOUS_DISCLOSURE | AMBIGUOUS_DISCLOSURE | True |  |
| C08 | permission_keyword | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | False |  |
| C08 | api_flat | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | False |  |
| C08 | privacytrace | AMBIGUOUS_DISCLOSURE | AMBIGUOUS_DISCLOSURE | True |  |
| C09 | permission_keyword | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | False |  |
| C09 | api_flat | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | False |  |
| C09 | privacytrace | AMBIGUOUS_DISCLOSURE | AMBIGUOUS_DISCLOSURE | True |  |
| C10 | permission_keyword | INSUFFICIENT_EVIDENCE | NOT_DECLARED | False |  |
| C10 | api_flat | INSUFFICIENT_EVIDENCE | NOT_DECLARED | False |  |
| C10 | privacytrace | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | True |  |
| C11 | permission_keyword | EXACT_MATCH | NOT_DECLARED | False |  |
| C11 | api_flat | EXACT_MATCH | NOT_DECLARED | False |  |
| C11 | privacytrace | EXACT_MATCH | EXACT_MATCH | True |  |
| C12 | permission_keyword | EXACT_MATCH | NO_PREDICTION | False |  |
| C12 | api_flat | EXACT_MATCH | EXACT_MATCH | True |  |
| C12 | privacytrace | EXACT_MATCH | EXACT_MATCH | True |  |

P/R/F1: N/A (no binary runtime collection/legality target). CPU, peak memory and human preparation cost: not measured.

The legacy failures column includes missing target predictions; diagnostics separately count execution failures and successful runs with no target output.

Complete DEX processing does not prove complete behavior coverage. Prediction files retain non-target findings and coverage limitations.
