"""Implements negotiated resources.

Aspen supports content negotiation. If a file has no file extension, then it
will be handled as a "negotiated resource". The format of the file is like
this:

    import foo, json
    ^L
    data = foo.bar(request)
    ^L text/plain
    {{ data }}
    ^L text/json
    {{ json.dumps(data) }}

We have vendored in Joe Gregorio's content negotiation library to do the heavy
lifting (parallel to how we handle _cherrypy and _tornado vendoring). If a file
*does* have a file extension (foo.html), then it is a rendered resource with a
mimetype computed from the file extension. It is a SyntaxError for a file to
have both an extension *and* multiple content pages.

"""
import re

from aspen import Response
from aspen._mimeparse import mimeparse
from aspen.resources import PAGE_BREAK
from aspen.resources.dynamic_resource import DynamicResource


renderer_re = re.compile(r'#![a-z0-9.-]+')
media_type_re = re.compile(r'[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+')


class NegotiatedResource(DynamicResource):
    """This is a negotiated resource. It has three or more pages.
    """

    min_pages = 3 
    max_pages = None


    def __init__(self, *a, **kw):
        self.renderers = {}         # mapping of media type to render function
        self.available_types = []   # ordered sequence of media types
        DynamicResource.__init__(self, *a, **kw)


    def compile_page(self, page, __ignored):
        """Given a bytestring, return a (media type, renderer) pair.
        """
        if '\n' in page:
            specline, raw = page.split('\n', 1)
        else:
            specline = ''
            raw = page
        specline = specline.strip(PAGE_BREAK + ' \n')
        make_renderer, media_type = self._parse_specline(specline)
        render = make_renderer(self.fs, raw)
        if media_type in self.renderers:
            raise SyntaxError("Two content pages defined for %s." % media_type)

        # update internal data structures
        self.renderers[media_type] = render
        self.available_types.append(media_type)

        return (render, media_type)  # back to parent class


    def _parse_specline(self, specline):
        """Given a bytestring, return a two-tuple.

        The incoming string is expected to be of the form:

            ^L #!renderer media/type
       
        The renderer is optional. It will be computed based on media type if
        absent. The return two-tuple contains a render function and a media
        type (as unicode). SyntaxError is raised if there aren't one or two
        parts or if either of the parts is malformed. If only one part is
        passed in it's interpreted as a media type.
        
        """
        assert isinstance(specline, str), type(specline)
        if specline == "":
            raise SyntaxError("Content pages in negotiated resources must "
                              "have a specline.")

        # Parse into one or two parts.
        parts = specline.split()
        nparts = len(parts)
        if nparts not in (1, 2):
            raise SyntaxError("A negotiated resource specline must have one "
                              "or two parts: #!renderer media/type. Yours is: "
                              "%s." % specline)
       
        # Assign parts.
        renderer = None
        if nparts == 1:
            renderer = "#!tornado"  # XXX compute from media type
            media_type = parts[0]
        else:
            assert nparts == 2, nparts
            renderer, media_type = parts

        # Validate media type.
        if media_type_re.match(media_type) is None:
            msg = ("Malformed media type %s in specline %s. It must match "
                   "%s.")
            msg %= (media_type, specline, media_type_re.pattern)
            raise SyntaxError(msg)
        media_type = media_type.decode('US-ASCII')

        # Hydrate and validate renderer.
        make_renderer = self._get_renderer_factory(renderer)
        if make_renderer is None:
            raise ValueError("Unknown renderer for %s: %s."
                             % (media_type, renderer))

        # Return.
        return (make_renderer, media_type)

    
    def _get_renderer_factory(self, renderer):
        """Given a bytestring, return a renderer factory or None.
        """
        make_renderer = None
        if renderer is not None:
            if renderer_re.match(renderer) is None:
                msg = "Malformed renderer %s. It must match %s."
                raise SyntaxError(msg % (renderer, renderer_re.pattern))
            renderer = renderer[2:]  # strip off the hashbang 
            renderer = renderer.decode('US-ASCII')
            make_renderer = self.website.renderer_factories.get(renderer)
        return make_renderer


    def get_response(self, context):
        """Given a context dict, return a response object.
        """
        request = context['request']
        accept = request.headers.get('Accept')
        if accept:
            media_type = mimeparse.best_match(self.available_types, accept)
            if not media_type:
                msg = "The following media types are available: %s."
                msg %= ', '.join(self.available_types)
                raise Response(406, msg.encode('US-ASCII'))
            render = self.renderers[media_type]
        else:
            render, media_type = self.pages[2]  # default to first content page

        response = context['response']
        response.body = render(context)
        if 'Content-Type' not in response.headers:
            response.headers['Content-Type'] = media_type
            if media_type.startswith('text/'):
                charset = response.charset
                if charset is not None:
                    response.headers['Content-Type'] += '; charset=' + charset

        return response
