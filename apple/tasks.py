import uuid
import graypy
import requests

from celery import Task
from raven import Client
from celery.utils.log import get_task_logger

from core import settings
from apple import appstore
from core.celery import app
from core.db import appbuy, redis


logger = get_task_logger(__name__)

client = Client(settings.SENTRY_DSN)

handler = graypy.GELFHandler(settings.LOGSTASH_GELF_HOST, settings.LOGSTASH_GELF_PORT)
logger.addHandler(handler)


class AppBuyTask(Task):
    abstract = True

    _appstore = None
    _itunes_account = None
    _token = None
    _user_id = None

    @property
    def itunes_account(self):
        if self._itunes_account is None:
            self._itunes_account = appbuy.itunes_accounts.find_one({'active': True}, sort=[('order', 1)])

        if not self._itunes_account:
            raise Exception("No iTunes account was found.")

        return self._itunes_account
    

    @property
    def appstore(self):
        if self._appstore is None:
            account = self.itunes_account
            self._appstore = appstore.AppStore(account['username'], account['password'], account['guid'], account['apple_action_signature'])
            self._appstore.authenticate()

        return self._appstore

    def _check_token(self):
        if self._token is None:
            return False

        try:
            check_url = settings.TOKEN_CHECK_URL.format(token=self._token, user_id=self._user_id)
            data = requests.post(check_url).json()

            return data['success']
        except:
            return False

    def _update_token(self):
        if self._check_token():
            return

        token_data = request.post(settings.TOKEN_NEW_URL, data={
                'username': settings.USERS_USERNAME,
                'password': settings.USERS_PASSWORD
            }).json()

        if token_data['success']:
            self._token = token_data['token']
            self._user_id = token_data['user']
        else:
            raise Exception("Could not get token.")

    @property
    def token(self):
        self._update_token()
        return self._token

    def update_order_status(self, order_id, state):
        requests.post(settings.CHANGE_STATUS_URL, data={
                'order_id': order_id,
                'status': status,
                'token': self.token
            })


@app.task(base=AppBuyTask)
def gift_app(order_id, app_id, user_id, apple_id):
    logger.info('Processing gift request for app={}, user={}. This app will be gifted to PROJECT2={}.'.format(app_id, user_id, apple_id))
    logger.info('order_id={}'.format(order_id))

    try:
        gift_app.update_order_status(order_id, 4)
        gift_app.appstore.gift_app(app_id, apple_id, dry_run=True)
        gift_app.update_order_status(order_id, 6)

        return True

    except Exception as ex:
        logger.exception(ex)

        gift_app.update_order_status(order_id, 5)

        client.extra_context({
            'order_id': order_id,
            'app_id': app_id,
            'user_id': user_id,
            'apple_id': apple_id,
        })

        client.captureException()
        client.context.clear()

        return False

