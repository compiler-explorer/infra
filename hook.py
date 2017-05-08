#!/usr/bin/env python

import logging
import tornado.ioloop
import tornado.web
import json
import update_instances


class MainHandler(tornado.web.RequestHandler):
    def post(self):
        event = self.request.headers.get('X-GitHub-Event')
        obj = json.loads(self.request.body)
        logging.info("Got {}: {}".format(event, obj))
        if event == 'ping':
            logging.info("Got a ping")
            self.write("OK")
            return
        if event != 'push':
            raise RuntimeError("Unsupported")

        if 'ref' not in obj:
            logging.info("Skipping, no ref")
            return

        repo = obj['repository']['name']
        branch = obj['ref']
        hash = obj['after']
        if repo == 'compiler-explorer':
            if branch != 'refs/heads/master':
                update_instances.build_deployment(hash)
            if branch == 'refs/heads/release':
                update_instances.update_compiler_explorers()
            self.write("OK")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(module)s: %(message)s")

    application = tornado.web.Application([
        ("/", MainHandler)
    ], debug=True)
    application.listen(7453)
    tornado.ioloop.IOLoop.instance().start()
