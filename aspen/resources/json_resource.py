import re

from aspen import json
from aspen.resources.dynamic_resource import DynamicResource


callback_pattern = re.compile(r'[_A-Za-z0-9]+')


class JSONResource(DynamicResource):

    min_pages = 2
    max_pages = 2

    def compile_page(self, page):
        raise SyntaxError('JSON resources should only have logic pages')

    def process_raised_response(self, response):
        """Given a response, mutate it as needed.
        """
        self._process(response)

    def get_response(self, context):
        """Given a context dict, return a response object.
        """
        response = context['response']
        self._process(response)
        return response

    def _process(self, response):
        """Given a response object, mutate it for JSON.
        """
        if not isinstance(response.body, basestring):
            response.body = json.dumps(response.body)
        response.headers['Content-Type'] = self.website.media_type_json


        # Do a JSONP dance.
        # =================

        enable_jsonp = response.request.context.get('enable_jsonp')
        if enable_jsonp:
            callback = response.request.line.uri.querystring.get('callback')
            if callback is not None:
                if callback_pattern.match(callback) is not None:
                    response.body = "%s(%s)" % (callback, response.body)
                    response.headers['Content-Type'] = self.website.media_type_jsonp

        enable_cors = response.request.context.get('enable_cors')
        if enable_cors:
            response.headers["Access-Control-Allow-Origin"] = "*"
