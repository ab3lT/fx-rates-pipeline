"""FX rates ETL pipeline.

A small, production-shaped pipeline that ingests foreign exchange rates from a
public API (or a CSV file), validates and transforms them, runs data quality
checks, and loads the result into a relational database.
"""

__version__ = "0.1.0"
