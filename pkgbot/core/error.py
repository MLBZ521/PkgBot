from functools import reduce

from pkgbot.db import models


async def create_error(**kwargs: dict):
	# Create DB entry in errors table

	return await models.ErrorMessages.create(**kwargs)


async def construct_error_msg(recipe_id: str, error: str, task_id: str = None):
	# Construct message content

	try:
		error_list = error.split(': ')
		error_dict = reduce(lambda x, y: {y:x}, error_list[::-1])
	except Exception:
		error_dict = { recipe_id: error }

	# Add task_id to error message for easier lookup
	error_dict["Task ID"] = task_id

	return error_dict


async def update_error(filter: dict, updates: dict):

	return await models.ErrorMessages.filter(**filter).update(**updates)
