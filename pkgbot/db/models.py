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
	icon = fields.CharField(1024, null=True)
	packaged_date = fields.DatetimeField(auto_now_add=True)
	promoted_date = fields.DatetimeField(null=True, default=None)
	last_update = fields.DatetimeField(auto_now=True)
	status = fields.CharField(64, default="dev")
	updated_by = fields.CharField(64, default="PkgBot")
	special_flags = fields.JSONField(null=True)
	notes = fields.CharField(4096, null=True)
	slack_channel = fields.CharField(32, null=True)
	slack_ts = fields.CharField(32, null=True)
	response_url = fields.CharField(1024, null=True)

Package_Out = pydantic_model_creator(Packages, name="Package_Out")
Package_In = pydantic_model_creator(Packages, name="Package_In", exclude_readonly=True)


class Recipes(Model):
	id = fields.IntField(pk=True)
	recipe_id = fields.CharField(512, unique=True)
	enabled = fields.BooleanField(default=True)
	manual_only = fields.BooleanField(default=False)
	pkg_only = fields.BooleanField(default=False)
	last_ran = fields.DatetimeField(null=True, default=None)
	recurring_fail_count = fields.IntField(null=True, default=0)
	schedule = fields.IntField(default=0)
	notes = fields.CharField(4096, null=True)

Recipe_Out = pydantic_model_creator(Recipes, name="Recipe_Out")
Recipe_In = pydantic_model_creator(Recipes, name="Recipe_In", exclude_readonly=True)
# Recipe_Filter = pydantic_model_creator(
# 	Recipes, name="Recipe_Filter", exclude_readonly=True, 
# 	exclude=('id', "recipe_id", "name", "last_ran", "notes"), 
# 	optional=( "enabled", "manual_only", "pkg_only", "recurring_fail_count", "schedule"))

class Recipe_Filter(BaseModel):
	enabled: bool | None = None
	manual_only: bool | None = None
	pkg_only: bool | None = None
	recurring_fail_count: int | None = None
	schedule: int | None = None


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
	type = fields.CharField(64, default="error")
	status = fields.CharField(64, null=True)
	last_update = fields.DatetimeField(auto_now=True)
	ack_by = fields.CharField(64)
	slack_ts = fields.CharField(32, null=True)
	slack_channel = fields.CharField(32, null=True)
	response_url = fields.CharField(1024, null=True)

ErrorMessage_Out = pydantic_model_creator(ErrorMessages, name="ErrorMessage_Out")
ErrorMessage_In = pydantic_model_creator(
	ErrorMessages, name="ErrorMessage_In", exclude_readonly=True)


class TrustUpdates(Model):
	id = fields.IntField(pk=True)
	recipe_id = fields.CharField(1024)
	status = fields.CharField(64, null=True)
	updated_by = fields.CharField(64, default="PkgBot")
	last_update = fields.DatetimeField(auto_now=True)
	slack_channel = fields.CharField(32, null=True)
	slack_ts = fields.CharField(32, null=True)
	response_url = fields.CharField(1024, null=True)

TrustUpdate_Out = pydantic_model_creator(TrustUpdates, name="TrustUpdate_Out")
TrustUpdate_In = pydantic_model_creator(
	TrustUpdates, name="TrustUpdate_In", exclude_readonly=True)


##### May make this a Tortoise Model, to support tracking who/what generated each command
class AutoPkgCMD(BaseModel):
	ignore_parent_trust: bool = False
	match_pkg: str | None = None
	overrides: str | None = None
	pkg_only: bool = False
	promote: bool = False
	quiet: bool = True
	verbose: str = "vvv"


# Not currently used
class AutoPkgTaskResults(BaseModel):
	event: str
	event_id: str = ""
	recipe_id: str
	success: str
	stdout: str
	stderr: str
