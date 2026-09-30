## Latency benchmark

Run: 2026-10-01 00:44; 25 test questions; warm rows = 3 rounds.

| Retrieval only | samples | avg ms | median ms | p95 ms |
|---|---|---|---|---|
| Cold start: load model + open index (once, at server startup) | 1 | 8112 | – | – |
| Cold: first query after loading | 1 | 34.1 | – | – |
| Warm, cache miss: embed query | 75 | 7.40 | 7.59 | 8.53 |
| Warm, cache miss: vector search | 75 | 1.91 | 1.93 | 2.17 |
| **Warm, cache miss: total retrieval** | 75 | 9.38 | 9.57 | 10.44 |
| **Warm, cache hit** | 75 | 0.04 | 0.03 | 0.05 |

| End-to-end (answerable questions) | samples | avg ms | median ms | p95 ms |
|---|---|---|---|---|
| Retrieval (runs in parallel with the classifier) | 20 | 9.93 | 9.91 | 11.63 |
| Off-topic classifier (LLM call) | 20 | 354.32 | 345.12 | 352.99 |
| **Time to first token** | 20 | 931.93 | 806.67 | 837.51 |
| **Total reply time** | 20 | 1303.82 | 1117.70 | 1514.82 |

Retrieval = **0.8%** of the total reply time on average. It runs in parallel with the classifier (354 ms average), so it adds about 0 ms to the wait for the first token.
