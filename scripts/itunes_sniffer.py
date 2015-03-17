from __future__ import print_function

import plistlib

def request(context, flow):
    if 'X-Apple-ActionSignature' in flow.request.headers:
        print('X-Apple-ActionSignature:', flow.request.headers['X-Apple-ActionSignature'][0])
        print('X-Apple-Store-Front:', flow.request.headers['X-Apple-Store-Front'][0])
        print('User-Agent:', flow.request.headers['User-Agent'])
                
        exit(0)