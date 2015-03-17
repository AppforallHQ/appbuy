import pdb
import json
import plistlib
import logging
import requests

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(levelname)s:%(name)s] %(message)s"
)

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
    
    USER_AGENT = "AppStore/2.0 iOS/7.0.4 model/iPad3,1 (4; dt:77)"
    
    def __init__(self, username, password, guid):
        self.username = username
        self.password = password
        self.guid = guid
        self.is_authenticated = False
        self.session = requests.Session()
        
        self.session.headers.update({
            'User-Agent': AppStore.USER_AGENT,
            'X-Apple-Client-Versions': 'iBooks/3.2; GameCenter/2.0',
            'X-Apple-Client-Application': 'Software',
            'X-Apple-Connection-Type': 'WiFi',
        })
        
    def authenticate(self):
        auth_request_data = {
            'appleId': self.username,
            'attempt': '0',
            'createSession': 'true',
            'guid': self.guid,
            'password': self.password,
            'rmp': '0',
            'why': 'signIn'
        }
        
        headers = {
            'Content-Type': 'application/x-apple-plist',
            'X-Apple-Store-Front': '143441-1,20 t:native',
            'X-Apple-ActionSignature': 'AnR+qWQeZ3vV/aIHylVv72geo4EYv6qg7x0BjsgDoEx4AAABUAMAAABNAAAAgMHqueVTvZxkPWQFHkIjrqWjaa3O7WQu801qTPdVkEKVOHLjxjTsdN2AwHHZrNsLyQbTaFlavcIv7ckemPnvfxWLiTCStjGkX9c3NVu7OTqOOkstO8PlJRoCwvGiK9CSwXnvvSdhXIigUs5As78hMFJVnnLR9F3nzrWf2mkYSkiSAAAAFrbQkVPKSpw8MhsuHR+PJNKPMJ44uysAAACfAa7U6dP7JW5Vll503fmTN510kt6aAAAAhgYHdrX4PFhadncRCAeyN40pkFUENk7jn8DJMMMaqzo/P9fDT9RDWZTxPKJ8IQyX+kfn6eOD3hK84hqt2BRi5pmUVWSynTUcr/rkVRaVKGlpEY8Ys6quENczIBroOaLdxP57niyY8zONU1GBG+67Er0PqEbL2P4qziEhmHnc+zDxsuGmOFQfAAAAAAAAAAAAAA==',
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
        ds_person_id = auth_result['dsPersonId']
        
        self.session.headers.update({
            'X-Token': password_token,
            'X-Dsid': ds_person_id
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
        
    def gift_app(self, app_id, to_email, dry_run=False):
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
            'fromName': 'Ansar',
            'dateSendType': 'today'
        }
        
        response = self.session.post(AppStore.Locations.GIFT_VALIDATE_URL, headers={
                'Content-Type': 'application/json',
            }, data=json.dumps(gift_validate_request))
            
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
            'message': 'This gift is automatically sent to you by PROJECT.',
            'fcAdamId': 586798532,
        })
        
        response = self.session.post(AppStore.Locations.GIFT_BUY_URL, headers={
                'Content-Type': 'application/json',
            }, data=json.dumps(gift_buy_request))
            
        if response.status_code // 100 != 2:
            raise Exception("Gift buy went wrong.")
            
        response_data = json.loads(response.text)
        if response_data['status'] != 0:
            raise Exception("Gift buy error: {}".format(response_data.get('errorMessage', '')))
        
        logger.info("App '{}' successfully gifted to {}.".format(app_datato_email))
        
        
if __name__ == '__main__':
    store = AppStore("user.appbuy@outlook.com", "Asp5Jx6z@", "bb7f7439219f126243b2c4e9efc8edb40438fec6")
    store.authenticate()
    store.gift_app("748048441", "ashkan.roshanayi@gmail.com", dry_run=True)
