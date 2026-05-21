import pandas as pd
from sqlalchemy import create_engine
import sys
import os
from config import Config
from utils import setup_logger

# Initialize logger
logger = setup_logger(__name__)

def create_database_engine():
    """
    Create a SQLAlchemy engine for connecting to the PostgreSQL database.

    Returns:
        engine: SQLAlchemy engine object.
    """
    try:
        engine = create_engine(Config.DATABASE_URL)
        return engine
    except Exception as e:
        logger.error(f"Error creating database engine: {e}")
        sys.exit(1)

def load_data_to_postgresql(df, table_name="weather_data"):
    """
    Load the DataFrame into a PostgreSQL database table.

    Parameters:
        df (pd.DataFrame): The DataFrame containing the transformed data.
        table_name (str): The name of the table to load the data into.
    """
    engine = create_database_engine()

    try:
        # Load DataFrame into PostgreSQL table
        df.to_sql(table_name, engine, if_exists='replace', index=False)
        logger.info(f"Data loaded into the table {table_name} successfully!")
    except Exception as e:
        logger.error(f"Error loading data to PostgreSQL: {e}")
        sys.exit(1)

def main():
    output_dir = "/tmp" if os.environ.get("VERCEL") else "."
    transformed_path = os.path.join(output_dir, "transformed_weather_data.csv")

    # Load the transformed data from the CSV file
    try:
        df = pd.read_csv(transformed_path)
    except FileNotFoundError:
        logger.error("Error: Transformed data file not found.")
        sys.exit(1)
    except pd.errors.EmptyDataError:
        logger.error("Error: Transformed data file is empty.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading transformed data file: {e}")
        sys.exit(1)

    # Load the data into PostgreSQL
    load_data_to_postgresql(df, table_name="weather_data")

if __name__ == "__main__":
    main()
