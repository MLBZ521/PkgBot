from celery import current_app as current_celery_app

from pkgbot import settings


def create_celery():
	celery_app = current_celery_app
	celery_app.config_from_object(settings.celery.settings, namespace='CELERY')
	celery_app.conf.update(task_track_started=True)
	celery_app.conf.update(task_serializer='pickle')
	celery_app.conf.update(result_serializer='pickle')
	celery_app.conf.update(accept_content=['pickle', 'json'])
	celery_app.conf.update(result_expires=200)
	celery_app.conf.update(result_persistent=True)
	celery_app.conf.update(worker_send_task_events=False)
	celery_app.conf.update(worker_prefetch_multiplier=1)

	return celery_app


##### This file currently isn't used
