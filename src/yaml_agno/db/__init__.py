"""yaml-agno config-store ORM package (SPEC_03 §3).

Declares the SQLAlchemy 2.0 ``DeclarativeBase`` entities for the ``yamlagno_*``
tables. This slice defines ONLY the ORM models; no engine, session, or DDL is
created here. Downstream SPEC_03 slices (provisioner, repositories, bootstrap)
consume :class:`yaml_agno.db.base.Base` and the record classes.
"""
