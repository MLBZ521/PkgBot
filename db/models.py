from pydantic import BaseModel
from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class Packages(Model):
	id = fields.IntField(pk=True)
	recipe_id = fields.CharField(1024)
	name = fields.CharField(64)
	version = fields.CharField(64)
	pkg_name = fields.CharField(256, null=True)
	# jps_url = fields.CharField(64, null=True)
	# icon_id = fields.CharField(64, null=True)
	icon = fields.CharField(1024)
	# jps_id_dev = fields.IntField(unique=True, null=True)
	# jps_id_prod = fields.IntField(unique=True, null=True)
	packaged_date = fields.DatetimeField(auto_now_add=True)
	promoted_date = fields.DatetimeField(null=True, default=None)
	last_update = fields.DatetimeField(auto_now=True)
	status = fields.CharField(64, default="dev")
	status_updated_by = fields.CharField(64, default="PkgBot")
	used_in_common = fields.BooleanField(default=False)
	special_flags = fields.CharField(64, null=True)
	notes = fields.CharField(4096, null=True)
	slack_ts = fields.CharField(32, null=True)
	slack_channel = fields.CharField(32, null=True)
	response_url = fields.CharField(1024, null=True)

Package_Out = pydantic_model_creator(Packages, name="Package_Out")
Package_In = pydantic_model_creator(Packages, name="Package_In", exclude_readonly=True)


class Recipes(Model):
	id = fields.IntField(pk=True)
	recipe_id = fields.CharField(512, unique=True)
	name = fields.CharField(64)
	enabled = fields.BooleanField(default=True)
	manual_only = fields.BooleanField(default=False)
	pkg_only = fields.BooleanField(default=False)
	last_ran = fields.DatetimeField(null=True, default=None)
	schedule = fields.IntField(default=0)
	notes = fields.CharField(4096, null=True)

Recipe_Out = pydantic_model_creator(Recipes, name="Recipe_Out")
Recipe_In = pydantic_model_creator(Recipes, name="Recipe_In", exclude_readonly=True)


class PkgBotAdmins(Model):
	username = fields.CharField(64, pk=True, unique=True, generated=False)
	slack_id = fields.CharField(64, unique=True, null=True)
	full_admin = fields.BooleanField(default=False)
	jps_token = fields.CharField(1024, unique=True, null=True)
	jps_token_expires = fields.DatetimeField(default=None, null=True)
	site_access = fields.CharField(1024, null=True)
	last_update = fields.DatetimeField(auto_now=True, null=True)

PkgBotAdmin_Out = pydantic_model_creator(PkgBotAdmins, name="PkgBotAdmin_Out")
PkgBotAdmin_In = pydantic_model_creator(
	PkgBotAdmins, name="PkgBotAdmin_In", exclude_readonly=False)


class ErrorMessages(Model):
	id = fields.IntField(pk=True)
	recipe_id = fields.CharField(1024)
	slack_ts = fields.CharField(32, null=True)
	slack_channel = fields.CharField(32, null=True)
	response_url = fields.CharField(1024, null=True)
	status_updated_by = fields.CharField(64, default="PkgBot")
	last_update = fields.DatetimeField(auto_now=True)
	status = fields.CharField(64, null=True)

ErrorMessage_Out = pydantic_model_creator(ErrorMessages, name="ErrorMessage_Out")
ErrorMessage_In = pydantic_model_creator(
	ErrorMessages, name="ErrorMessage_In", exclude_readonly=True)


class TrustUpdates(Model):
	id = fields.IntField(pk=True)
	recipe_id = fields.CharField(1024)
	slack_ts = fields.CharField(32, null=True)
	slack_channel = fields.CharField(32, null=True)
	response_url = fields.CharField(1024, null=True)
	status_updated_by = fields.CharField(64, default="PkgBot")
	last_update = fields.DatetimeField(auto_now=True)
	status = fields.CharField(64, null=True)

TrustUpdate_Out = pydantic_model_creator(TrustUpdates, name="TrustUpdate_Out")
TrustUpdate_In = pydantic_model_creator(
	TrustUpdates, name="TrustUpdate_In", exclude_readonly=True)


##### May make this a Tortoise Model, to support tracking who/what generated each command
class AutopkgCMD(BaseModel):
	ignore_parent_trust: bool = False
	match_pkg: str | None = None
	pkg_only: bool = False
	prefs: str | None = None
	promote: bool = False
	# recipe_id: str
	verbose: str = "v"


class AutoPkgTaskResults(BaseModel):
	event: str
	event_id: str = ""
	recipe_id: str
	success: str
	stdout: str
	stderr: str
