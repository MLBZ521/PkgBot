from functools import reduce

from pkgbot.db import models, schemas


async def create(error_object: dict):
	# Create DB entry in errors table

	return await models.Errors.create(**error_object)


async def update(error_filter: dict, updates: dict):

	result = await models.Errors.filter(**error_filter).first()
	await (result.update_from_dict(updates)).save()
	return await schemas.Error_Out.from_tortoise_orm(result)


async def construct_msg(recipe_id: str, error: str, task_id: str = None):
	# Construct message content

	try:
		error_list = error.split(': ')
		error_dict = reduce(lambda x, y: {y:x}, error_list[::-1])
	except Exception:
		error_dict = { recipe_id: error }

	# Add task_id to error message for easier lookup
	error_dict["Task ID"] = task_id

	return error_dict
