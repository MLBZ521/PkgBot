from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from tortoise.contrib.fastapi import HTTPNotFoundError

from pkgbot import api, settings
from pkgbot.db import models
from pkgbot.utilities import common as utility
from pkgbot.tasks import task


log = utility.log

router = APIRouter(
	prefix = "/package",
	tags = ["package"],
	responses = settings.api.custom_responses
)


@router.get("/", summary="Get all packages", description="Get all packages in the database.",
	dependencies=[Depends(api.user.get_current_user)], response_model=dict)
async def get_packages():

	packages = await models.Package_Out.from_queryset(models.Packages.all())

	return { "total": len(packages), "packages": packages }


@router.get("/id/{id}", summary="Get package by id", description="Get a package by its id.",
	dependencies=[Depends(api.user.get_current_user)], response_model=models.Package_Out)
async def get_package_by_id(id: int):

	pkg_object = await models.Package_Out.from_queryset_single(models.Packages.get(id=id))

	return pkg_object


@router.post("/", summary="Create a package", description="Create a package.",
	dependencies=[Depends(api.user.verify_admin)], response_model=models.Package_Out)
async def create(pkg_object: models.Package_In = Depends(models.Package_In)):

	created_pkg = await models.Packages.create(**pkg_object.dict(exclude_unset=True, exclude_none=True))

	return await models.Package_Out.from_tortoise_orm(created_pkg)


@router.put("/id/{id}", summary="Update package by id", description="Update a package by id.",
	dependencies=[Depends(api.user.verify_admin)], response_model=models.Package_Out)
async def update(id: int, pkg_object: models.Package_In = Depends(models.Package_In)):

	if type(pkg_object) != dict:
		pkg_object = pkg_object.dict(exclude_unset=True, exclude_none=True)

	await models.Packages.filter(id=id).update(**pkg_object)

	return await models.Package_Out.from_queryset_single(models.Packages.get(id=id))


@router.delete("/id/{id}", summary="Delete package by id", description="Delete a package by id.",
	dependencies=[Depends(api.user.verify_admin)])
async def delete_package_by_id(id: int):

	delete_object = await models.Packages.filter(id=id).delete()

	if not delete_object:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package does not exist.")

	else:
		return { "result":  f"Successfully deleted package id:  {id}" }


@router.post("/promote", summary="Promote package to production",
description="Promote a package to production by id.", dependencies=[Depends(api.user.verify_admin)])
async def promote_package(id: int):

	pkg_object = await get_package_by_id(id)

	recipe = await api.recipe.get_by_recipe_id(pkg_object.recipe_id)

	switches = {
		"promote": True,
		"match_pkg": pkg_object.dict().get("pkg_name"),
		"pkg_id": pkg_object.dict().get("id")
	}

	queued_task = task.autopkg_run.apply_async(([recipe.dict()], switches, "slack"), queue='autopkg', priority=6)

	return { "Result": "Queued background task..." , "task_id": queued_task.id }


@router.post("/deny", summary="Do not promote package to production",
	description="Performs the necessary actions when a package is not approved to production use.",
	dependencies=[Depends(api.user.verify_admin)])
async def deny_package(id: int = Depends(get_package_by_id)):

	# pkg_object = await package.get_package_by_id(id)

	# background_tasks.add_task(
	# 	recipe_manager.main,
	# 	[
	# 		"single",
	# 		"--recipe-identifier", pkg_object.dict().get("recipe_id"),
	# 		"--disable",
	# 		"--force"
	# 	]
	# )

	pkg_object = await models.Packages.filter(id=id).first()
	pkg_object.status = "Denied"
	pkg_object.save()

	return await api.send_msg.deny_pkg_msg(pkg_object)
