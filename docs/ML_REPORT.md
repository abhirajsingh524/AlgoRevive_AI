# ML Recommendation Engine - Training & Evaluation Report

**Generated:** 2026-11-16 02:59:39 UTC  
**Selected Best Model:** `RandomForestClassifier` (selected by highest Macro F1)

---

## 1. Executive Summary & Metric Comparison

Both models were trained on the empirical dataset using stratified train/test split (80/20) with fixed random seed 42.

| Metric | RandomForestClassifier | XGBClassifier | Selected (`RandomForestClassifier`) |
|---|---|---|---|
| **Accuracy** | 1.0000 | 1.0000 | 1.0000 |
| **Macro Precision** | 1.0000 | 1.0000 | 1.0000 |
| **Macro Recall** | 1.0000 | 1.0000 | 1.0000 |
| **Macro F1 (Key)** | **1.0000** | **1.0000** | **1.0000** |
| **Top-3 Accuracy** | 1.0000 | 1.0000 | 1.0000 |
| **MRR (Mean Reciprocal Rank)** | 1.0000 | 1.0000 | 1.0000 |

---

## 2. Feature Importances (Ranked)

| Rank | Feature | Importance | Description |
|---|---|---|---|
| 1 | `current_algorithm_code` | 0.4331 | 12-dim FeatureVector field |
| 2 | `input_size_log10` | 0.1489 | 12-dim FeatureVector field |
| 3 | `current_complexity_rank` | 0.0999 | 12-dim FeatureVector field |
| 4 | `runtime_pct` | 0.0959 | 12-dim FeatureVector field |
| 5 | `call_count_log10` | 0.0859 | 12-dim FeatureVector field |
| 6 | `lookup_freq_level` | 0.0661 | 12-dim FeatureVector field |
| 7 | `read_write_ratio` | 0.0223 | 12-dim FeatureVector field |
| 8 | `insert_ratio` | 0.0165 | 12-dim FeatureVector field |
| 9 | `latency_requirement_level` | 0.0101 | 12-dim FeatureVector field |
| 10 | `delete_ratio` | 0.0098 | 12-dim FeatureVector field |
| 11 | `data_distribution_code` | 0.0059 | 12-dim FeatureVector field |
| 12 | `memory_constraint_level` | 0.0057 | 12-dim FeatureVector field |

---

## 3. Detailed Classification Report (Selected Model)

```text
                         precision    recall  f1-score   support

                  deque       1.00      1.00      1.00        93
         hash_map_index       1.00      1.00      1.00        70
               hash_set       1.00      1.00      1.00        27
           keep_current       1.00      1.00      1.00       359
              list_join       1.00      1.00      1.00        94
        memoization_lru       1.00      1.00      1.00        94
min_max_builtin_or_heap       1.00      1.00      1.00        70

               accuracy                           1.00       807
              macro avg       1.00      1.00      1.00       807
           weighted avg       1.00      1.00      1.00       807

```

---

## 4. Model Artifact Details
- **Path:** `backend/ml/models/recommender.joblib`
- **Metadata:** `backend/ml/models/metadata.json`
- **Target Classes (7):** `deque`, `hash_map_index`, `hash_set`, `keep_current`, `list_join`, `memoization_lru`, `min_max_builtin_or_heap`
- **Feature Vector Dimension:** 12 numeric features
- **Fallback Guarantee:** Deterministic rule-based engine when model artifact is missing or low-confidence (< 0.50).
