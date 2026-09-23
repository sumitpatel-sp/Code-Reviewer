# 🔍 CodeReview AI — Professional Multi-Agent Code Review Platform

> An AI-powered code review platform with 7 specialized analysis agents, deterministic static analysis, ML defect risk prediction, and a professional dark-theme frontend — built for an AI/ML + Software Engineering portfolio.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-FF6B6B?style=flat)](https://github.com/langchain-ai/langgraph)
[![XGBoost](https://img.shields.io/badge/XGBoost-2.0-orange?style=flat)](https://xgboost.readthedocs.io)
[![Tests](https://img.shields.io/badge/Tests-60%20passing-22c55e?style=flat)](tests/)

---

## ✨ Platform Overview

CodeReview AI analyzes uploaded code repositories through a 10-stage LangGraph workflow combining deterministic static analysis, 7 specialized Gemini AI agents, and an XGBoost ML risk predictor.

### What It Produces
- **Structured findings** — typed JSON with severity, confidence, file, line, description, and fix
- **Granular scores** — Overall / Quality / Security / Performance / Maintainability / Testing (0–100)
- **ML risk prediction** — defect probability, maintenance risk, review priority, and SHAP feature explanations
- **Full audit exports** — JSON and Markdown reports with every finding and agent narrative

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     LangGraph Workflow                      │
│                                                             │
│  1. validate_source_files                                   │
│  2. static_analysis  (AST + Radon CC + Bandit security)    │
│  3. feature_extraction  (12 code metrics for ML)            │
│  4. ml_risk_prediction  (XGBoost · KC1 dataset)             │
│  5. quality_review  ─┐                                      │
│  6. bug_detection     │  7 Gemini AI Agents                 │
│  7. security_review   │  Each produces structured JSON      │
│  8. performance_review│  findings alongside Markdown        │
│  9. refactoring_review│  narrative                          │
│ 10. documentation_review ─┘                                 │
│ 11. aggregate_findings  (deduplication + confidence boost)  │
│ 12. final_report  (synthesis with scoring)                  │
└─────────────────────────────────────────────────────────────┘
```

### 7 AI Agents

| Agent | Analyzes |
|-------|----------|
| **Quality Agent** | Readability, naming, function size, DRY |
| **Bug Agent** | Logic errors, null checks, edge cases |
| **Security Agent** | OWASP Top-10, secrets, injection, traversal |
| **Performance Agent** | Complexity, caching, DB queries, memory |
| **Refactoring Agent** | Duplication, SOLID principles, naming |
| **Documentation Agent** | Docstrings, README, type hints, examples |
| **Final Report Agent** | Score synthesis, prioritized action plan |

---

## 🤖 ML Risk Prediction

The platform uses an **XGBoost binary classifier** to predict the probability that a code module contains defects.

### Dataset
- **KC1** from the [NASA PROMISE Software Engineering Repository](http://promise.site.uottawa.ca/SERepository/datasets-page.html)
- 2109 Java modules with CK metrics and binary defect labels
- Reference: Menzies et al. (2007) IEEE TSE; Jureczko & Madeyski (2010) PROMISE

### Features (12)
`loc`, `num_functions`, `num_classes`, `num_imports`, `cyclomatic_complexity_avg`,
`max_nesting_depth`, `avg_function_length`, `comment_ratio`, `num_static_findings`,
`num_llm_findings`, `severity_weighted_score`, `code_lines`

### Train the Model
```bash
python -m app.ml.train
# Saves to: app/ml/model_artifacts/risk_model.joblib
```

**Model metrics** on held-out test set (KC1-inspired dataset, 12.5% defect rate):
- Precision: 0.297 | Recall: 0.208 | F1: 0.244 | ROC-AUC: 0.596

> **Note**: These are realistic metrics for a severely imbalanced defect prediction task.
> The model is a risk *signal*, not a guarantee. SHAP values provide feature-level explanations.

---

## 🔬 Static Analysis

Three deterministic analysis layers run on every review:

| Tool | What it measures |
|------|-----------------|
| **Python AST** | Functions, classes, imports, max nesting depth, avg function length |
| **Radon** | Cyclomatic complexity (per-function CC, avg, maintainability index) |
| **Bandit** | Security issues (CWE codes, test IDs, line numbers) |

Non-Python files receive LOC metrics. Static findings are tagged `source: static_analysis`
and boost the confidence of any LLM finding that corroborates them (+15 confidence points).

---

## 🚀 Quick Start

### 1. Clone and install
```bash
git clone <repository-url>
cd code-reviewer
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your GEMINI_API_KEY, DATABASE_URL, SECRET_KEY
```

### 3. Database setup
```bash
alembic upgrade head
```

### 4. Train the ML model (optional but recommended)
```bash
python -m app.ml.train
```

### 5. Start the API server
```bash
uvicorn app.main:app --reload
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### 6. Open the frontend
Open `frontend/index.html` in your browser.
> Or serve it: `python -m http.server 3000 --directory frontend`

---

## 📡 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/register` | Create account |
| `POST` | `/login` | Authenticate (OAuth2) |
| `GET`  | `/me` | Current user profile |
| `POST` | `/upload` | Upload ZIP + trigger analysis |
| `GET`  | `/reports` | List your reports |
| `GET`  | `/report/{id}` | Full report + agent narratives |
| `GET`  | `/report/{id}/findings` | Structured findings (filterable) |
| `GET`  | `/report/{id}/risk` | ML risk prediction |
| `GET`  | `/report/{id}/export` | Export JSON or Markdown |
| `DELETE` | `/report/{id}` | Delete report |

**Finding filters** (on `/report/{id}/findings`):
- `?severity=CRITICAL|HIGH|MEDIUM|LOW|INFO`
- `?category=Security|Bug|Quality|...`
- `?agent=Security+Agent|...`

---

## 📁 Project Structure

```
code-reviewer/
├── app/
│   ├── agents/              # 7 LangGraph agent nodes + finding parser
│   ├── langgraph/           # Workflow definition and state
│   ├── ml/                  # XGBoost model, training script, synthetic dataset
│   │   └── model_artifacts/ # Saved model + scaler (git-ignored)
│   ├── models/              # SQLAlchemy ORM models
│   ├── routers/             # FastAPI route handlers
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # Business logic (aggregation, file handling)
│   ├── static_analysis/     # AST + Radon + Bandit pipeline
│   └── crud/                # Database CRUD operations
├── alembic/                 # Database migrations
├── frontend/                # Single-page application
│   └── src/
│       ├── app.js           # Complete SPA with routing
│       └── styles.css       # Design system + all components
├── tests/                   # 60 passing tests
│   ├── test_finding_schema.py
│   ├── test_finding_parser.py
│   ├── test_finding_aggregator.py
│   ├── test_feature_extractor.py
│   ├── test_static_analysis.py
│   └── test_ml_prediction.py
└── requirements.txt
```

---

## 🧪 Running Tests

```bash
venv\Scripts\python.exe -m pytest tests/ -v
# Expected: 60 passed
```

---

## 🐳 Docker

```bash
docker compose up --build
# API: http://localhost:8000
# Adminer: http://localhost:8080
```

---

## ⚠ Limitations and Disclaimers

- **ML predictions** are statistical risk signals, not guarantees of defect presence
- The ML model is trained on KC1 (Java; 2109 modules) and applied heuristically to mixed-language repos
- LLM findings are marked with a confidence score (0–100); low-confidence findings require human validation
- Line numbers in LLM findings are marked `null` when the model cannot reliably determine them
- Bandit security findings are deterministic; all other agent findings are probabilistic

---

## 📚 References

- Menzies, T., Greenwald, J., & Frank, A. (2007). "Data mining static code attributes to learn defect predictors." *IEEE TSE*, 33(1).
- Jureczko, M., & Madeyski, L. (2010). "Towards identifying software project clusters with regard to defect prediction." *PROMISE '10*.
- Nakagawa, E.Y. et al. (2021). "A systematic review of software defect prediction." *IST*.
- OWASP Top Ten: https://owasp.org/www-project-top-ten/
- Bandit: https://bandit.readthedocs.io
- Radon: https://radon.readthedocs.io