from fastapi import APIRouter, HTTPException

from app.database.metadata import get_dataset
from app.database.spaces import (
    create_space,
    delete_space,
    get_space,
    get_space_datasets,
    link_dataset,
    list_spaces,
    unlink_dataset,
    update_space,
)
from app.models.schemas import CreateSpaceRequest, UpdateSpaceRequest

router = APIRouter(prefix="/spaces", tags=["spaces"])


@router.post("")
async def create_new_space(request: CreateSpaceRequest):
    space = create_space(name=request.name, description=request.description)
    return space.model_dump()


@router.get("")
async def get_all_spaces():
    spaces = list_spaces()
    return {"spaces": [s.model_dump() for s in spaces]}


@router.get("/{space_id}")
async def get_space_detail(space_id: str):
    space = get_space(space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")

    datasets = get_space_datasets(space_id)

    return {
        **space.model_dump(),
        "datasets": [d.model_dump() for d in datasets],
    }


@router.put("/{space_id}")
async def update_existing_space(space_id: str, request: UpdateSpaceRequest):
    space = update_space(space_id, name=request.name, description=request.description)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")
    return space.model_dump()


@router.delete("/{space_id}")
async def remove_space(space_id: str):
    if not delete_space(space_id):
        raise HTTPException(status_code=404, detail="Space not found")
    return {"status": "deleted", "space_id": space_id}


@router.post("/{space_id}/datasets/{dataset_id}")
async def link_dataset_to_space(space_id: str, dataset_id: str):
    space = get_space(space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")

    dataset = get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not link_dataset(space_id, dataset_id):
        raise HTTPException(status_code=409, detail="Dataset already linked to this space")

    return {"status": "linked", "space_id": space_id, "dataset_id": dataset_id}


@router.delete("/{space_id}/datasets/{dataset_id}")
async def unlink_dataset_from_space(space_id: str, dataset_id: str):
    if not unlink_dataset(space_id, dataset_id):
        raise HTTPException(status_code=404, detail="Dataset not linked to this space")
    return {"status": "unlinked", "space_id": space_id, "dataset_id": dataset_id}
