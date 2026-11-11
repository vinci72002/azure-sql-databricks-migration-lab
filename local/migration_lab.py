"""Local runnable migration laboratory using SQLite as a SQL source and target.
This is NOT Azure SQL/Databricks and is NOT a 1TB benchmark.
"""
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / 'data'
DATA.mkdir(exist_ok=True)
SOURCE = DATA / 'source.db'
TARGET = DATA / 'target.db'

SRC_DDL = '''
CREATE TABLE IF NOT EXISTS payments (payment_id INTEGER PRIMARY KEY, merchant_id INTEGER NOT NULL, amount_cents INTEGER NOT NULL, status TEXT NOT NULL, updated_seq INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS changes (change_seq INTEGER PRIMARY KEY AUTOINCREMENT, payment_id INTEGER NOT NULL, op TEXT NOT NULL, merchant_id INTEGER, amount_cents INTEGER, status TEXT);
'''
TGT_DDL = '''
CREATE TABLE IF NOT EXISTS payments (payment_id INTEGER PRIMARY KEY, merchant_id INTEGER NOT NULL, amount_cents INTEGER NOT NULL, status TEXT NOT NULL, updated_seq INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS migration_control (name TEXT PRIMARY KEY, last_seq INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS applied_changes (change_seq INTEGER PRIMARY KEY);
'''

def init(rows):
    for db in (SOURCE,TARGET):
        if db.exists(): db.unlink()
    with sqlite3.connect(SOURCE) as c:
        c.executescript(SRC_DDL)
        c.executemany('INSERT INTO payments VALUES (?,?,?,?,?)', ((i, i%37+1, 100+(i*73)%100000, 'COMPLETED' if i%7 else 'PENDING', 0) for i in range(1,rows+1)))
        c.commit()
    with sqlite3.connect(TARGET) as c:
        c.executescript(TGT_DDL)
        c.execute("INSERT INTO migration_control VALUES ('payments',0)")
    print(f'initialized source rows={rows}; sqlite databases in {DATA}')

def snapshot(chunk_size):
    with sqlite3.connect(SOURCE) as s, sqlite3.connect(TARGET) as t:
        s.execute('BEGIN')
        high = s.execute('SELECT COALESCE(MAX(change_seq),0) FROM changes').fetchone()[0]
        total=0
        last=0
        while True:
            rows=s.execute('SELECT payment_id,merchant_id,amount_cents,status,updated_seq FROM payments WHERE payment_id>? ORDER BY payment_id LIMIT ?', (last,chunk_size)).fetchall()
            if not rows: break
            t.executemany('INSERT INTO payments VALUES (?,?,?,?,?) ON CONFLICT(payment_id) DO UPDATE SET merchant_id=excluded.merchant_id, amount_cents=excluded.amount_cents, status=excluded.status, updated_seq=excluded.updated_seq WHERE excluded.updated_seq>=payments.updated_seq',rows)
            last=rows[-1][0]
            total += len(rows)
        t.execute("UPDATE migration_control SET last_seq=? WHERE name='payments'",(high,))
        t.commit()
    print(f'snapshot copied={total}, source change watermark={high}')

def mutate():
    with sqlite3.connect(SOURCE) as c:
        changes=[('UPDATE',1,1,219900,'REFUNDED'),('UPDATE',2,2,10100,'COMPLETED'),('DELETE',3,None,None,None),('INSERT',999999,99,5500,'COMPLETED')]
        for op,pid,merchant,amount,status in changes:
            c.execute('INSERT INTO changes(payment_id,op,merchant_id,amount_cents,status) VALUES (?,?,?,?,?)',(pid,op,merchant,amount,status))
            seq=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            if op=='DELETE': c.execute('DELETE FROM payments WHERE payment_id=?',(pid,))
            else: c.execute('INSERT INTO payments VALUES (?,?,?,?,?) ON CONFLICT(payment_id) DO UPDATE SET merchant_id=excluded.merchant_id, amount_cents=excluded.amount_cents,status=excluded.status,updated_seq=excluded.updated_seq',(pid,merchant,amount,status,seq))
    print('created UPDATE/DELETE/INSERT events in source')

def sync():
    with sqlite3.connect(SOURCE) as s, sqlite3.connect(TARGET) as t:
        last=t.execute("SELECT last_seq FROM migration_control WHERE name='payments'").fetchone()[0]
        changes=s.execute('SELECT change_seq,payment_id,op,merchant_id,amount_cents,status FROM changes WHERE change_seq>? ORDER BY change_seq',(last,)).fetchall()
        for seq,pid,op,merchant,amount,status in changes:
            # Exactly-once effect for sequential replay in this lab (single target transaction).
            if t.execute('SELECT 1 FROM applied_changes WHERE change_seq=?',(seq,)).fetchone(): continue
            if op=='DELETE': t.execute('DELETE FROM payments WHERE payment_id=?',(pid,))
            else:
                t.execute('INSERT INTO payments VALUES (?,?,?,?,?) ON CONFLICT(payment_id) DO UPDATE SET merchant_id=excluded.merchant_id, amount_cents=excluded.amount_cents,status=excluded.status,updated_seq=excluded.updated_seq WHERE excluded.updated_seq>=payments.updated_seq',(pid,merchant,amount,status,seq))
            t.execute('INSERT INTO applied_changes VALUES (?)',(seq,))
            t.execute("UPDATE migration_control SET last_seq=? WHERE name='payments'",(seq,))
        t.commit()
    print(f'applied {len(changes)} change events; safe to rerun')

def verify():
    with sqlite3.connect(SOURCE) as s, sqlite3.connect(TARGET) as t:
        q='SELECT COUNT(*), COALESCE(SUM(amount_cents),0) FROM payments'
        src=s.execute(q).fetchone(); dst=t.execute(q).fetchone()
        missing=s.execute('SELECT payment_id FROM payments EXCEPT SELECT payment_id FROM main.payments LIMIT 1').fetchall() if False else []
        src_rows=s.execute('SELECT * FROM payments ORDER BY payment_id').fetchall()
        dst_rows=t.execute('SELECT * FROM payments ORDER BY payment_id').fetchall()
        exact=(src_rows==dst_rows)
        print(f'source count,sum_cents={src}; target count,sum_cents={dst}; exact_match={exact}')
        if not exact: raise SystemExit('FAIL: reconciliation mismatch')
        print('PASS: 100% exact row reconciliation (local test only)')

def main():
    p=argparse.ArgumentParser(); p.add_argument('command', choices=['init','snapshot','mutate','sync','verify','demo']); p.add_argument('--rows',type=int,default=10000); p.add_argument('--chunk-size',type=int,default=2000)
    args=p.parse_args()
    if args.command=='demo':
        init(args.rows); snapshot(args.chunk_size); verify(); mutate(); sync(); verify(); sync(); verify()
    else: globals()[args.command](args.rows if args.command=='init' else args.chunk_size) if args.command in ('init','snapshot') else globals()[args.command]()
if __name__=='__main__': main()
