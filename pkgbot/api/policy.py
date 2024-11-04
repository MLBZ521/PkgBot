from fastapi import APIRouter, Depends, HTTPException, status

from pkgbot import core, settings
from pkgbot.db import schemas
from pkgbot.utilities import common as utility


log = utility.log

router = APIRouter(
	prefix = "/policy",
	tags = ["policy"],
	responses = settings.api.custom_responses
)


@router.get("/", summary="Get all policies", description="Get all policies in the database.",
	dependencies=[Depends(core.user.get_current)], response_model=dict)
async def get_policies():

	policies = await core.policy.get()
	return { "total": len(policies), "policies": policies }


@router.get("/id/{id}", summary="Get policy by id", description="Get a policy by its id.",
	dependencies=[Depends(core.user.get_current)], response_model=schemas.Policy_Out)
async def get_by_id(id: int):

	if policy_object := await core.policy.get({"id": id}):
		return policy_object

	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown policy id:  '{id}'")


@router.delete("/id/{id}", summary="Delete policy by id", description="Delete a policy by id.",
	dependencies=[Depends(core.user.verify_admin)])
async def delete_by_id(id: int):

	if await core.policy.delete({"id": id}):
		return { "result":  f"Successfully deleted policy id:  {id}" }

	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND, detail=f"A policy does not exist with id:  '{id}'")


@router.get("/policy_id/{policy_id}", summary="Get policy by policy_id",
	description="Get a policy by its policy_id.",
	dependencies=[Depends(core.user.get_current)], response_model=schemas.Policy_Out)
async def get_by_policy_id(policy_id: str):

	if policy_object := await core.policy.get({"policy_id__iexact": policy_id}):
		return policy_object

	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown Jamf Pro Policy ID:  '{policy_id}'")


@router.delete("/policy_id/{policy_id}", summary="Delete policy by policy_id",
	description="Delete a policy by policy_id.", dependencies=[Depends(core.user.verify_admin)])
async def delete_by_policy_id(policy_id: str):

	if await core.policy.delete({"policy_id__iexact": policy_id}):
		return { "result":  f"Successfully deleted Jamf Pro Policy ID:  {policy_id}" }

	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown Jamf Pro Policy ID:  '{policy_id}'")


@router.get("/cache_policies", summary="Adhoc policy cache",
	description="Force an adhoc cache of Jamf Pro Policies.",
	dependencies=[Depends(core.user.get_current)], response_model=dict)
async def cache_policies():

	await core.policy.cache_policies()
	return { "result": "Caching Policies..." }
