import requests, sys, logging, re
from .errors import *
from requests.packages.urllib3.util.retry import Retry
'''
'''

__version__ = '0.0.1'


class APIResultsIterator(object):
    '''
    The agents iterator provides a scalable way to work through agent result
    sets of any size.  The iterator will walk through each page of data,
    returning one record at a time.  If it reaches the end of a page of
    records, then it will request the next page of information and then continue
    to return records from the next page (and the next, and the next) until the
    counter reaches the total number of records that the API has reported.

    Attributes:
        count (int): The current number of records that have been returned
        page (list): 
            The current page of data being walked through.  pages will be
            cycled through as the iterator requests more information from the
            API.
        page_count (int): The number of record returned from the current page.
        total (int): 
            The total number of records that exist for the current request.
    '''
    count = 0
    page_count = 0
    total = 0
    page = []

    # The API will be grafted on here.
    _api = None

    # The page size limit
    _limit = None

    # The current record offset
    _offset = None

    # The number of pages that may be requested before bailing.  If set to
    # None, then there is no limitation to the number of pages that may be
    # requested.
    _pages_total = None
    _pages_requested = 0

    def __init__(self, api, **kw):
        self._api = api
        self.__dict__.update(kw)
        self._get_page()

    def _get_page(self):
        pass

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def next(self):
        '''
        Ask for the next Agent record
        '''
        # If there are no more agent records to return, then we should raise
        # a StopIteration exception to end the madness.
        if self.count >= self.total:
            raise StopIteration()

        # If we have worked through the current page of records and we still
        # haven't hit to the total number of available records, then we should
        # query the next page of records.
        if self.page_count >= len(self.page) and self.count <= self.total:
            self._get_page()

        # Get the relevant record, increment the counters, and return the
        # record.
        item = self.page[self.page_count]
        self.count += 1
        self.page_count += 1
        return item


class APIEndpoint(object):
    '''
    APIEndpoint is the base model for which all API endpoint classes are
    sired from.  The main benefit is the addition of the ``_check()``
    function from which it's possible to check the type & content of a
    variable to ensure that we are passing good data to the API.

    Args:
        api (APISession): 
            The APISession (or sired child) instance that the endpoint will
            be using to perform calls to the API.
    '''

    def __init__(self, api):
        self._api = api

    def _check(self, name, obj, expected_type, 
               choices=None, default=None, case=None, pattern=None):
        '''
        Internal function for validating thet inputs we are receiving are of
        the right type, have the expected values, and can handle defaults as
        necessary.

        Args:
            name (str): The name of the object (for exception reporting)
            obj (obj): The object that we will be checking
            expected_type (type): 
                The expected type of object that we will check against.
            choices (list, optional):
                if the object is only expected to have a finite number of values
                then we can check to make sure that our input is one of these
                values.
            default (obj, optional):
                if we want to return a default setting if the object is None,
                we can set one here.
            case (string, optional):
                if we want to force the object values to be upper or lower case,
                then we will want to set this to either ``upper`` or ``lower``
                depending on the desired outcome.  The returned object will then
                also be in the specified case.
            pattern (string, optional):
                If we want to validate the input based on a regex pattern, then
                we should specify one here.

        Returns:
             obj: Either the object or the default object depending.
        '''

        # We have a simple function to convert the case of string values so that
        # we can ensure correct output. 
        def conv(obj, case):
            '''
            Case conversion function
            '''
            if case == 'lower':
                if isinstance(obj, list):
                    return [i.lower() for i in obj if isinstance(i, str)]
                elif isinstance(obj, str):
                    return obj.lower()
            elif case == 'upper':
                if isinstance(obj, list):
                    return [i.upper() for i in obj if isinstance(i, str)]
                elif isinstance(obj, str):
                    return obj.upper()
            return obj

        # Convert the case of the inputs.
        obj = conv(obj, case)
        choices = conv(choices, case)
        default = conv(default, case)

        # If the object sent to us has a None value, then we will return None.
        # If a default was set, then we will return the default value.
        if obj == None:
            if default:
                return default
            else:
                return None

        # As we can support a singular expected type, or multiple types, we need
        # to check to see if the expected types was a list of types.  If so, we
        # will just pass expected_types into the etypes list.  If not, then this
        # is a singular type, and we will want to wrap it into a list before
        # passing to the etypes list.
        if isinstance(expected_type, list) and len(expected_type) > 0:
            etypes = expected_type
        else:
            etypes = [expected_type,]

        # If the type is of "uuid", then we will specify a pattern and then
        # overload the type to be a type of str.
        if 'uuid' in etypes:
            pattern = r'[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}'
            etypes[etypes.index('uuid')] = str

        if 'scanner-uuid' in etypes:
            pattern = r'[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12,32}'
            etypes[etypes.index('uuid')] = str         

        # If we are checking for a string type, we will also want to check for
        # unicode type transparently, so add the unicode type to the expected
        # types list.  NOTE this is for Python2 only, as Python3 treats all
        # strings as type string.
        if str in etypes:
            try:
                etypes.append(unicode)
            except NameError:
                pass

        # iterate through the expected types and flag as passing if any of the
        # types match.
        type_pass = False
        for etype in etypes:
            if isinstance(obj, etype):
                type_pass = True

        # If the object is none of the right types then we want to raise a
        # TypeError as it was something we weren't expecting.
        if not type_pass:
            raise TypeError('{} is of type {}.  Expected {}.'.format(
                name, obj.__class__.__name__, expected_type.__name__
            ))

        # if the object is only expected to have one of a finite set of values,
        # we should check against that and raise an exception if the the actual
        # value is outside of what we expect.

        if isinstance(obj, list):
            for item in obj:
                if isinstance(choices, list) and item not in choices:
                    raise UnexpectedValueError(
                        '{} has value of {}.  Expected one of {}'.format(
                            name, obj, ','.join([str(i) for i in choices])
                    ))
        elif isinstance(choices, list) and obj not in choices:
            raise UnexpectedValueError(
                '{} has value of {}.  Expected one of {}'.format(
                    name, obj, ','.join([str(i) for i in choices])
            ))

        if pattern and isinstance(obj, str):
            if len(re.findall(pattern, str(obj))) <= 0:
                raise UnexpectedValueError(
                    '{} has value of {}.  Does not match pattern {}'.format(
                        name, obj, pattern)
                )


        # if we made it this fire without an exception being raised, then assume
        # everything is good to go and return the object passed to us initially.
        return obj


