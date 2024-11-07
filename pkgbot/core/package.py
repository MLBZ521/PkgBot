from pkgbot import core
from pkgbot.db import models, schemas
from pkgbot.tasks import task


async def get(package_filter: dict | None = None):

	if not package_filter:
		return await models.Packages.all()

	results = await schemas.Package_Out.from_queryset(models.Packages.filter(**package_filter))
	return results[0] if len(results) == 1 else results


async def get_note(note_filter: dict | None = None):

	if not note_filter:
		return await models.PackageNotes.all()

	results = await schemas.PackageNote_Out.from_queryset(models.PackageNotes.filter(**note_filter))
	return results[0] if len(results) == 1 else results


async def get_hold(hold_filter: dict | None = None):

	if not hold_filter:
		return await models.PackageHold.all()

	results = await schemas.PackageHold_Out.from_queryset(models.PackageHold.filter(**hold_filter))
	return results[0] if len(results) == 1 else results


async def create(pkg_object: dict):

	return await models.Packages.create(**pkg_object)


async def create_note(pkg_note_object: dict):

	return await models.PackageNotes.create(**pkg_note_object)


async def create_hold(pkg_hold_object: dict):

	return await models.PackageHold.create(**pkg_hold_object)


async def update(package_filter: dict, updates: dict):

	result = await models.Packages.filter(**package_filter).first()
	await (result.update_from_dict(updates)).save()
	return await schemas.Package_Out.from_tortoise_orm(result)


async def delete(package_filter: dict):

	return await models.Packages.filter(**package_filter).delete()


async def promote(id: int, autopkg_cmd: models.AutoPkgCMD | None = None):

	pkg_object = await get({ "id": id })
	recipe = await core.recipe.get({ "recipe_id": pkg_object.recipe.recipe_id })

	if autopkg_cmd is None:
		autopkg_cmd = models.AutoPkgCMD(
			**{
				"verb": "run",
				"promote": True,
				"match_pkg": pkg_object.pkg_name,
				"pkg_id": pkg_object.id
			}
		)
	elif not isinstance(autopkg_cmd, models.AutoPkgCMD):
		autopkg_cmd = models.AutoPkgCMD(
			**autopkg_cmd,
			**{
				"verb": "run",
				"promote": True,
				"match_pkg": pkg_object.pkg_name
			}
		)

	return task.autopkg_verb_parser.apply_async(
		kwargs = {
			"recipes": [ recipe.dict() ],
			"autopkg_cmd": autopkg_cmd.dict(),
			"event_id": pkg_object.id
		},
		queue="autopkg",
		priority=4
	)


async def deny(id: int):

	return await core.chatbot.send.deny_pkg_msg(await update({"id": id}, {"status": "Denied"}))
