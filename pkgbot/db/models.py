import asyncio

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, validator
from tortoise import fields
from tortoise.models import Model

from pkgbot import config
from pkgbot.utilities import common as utility


config = config.load_config()


class PkgBotAdmins(Model):
	username = fields.CharField(max_length=64, pk=True, unique=True, generated=False)
	slack_id = fields.CharField(max_length=64, unique=True, null=True)
	full_admin = fields.BooleanField(default=False)
	pkgbot_token = fields.CharField(max_length=1024, unique=True, null=True)
	jps_token = fields.CharField(max_length=1024, unique=True, null=True)
	jps_token_expires = fields.DatetimeField(default=None, null=True)
	site_access = fields.CharField(max_length=1024, null=True)
	last_update = fields.DatetimeField(auto_now=True, null=True)

	class Meta:
		table = "pkgbot_admins"


class Recipes(Model):
	id = fields.IntField(pk=True)
	recipe_id = fields.CharField(max_length=512, unique=True)
	packages: fields.ReverseRelation["Packages"]
	enabled = fields.BooleanField(default=True)
	manual_only = fields.BooleanField(default=False)
	pkg_only = fields.BooleanField(default=False)
	last_ran = fields.DatetimeField(null=True, default=None)
	recurring_fail_count = fields.IntField(null=True, default=0)
	schedule = fields.IntField(default=0)

	class Meta:
		table = "recipes"


class Recipe_Filter(BaseModel):
	enabled: Optional[bool]
	manual_only: Optional[bool]
	pkg_only: Optional[bool]
	recurring_fail_count: Optional[int]
	schedule: Optional[int]


class RecipeNotes(Model):
	id = fields.IntField(pk=True)
	note = fields.CharField(max_length=4096, default="", null=True)
	submitted_by = fields.CharField(max_length=64)
	time_stamp = fields.DatetimeField(auto_now_add=True)
	recipe: fields.ForeignKeyRelation["Recipes"] = fields.ForeignKeyField(
		model_name = "pkgbot.Recipes",
		related_name = "notes",
		on_delete = fields.CASCADE,
		to_field = "recipe_id"
	)

	class Meta:
		table = "recipe_notes"


class RecipeResults(Model):
	id = fields.IntField(pk=True)
	type = fields.CharField(max_length=64)
	status = fields.CharField(max_length=64, null=True)
	last_update = fields.DatetimeField(auto_now=True)
	updated_by = fields.CharField(max_length=64, default=config.Slack.get('bot_name'))
	slack_ts = fields.CharField(max_length=32, null=True)
	slack_channel = fields.CharField(max_length=32, null=True)
	response_url = fields.CharField(max_length=1024, null=True)
	task_id = fields.CharField(max_length=36, null=True)
	details = fields.CharField(max_length=4096)
	recipe: fields.ForeignKeyRelation["Recipes"] = fields.ForeignKeyField(
		model_name = "pkgbot.Recipes",
		related_name = "results",
		on_delete = fields.CASCADE,
		to_field = "recipe_id"
	)

	class Meta:
		table = "recipe_results"


class Packages(Model):
	id = fields.IntField(pk=True)
	name = fields.CharField(max_length=64)
	version = fields.CharField(max_length=64)
	pkg_name = fields.CharField(max_length=256, null=True, unique=True)
	icon = fields.CharField(max_length=1024, null=True)
	packaged_date = fields.DatetimeField(auto_now_add=True)
	promoted_date = fields.DatetimeField(null=True, default=None)
	last_update = fields.DatetimeField(auto_now=True)
	status = fields.CharField(max_length=64, default="dev")
	updated_by = fields.CharField(max_length=64, default=config.Slack.get('bot_name'))
	slack_channel = fields.CharField(max_length=32, null=True)
	slack_ts = fields.CharField(max_length=32, null=True)
	response_url = fields.CharField(max_length=1024, null=True)
	policies: fields.ManyToManyRelation["Policies"] = fields.ManyToManyField(
		model_name = "pkgbot.Policies",
		through = "pkgs_in_policies",
		related_name = "packages",
		null = True,
		on_delete = fields.SET_NULL,
		create_unique_index = False
	)
	recipe: fields.ForeignKeyRelation["Recipes"] = fields.ForeignKeyField(
		model_name = "pkgbot.Recipes",
		related_name = "recipe",
		null = True,
		on_delete = fields.SET_NULL,
		to_field = "recipe_id"
	)

	class Meta:
		table = "packages"


