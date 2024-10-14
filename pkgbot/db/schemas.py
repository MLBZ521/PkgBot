from tortoise.contrib.pydantic import pydantic_model_creator

from pkgbot.db import models

PkgBotAdmin_Out = pydantic_model_creator(models.PkgBotAdmins, name="PkgBotAdmin_Out")
PkgBotAdmin_In = pydantic_model_creator(
	models.PkgBotAdmins, name="PkgBotAdmin_In", exclude_readonly=False)

Recipe_Out = pydantic_model_creator(models.Recipes, name="Recipe_Out")
Recipe_In = pydantic_model_creator(models.Recipes, name="Recipe_In", exclude_readonly=True)

RecipeNote_Out = pydantic_model_creator(models.RecipeNotes, name="RecipeNote_Out")
RecipeNote_In = pydantic_model_creator(models.RecipeNotes, name="RecipeNote_In", exclude_readonly=True)

RecipeResult_Out = pydantic_model_creator(models.RecipeResults, name="RecipeResult_Out")
RecipeResult_In = pydantic_model_creator(
    models.RecipeResults, name="RecipeResult_In", exclude_readonly=True)

Package_Out = pydantic_model_creator(models.Packages, name="Package_Out")
Package_In = pydantic_model_creator(models.Packages, name="Package_In", exclude_readonly=True)

Package_Manual_Out = pydantic_model_creator(models.PackagesManual, name="Package_Manual_Out")
Package_Manual_In = pydantic_model_creator(models.PackagesManual, name="Package_Manual_In", exclude_readonly=True)

PackageNote_Out = pydantic_model_creator(models.PackageNotes, name="PackageNote_Out")
PackageNote_In = pydantic_model_creator(models.PackageNotes, name="PackageNote_In", exclude_readonly=True)

PackageHold_Out = pydantic_model_creator(models.PackageHold, name="PackageHold_Out")
PackageHold_In = pydantic_model_creator(models.PackageHold, name="PackageHold_In", exclude_readonly=True)

Error_Out = pydantic_model_creator(models.Errors, name="Error_Out")
Error_In = pydantic_model_creator(models.Errors, name="Error_In", exclude_readonly=True)

Policy_Out = pydantic_model_creator(models.Policies, name="Policy_Out")
Policy_In = pydantic_model_creator(models.Policies, name="Policy_In", exclude_readonly=True)
