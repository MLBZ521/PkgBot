from fastapi import APIRouter, Body, Depends, HTTPException, status

from pkgbot import core, settings
from pkgbot.db import models
from pkgbot.utilities import common as utility


log = utility.log

router = APIRouter(
	prefix = "/recipe",
	tags = ["recipe"],
	responses = settings.api.custom_responses
)


@router.get("s/", summary="Get all recipes", description="Get all recipes in the database.",
	dependencies=[Depends(core.user.get_current)], response_model=dict)
async def get_recipes(recipe_filter: models.Recipe_Filter = Depends(models.Recipe_Filter)):

	recipes = await core.recipe.get(recipe_filter.dict(exclude_unset=True, exclude_none=True))
	return { "total": len(recipes), "recipes": recipes }


@router.get("/id/{id}", summary="Get recipe by id", description="Get a recipe by its id.",
	dependencies=[Depends(core.user.get_current)], response_model=models.Recipe_Out)
async def get_by_id(id: int):

	return await core.recipe.get({"id": id})


@router.get("/recipe_id/{recipe_id}", summary="Get recipe by recipe_id",
	description="Get a recipe by its recipe_id.",
	dependencies=[Depends(core.user.get_current)], response_model=models.Recipe_Out)
async def get_by_recipe_id(recipe_id: str):

	if recipe_object := await core.recipe.get({"recipe_id__iexact": recipe_id}):
		return recipe_object

	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown recipe id:  '{recipe_id}'")


@router.post("/", summary="Create a recipe", description="Create a recipe.",
	dependencies=[Depends(core.user.verify_admin)], response_model=models.Recipe_Out)
async def create(recipe_object: models.Recipe_In = Body()):

	return await models.Recipe_Out.from_tortoise_orm(
		await core.recipe.create(recipe_object.dict(exclude_unset=True, exclude_none=True)))


@router.put("/id/{id}", summary="Update recipe by id", description="Update a recipe by id.",
	dependencies=[Depends(core.user.verify_admin)], response_model=models.Recipe_Out)
async def update_by_id(id: int, updates_object: models.Recipe_In = Depends(models.Recipe_In)):

	await core.recipe.update(
		{"id": id},
		updates_object.dict(exclude_unset=True, exclude_none=True)
	)

	return await core.recipe.get({"id": id})


@router.put("/recipe_id/{recipe_id}", summary="Update recipe by recipe_id",
	description="Update a recipe by recipe_id.",
	dependencies=[Depends(core.user.verify_admin)], response_model=models.Recipe_Out)
async def update_by_recipe_id(recipe_id: str,
	updates_object: models.Recipe_In = Depends(models.Recipe_In)):

	if results := await core.recipe.update(
		{"recipe_id__iexact": recipe_id},
		updates_object.dict(exclude_unset=True, exclude_none=True)
	):
		return await core.recipe.get({"recipe_id__iexact": recipe_id})

	raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown recipe id:  '{recipe_id}'")


@router.delete("/id/{id}", summary="Delete recipe by id", description="Delete a recipe by id.",
	dependencies=[Depends(core.user.verify_admin)])
async def delete_by_id(id: int):

	if await core.recipe.delete({"id": id}):
		return { "result":  f"Successfully deleted recipe id:  {id}" }

	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND, detail=f"A recipe does not exist with id:  '{id}'")


@router.delete("/recipe_id/{recipe_id}", summary="Delete recipe by recipe_id",
	description="Delete a recipe by recipe_id.", dependencies=[Depends(core.user.verify_admin)])
async def delete_by_recipe_id(recipe_id: str):

	if await core.recipe.delete({"recipe_id__iexact": recipe_id}):
		return { "result":  f"Successfully deleted recipe id:  {recipe_id}" }

	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown recipe id:  '{recipe_id}'")


@router.post("/error", summary="Handle recipe errors",
	description="This endpoint is called when a recipe errors out during an autopkg run.",
	dependencies=[Depends(core.user.verify_admin)])
async def recipe_error(recipe_id: str, error: str, task_id: str = None):

	return await core.recipe.error(recipe_id, error, task_id)


@router.post("/trust/deny", summary="Do not approve trust changes",
	description="This endpoint will update that database to show that the "
		"changes to parent recipe(s) were not approved.",
	dependencies=[Depends(core.user.verify_admin)])
async def recipe_trust_deny(trust_object_id: int):

	return await core.recipe.deny_trust(trust_object_id)


@router.post("/trust/update/success", summary="Trust info was updated successfully",
	description="Performs the necessary actions after trust info was successfully updated.",
	dependencies=[Depends(core.user.verify_admin)])
async def recipe_trust_update_success(trust_id: int):

	return await core.recipe.update_trust_result(True, trust_id)


@router.post("/trust/update/failed", summary="Failed to update recipe trust info",
	description="Performs the necessary actions after trust info failed to update.",
	dependencies=[Depends(core.user.verify_admin)])
async def recipe_trust_update_failed(trust_id: int, msg: str):

	return await core.recipe.update_trust_result(False, trust_id, msg)


@router.post("/trust/verify/failed", summary="Parent trust info has changed",
	description="Performs the necessary actions after parent recipe trust info has changed.",
	dependencies=[Depends(core.user.verify_admin)])
async def recipe_trust_verify_failed(recipe_id: str, diff_msg: str = Body()):
	""" When `autopkg verify-trust-info <recipe_id>` fails """

	return await core.recipe.verify_trust_failed(recipe_id, diff_msg)
