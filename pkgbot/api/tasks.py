from fastapi import APIRouter, Depends

from pkgbot import config, core, settings
from pkgbot.db import schemas
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
router = APIRouter(
	prefix = "/tasks",
	tags = ["tasks"],
	responses = settings.api.custom_responses
)


@router.get("/cache_policies", summary="Adhoc cache policies from Jamf Pro",
	description="Force an adhoc cache of Jamf Pro Policies.",
	dependencies=[Depends(core.user.verify_admin)], response_model=dict)
async def cache_policies(user_object: schemas.PkgBotAdmin_In = Depends(core.user.get_current)):

	queued_task = await core.policy.cache_policies(source="API", called_by=user_object.username)
	return {
		"result": "Caching Policies.  See queued background task id for status.",
		"task_id": queued_task.id
	}


@router.post("/package_cleanup", summary="Build adhoc package cleanup report",
	description="Force an adhoc clean up report of packages in Jamf Pro.",
	dependencies=[Depends(core.user.verify_admin)], response_model=dict)
async def package_cleanup(kwargs: dict | None = None,
	user_object: schemas.PkgBotAdmin_In = Depends(core.user.get_current)):

	package_cleanup_config = config.JamfPro_Prod.Package_Cleanup
	kwargs.setdefault("source", "API")
	kwargs.setdefault("called_by", user_object.username)
	kwargs.setdefault("versions_to_keep", package_cleanup_config.get("versions_to_keep"))
	kwargs.setdefault(
		"maximum_allowed_packages_to_delete",
		package_cleanup_config.get("maximum_allowed_packages_to_delete")
	)
	kwargs.setdefault("dry_run", package_cleanup_config.get("dry_run"))

	queued_task = await core.package.package_cleanup(kwargs)
	return {
		"result": "Building cleanup report.  See queued background task id for status.",
		"task_id": queued_task.id
	}
