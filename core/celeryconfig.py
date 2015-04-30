BROKER_URL = 'amqp://guest:guest@localhost:5672//'
CELERY_RESULT_BACKEND = 'amqp://guest:guest@localhost:5672//'
CELERY_TASK_SERIALIZER = 'json'
CELERY_IMPORTS=['apple.tasks',]
CELERY_CREATE_MISSING_QUEUES = True

try:
	from core.local_celeryconfig import *
except:
	pass