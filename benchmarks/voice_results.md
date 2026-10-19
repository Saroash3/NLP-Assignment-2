# Voice latency benchmark

All times in ms, measured by the server per voice turn (`latency` event). "End of speech" = the moment the VAD decides the member stopped talking, which is 0.5 s of silence after the last word (that hangover is not included).

## 1. One voice user

| User | Question (spoken) | Transcript | Tool | ASR | Retrieval+routing | Tool | LLM 1st token | TTS 1st audio | **End-of-speech → 1st audio** |
|---|---|---|---|---|---|---|---|---|---|
| A | What time does the F-7 branch open? | What time does the F-7 branch open? | - | 164 | 116 | - | 235 | 127 | **812** |
| A | How much protein is in two eggs? | How much protein is in two eggs? | lookup_nutrition | 168 | 289 | 0 | 109 | 79 | **758** |
| A | What is my BMI if I weigh 80 kilos and I am 180 centimetres tall? | What is my BMI if I weigh 80 kilos and I am 180 centimeters tall? | calculate_fitness_metrics | 167 | 364 | 0 | 119 | 56 | **811** |
| A | Add leg day on Monday to my workout schedule. | Add leg day on Monday to my workout schedule. | workout_schedule | 186 | 309 | 1 | 267 | 67 | **932** |
| A | How much is the Elite plan? | How much is the Elite plan? | - | 132 | 106 | - | 229 | 112 | **757** |
| A | Hi, how are you today? | Hi, how are you today? | - | 148 | 100 | - | 93 | 20 | **381** |

End-of-speech → first audio (ms): median **784**, max 932, n=6.

## 2. One voice user + one text user concurrently

| User | Question (spoken) | Transcript | Tool | ASR | Retrieval+routing | Tool | LLM 1st token | TTS 1st audio | **End-of-speech → 1st audio** |
|---|---|---|---|---|---|---|---|---|---|
| A | What time does the F-7 branch open? | What time does the F-7 branch open? | - | 455 | 110 | - | 207 | 98 | **1028** |
| A | How much protein is in two eggs? | How much protein is in two eggs? | lookup_nutrition | 171 | 295 | 0 | 118 | 59 | **734** |
| A | What is my BMI if I weigh 80 kilos and I am 180 centimetres tall? | What is my BMI if I weigh 80 kilos and I am 180 centimeters tall? | calculate_fitness_metrics | 160 | 336 | 0 | 126 | 52 | **769** |
| A | Add leg day on Monday to my workout schedule. | Add leg day on Monday to my workout schedule. | workout_schedule | 162 | 304 | 15 | 253 | 75 | **910** |

End-of-speech → first audio (ms): median **840**, max 1028, n=4.

Text user (same time), time to first token: 279 ms, 272 ms, 301 ms, 453 ms

## 3. Two voice users concurrently

| User | Question (spoken) | Transcript | Tool | ASR | Retrieval+routing | Tool | LLM 1st token | TTS 1st audio | **End-of-speech → 1st audio** |
|---|---|---|---|---|---|---|---|---|---|
| A | What time does the F-7 branch open? | What time does the F-7 branch open? | - | 158 | 120 | - | 539 | 103 | **1233** |
| A | How much protein is in two eggs? | How much protein is in two eggs? | lookup_nutrition | 180 | 784 | 0 | 98 | 66 | **1367** |
| A | What is my BMI if I weigh 80 kilos and I am 180 centimetres tall? | What is my BMI if I weigh 80 kilos and I am 180 centimeters tall? | calculate_fitness_metrics | 169 | 360 | 0 | 147 | 51 | **821** |
| B | Add leg day on Monday to my workout schedule. | Add leg day on Monday to my workout schedule. | workout_schedule | 601 | 305 | 2 | 219 | 24 | **1187** |
| B | How much is the Elite plan? | How much is the Elite plan? | - | 365 | 115 | - | 239 | 128 | **1223** |
| B | Hi, how are you today? | Hi, how are you today? | - | 161 | 220 | - | 114 | 23 | **570** |

End-of-speech → first audio (ms): median **1205**, max 1367, n=6.

