<p align="center">
  <img src="icon.png" alt="Data Validator Logo" width="128" height="128" />
</p>

# Data Validator for VS Code

An AI-powered linter, live verifier, and auto-remediator for data pipelines. Starting with Apache Airflow DAGs, this extension catches structural errors before they are deployed, verifies external references, and suggests one-click AI fixes right in your editor.

---

## Key Features

### 1. Advanced Airflow DAG Analysis
Safely inspects Airflow DAG files natively inside VS Code without executing them. Catches issues like:
*   **Syntax Errors & Imports**: Detects unresolved imports and basic syntax issues.
*   **Structural Integrity**: Finds circular dependencies in your tasks (`>>`).
*   **Deprecation Warnings**: Flags outdated practices like using `schedule_interval` instead of `schedule`.
*   **SQL Lints**: Finds duplicate columns in inline SQL queries using `sqlglot`.

### 2. Live Target Verification (Data Warehouses)
Extracts source tables and columns from the DAG's SQL queries and verifies them against your live databases. 
*   **Supported Warehouses**: Doris, BigQuery, Snowflake.
*   **Fuzzy Matching**: If you misspell a column name, the extension suggests the closest match from the live warehouse.
*   **Airflow API**: Connects to your Airflow REST API to check if referenced connection IDs actually exist in the target environment.

### 3. AI-Powered Auto-Remediation
Powered by Google Gemini (default) or Anthropic Claude. 
*   **Gated Fixes**: When you encounter an error, click "Fix with AI" in the validator dashboard. The AI will stream code fix variants (low, medium, high impact).
*   **Deterministic Safety**: The extension runs the proposed AI changes through the static-check engine in the background. If the AI introduces new errors, the fix is gated to prevent you from applying broken code.

---

## Installation

1. Install the extension from the VS Code Marketplace.
2. Ensure you have **Python 3.10+** installed on your system.
3. Install the required Python backend engine packages in your active environment:
   ```bash
   pip install sqlglot google-generativeai pymysql google-cloud-bigquery snowflake-connector-python
   ```

---

## Configuration

### Setting your AI Provider (Gemini / Claude)
The extension securely stores API keys in your OS keychain.
1. Open the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`).
2. Run **`AI Validator: Set API Key`**.
3. Select your provider (`gemini` or `claude`) and paste your API key.

### Configuring Live Data Connections
To enable live checks against your warehouse or Airflow instance, configure your connections in the VS Code settings.
1. Go to **Settings** (`Ctrl+,`).
2. Search for `AI Validator Connections`.
3. Add a connection profile (e.g., Doris, Snowflake, or Airflow).
4. Run **`AI Validator: Set Connection Password`** from the Command Palette to securely save the password/token for that connection profile.

---

## How to Use

1. **Open a DAG**: Simply open any Python file containing an Airflow DAG. 
2. **View Lints**: You will immediately see inline squiggles for syntax errors, circular dependencies, or deprecated calls. Hover over them for details.
3. **Open Dashboard**: Run **`AI Validator: Open Validator Panel`** from the Command Palette to see a comprehensive overview of all passed and failed checks for your current DAG.
4. **Apply Fixes**: Click **Fix with AI** in the panel to stream structural code fixes directly into the side-by-side diff viewer. You can accept the changes with a single click.

---

## Security & Privacy
*   **Local First**: All static analysis, DAG parsing, and engine rules run entirely locally on your machine via a spawned Python process.
*   **Secure Credentials**: All passwords and API keys are stored securely in the VS Code `SecretStorage` API (backed by Windows Credential Manager, macOS Keychain, or Linux Secret Service).
*   **AI Redaction**: Before sending code to the AI provider, the engine automatically redacts sensitive connection tokens and passwords.
