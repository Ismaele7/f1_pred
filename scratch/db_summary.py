import sqlite3, pandas as pd
DB = r'C:\Users\grand\Documents\F1_predictions\data\f1.db'
conn = sqlite3.connect(DB)
for tbl in ['sessions', 'qualifying_results', 'race_results']:
    df = pd.read_sql_query(f'SELECT * FROM {tbl}', conn)
    row_count = len(df)
    years = sorted(df['year'].unique())
    min_year = years[0] if years else None
    max_year = years[-1] if years else None
    print(f'Table: {tbl}')
    print(f'Row count: {row_count}')
    print(f'Years present: min={min_year}, max={max_year}, unique={years}')
    print(df.isna().sum())
    print()
conn.close()
