import os

from functools import lru_cache
from kombu import Queue


def route_task(name, args, kwargs, options, task=None, **kw):
	if ":" in name:
		queue, _ = name.split(":")
		return {"queue": queue}
	return {"queue": "celery"}


class CeleryConfig:
	broker_url: str = os.environ.get("broker_url", "amqp://guest:guest@localhost:5672//")
	# result_backend: str = os.environ.get("result_backend", "rpc://")
	# result_backend: str = os.environ.get("result_backend", "db+sqlite:////Library/AutoPkg/PkgBot/db/db.sqlite")
	result_backend: str = os.environ.get("result_backend", "db+sqlite:///db/db.sqlite")

	task_queues: list = (
		# default queue
		Queue("autopkg", queue_arguments={'x-max-priority': 10}),
		# custom queue
		# Queue("run"),
		# Queue("trust"),
	)

	task_routes = (route_task,)

	task_default_priority = 5
	task_queue_max_priority = 10
	task_acks_late = True
	worker_prefetch_multiplier = 1


# class DevelopmentConfig(BaseConfig):
# 	pass


@lru_cache()
def get_settings():
	config_cls_dict = {
		"pkgbot": CeleryConfig,
	}
	config_name = os.environ.get("CELERY_CONFIG", "pkgbot")
	config_cls = config_cls_dict[config_name]
	return config_cls()


settings = get_settings()
