from fastapi import APIRouter, Depends, HTTPException, status

from pkgbot import core, settings
from pkgbot.db import models


router = APIRouter(
	prefix = "/package",
	tags = ["package"],
	responses = settings.api.custom_responses
)


@router.get("/", summary="Get all packages", description="Get all packages in the database.",
	dependencies=[Depends(core.user.get_current)], response_model=dict)
async def get_packages():

	packages = await models.Package_Out.from_queryset(core.package.get())
	return { "total": len(packages), "packages": packages }


@router.get("/id/{id}", summary="Get package by id", description="Get a package by its id.",
	dependencies=[Depends(core.user.get_current)], response_model=models.Package_Out)
async def get_package_by_id(id: int):

	return await core.package.get({"id": id})


@router.post("/", summary="Create a package", description="Create a package.",
	dependencies=[Depends(core.user.verify_admin)], response_model=models.Package_Out)
async def create(pkg_object: models.Package_In = Depends(models.Package_In)):

	return await models.Package_Out.from_tortoise_orm(
		await core.package.create(pkg_object.dict(exclude_unset=True, exclude_none=True)))


@router.put("/id/{id}", summary="Update package by id", description="Update a package by id.",
	dependencies=[Depends(core.user.verify_admin)], response_model=models.Package_Out)
async def update(id: int, pkg_object: models.Package_In = Depends(models.Package_In)):

	await core.package.update(
		{"id": id},
		pkg_object.dict(exclude_unset=True, exclude_none=True)
	)

	return await core.package.get({"id": id})


@router.delete("/id/{id}", summary="Delete package by id", description="Delete a package by id.",
	dependencies=[Depends(core.user.verify_admin)])
async def delete_package_by_id(id: int):

	if await core.package.delete({"id": id}):
		return { "result":  f"Successfully deleted package id:  {id}" }

	raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package does not exist.")


@router.post("/promote", summary="Promote package to production",
	description="Promote a package to production by id.",
	dependencies=[Depends(core.user.verify_admin)])
async def promote_package(
	id: int, autopkg_cmd: models.AutoPkgCMD | None = Depends(models.AutoPkgCMD)):

	queued_task = await core.package.promote(id, autopkg_cmd)
	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/deny", summary="Do not promote package to production",
	description="Performs the necessary actions when a package is not approved to production use.",
	dependencies=[Depends(core.user.verify_admin)])
async def deny_package(id: int = Depends(core.package.get)):

	return await core.package.deny(id)
