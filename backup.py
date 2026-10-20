"""Dated snapshots of the whole database in a second one, and a restore from the newest.

Run nightly as a Railway cron service: `flask --app app backup-db` with BACKUP_DATABASE_URL
pointing at a separate Postgres. Each run writes one snapshot: a copy of every table named
`<table>_YYYYMMDD` (a rerun on the same day replaces that day's copy), plus a row in
`backup_snapshot` that is written last, in the same transaction, and so marks the snapshot
complete. The newest SNAPSHOTS_KEPT complete snapshots are kept and older ones are dropped,
so damage noticed a few days late can still be undone.

The source is read inside one transaction (REPEATABLE READ on Postgres), so every table of a
snapshot shows the database at the same moment.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, MetaData, String, Table, Text, create_engine, func, inspect, select, text,
)

from extensions import db

log = logging.getLogger(__name__)

CHUNK = 1000
SNAPSHOTS_KEPT = 7

catalog = Table(
    'backup_snapshot', MetaData(),
    Column('name', String(8), primary_key=True),  # YYYYMMDD, the suffix of its tables
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('complete', Boolean, nullable=False),
    Column('tables', Text, nullable=False),  # comma-separated table names of the snapshot
)


def normalise_url(url):
    return url.replace('postgres://', 'postgresql://', 1) if url.startswith('postgres://') else url


def snapshot_table(table, suffix, columns=None, metadata=None):
    """A plain copy of a model table under its dated name: columns only, no keys between tables,
    so snapshots never depend on each other or on the order rows are written in."""
    names = None if columns is None else set(columns)
    return Table(
        f'{table.name}_{suffix}', metadata if metadata is not None else MetaData(),
        *[Column(c.name, c.type, primary_key=c.primary_key, autoincrement=False)
          for c in table.columns if names is None or c.name in names],
    )


def copy_rows(src, source_table, dst, target_table):
    """Copy every row the two tables have columns for. Returns the row count."""
    shared = [c.name for c in source_table.columns if c.name in target_table.columns]
    pk = [source_table.c[c.name] for c in target_table.primary_key.columns if c.name in source_table.c]
    rows = src.execute(select(*[source_table.c[n] for n in shared]).order_by(*pk)).mappings()
    batch, total = [], 0
    for row in rows:
        batch.append(dict(row))
        if len(batch) >= CHUNK:
            dst.execute(target_table.insert(), batch)
            total += len(batch)
            batch = []
    if batch:
        dst.execute(target_table.insert(), batch)
        total += len(batch)
    return total


def drop_tables(conn, names):
    quote = conn.dialect.identifier_preparer.quote
    for name in names:
        conn.execute(text(f'DROP TABLE IF EXISTS {quote(name)}'))


def drop_snapshot(conn, name, tables):
    drop_tables(conn, tables)
    conn.execute(catalog.delete().where(catalog.c.name == name))


def snapshot(source_engine, backup_engine, now=None):
    """Write today's snapshot of the source into the backup database. Returns {table: row count}."""
    now = now or datetime.now(timezone.utc)
    suffix = now.strftime('%Y%m%d')
    tables = db.metadata.sorted_tables
    counts = {}
    src = source_engine.connect()
    if src.dialect.name == 'postgresql':
        # One snapshot of the whole database: rows written meanwhile are in no table or in all.
        src = src.execution_options(isolation_level='REPEATABLE READ')
    try:
        with src.begin(), backup_engine.begin() as dst:
            catalog.create(dst, checkfirst=True)
            # A second run on the same day replaces that day's copy.
            existing = dst.execute(select(catalog.c.tables).where(catalog.c.name == suffix)).scalar()
            drop_snapshot(dst, suffix, set((existing or '').split(',') if existing else [])
                          | {f'{t.name}_{suffix}' for t in tables})
            for table in tables:
                copy = snapshot_table(table, suffix)
                copy.create(dst)
                counts[table.name] = copy_rows(src, table, dst, copy)
            # Written last: a snapshot without this row never finished and is never restored.
            dst.execute(catalog.insert(), {
                'name': suffix, 'created_at': now, 'complete': True,
                'tables': ','.join(f'{t.name}_{suffix}' for t in tables),
            })
            prune(dst)
    finally:
        src.close()
    return counts


def prune(conn, keep=SNAPSHOTS_KEPT):
    """Drop all but the newest `keep` complete snapshots."""
    rows = conn.execute(select(catalog.c.name, catalog.c.tables).where(catalog.c.complete.is_(True))
                        .order_by(catalog.c.name.desc())).all()
    for name, tables in rows[keep:]:
        drop_snapshot(conn, name, [t for t in tables.split(',') if t])
        log.info('Dropped backup snapshot %s', name)


def snapshots(backup_engine):
    """Names (YYYYMMDD) of the complete snapshots, newest first."""
    with backup_engine.connect() as conn:
        if not inspect(conn).has_table(catalog.name):
            return []
        return list(conn.execute(select(catalog.c.name).where(catalog.c.complete.is_(True))
                                 .order_by(catalog.c.name.desc())).scalars())


def restore_snapshot(backup_engine, target_engine):
    """Replace the target's rows with the newest complete snapshot. Returns (name, {table: rows}).

    The target's schema is brought up to date first, and only columns both sides have are
    copied, so a snapshot taken before a deploy that added a column still restores (the new
    column gets its default).
    """
    from app import upgrade_schema

    names = snapshots(backup_engine)
    if not names:
        raise RuntimeError('The backup database holds no complete snapshot')
    suffix = names[0]
    db.metadata.create_all(target_engine)
    upgrade_schema(target_engine)
    tables = db.metadata.sorted_tables
    counts = {}
    with backup_engine.connect() as src, target_engine.begin() as dst:
        present = set(inspect(src).get_table_names())
        for table in reversed(tables):  # children before parents
            dst.execute(table.delete())
        for table in tables:
            name = f'{table.name}_{suffix}'
            if name not in present:
                counts[table.name] = 0
                continue
            source_columns = {c['name'] for c in inspect(src).get_columns(name)}
            target_columns = {c['name'] for c in inspect(dst).get_columns(table.name)}
            source = snapshot_table(table, suffix, source_columns & target_columns)
            counts[table.name] = copy_rows(src, source, dst, table)
        if dst.dialect.name == 'postgresql':
            # Rows were inserted with their ids, so move each id sequence past the highest one.
            for table in tables:
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and pk[0].autoincrement:
                    top = dst.execute(select(func.max(pk[0]))).scalar() or 0
                    dst.execute(text("SELECT setval(pg_get_serial_sequence(:t, :c), :v, :called)"),
                                {'t': table.name, 'c': pk[0].name, 'v': max(top, 1), 'called': top > 0})
    return suffix, counts


def backup(source_url, backup_url):
    counts = snapshot(create_engine(normalise_url(source_url)), create_engine(normalise_url(backup_url)))
    log.info('Backup complete: %s', counts)
    return counts


def restore(backup_url, target_url):
    name, counts = restore_snapshot(create_engine(normalise_url(backup_url)), create_engine(normalise_url(target_url)))
    log.info('Restored snapshot %s: %s', name, counts)
    return {'snapshot': name, **counts}
