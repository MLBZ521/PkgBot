#!/usr/local/autopkg/python

from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from tortoise.contrib.fastapi import HTTPNotFoundError

import utils
from db import models
from api import user, settings


log = utils.log

router = APIRouter(
	prefix = "/package",
	tags = ["package"],
	responses = settings.custom_responses
)


@router.get("/", summary="Get all packages", description="Get all packages in the database.", 
	dependencies=[Depends(user.get_current_user)])
async def get_packages():

	packages = await models.Package_Out.from_queryset(models.Packages.all())

	return { "total": len(packages), "packages": packages }


@router.get("/id/{id}", summary="Get package by id", description="Get a package by its id.", 
	dependencies=[Depends(user.get_current_user)], response_model=models.Package_Out)
async def get_package_by_id(id: int):

	pkg_object = await models.Package_Out.from_queryset_single(models.Packages.get(id=id))

	return pkg_object


@router.post("/", summary="Create a package", description="Create a package.", 
	dependencies=[Depends(user.verify_admin)], response_model=models.Package_Out)
async def create(pkg_object: models.Package_In = Depends(models.Package_In)):

	created_pkg = await models.Packages.create(**pkg_object.dict(exclude_unset=True, exclude_none=True))

	return await models.Package_Out.from_tortoise_orm(created_pkg)


@router.put("/id/{id}", summary="Update package by id", description="Update a package by id.", 
	dependencies=[Depends(user.verify_admin)], response_model=models.Package_Out)
async def update(id: int, pkg_object: models.Package_In = Depends(models.Package_In)):

	if type(pkg_object) != dict:
		pkg_object = pkg_object.dict(exclude_unset=True, exclude_none=True)

	await models.Packages.filter(id=id).update(**pkg_object)

	return await models.Package_Out.from_queryset_single(models.Packages.get(id=id))


@router.delete("/id/{id}", summary="Delete package by id", description="Delete a package by id.", 
	dependencies=[Depends(user.verify_admin)])
async def delete_package_by_id(id: int):

	delete_object = await models.Packages.filter(id=id).delete()

	if not delete_object:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package does not exist.")

	else:
		return { "result":  "Successfully deleted package id:  {}".format(id) }