#class APIModel(object):
#    def __init__(self, api_session=None, **entries):
#        self._api = api_session
#        self.__dict__.update(entries)
#    def __str__(self):
#        return str(self.id)
#    def dict(self):
#        return self.__dict__   


class APISession(object):
    '''
    The APISession class is the base model for APISessions for different
    products and applications.  This is the model that the APIEndpoints
    will be grafted onto and supports some basic wrapping of standard HTTP
    methods on it's own.

    Args:
        url (str, optional):
            The base URL that the paths will be appended onto.  

            For example, if you want to override the default URL base with 
            _http://a.b.c/api_, you could then make a GET requests with 
            self.get('item').  This would then inform APISession to 
            construct a GET request to _http://ab.c./api/item_ and use
            whatever parameters you wanted to pass to the Requests Session
            object.
        retries (int, optional):
            The number of retries to make before failing a request.  The
            default is 3.
        backoff (float, optional):
            If a 429 response is returned, how much do we want to backoff
            if the response didn't send a Retry-After header.
    '''

    URL = None
    '''
    str: URL Base path
    '''

    RETRIES = 5
    '''
    int: Number of retries to attempt to make before failing the HTTP request
    '''

    RETRY_BACKOFF = 0.2
    '''
    float: The backoff timer to use if a 429 response was returned and no
    Retry-After header was returned.
    '''

    def __init__(self, url=None, retries=None, backoff=None):
        if url:
            self.URL = url
        if retries and isinstance(retries, int):
            self.RETRIES = retries
        if backoff and isinstance(backoff, float):
            self.RETRY_BACKOFF = backoff
        self._build_session()

    def _build_session(self):
        '''
        Requests session builder
        '''
        # Sets the retry adaptor with the ability to properly backoff if we get 429s
        retries = Retry(
            total=self.RETRIES,
            status_forcelist={429, 501, 502, 503, 504}, 
            backoff_factor=self.RETRY_BACKOFF, 
            respect_retry_after_header=True
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retries)

        # initiate the session and then attach the Retry adaptor.
        self._session = requests.Session()
        self._session.mount('https://', adapter)

        # we need to make sure to identify ourselves.
        self._session.headers.update({
            'User-Agent': 'pyTenable/{} Python/{}'.format(__version__, '.'.join([str(i) for i in sys.version_info][0:3])),
        })

    def _resp_error_check(self, response):
        '''
        A more general response error checker that can be overloaded if needed.
        '''
        return response

    def _request(self, method, path, **kwargs):
        '''
        Request call builder
        '''
        resp = self._session.request(method, '{}/{}'.format(self.URL, path), **kwargs)

        status = resp.status_code
        if status == 200:
            # As everything looks ok, lets pass the response on to the error
            # checker and then return the response.
            return self._resp_error_check(resp)
        elif status == 400:
            raise InvalidInputError(resp)
        elif status == 403:
            raise PermissionError(resp)
        elif status == 404:
            raise NotFoundError(resp)
        elif status == 500:
            raise ServerError(resp)
        else:
            raise UnknownError(resp)

    def get(self, path, **kwargs):
        '''
        Initiates an HTTP GET request using the specified path.  Refer to the
        `Requests documentation`_ for more detailed information on what keyword
        arguments can be passed: 

        Args:
            path (str):
                The path to be appented onto the base URL for the request.
            **kwargs (dict):
                Keyword arguments to be passed to the Requests Sessions request
                method.

        Returns:
            `requests.Response`_: 

        .. _requests.Response:
            http://docs.python-requests.org/en/master/api/#requests.Response
        .. _Requests documentation:
            http://docs.python-requests.org/en/master/api/#requests.request
        '''
        return self._request('GET', path, **kwargs)

    def post(self, path, **kwargs):
        '''
        Initiates an HTTP POST request using the specified path.  Refer to the
        `Requests documentation`_ for more detailed information on what keyword
        arguments can be passed: 

        Args:
            path (str):
                The path to be appented onto the base URL for the request.
            **kwargs (dict):
                Keyword arguments to be passed to the Requests Sessions request
                method.

        Returns:
            `requests.Response`_: 

        .. _requests.Response:
            http://docs.python-requests.org/en/master/api/#requests.Response
        .. _Requests documentation:
            http://docs.python-requests.org/en/master/api/#requests.request
        '''
        return self._request('POST', path, **kwargs)

    def put(self, path, **kwargs):
        '''
        Initiates an HTTP PUT request using the specified path.  Refer to the
        `Requests documentation`_ for more detailed information on what keyword
        arguments can be passed: 

        Args:
            path (str):
                The path to be appented onto the base URL for the request.
            **kwargs (dict):
                Keyword arguments to be passed to the Requests Sessions request
                method.

        Returns:
            `requests.Response`_: 

        .. _requests.Response:
            http://docs.python-requests.org/en/master/api/#requests.Response
        .. _Requests documentation:
            http://docs.python-requests.org/en/master/api/#requests.request
        '''
        return self._request('PUT', path, **kwargs)

    def patch(self, path, **kwargs):
        '''
        Initiates an HTTP PATCH request using the specified path.  Refer to the
        `Requests documentation`_ for more detailed information on what keyword
        arguments can be passed: 

        Args:
            path (str):
                The path to be appented onto the base URL for the request.
            **kwargs (dict):
                Keyword arguments to be passed to the Requests Sessions request
                method.

        Returns:
            `requests.Response`_: 

        .. _requests.Response:
            http://docs.python-requests.org/en/master/api/#requests.Response
        .. _Requests documentation:
            http://docs.python-requests.org/en/master/api/#requests.request
        '''
        return self._request('PATCH', path, **kwargs)

    def delete(self, path, **kwargs):
        '''
        Initiates an HTTP DELETE request using the specified path.  Refer to the
        `Requests documentation`_ for more detailed information on what keyword
        arguments can be passed: 

        Args:
            path (str):
                The path to be appented onto the base URL for the request.
            **kwargs (dict):
                Keyword arguments to be passed to the Requests Sessions request
                method.

        Returns:
            `requests.Response`_: 

        .. _requests.Response:
            http://docs.python-requests.org/en/master/api/#requests.Response
        .. _Requests documentation:
            http://docs.python-requests.org/en/master/api/#requests.request
        '''
        return self._request('DELETE', path, **kwargs)

    def head(self, path, **kwargs):
        '''
        Initiates an HTTP HEAD request using the specified path.  Refer to the
        `Requests documentation`_ for more detailed information on what keyword
        arguments can be passed: 

        Args:
            path (str):
                The path to be appented onto the base URL for the request.
            **kwargs (dict):
                Keyword arguments to be passed to the Requests Sessions request
                method.

        Returns:
            `requests.Response`_: 

        .. _requests.Response:
            http://docs.python-requests.org/en/master/api/#requests.Response
        .. _Requests documentation:
            http://docs.python-requests.org/en/master/api/#requests.request
        '''
        return self._request('HEAD', path, **kwargs)
