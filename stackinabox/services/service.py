"""
Stack-In-A-Box: Service Interface
"""
import logging
import re
import uuid

import six


logger = logging.getLogger(__name__)


class StackInABoxServiceErrors(Exception):
    pass


class RouteAlreadyRegisteredError(StackInABoxServiceErrors):
    pass


class InvalidRouteRegexError(StackInABoxServiceErrors):
    pass


class StackInABoxServiceRouter(object):

    def __init__(self, name, uri, obj, parent_obj):
        self.service_name = name
        self.uri = uri
        self.obj = obj
        self.parent_obj = parent_obj
        self.methods = {}

        # Ensure we do not have any circular references
        assert(self.obj != self.parent_obj)

    @property
    def is_subservice(self):
        if self.obj is not None:
            return True

        return False

    def set_subservice(self, obj):
        if self.obj is not None:
            raise RouteAlreadyRegisteredError(
                'Service Router ({0} - {1}): Route {2} already has a '
                'sub-service handler'
                .format(id(self), self.service_name, self.uri))

        if len(self.methods):
            logger.debug(
                'WARNING: Service Router ({0} - {1}): Methods detected '
                'on Route {2}. Sub-Service {3} may be hidden.'
                .format(id(self), self.service_name, self.uri, obj.name))

        # Ensure we do not have any circular references
        assert(obj != self.parent_obj)
        self.obj = obj
        self.obj.base_url = '{0}/{1}'.format(self.uri, self.service_name)

    def update_uris(self, new_uri):
        self.uri = new_uri
        if self.obj:
            self.obj.base_url = '{0}/{1}'.format(self.uri, self.service_name)

    def register_method(self, method, fn):
        if method not in self.methods.keys():
            logger.debug('Service Router ({0} - {1}): Adding method {2} on '
                         'route {3}'
                         .format(id(self),
                                 self.service_name,
                                 method,
                                 self.uri))
            self.methods[method] = fn

        else:
            raise RouteAlreadyRegisteredError(
                'Service Router ({0} - {1}): Method {2} already registered '
                'on Route {3}'
                .format(id(self),
                        self.service_name,
                        method,
                        self.uri))

    def __call__(self, method, request, uri, headers):
        if method in self.methods:
            logger.debug('Service Router ({0} - {1}): Located Method {2} on '
                         'Route {3}. Calling...'
                         .format(id(self),
                                 self.service_name,
                                 method,
                                 self.uri))
            return self.methods[method](self.parent_obj,
                                        request,
                                        uri,
                                        headers)
        else:
            logger.debug('Service Router ({0} - {1}): Located Subservice {2} '
                         'on Route {3}. Calling...'
                         .format(id(self),
                                 self.service_name,
                                 self.obj.name,
                                 self.uri))

            return self.obj.sub_request(method,
                                        request,
                                        uri,
                                        headers)


