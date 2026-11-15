# ML Recommendation Engine - Training & Evaluation Report

**Generated:** 2026-11-15 14:10:09 UTC  
**Selected Best Model:** `RandomForestClassifier` (selected by highest Macro F1)

---

## 1. Executive Summary & Metric Comparison

Both models were trained on the empirical dataset using stratified train/test split (80/20) with fixed random seed 42.

| Metric | RandomForestClassifier | XGBClassifier | Selected (`RandomForestClassifier`) |
|---|---|---|---|
| **Accuracy** | 0.9938 | 0.9938 | 0.9938 |
| **Macro Precision** | 0.9966 | 0.9966 | 0.9966 |
| **Macro Recall** | 0.9846 | 0.9846 | 0.9846 |
| **Macro F1 (Key)** | **0.9904** | **0.9904** | **0.9904** |
| **Top-3 Accuracy** | 1.0000 | 1.0000 | 1.0000 |
| **MRR (Mean Reciprocal Rank)** | 0.9975 | 0.9969 | 0.9975 |

---

## 2. Feature Importances (Ranked)

| Rank | Feature | Importance | Description |
|---|---|---|---|
| 1 | `current_algorithm_code` | 0.3548 | 12-dim FeatureVector field |
| 2 | `lookup_freq_level` | 0.1693 | 12-dim FeatureVector field |
| 3 | `runtime_pct` | 0.1398 | 12-dim FeatureVector field |
| 4 | `current_complexity_rank` | 0.1200 | 12-dim FeatureVector field |
| 5 | `call_count_log10` | 0.0877 | 12-dim FeatureVector field |
| 6 | `input_size_log10` | 0.0816 | 12-dim FeatureVector field |
| 7 | `latency_requirement_level` | 0.0106 | 12-dim FeatureVector field |
| 8 | `read_write_ratio` | 0.0103 | 12-dim FeatureVector field |
| 9 | `data_distribution_code` | 0.0092 | 12-dim FeatureVector field |
| 10 | `insert_ratio` | 0.0081 | 12-dim FeatureVector field |
| 11 | `memory_constraint_level` | 0.0047 | 12-dim FeatureVector field |
| 12 | `delete_ratio` | 0.0038 | 12-dim FeatureVector field |

---

## 3. Detailed Classification Report (Selected Model)

```text
                         precision    recall  f1-score   support

                  deque       1.00      1.00      1.00        70
         hash_map_index       0.99      0.97      0.98        70
               hash_set       1.00      0.92      0.96        26
           keep_current       0.99      1.00      0.99       431
              list_join       1.00      1.00      1.00        70
        memoization_lru       1.00      1.00      1.00        70
min_max_builtin_or_heap       1.00      1.00      1.00        70

               accuracy                           0.99       807
              macro avg       1.00      0.98      0.99       807
           weighted avg       0.99      0.99      0.99       807

```

---

## 4. Model Artifact Details
- **Path:** `backend/ml/models/recommender.joblib`
- **Metadata:** `backend/ml/models/metadata.json`
- **Target Classes (7):** `deque`, `hash_map_index`, `hash_set`, `keep_current`, `list_join`, `memoization_lru`, `min_max_builtin_or_heap`
- **Feature Vector Dimension:** 12 numeric features
- **Fallback Guarantee:** Deterministic rule-based engine when model artifact is missing or low-confidence (< 0.50).
