"""Copy the whole database into a second one (and back, to restore).

Run nightly as a Railway cron service: `flask --app app backup-db` with BACKUP_DATABASE_URL
pointing at a separate Postgres. The copy is a full replacement inside one transaction on the
target, so the backup is always one complete, consistent snapshot of the last run.
"""
import logging

from sqlalchemy import create_engine, func, select, text

from extensions import db

log = logging.getLogger(__name__)

CHUNK = 1000


def normalise_url(url):
    return url.replace('postgres://', 'postgresql://', 1) if url.startswith('postgres://') else url


def copy_database(source_engine, target_engine):
    """Replace everything in the target with the source's rows. Returns {table: row count}."""
    tables = db.metadata.sorted_tables  # parents before children
    counts = {}
    with source_engine.connect() as src, target_engine.begin() as dst:
        # Rebuild the target's tables from the current models, so columns added since the
        # last run exist there too. On Postgres this DDL is part of the same transaction.
        db.metadata.drop_all(dst)
        db.metadata.create_all(dst)
        for table in tables:
            rows = src.execute(select(table).order_by(*table.primary_key.columns)).mappings()
            batch, total = [], 0
            for row in rows:
                batch.append(dict(row))
                if len(batch) >= CHUNK:
                    dst.execute(table.insert(), batch)
                    total += len(batch)
                    batch = []
            if batch:
                dst.execute(table.insert(), batch)
                total += len(batch)
            counts[table.name] = total
        if dst.dialect.name == 'postgresql':
            # Rows were inserted with their ids, so move each id sequence past the highest one.
            for table in tables:
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and pk[0].autoincrement:
                    top = dst.execute(select(func.max(pk[0]))).scalar() or 0
                    dst.execute(text("SELECT setval(pg_get_serial_sequence(:t, :c), :v, :called)"),
                                {'t': table.name, 'c': pk[0].name, 'v': max(top, 1), 'called': top > 0})
    return counts


def backup(source_url, backup_url):
    counts = copy_database(create_engine(normalise_url(source_url)), create_engine(normalise_url(backup_url)))
    log.info('Backup complete: %s', counts)
    return counts
