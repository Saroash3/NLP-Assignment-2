## Latency benchmark

Run: 2026-10-03 00:21; 25 test questions; warm rows = 3 rounds.

| Retrieval only | samples | avg ms | median ms | p95 ms |
|---|---|---|---|---|
| Cold start: load model + open index (once, at server startup) | 1 | 7683 | – | – |
| Cold: first query after loading | 1 | 60.3 | – | – |
| Warm, cache miss: embed query | 75 | 11.69 | 11.38 | 15.16 |
| Warm, cache miss: vector search | 75 | 2.13 | 2.11 | 2.30 |
| **Warm, cache miss: total retrieval** | 75 | 14.91 | 14.17 | 21.16 |
| **Warm, cache hit** | 75 | 0.03 | 0.02 | 0.04 |

| End-to-end (answerable questions) | samples | avg ms | median ms | p95 ms |
|---|---|---|---|---|
| Retrieval (runs in parallel with the classifier) | 20 | 22.01 | 21.64 | 28.93 |
| Off-topic classifier (LLM call) | 20 | 362.34 | 359.18 | 384.67 |
| **Time to first token** | 20 | 941.33 | 825.17 | 893.27 |
| **Total reply time** | 20 | 1260.30 | 1169.38 | 1617.98 |

Retrieval = **1.9%** of the total reply time on average. It runs in parallel with the classifier (362 ms average), so it adds about 0 ms to the wait for the first token.
