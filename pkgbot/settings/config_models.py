from pydantic import BaseModel
from typing import Dict, List, Optional


class AutoPkg(BaseModel):
	binary: Optional[str] = "/usr/local/bin/autopkg"
	UseTrustInfo: bool
	recipe_overrides: Optional[str]
	cache_volume: str
	minimum_free_space: int
	warning_free_space: int
	recipe_config: Optional[str]
	public_repo_list: Optional[str]


class Celery(BaseModel):
  broker_url: str
  result_expires: int


class Database(BaseModel):
	location: str


class JamfPro_Dev(BaseModel):
	autopkg_prefs: str
	jps_url: str
	verify_ssl: bool
	api_user: str
	api_password: str
	dp1_name: Optional[str]
	dp1_user: Optional[str]
	dp1_password: Optional[str]


class Package_Cleanup(BaseModel):
	versions_to_keep: int
	maximum_allowed_packages_to_delete: int
	dry_run: bool


class JamfPro_Prod(BaseModel):
	autopkg_prefs: str
	jps_url: str
	verify_ssl: bool
	api_user: str
	api_password: str
	dp1_name: Optional[str]
	dp1_user: Optional[str]
	dp1_password: Optional[str]
	recipe_template: str
	recipe_template_pkg_only: str
	unauthorized_sites: str | List[str]
	Package_Cleanup: Dict
	# Package_Cleanup: {
	# 	versions_to_keep: int,
	# 	maximum_allowed_packages_to_delete: int,
	# 	dry_run: bool
	# }


class Git(BaseModel):
	binary: Optional[str] = "/usr/bin/git"
	user_name: str
	user_email: str
	private_repo: Optional[str]
	local_repo_dir: str
	repo_primary_branch: str
	repo_push_branch: str
	ssh_config: str
	ssh_known_hosts: str
	ssh_private_key: str


class Services(BaseModel):
	pkgbot_LaunchDaemon_label: Optional[str]
	autopkg_service_start_interval: int
	execute_autopkg_run_on_start: bool


class Slack(BaseModel):
	signing_secret: str
	bot_token: str
	bot_name: str
	slack_id: str
	channel: str
	test_channel: str
	slash_cmds_enabled: bool
	shortcuts_enabled: bool


class PkgBot(BaseModel):
	enable_ssl: bool
	host: str
	ip: str
	port: int
	ssl_keyfile: str
	ssl_certfile: str
	keep_alive: bool
	Admins: Dict
	icon_denied: str
	icon_error: str
	icon_permission_denied: str
	icon_warning: str
	webhook_secret: str
	jinja_templates: str
	jinja_static: str
	token_valid_for: int
	uvicorn_log_level: str
	log_config: Dict
		# version: 1
		# disable_existing_loggers: false
		# formatters:
		#     default:
		#         (): 'uvicorn.logging.DefaultFormatter'
		#         fmt: '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
		#     debug:
		#         (): 'uvicorn.logging.DefaultFormatter'
		#         fmt: '%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)s - %(funcName)20s() | %(message)s'
		#     access:
		#         (): 'uvicorn.logging.AccessFormatter'
		#         fmt: '%(asctime)s | %(name)s | %(levelname)s | %(client_addr)s - "%(request_line)s" %(status_code)s'
		# handlers:
		#     default:
		#         formatter: default
		#         class: logging.handlers.RotatingFileHandler
		#         maxBytes: 10485760 # 10MB
		#         backupCount: 20
		#         encoding: utf8
		#         filename: /Library/AutoPkg/PkgBot/logs/PkgBotServer.log
		#         level: INFO
		#     debugging:
		#         formatter: debug
		#         class: logging.handlers.RotatingFileHandler
		#         maxBytes: 10485760 # 10MB
		#         backupCount: 20
		#         encoding: utf8
		#         filename: /Library/AutoPkg/PkgBot/logs/PkgBotServer.debug.log
		#         level: DEBUG
		#     access:
		#         formatter: access
		#         class: logging.handlers.RotatingFileHandler
		#         maxBytes: 10485760 # 10MB
		#         backupCount: 20
		#         encoding: utf8
		#         filename: /Library/AutoPkg/PkgBot/logs/PkgBotServer.HTTP.Access.log
		# loggers:
		#     uvicorn.debug:
		#         level: DEBUG
		#         handlers:
		#         - debugging
		#     uvicorn.error:
		#         level: ERROR
		#         handlers:
		#         - default
		#     uvicorn.access:
		#         level: INFO
		#         propagate: false
		#         handlers:
		#         - access
		#     PkgBot:
		#         level: DEBUG
		#         handlers:
		#         - default
		#         - debugging


class Common(BaseModel):
	redaction_strings: str
	additional_sensitive_key_names: str
	timezone: str
