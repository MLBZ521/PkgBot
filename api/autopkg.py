#!/usr/local/autopkg/python

from datetime import datetime

from fastapi import APIRouter, Body, Depends

import config, utils
from db import models
from api import package, settings, user
from api.slack import send_msg
from execute import recipe_manager, recipe_runner


config.load()
log = utils.log
router = APIRouter(
	prefix = "/autopkg",
	tags = ["autopkg"],
	dependencies = [Depends(user.verify_admin)],
	responses = settings.custom_responses
)


@router.post("/workflow/dev", summary="Dev Workflow", 
	description="The Dev workflow will create a new package and post to chat.")
async def dev(pkg_object: models.Package_In = Body(..., pkg_object=Depends(models.Package_In))):
	"""Workflow to create a new package in the database and then post a message to chat.

	Args:
		pkg_object (models.Package_In): Details about a package object

	Returns:
		[JSON]: Result of the operation
	"""

	created_pkg = await package.create(pkg_object)
	results = await send_msg.new_pkg_msg(created_pkg)
	pkg_db_object = await models.Packages.filter(id=created_pkg.id).first()
	pkg_db_object.slack_ts = results.get('ts')
	pkg_db_object.slack_channel = results.get('channel')
	await pkg_db_object.save()

	# Update the "Last Ran" attribute for this recipe
	recipe_object = await models.Recipes.filter(recipe_id=pkg_db_object.recipe_id).first()
	recipe_object.last_ran = pkg_db_object.packaged_date
	await recipe_object.save()

	return { "Result": "Success" }


@router.post("/workflow/prod", summary="Production Workflow", 
	description="Workflow to move a package into production and update the Slack message.")
async def prod(pkg_object: models.Package_In = Body(..., pkg_object=Depends(models.Package_In))):

	if pkg_object.promoted_date is None:
		date_to_convert = datetime.now()

	else:
		date_to_convert = pkg_object.promoted_date
		
	pkg_object.promoted_date = await utils.utc_to_local(date_to_convert)

	pkg_object.status = "prod"

	packages = await models.Package_Out.from_queryset(
		models.Packages.filter(recipe_id=pkg_object.recipe_id, version=pkg_object.version))

	updated_pkg_object = await package.update(packages[-1].id, pkg_object)

	# try:
	results = await send_msg.promote_msg(updated_pkg_object)
	return { "Result": "Success" }

	# except:
	#     return { "statuscode": 400, "Result": "Failed to post message" }


@router.post("/workflow/promote", summary="Promote package to production", 
description="Promote a package to production by id.")
async def promote_package(background_tasks, id: int = Depends(package.get_package_by_id)):

	pkg_object = await package.get_package_by_id(id)

	background_tasks.add_task( 
		recipe_runner.main,
		[
			"run",
			"--action", "promote",
			"--environment", "prod",
			"--recipe-identifier", pkg_object.dict().get("recipe_id"),
			"--pkg-name", "{}".format(pkg_object.dict().get("pkg_name"))
		] 
	)

	return { "Result": "Queued background task..." }


@router.post("/workflow/deny", summary="Do not promote package to production", 
	description="Performs the necessary actions when a package is not approved to production use.")
async def deny_package(background_tasks, id: int = Depends(package.get_package_by_id)):

	pkg_object = await package.get_package_by_id(id)

	background_tasks.add_task( 
		recipe_manager.main,
		[
			"single",
			"--recipe-identifier", pkg_object.dict().get("recipe_id"),
			"--disable",
			"--force"
		] 
	)

	await send_msg.deny_pkg_msg(pkg_object)
