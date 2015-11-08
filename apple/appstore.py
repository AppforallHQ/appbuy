import pdb
import json
import logging
import datetime
import requests
import plistlib

from core.db import appbuy

"""
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(levelname)s:%(name)s] %(message)s"
)
"""

logger = logging.getLogger(__name__)

def login_required(func):
    def func_wrapper(*args, **kwargs):
        self = args[0]
        if getattr(self, 'is_authenticated', False):
            raise Exception("Not logged in.")
        else:
            return func(*args, **kwargs)

    return func_wrapper

class AppStore:
    class Locations:
        AUTHENTICATION_URL = "https://buy.itunes.apple.com/WebObjects/MZFinance.woa/wa/authenticate"
        TEST_APP_URL = "https://itunes.apple.com/ae/app/alpha-omega/id748048441?mt=8"
        GET_BAG_URL = "https://init.itunes.apple.com/bag.xml?ix=5&os=7&locale=en_US"
        GIFT_VALIDATE_URL = "https://buy.itunes.apple.com/WebObjects/MZFinance.woa/wa/giftValidateSrv"
        GIFT_BUY_URL = "https://buy.itunes.apple.com/WebObjects/MZFinance.woa/wa/giftBuySrv"
        LOOKUP_URL = "https://itunes.apple.com/lookup?id={}"

#    USER_AGENT = "AppStore/2.0 iOS/7.0.4 model/iPad3,1 (4; dt:77)"
    USER_AGENT = "iTunes/10.6 (Windows; Microsoft Windows 7 x64 Ultimate Edition Service Pack 1 (Build 7601)) AppleWebKit/534.54.16 (myapp)"

    def __init__(self, username, password, guid, action_signature=None):
        self.username = username
        self.password = password
        self.guid = guid
        self.action_signature = action_signature
        self.is_authenticated = False
        self.session = requests.Session()

        proxy = appbuy.proxies.find_one({'enabled': True}, sort=[('order', 1)])

        if proxy and proxy.get('http_proxy') and proxy.get('https_proxy'):
            self.session.proxies = {
                'http': proxy.get('http_proxy'),
                'https': proxy.get('https_proxy')
            }
        else:
            raise Exception("Invalid proxy configuration.")

        self.session.headers.update({
            'User-Agent': AppStore.USER_AGENT,
#            'X-Apple-Client-Versions': 'iBooks/3.2; GameCenter/2.0',
#            'X-Apple-Client-Application': 'Software',
#            'X-Apple-Connection-Type': 'WiFi',
#            'X-Apple-Partner': 'origin.0'
        })

    def authenticate(self):
        auth_request_data = {
            'machineName' : 'MYAPP',
            'appleId': self.username,
            'attempt': '1',
            'createSession': 'true',
            'guid': self.guid,
            'password': self.password,
#            'rmp': '0',
            'why': 'signin'
        }

        headers = {
            'Content-Type': 'application/x-apple-plist',
            'X-Apple-Store-Front': '143441-1',#,20 t:native',
#            'X-Apple-ActionSignature': self.action_signature,
        }

        response = self.session.post(AppStore.Locations.AUTHENTICATION_URL, headers=headers,
            data=plistlib.dumps(auth_request_data), allow_redirects=False)

        if response.status_code // 100 == 3 and response.headers.get('location', None): #redirect
            logger.info('Response [{}]. Following redirect and resending required data.'.format(response.status_code))
            response = self.session.post(response.headers['location'], headers=headers,
                data=plistlib.dumps(auth_request_data), allow_redirects=False)

        if response.status_code // 100 != 2:
            raise Exception("Unable to authenticate.")

        auth_result = plistlib.loads(response.text.encode('utf-8'))
        password_token = auth_result['passwordToken']
        ds_person_id = auth_result['dsid']


        self.session.headers.update({
            'X-Token': password_token,
            'X-Dsid': ds_person_id,
            'X-Apple-Tz' : 28800,
            'X-Apple-Cuid' : '7c1c1c990bcd9faec5493e21e6fd8d69',
        })

        self.is_authenticated = True

        logger.info("Authenticate successully as '{}' with Dsid={}".format(self.username, ds_person_id))

        return response

    @login_required
    def get_bag(self):
        response = self.session.get(AppStore.Locations.GET_BAG_URL)

    def get_app_data(self, app_id):
        response = requests.get(AppStore.Locations.LOOKUP_URL.format(app_id))
        data = json.loads(response.text)

        if data['resultCount'] < 1:
            return None

        itunes_url = data['results'][0]['trackViewUrl']
        response = self.session.get(itunes_url)
        return json.loads(response.text)

    def gift_app(self, order_id, app_id, to_email, dry_run=False):
        app_data = self.get_app_data(app_id)

        ##############################################################
        # Gift validation step                                       #
        ##############################################################

        app_name = app_data['storePlatformData']['product-dv-product']['results'][app_id]['name']
        action_params = app_data['storePlatformData']['product-dv-product']['results'][app_id]['offers'][0]['buyParams']

        gift_validate_request = {
            'actionParams': action_params,
            'giftType': 'product',
            'guid': self.guid,
            'toEmail': to_email,
            'senderEmail': self.username,
            'fromName': 'PROJECT',
            'dateSendType': 'today'
        }

        response = self.session.post(AppStore.Locations.GIFT_VALIDATE_URL, headers={
                'Content-Type': 'application/json',
            }, data=json.dumps(gift_validate_request))

        obj_id = appbuy.orders.insert({
                'order_id': order_id,
                'validation_data': response.text,
                'validation_time': datetime.datetime.now(),
            })

        if response.status_code // 100 != 2:
            raise Exception("Gift validation went wrong.")

        response_data = json.loads(response.text)
        if response_data['status'] != 0:
            raise Exception("Gift validation error: {}".format(response_data.get('errorMessage', '')))

        logger.info('Gift successfully validated.')

        if dry_run:
            return

        ##############################################################
        # Gift buy step                                              #
        ##############################################################

        gift_buy_request = gift_validate_request.copy()
        gift_buy_request.update({
            'message': 'This app is automatically sent to you by PROJECT.',
            'fcAdamId': 586798532,
        })

        response = self.session.post(AppStore.Locations.GIFT_BUY_URL, headers={
                'Content-Type': 'application/json',
            }, data=json.dumps(gift_buy_request))


        appbuy.orders.update({'_id': obj_id}, {'$set': {
                'buy_data': response.text,
                'buy_time': datetime.datetime.now()
            }})

        if response.status_code // 100 != 2:
            raise Exception("Gift buy went wrong.")

        response_data = json.loads(response.text)
        if response_data['status'] != 0:
            raise Exception("Gift buy error: {}".format(response_data.get('errorMessage', '')))

        logger.info("App '{}' successfully gifted to {}.".format(app_name, to_email))


if __name__ == '__main__':
    store = AppStore("user.appbuy@outlook.com", "Asp5Jx6z@", "bb7f7439219f126243b2c4e9efc8edb40438fec6")
    
    store.authenticate()
    store.gift_app("748048441", "ashkan.roshanayi@gmail.com", dry_run=True)
