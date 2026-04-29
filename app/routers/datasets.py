from fastapi import APIRouter, HTTPException

from app.database.metadata import delete_dataset, get_dataset, get_table_schema, list_datasets
from app.chat.suggestions import generate_suggested_questions

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
async def get_datasets():
    datasets = list_datasets()
    return {"datasets": [d.model_dump() for d in datasets]}


@router.get("/{dataset_id}")
async def get_dataset_detail(dataset_id: str):
    dataset = get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    schema_info = get_table_schema(dataset.table_name)
    suggestions = generate_suggested_questions(dataset.column_dictionary, schema_info)

    return {
        **dataset.model_dump(),
        "schema": schema_info,
        "suggested_questions": suggestions,
    }


@router.delete("/{dataset_id}")
async def remove_dataset(dataset_id: str):
    if not delete_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "deleted", "dataset_id": dataset_id}
