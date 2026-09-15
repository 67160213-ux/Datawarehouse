from pathlib import Path
import sqlite3
import pandas as pd
ROOT=Path(__file__).resolve().parent
with sqlite3.connect((ROOT/'data'/'warehouse.db').as_uri()+'?mode=ro',uri=True) as con:
    df=pd.read_sql_query('SELECT * FROM sales',con)
print(df.head())
# TODO P1: province x month, sum(amount), fill_value=0, margins=True
pivot_p1 = df.pivot_table(index='province', columns='month', values='amount', aggfunc='sum', fill_value=0, margins=True, margins_name='Total')
pivot_p1.to_csv('pivot_province_month.csv')
# TODO P2: filter September, then category x province
df_sep = df[df['month'] == '2026-09']
pivot_p2 = df_sep.pivot_table(index='category', columns='province', values='amount', aggfunc='sum', fill_value=0)
pivot_p2.to_csv('pivot_september.csv')
# TODO P3: assert that the pivot grand total equals df['amount'].sum()
assert pivot_p1.loc['Total', 'Total'] == df['amount'].sum()
# TODO P4: export each result to CSV in your submission folder