class StackInABoxService(object):
    DELETE = 'DELETE'
    GET = 'GET'
    HEAD = 'HEAD'
    OPTIONS = 'OPTIONS'
    PATCH = 'PATCH'
    POST = 'POST'
    PUT = 'PUT'
    METHODS = [
        DELETE,
        GET,
        HEAD,
        OPTIONS,
        PATCH,
        POST,
        PUT
    ]

    def __init__(self, name):
        self.__base_url = '/{0}'.format(name)
        self.__id = uuid.uuid4()
        self.name = name
        self.routes = {
        }
        logger.debug('StackInABoxService ({0}): Hosting Service {1}'
                     .format(self.__id, self.name))

    @staticmethod
    def is_regex(uri):
        regex_type = type(re.compile(''))
        return isinstance(uri, regex_type)

    @staticmethod
    def validate_regex(regex, sub_service):
        # The regex generated by stackinabox starts with ^
        # and ends with $. Enforce that the provided regex does the same.

        if regex.pattern.startswith('^') is False:
            logger.debug('StackInABoxService: Pattern must start with ^')
            raise InvalidRouteRegexError('Pattern must start with ^')

        # Note: pattern may end with $ even if sub_service is True
        if regex.pattern.endswith('$') is False and sub_service is False:
            logger.debug('StackInABoxService: Pattern must end with $')
            raise InvalidRouteRegexError('Pattern must end with $')

        # Enforce that if the pattern does not end with $ that it is a service
        if regex.pattern.endswith('$') is True and sub_service is True:
            logger.debug(
                'StackInABoxService: Sub-Service RegEx Pattern must not '
                'end with $')
            raise InvalidRouteRegexError('Pattern must end with $')

    @staticmethod
    def get_service_regex(base_url, service_url, sub_service):
        # if the specified service_url is already a regex
        # then just use. Otherwise create what we need
        if StackInABoxService.is_regex(service_url):
            logger.debug('StackInABoxService: Received regex {0} for use...'
                         .format(service_url.pattern))

            # Validate the regex against StackInABoxService requirement
            StackInABoxService.validate_regex(service_url, sub_service)

            return service_url
        else:
            regex = '^{0}{1}$'.format('', service_url)
            logger.debug('StackInABoxService: {0} + {1} -> {2}'
                         .format(base_url, service_url, regex))
            return re.compile(regex)

    @property
    def base_url(self):
        return self.__base_url

    @base_url.setter
    def base_url(self, value):
        logger.debug('StackInABoxService ({0}:{1}) Updating Base URL '
                     'from {2} to {3}'
                     .format(self.__id,
                             self.name,
                             self.__base_url,
                             value))
        self.__base_url = value
        for k, v in six.iteritems(self.routes):
            v['regex'] = StackInABoxService.get_service_regex(
                value,
                v['uri'],
                v['handlers'].is_subservice)

    def reset(self):
        logger.debug('StackInABoxService ({0}): Reset'
                     .format(self.__id, self.name))
        self.base_url = '/{0}'.format(self.name)
        logger.debug('StackInABoxService ({0}): Hosting Service {1}'
                     .format(self.__id, self.name))

    def try_handle_route(self, route_uri, method, request, uri, headers):
        uri_path = route_uri
        if '?' in uri:
            logger.debug('StackInABoxService ({0}:{1}): Found query string '
                         'removing for match operation.'
                         .format(self.__id, self.name))
            uri_path, uri_qs = uri.split('?')
            logger.debug('StackInABoxService ({0}:{1}): uri =  "{2}", '
                         'query = "{3}"'
                         .format(self.__id, self.name, uri_path, uri_qs))

        for k, v in six.iteritems(self.routes):
            logger.debug('StackInABoxService ({0}:{1}): Checking if '
                         'route {2} handles...'
                         .format(self.__id, self.name, v['uri']))
            logger.debug('StackInABoxService ({0}:{1}): ...using regex '
                         'pattern {2} against {3}'
                         .format(self.__id,
                                 self.name,
                                 v['regex'].pattern,
                                 uri_path))
            if v['regex'].match(uri_path):
                logger.debug('StackInABoxService ({0}:{1}): Checking if '
                             'route {2} handles method {2}...'
                             .format(self.__id, self.name, v['uri'], method))
                return v['handlers'](method,
                                     request,
                                     uri,
                                     headers)
        return (500, headers, 'Server Error')

    def request(self, method, request, uri, headers):
        logger.debug('StackInABoxService ({0}:{1}): Request Received {2} - {3}'
                     .format(self.__id, self.name, method, uri))
        return self.try_handle_route(uri, method, request, uri, headers)

    def sub_request(self, method, request, uri, headers):
        logger.debug('StackInABoxService ({0}:{1}): Sub-Request Received '
                     '{2} - {3}'
                     .format(self.__id, self.name, method, uri))
        return self.request(method, request, uri, headers)

    def create_route(self, uri, sub_service):
        if uri not in self.routes.keys():
            logger.debug('Service ({0}): Creating routes'
                         .format(self.name))
            self.routes[uri] = {
                'regex': StackInABoxService.get_service_regex(self.base_url,
                                                              uri,
                                                              sub_service),
                'uri': uri,
                'handlers': StackInABoxServiceRouter(self.name,
                                                     uri,
                                                     None,
                                                     self)
            }

    def register(self, method, uri, call_back):
        found = False

        self.create_route(uri, False)
        self.routes[uri]['handlers'].register_method(method,
                                                     call_back)

    def register_subservice(self, uri, service):
        found = False

        self.create_route(uri, True)
        self.routes[uri]['handlers'].set_subservice(service)
