import json

from app.database.connection import get_connection, get_read_connection
from app.models.schemas import DatasetMetadata


def save_dataset_metadata(
    dataset_id: str,
    dataset_name: str,
    original_filename: str,
    column_dictionary: dict,
    table_name: str,
    row_count: int,
    business_context: str = "",
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO dataset_metadata (id, dataset_name, original_filename, column_dictionary, business_context, table_name, row_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [dataset_id, dataset_name, original_filename, json.dumps(column_dictionary), business_context, table_name, row_count],
        )
    finally:
        conn.close()


def get_dataset(dataset_id: str) -> DatasetMetadata | None:
    conn = get_read_connection()
    try:
        result = conn.execute(
            "SELECT id, dataset_name, original_filename, column_dictionary, business_context, table_name, row_count, upload_date FROM dataset_metadata WHERE id = ?",
            [dataset_id],
        ).fetchone()

        if result is None:
            return None

        col_dict = result[3]
        if isinstance(col_dict, str):
            col_dict = json.loads(col_dict)

        return DatasetMetadata(
            id=result[0],
            dataset_name=result[1],
            original_filename=result[2],
            column_dictionary=col_dict,
            business_context=result[4] or "",
            table_name=result[5],
            row_count=result[6],
            upload_date=str(result[7]),
        )
    finally:
        conn.close()


def list_datasets() -> list[DatasetMetadata]:
    conn = get_read_connection()
    try:
        results = conn.execute(
            "SELECT id, dataset_name, original_filename, column_dictionary, business_context, table_name, row_count, upload_date FROM dataset_metadata ORDER BY upload_date DESC"
        ).fetchall()

        datasets = []
        for row in results:
            col_dict = row[3]
            if isinstance(col_dict, str):
                col_dict = json.loads(col_dict)

            datasets.append(DatasetMetadata(
                id=row[0],
                dataset_name=row[1],
                original_filename=row[2],
                column_dictionary=col_dict,
                business_context=row[4] or "",
                table_name=row[5],
                row_count=row[6],
                upload_date=str(row[7]),
            ))
        return datasets
    finally:
        conn.close()


def get_table_schema(table_name: str) -> dict[str, str]:
    conn = get_read_connection()
    try:
        columns = conn.execute(f"DESCRIBE {table_name}").fetchall()
        return {col[0]: col[1] for col in columns}
    finally:
        conn.close()


def delete_dataset(dataset_id: str) -> bool:
    meta = get_dataset(dataset_id)
    if meta is None:
        return False

    conn = get_connection()
    try:
        conn.execute(f"DROP TABLE IF EXISTS {meta.table_name}")
        conn.execute("DELETE FROM dataset_metadata WHERE id = ?", [dataset_id])
        return True
    finally:
        conn.close()
