from adobe_analytics.session import OmnitureSession

import json
from warnings import warn
from copy import deepcopy

class OmnitureApi:
    def __init__(self, session):
        self._session = session
    
    @classmethod
    def init(cls, username=None, secret=None, company=None, 
             proxies=None, timeout=None):
        
        session = OmnitureSession(
                username=username, 
                secret=secret, 
                company=company, 
                proxies=proxies, 
                timeout=timeout
            )
        api = cls(session)
        cls.set_default_api(api)
        
        return api

    @classmethod
    def from_json(cls, filepath, 
                  proxies=None, timeout=None):
        with open(filepath, mode='r') as f:
            j = json.load(f)
        company = j['company']
        username = j['username']
        secret = j['secret']

        return cls.init(username, secret, company,
                        proxies, timeout)

    @classmethod
    def set_default_api(cls, api):
        cls._default_api = api

    @classmethod
    def get_default_api(cls):
        return cls._default_api

    def call(self, method, params=None):
        url = self._session.base_url
        json = params or {}
        
        response = self._session.session.request(
            method=method, url=url, json=json,
            headers=self._session.default_headers,
            timeout=self._session.timeout
        )

        response.raise_for_status()

        return response

class OmnitureRequest:
    def __init__(self, method, api=None):
        self._api = api or OmnitureApi.get_default_api()
        self._method = method
        self._endpoint = self._api.base_url
        self._json = {'method': self._method}

    def add_params(self, params):
        if params:
            for key, value in params.items():
                # add method for validating parameters
                self._json[key] = value

        return self
        
    def execute(self):
        if self._method == 'GET':
            cursor = Cursor(
                params=self._params,
                path=self._path,
                api_type=self._api_type,
                api=self._api
            )
            response = cursor.execute()

            return response

        else:
            response = self._api.call(
                method=self._method,
                path=self._path,
                api_type=self._api_type,
                params=self._params
            ).json()

            return response

class Cursor:
    """
    A cursor for handling GET requests, including an iterator
    for handling large responses (>1k for REST, >50k for BULK)
    """
    def __init__(self, params=None, path=None, 
                 api=None, api_type=None):
        self._params = params or {}
        self._path = path
        self._api = api
        self._api_type = (api_type or 'REST').upper()
       
        self._response = self._data = {}
        self._queue = []
        self._pages = params['page'] if 'page' in params else None
        self._finished = False
        self._total = None

        # Explicit BULK API Handling
        if self._api_type == 'BULK':
            if 'limit' not in self._params:
                self._params['limit'] = 50000
            if 'offset' not in self._params:
                self._params['offset'] = 0

    def __iter__(self):
        return self

    def __next__(self):
        if not self._queue and not self.load():
            raise StopIteration()
        else:
            return self._queue.pop(0)

    def __repr__(self):
        return str(self._response)

    def __len__(self):
        return len(self._response)

    def __getitem__(self, index):
        return self._response[index]
    
    def load(self):
        if self._finished:
            return False

        response = self._api.call(
            method='GET',
            path=self._path,
            api_type=self._api_type,
            params=self._params
        ).json()
        
        self._data = deepcopy(response)
        
        self._total = 1
        for key in ['total', 'totalResults']:
            if key in response:
                self._total = response[key]

        if self._api_type == 'BULK':
            self._params['offset'] += self._params['limit']
            if 'hasMore' in response:
                self._finished = not response['hasMore']
            else:
                self._finished = True
        else:
            pages = self._pages or int((self._total - 1) / PAGE_SIZE) + 1
            page = response['page'] if 'page' in response else 1
            self._params['page'] = page + 1
            self._finished = not (page < pages) # "not pages left"
        for key in ['elements', 'items']:
            if key in response:
                self._queue = response[key]
                del self._data[key]

        return len(self._queue) > 0
    
    def execute(self):

        if self._api_type == 'BULK':
            self._response['items'] = []
            for queue in self:
                self._response['items'].append(queue)
        else:
            self._response['elements'] = []
            for element in self:
                element = element # trivial until object work is done
                self._response['elements'].append(element)
        
        # append data features
        for key in list(self._data):
            self._response[key] = self._data[key]

        # cleanup unneeded or empty features
        dropkeys = ['page', 'pageSize', 'limit', 'offset', 'count']
        for key in list(self._response):
            if not self._response[key] or key in dropkeys:
                del self._response[key]
        
        # detatch data
        del self._data

        return self._response