class PackageNotes(Model):
	id = fields.IntField(pk=True)
	note = fields.CharField(max_length=4096, default="", null=True)
	package = fields.ForeignKeyField(
		model_name = "pkgbot.Packages",
		related_name = "notes",
		on_delete = fields.CASCADE,
		to_field = "pkg_name"
	)
	submitted_by = fields.CharField(max_length=64)
	time_stamp = fields.DatetimeField(auto_now_add=True)

	class Meta:
		table = "package_notes"


class PackageHold(Model):
	id = fields.IntField(pk=True)
	enabled = fields.BooleanField()
	package = fields.ForeignKeyField(
		model_name = "pkgbot.Packages",
		related_name = "holds",
		on_delete = fields.CASCADE,
		to_field = "pkg_name"
	)
	site = fields.CharField(max_length=128)
	submitted_by = fields.CharField(max_length=64)
	time_stamp = fields.DatetimeField(auto_now=True)

	class Meta:
		table = "package_holds"


class PackagesManual(Model):
	id = fields.IntField(pk=True)
	name = fields.CharField(max_length=64)
	version = fields.CharField(max_length=64)
	pkg_name = fields.CharField(max_length=256, null=True, unique=True)
	status = fields.CharField(max_length=64, default="dev")
	policies: fields.ManyToManyRelation["Policies"] = fields.ManyToManyField(
		model_name = "pkgbot.Policies",
		through = "manual_pkgs_in_policies",
		related_name = "packages_manual",
		null = True,
		on_delete = fields.SET_NULL,
		create_unique_index = False
	)

	class Meta:
		table = "packages_manual"


class Errors(Model):
	id = fields.IntField(pk=True)
	type = fields.CharField(max_length=64, default="error")
	status = fields.CharField(max_length=64, null=True)
	last_update = fields.DatetimeField(auto_now=True)
	updated_by = fields.CharField(max_length=64, null=True)
	slack_ts = fields.CharField(max_length=32, null=True)
	slack_channel = fields.CharField(max_length=32, null=True)
	response_url = fields.CharField(max_length=1024, null=True)
	task_id = fields.CharField(max_length=36, null=True)
	details = fields.CharField(max_length=4096)

	class Meta:
		table = "errors"


class Policies(Model):
	id = fields.IntField(pk=True)
	policy_id = fields.IntField(unique=True)
	name = fields.CharField(max_length=256)
	site = fields.CharField(max_length=128)

	class Meta:
		table = "policies"


class CallBack(BaseModel):
	egress: Optional[str]
	ingress: Literal["Schedule", "API", "Slack"] = "Schedule"
	channel: Optional[str]
	start: datetime = asyncio.run(utility.get_timestamp())
	completed: Optional[datetime]

	@validator('ingress')
	def prevent_none(cls, v, values):
		match v:
			case "Slack":
				assert "egress" in values and values["egress"] is not None, 'egress may not be None'
			case "Schedule":
				values["egress"] == "PkgBot"
			case "API":
				values["egress"] == "API"
		return v


##### May make this a Tortoise Model, to support tracking who/what generated each command
class AutoPkgCMD(CallBack):
	verb: Literal["help", "disable", "enable", "repo-add", "run",
		"update-trust-info", "verify-trust-info", "version"]
	ignore_parent_trust: bool = False
	overrides: Optional[str]
	pkg_only: bool = False
	quiet: bool = True
	verbose: str = "vvv"

	match_pkg: Optional[str]
	promote: bool = False

	@validator('promote')
	def prevent_none(cls, v, values):
		if v == "promote" and "egress" in values:
			assert "match_pkg" in values and values["match_pkg"] is not None, 'match_pkg may not be None'
		return v


class AutoPkgCMD_Run(AutoPkgCMD):
	verb: Literal["run"] = "run"


class AutoPkgCMD_UpdateTrustInfo(AutoPkgCMD):
	verb: Literal["update-trust-info"] = "update-trust-info"


class AutoPkgCMD_VerifyTrustInfo(AutoPkgCMD):
	verb: Literal["verify-trust-info"] = "verify-trust-info"


class AutoPkgCMD_RepoAdd(AutoPkgCMD):
	verb: Literal["repo-add"] = "repo-add"


class AutoPkgCMD_Version(AutoPkgCMD):
	verb: Literal["version"] = "version"


# Not currently used
class TaskResults(BaseModel):
	event: str
	event_id: str = ""
	recipe_id: str
	success: str
	stdout: str
	stderr: str
