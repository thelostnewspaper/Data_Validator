# AI Validator VS Code Extension

An AI-powered linter and validator platform for data pipelines with pluggable rule packs, starting with **Airflow DAGs**. It runs entirely locally via a Python child process, performing static analysis, deterministic refactoring, target warehouse checks, and gated AI remediation.

## Key Features

1. **Flagship Airflow Pack (Universal)**: Safely inspects Airflow DAG files via Python AST parser without executing them. Catches 13 check types (e.g., syntax errors, circular dependencies, duplicate column queries, `schedule_interval` deprecations).
2. **Live Target Schema Checks**: Extracts source tables/columns from the DAG's own SQL queries. Uses lightweight database connectors (Doris, BigQuery, Snowflake) to verify column existence, offering fuzzy renaming suggestions.
3. **Airflow Connection Verification**: Connects to the Airflow REST API to check if referenced connection IDs (e.g. `mysql_conn_id`) are present in the target environment.
4. **Secure Credentials**: All passwords and API keys are stored securely in the host operating system's keychain via the VS Code `SecretStorage` API.
5. **Gated AI Remediation**: Streams three code fix variants (low, medium, high impact) using Claude. The engine validates each variant against a static-check gate to prevent the model from introducing new errors.

---

## How to Run End-to-End

### 1. Requirements
- VS Code / Antigravity editor.
- **Node.js** (v18+) & **npm** for bundling the extension host.
- **Python** (3.10+) with required libs:
  ```bash
  pip install sqlglot
  # Optional: for AI fixes & live checks:
  pip install anthropic pymysql google-cloud-bigquery snowflake-connector-python
  ```

### 2. Launching in Debug Mode
1. Open the project root folder in VS Code.
2. Open the **Run and Debug** view (`Ctrl+Shift+D` / `Cmd+Shift+D`).
3. Select **Run Extension** and press **F5** (or click the green arrow).
4. A new window (Extension Development Host) will open.

### 3. Testing the Extension
1. In the new window, open any Python file containing an Airflow DAG import.
2. You will immediately see inline squiggles (diagnostics) for any syntax errors, circular dependencies, or deprecated calls.
3. Hover over a squiggle to view suggestions, or click the lightbulb (Quick Fix) to auto-apply deterministic renames.
4. Run the command `AI Validator: Open Validator Panel` (via Command Palette `Ctrl+Shift+P` / `Cmd+Shift+P`) to open the interactive dashboard.
5. Click **Fix with AI** in the panel to stream structural code fixes directly into the side-by-side diff viewer.

---

## Running Engine Tests

To run the unit tests for the Python engine, connectors, and AI remediator:

```bash
# Register Pytest and run tests
pip install pytest
python -m pytest engine/tests/ -v
```

All 76 tests will run and mock out live databases/APIs to verify rules, parsers, and connection handling.
