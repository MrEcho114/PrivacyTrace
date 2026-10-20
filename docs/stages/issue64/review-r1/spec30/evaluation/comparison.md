# Controlled comparison

Suite: spec30; truth SHA256: `9a0a10392d2d052f95e78c69231c27556120c0eff131a403f05d6f5c8cc10c40`.

One target per source scenario; failures and abstentions remain in the denominator.
Shared scanner evidence, scheme-referenced API locators and status agreement are separate. Scheme API locators are N/A when the frozen target has no invoke.

| Scheme | Total | Status agreement | Failures | Abstentions | Shared scanner | Scheme API locators (applicable) | API N/A | Shared policy spans | Complete DEX | Truncated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| permission_keyword | 6 | 2 | 0 | 0 | 6 | 0/5 | 1 | 6 | 6 | 0 |
| api_flat | 6 | 3 | 0 | 1 | 6 | 5/5 | 1 | 6 | 6 | 0 |
| privacytrace | 6 | 6 | 0 | 2 | 6 | 5/5 | 1 | 6 | 6 | 0 |

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

P/R/F1: N/A (no binary runtime collection/legality target). CPU, peak memory and human preparation cost: not measured.

The legacy failures column includes missing target predictions; diagnostics separately count execution failures and successful runs with no target output.

Complete DEX processing does not prove complete behavior coverage. Prediction files retain non-target findings and coverage limitations.
