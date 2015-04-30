from celery import Celery
import core.celeryconfig as celeryconfig

app = Celery()
app.config_from_object(celeryconfig)
