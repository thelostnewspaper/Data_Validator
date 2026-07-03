"""
Test fixtures — sample DAG files for testing.

Provides both valid and invalid DAGs covering all 13 check rules.
"""

import sys
import os

# Add the project root to sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ---------------------------------------------------------------------------
# Valid DAG — all checks should pass
# ---------------------------------------------------------------------------

VALID_DAG = '''
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
}

with DAG(
    'valid_test_dag',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
) as dag:

    def my_function():
        print("Hello")

    task1 = PythonOperator(
        task_id='extract_data',
        python_callable=my_function,
    )

    task2 = BashOperator(
        task_id='transform_data',
        bash_command='echo "transform"',
    )

    task3 = PythonOperator(
        task_id='load_data',
        python_callable=my_function,
    )

    task1 >> task2 >> task3
'''


# ---------------------------------------------------------------------------
# Syntax error DAG (AFW001)
# ---------------------------------------------------------------------------

SYNTAX_ERROR_DAG = '''
from airflow import DAG

def my_function(
    print("missing closing paren"
'''


# ---------------------------------------------------------------------------
# Variable typo DAG (AFW002)
# ---------------------------------------------------------------------------

VARIABLE_TYPO_DAG = '''
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

defdefault_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'typo_dag',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
) as dag:

    task1 = PythonOperator(
        task_id='task1',
        python_callable=lambda: None,
    )
'''


# ---------------------------------------------------------------------------
# Missing DAG definition (AFW003)
# ---------------------------------------------------------------------------

NO_DAG_DEFINITION = '''
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    'owner': 'airflow',
}

# No DAG() or with DAG() call
task1 = PythonOperator(
    task_id='orphan_task',
    python_callable=lambda: None,
)
'''


# ---------------------------------------------------------------------------
# Unused operator import (AFW004)
# ---------------------------------------------------------------------------

UNUSED_IMPORT_DAG = '''
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.email import EmailOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'unused_import_dag',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
) as dag:

    task1 = PythonOperator(
        task_id='only_task',
        python_callable=lambda: None,
    )
'''


# ---------------------------------------------------------------------------
# Duplicate task IDs (AFW005)
# ---------------------------------------------------------------------------

DUPLICATE_TASK_ID_DAG = '''
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'dup_task_dag',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
) as dag:

    task1 = PythonOperator(
        task_id='extract',
        python_callable=lambda: None,
    )

    task2 = PythonOperator(
        task_id='extract',
        python_callable=lambda: None,
    )
'''


# ---------------------------------------------------------------------------
# Circular dependencies (AFW010)
# ---------------------------------------------------------------------------

CIRCULAR_DEP_DAG = '''
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'circular_dag',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
) as dag:

    task1 = PythonOperator(
        task_id='task_a',
        python_callable=lambda: None,
    )

    task2 = PythonOperator(
        task_id='task_b',
        python_callable=lambda: None,
    )

    task3 = PythonOperator(
        task_id='task_c',
        python_callable=lambda: None,
    )

    task1 >> task2 >> task3 >> task1
'''


# ---------------------------------------------------------------------------
# Missing start_date (AFW012)
# ---------------------------------------------------------------------------

MISSING_START_DATE_DAG = '''
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    'owner': 'airflow',
}

with DAG(
    'no_start_date_dag',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
) as dag:

    task1 = PythonOperator(
        task_id='task1',
        python_callable=lambda: None,
    )
'''


# ---------------------------------------------------------------------------
# Deprecated schedule_interval (AFW009)
# ---------------------------------------------------------------------------

DEPRECATED_SCHEDULE_DAG = '''
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'deprecated_schedule_dag',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False,
) as dag:

    task1 = PythonOperator(
        task_id='task1',
        python_callable=lambda: None,
    )
'''


# ---------------------------------------------------------------------------
# Missing catchup (AFW011)
# ---------------------------------------------------------------------------

MISSING_CATCHUP_DAG = '''
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'no_catchup_dag',
    default_args=default_args,
    schedule='@daily',
) as dag:

    task1 = PythonOperator(
        task_id='task1',
        python_callable=lambda: None,
    )
'''


# ---------------------------------------------------------------------------
# SQL with duplicate columns (AFW007)
# ---------------------------------------------------------------------------

SQL_DUPLICATE_COLUMNS_DAG = '''
from datetime import datetime
from airflow import DAG
from airflow.providers.mysql.operators.mysql import MySqlOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'sql_dup_dag',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
) as dag:

    task1 = MySqlOperator(
        task_id='run_query',
        sql="SELECT id, name, email, name, status FROM users",
        mysql_conn_id='my_db',
    )
'''


# ---------------------------------------------------------------------------
# Top-level code (AFW013)
# ---------------------------------------------------------------------------

TOP_LEVEL_CODE_DAG = '''
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

print("This runs on every scheduler parse!")

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    'top_level_dag',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
) as dag:

    task1 = PythonOperator(
        task_id='task1',
        python_callable=lambda: None,
    )
'''


# ---------------------------------------------------------------------------
# Non-Airflow Python file (should not be detected as a DAG)
# ---------------------------------------------------------------------------

NON_AIRFLOW_FILE = '''
import os
import sys

def main():
    print("This is not an Airflow DAG")

if __name__ == "__main__":
    main()
'''
