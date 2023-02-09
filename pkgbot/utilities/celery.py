import asyncio

from celery import current_app as pkgbot_celery_app

from tortoise import Tortoise

from pkgbot import settings


async def create_celery(celery_app=pkgbot_celery_app):

	celery_app.config_from_object(settings.celery.settings)
	celery_app.conf.update(task_acks_late=True)
	celery_app.conf.update(task_default_priority=5)
	celery_app.conf.update(task_queue_max_priority=10)
	# celery_app.conf.update(task_track_started=True)
	# celery_app.conf.update(task_serializer='pickle')
	# celery_app.conf.update(result_serializer='pickle')
	# celery_app.conf.update(accept_content=['pickle', 'json'])
	# celery_app.conf.update(result_persistent=True)
	# celery_app.conf.update(worker_send_task_events=False)

	await Tortoise.init(config=settings.db.TORTOISE_CONFIG)

	return celery_app


celery_app = asyncio.run(create_celery(celery_app=pkgbot_celery_app))
